"""
Run History - Audit log for catalog job executions.

This module provides functions to:
1. Write run history entries when jobs complete
2. Archive and cleanup old jobs
3. Generate daily summary reports

Collections:
- catalog_run_history/{auto-id}: Individual run records (permanent audit log)
- catalog_run_summary/{YYYY-MM-DD}: Daily aggregated stats
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from google.cloud import firestore

from app.jobs.models import Job, JobStatus, JobType

logger = logging.getLogger(__name__)

# Collection names
RUN_HISTORY_COLLECTION = "catalog_run_history"
RUN_SUMMARY_COLLECTION = "catalog_run_summary"
JOBS_COLLECTION = "catalog_jobs"

# Retention policy
COMPLETED_JOB_RETENTION_DAYS = 7  # Delete completed jobs after 7 days
FAILED_JOB_RETENTION_DAYS = 30   # Keep failed jobs longer for investigation

# Initialize Firestore client lazily
_db: Optional[firestore.Client] = None


def get_db() -> firestore.Client:
    """Get or initialize Firestore client."""
    global _db
    if _db is None:
        _db = firestore.Client()
    return _db


def write_run_history(
    job: Job,
    status: JobStatus,
    duration_ms: int,
    changes: Optional[List[Dict[str, Any]]] = None,
    error: Optional[Dict[str, Any]] = None,
    worker_id: Optional[str] = None,
) -> str:
    """
    Write a run history entry for a completed job.
    
    Args:
        job: The completed job
        status: Final job status
        duration_ms: Execution duration in milliseconds
        changes: List of changes made (for apply mode)
        error: Error info if job failed
        worker_id: Worker that processed the job
        
    Returns:
        The run history document ID
    """
    db = get_db()
    now = datetime.now(timezone.utc)
    
    # Build history entry
    entry = {
        "job_id": job.id,
        "job_type": job.type.value,
        "queue": job.queue.value,
        "priority": job.priority,
        "status": status.value,
        "mode": job.payload.mode,
        
        # Timing
        "created_at": job.created_at,
        "started_at": job.started_at,
        "completed_at": now,
        "duration_ms": duration_ms,
        
        # Context
        "family_slug": job.payload.family_slug,
        "exercise_count": len(job.payload.exercise_doc_ids) if job.payload.exercise_doc_ids else 0,
        "attempt": job.attempts,
        "worker_id": worker_id,
        
        # Results
        "changes_count": len(changes) if changes else 0,
        "changes_preview": _summarize_changes(changes) if changes else None,
        
        # Metadata
        "recorded_at": now,
    }
    
    # Add error if present
    if error:
        entry["error"] = {
            "code": error.get("code", "unknown"),
            "message": str(error.get("message", error))[:500],  # Truncate
        }
    
    # Write to Firestore
    doc_ref = db.collection(RUN_HISTORY_COLLECTION).document()
    doc_ref.set(entry)
    
    logger.debug("Wrote run history: %s for job %s", doc_ref.id, job.id)
    return doc_ref.id


def _summarize_changes(changes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Summarize changes for storage (avoid storing full docs).
    
    Keeps first 10 changes with truncated previews.
    """
    if not changes:
        return []
    
    summaries = []
    for change in changes[:10]:  # Limit to 10
        summary = {
            "type": change.get("type", "unknown"),  # create, update, delete
            "collection": change.get("collection", "exercises"),
            "doc_id": change.get("doc_id", ""),
        }
        
        # Add field-level diff if available
        if "fields_changed" in change:
            summary["fields_changed"] = change["fields_changed"][:5]  # Limit fields
        
        summaries.append(summary)
    
    if len(changes) > 10:
        summaries.append({"type": "...", "remaining": len(changes) - 10})
    
    return summaries


def update_daily_summary(
    job_type: JobType,
    status: JobStatus,
    mode: str,
    duration_ms: int,
    changes_count: int = 0,
) -> None:
    """
    Update daily summary statistics.
    
    Uses atomic increments for concurrent safety.
    
    Args:
        job_type: Type of job completed
        status: Final status
        mode: dry_run or apply
        duration_ms: Execution duration
        changes_count: Number of changes made
    """
    db = get_db()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    doc_ref = db.collection(RUN_SUMMARY_COLLECTION).document(today)
    
    # Use atomic increments
    updates = {
        f"jobs_by_type.{job_type.value}": firestore.Increment(1),
        f"jobs_by_status.{status.value}": firestore.Increment(1),
        f"jobs_by_mode.{mode}": firestore.Increment(1),
        "total_jobs": firestore.Increment(1),
        "total_duration_ms": firestore.Increment(duration_ms),
        "total_changes": firestore.Increment(changes_count),
        "updated_at": datetime.now(timezone.utc),
    }
    
    try:
        doc_ref.set(updates, merge=True)
    except Exception as e:
        logger.warning("Failed to update daily summary: %s", e)


