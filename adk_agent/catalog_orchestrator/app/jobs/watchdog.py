"""
Watchdog - Self-healing for stuck jobs and stale locks.

Key responsibilities:
1. Recover stuck jobs (lease expired but status still leased/running)
2. Cleanup expired family locks
3. Cleanup old idempotency records

Uses only lease_expires_at as source of truth for stuck detection.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from google.cloud import firestore

from app.jobs.models import Job, JobStatus
from app.jobs.queue import (
    JOBS_COLLECTION,
    LOCKS_COLLECTION,
    get_db,
)

logger = logging.getLogger(__name__)

# Collections
IDEMPOTENCY_COLLECTION = "catalog_idempotency"

# Watchdog configuration
IDEMPOTENCY_TTL_DAYS = 7


def recover_stuck_jobs(dry_run: bool = True) -> Dict[str, Any]:
    """
    Find and recover jobs stuck in leased/running with expired leases.
    
    Uses lease_expires_at as the single source of truth.
    
    Args:
        dry_run: If True, only report what would be done
        
    Returns:
        Summary of stuck jobs found and actions taken
    """
    db = get_db()
    now = datetime.utcnow()
    
    # Query for stuck jobs:
    # - Status is LEASED or RUNNING
    # - lease_expires_at < now
    stuck_statuses = [JobStatus.LEASED.value, JobStatus.RUNNING.value]
    
    results = {
        "found": 0,
        "recovered": 0,
        "deadlettered": 0,
        "errors": 0,
        "jobs": [],
        "dry_run": dry_run,
    }
    
    for status in stuck_statuses:
        query = (
            db.collection(JOBS_COLLECTION)
            .where("status", "==", status)
            .where("lease_expires_at", "<", now)
            .limit(100)
        )
        
        for doc in query.stream():
            data = doc.to_dict()
            job_id = doc.id
            
            results["found"] += 1
            results["jobs"].append({
                "id": job_id,
                "type": data.get("type"),
                "status": data.get("status"),
                "lease_expires_at": str(data.get("lease_expires_at")),
                "attempts": data.get("attempts"),
                "last_lease_owner": data.get("last_lease_owner") or data.get("lease_owner"),
            })
            
            if dry_run:
                continue
            
            try:
                # Recover the job
                recovered = _recover_single_job(db, doc.id, data, now)
                if recovered == "recovered":
                    results["recovered"] += 1
                elif recovered == "deadlettered":
                    results["deadlettered"] += 1
            except Exception as e:
                logger.error("Failed to recover job %s: %s", job_id, e)
                results["errors"] += 1
    
    logger.info("Watchdog: found=%d stuck jobs, recovered=%d, deadlettered=%d",
               results["found"], results["recovered"], results["deadlettered"])
    
    return results


def _recover_single_job(
    db: firestore.Client,
    job_id: str,
    data: Dict[str, Any],
    now: datetime,
) -> str:
    """
    Recover a single stuck job.
    
    Returns:
        "recovered" if re-queued, "deadlettered" if exhausted retries
    """
    doc_ref = db.collection(JOBS_COLLECTION).document(job_id)
    
    attempts = data.get("attempts", 1)
    max_attempts = data.get("max_attempts", 5)
    
    if attempts >= max_attempts:
        # Exhausted retries - deadletter
        doc_ref.update({
            "status": JobStatus.DEADLETTER.value,
            "lease_owner": None,
            "lease_expires_at": None,
            "last_error_at": now,
            "error": {
                "code": "LEASE_EXPIRED",
                "message": f"Job stuck after {attempts} attempts, lease expired",
            },
            "updated_at": now,
        })
        logger.info("Deadlettered stuck job: %s (attempts=%d)", job_id, attempts)
        return "deadlettered"
    else:
        # Compute backoff for retry
        job = Job.from_dict(data)
        backoff = job.compute_backoff_seconds()
        run_after = now + timedelta(seconds=backoff)
        
        # Re-queue with backoff
        doc_ref.update({
            "status": JobStatus.QUEUED.value,
            "lease_owner": None,
            "lease_expires_at": None,
            "run_after": run_after,
            "last_error_at": now,
            "last_lease_owner": data.get("lease_owner"),
            "error": {
                "code": "LEASE_EXPIRED",
                "message": "Job lease expired, recovered by watchdog",
            },
            "updated_at": now,
        })
        logger.info("Recovered stuck job: %s, retry after %ds", job_id, backoff)
        return "recovered"


def cleanup_expired_locks(dry_run: bool = True) -> Dict[str, Any]:
    """
    Cleanup expired family locks.
    
    Finds locks where expires_at < now and deletes them.
    
    Args:
        dry_run: If True, only report what would be done
        
    Returns:
        Summary of locks cleaned up
    """
    db = get_db()
    now = datetime.utcnow()
    
    results = {
        "found": 0,
        "cleaned": 0,
        "errors": 0,
        "locks": [],
        "dry_run": dry_run,
    }
    
    query = (
        db.collection(LOCKS_COLLECTION)
        .where("expires_at", "<", now)
        .limit(100)
    )
    
    for doc in query.stream():
        data = doc.to_dict()
        family_slug = doc.id
        
        results["found"] += 1
        results["locks"].append({
            "family_slug": family_slug,
            "job_id": data.get("job_id"),
            "worker_id": data.get("worker_id"),
            "expires_at": str(data.get("expires_at")),
        })
        
        if dry_run:
            continue
        
        try:
            doc.reference.delete()
            results["cleaned"] += 1
            logger.info("Cleaned up expired lock: %s", family_slug)
        except Exception as e:
            logger.error("Failed to cleanup lock %s: %s", family_slug, e)
            results["errors"] += 1
    
    logger.info("Lock cleanup: found=%d, cleaned=%d", 
               results["found"], results["cleaned"])
    
    return results


def cleanup_idempotency_records(
    dry_run: bool = True,
    ttl_days: int = IDEMPOTENCY_TTL_DAYS,
) -> Dict[str, Any]:
    """
    Cleanup old idempotency records.
    
    Deletes records where expires_at < now or created_at + ttl < now.
    
    Args:
        dry_run: If True, only report what would be done
        ttl_days: TTL for records in days
        
    Returns:
        Summary of records cleaned up
    """
    db = get_db()
    now = datetime.utcnow()
    cutoff = now - timedelta(days=ttl_days)
    
    results = {
        "found": 0,
        "cleaned": 0,
        "errors": 0,
        "dry_run": dry_run,
    }
    
    # Query by expires_at if set
    query1 = (
        db.collection(IDEMPOTENCY_COLLECTION)
        .where("expires_at", "<", now)
        .limit(500)
    )
    
    for doc in query1.stream():
        results["found"] += 1
        
        if dry_run:
            continue
        
        try:
            doc.reference.delete()
            results["cleaned"] += 1
        except Exception as e:
            results["errors"] += 1
    
    # Also query by created_at for records without expires_at
    query2 = (
        db.collection(IDEMPOTENCY_COLLECTION)
        .where("created_at", "<", cutoff)
        .limit(500)
    )
    
    for doc in query2.stream():
        # Skip if already counted (has expires_at and was deleted)
        data = doc.to_dict()
        if data.get("expires_at") and data["expires_at"] < now:
            continue
        
        results["found"] += 1
        
        if dry_run:
            continue
        
        try:
            doc.reference.delete()
            results["cleaned"] += 1
        except Exception as e:
            results["errors"] += 1
    
    logger.info("Idempotency cleanup: found=%d, cleaned=%d",
               results["found"], results["cleaned"])
    
    return results


def run_watchdog(dry_run: bool = True) -> Dict[str, Any]:
    """
    Run all watchdog tasks.
    
    Args:
        dry_run: If True, only report what would be done
        
    Returns:
        Combined results from all tasks
    """
    logger.info("Running watchdog (dry_run=%s)", dry_run)
    
    results = {
        "stuck_jobs": recover_stuck_jobs(dry_run),
        "expired_locks": cleanup_expired_locks(dry_run),
        "idempotency": cleanup_idempotency_records(dry_run),
    }
    
    return results


__all__ = [
    "recover_stuck_jobs",
    "cleanup_expired_locks",
    "cleanup_idempotency_records",
    "run_watchdog",
]