def cleanup_completed_jobs(
    dry_run: bool = True,
    completed_retention_days: int = COMPLETED_JOB_RETENTION_DAYS,
    failed_retention_days: int = FAILED_JOB_RETENTION_DAYS,
) -> Dict[str, Any]:
    """
    Archive and delete old completed jobs.
    
    - Writes to run_history before deleting (if not already)
    - Deletes jobs older than retention period
    - Keeps failed/needs_review jobs longer
    
    Args:
        dry_run: If True, only report what would be deleted
        completed_retention_days: Days to keep successful jobs
        failed_retention_days: Days to keep failed jobs
        
    Returns:
        Summary of cleanup operation
    """
    db = get_db()
    now = datetime.now(timezone.utc)
    
    # Calculate cutoff dates
    completed_cutoff = now - timedelta(days=completed_retention_days)
    failed_cutoff = now - timedelta(days=failed_retention_days)
    
    # Query for old completed jobs
    completed_statuses = [
        JobStatus.SUCCEEDED.value,
        JobStatus.SUCCEEDED_DRY_RUN.value,
    ]
    
    failed_statuses = [
        JobStatus.FAILED.value,
        JobStatus.DEADLETTER.value,
        JobStatus.NEEDS_REVIEW.value,
    ]
    
    to_delete = []
    to_archive = []
    
    # Find completed jobs past retention
    for status in completed_statuses:
        query = (
            db.collection(JOBS_COLLECTION)
            .where("status", "==", status)
            .where("updated_at", "<", completed_cutoff)
            .limit(500)
        )
        for doc in query.stream():
            data = doc.to_dict()
            data["id"] = doc.id
            to_delete.append((doc.reference, data))
    
    # Find failed jobs past retention
    for status in failed_statuses:
        query = (
            db.collection(JOBS_COLLECTION)
            .where("status", "==", status)
            .where("updated_at", "<", failed_cutoff)
            .limit(200)
        )
        for doc in query.stream():
            data = doc.to_dict()
            data["id"] = doc.id
            to_delete.append((doc.reference, data))
    
    logger.info("Found %d jobs to cleanup", len(to_delete))
    
    if dry_run:
        return {
            "dry_run": True,
            "would_delete": len(to_delete),
            "sample_jobs": [
                {"id": d[1]["id"], "status": d[1].get("status"), "type": d[1].get("type")}
                for d in to_delete[:5]
            ],
        }
    
    # Archive to run_history (for jobs without history entry)
    archived = 0
    deleted = 0
    
    for doc_ref, data in to_delete:
        try:
            # Check if already in run_history
            existing = (
                db.collection(RUN_HISTORY_COLLECTION)
                .where("job_id", "==", data["id"])
                .limit(1)
                .get()
            )
            
            if not list(existing):
                # Archive first
                job = Job.from_dict(data)
                write_run_history(
                    job=job,
                    status=JobStatus(data.get("status", "unknown")),
                    duration_ms=0,  # Unknown at this point
                    worker_id=data.get("last_lease_owner"),
                )
                archived += 1
            
            # Delete from jobs collection
            doc_ref.delete()
            deleted += 1
            
        except Exception as e:
            logger.warning("Failed to cleanup job %s: %s", data.get("id"), e)
    
    logger.info("Cleanup complete: archived=%d, deleted=%d", archived, deleted)
    
    return {
        "dry_run": False,
        "archived": archived,
        "deleted": deleted,
    }


def get_run_history(
    job_type: Optional[JobType] = None,
    status: Optional[JobStatus] = None,
    family_slug: Optional[str] = None,
    since: Optional[datetime] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """
    Query run history with filters.
    
    Args:
        job_type: Filter by job type
        status: Filter by final status
        family_slug: Filter by family
        since: Only records after this time
        limit: Maximum records to return
        
    Returns:
        List of run history entries
    """
    db = get_db()
    query = db.collection(RUN_HISTORY_COLLECTION)
    
    if job_type:
        query = query.where("job_type", "==", job_type.value)
    if status:
        query = query.where("status", "==", status.value)
    if family_slug:
        query = query.where("family_slug", "==", family_slug)
    if since:
        query = query.where("completed_at", ">=", since)
    
    query = query.order_by("completed_at", direction=firestore.Query.DESCENDING)
    query = query.limit(limit)
    
    results = []
    for doc in query.stream():
        data = doc.to_dict()
        data["_id"] = doc.id
        results.append(data)
    
    return results


def get_daily_summary(date: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Get daily summary for a specific date.
    
    Args:
        date: Date in YYYY-MM-DD format (defaults to today)
        
    Returns:
        Daily summary or None
    """
    db = get_db()
    
    if date is None:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    doc = db.collection(RUN_SUMMARY_COLLECTION).document(date).get()
    
    if doc.exists:
        return doc.to_dict()
    return None


__all__ = [
    "write_run_history",
    "update_daily_summary",
    "cleanup_completed_jobs",
    "get_run_history",
    "get_daily_summary",
]
