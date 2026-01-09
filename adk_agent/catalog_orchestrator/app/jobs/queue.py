"""
Job Queue - Firestore-backed job queue operations.

All operations use Firestore transactions for atomicity.
Lease acquisition is conditional on status, run_after, and existing lease.

Collections:
- catalog_jobs/{jobId}: Job documents
- catalog_locks/{family_slug}: Family locks
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from google.cloud import firestore

from app.jobs.models import Job, JobPayload, JobQueue, JobStatus, JobType

logger = logging.getLogger(__name__)

# Firestore collection names
JOBS_COLLECTION = "catalog_jobs"
LOCKS_COLLECTION = "catalog_locks"
ATTEMPTS_COLLECTION = "catalog_job_runs"

# Lease duration
LEASE_DURATION_SECS = 300  # 5 minutes
LEASE_RENEWAL_MARGIN_SECS = 120  # 2 minutes

# Initialize Firestore client lazily
_db: Optional[firestore.Client] = None


def get_db() -> firestore.Client:
    """Get or initialize Firestore client."""
    global _db
    if _db is None:
        _db = firestore.Client()
    return _db


# =============================================================================
# JOB CREATION
# =============================================================================

def create_job(
    job_type: JobType,
    queue: JobQueue = JobQueue.PRIORITY,
    priority: int = 100,
    family_slug: Optional[str] = None,
    exercise_doc_ids: Optional[List[str]] = None,
    mode: str = "dry_run",
    intent: Optional[Dict[str, Any]] = None,
    merge_config: Optional[Dict[str, Any]] = None,
) -> Job:
    """
    Create a new job in the queue.
    
    Args:
        job_type: Type of job
        queue: Queue lane (priority or maintenance)
        priority: Numeric priority (higher = more urgent)
        family_slug: Target family (if applicable)
        exercise_doc_ids: Target exercise IDs (if applicable)
        mode: "dry_run" or "apply"
        intent: Intent data for EXERCISE_ADD
        merge_config: Config for FAMILY_MERGE
        
    Returns:
        Created Job object
    """
    db = get_db()
    
    job_id = f"job-{uuid.uuid4().hex[:12]}"
    now = datetime.utcnow()
    
    payload = JobPayload(
        family_slug=family_slug,
        exercise_doc_ids=exercise_doc_ids or [],
        mode=mode,
        intent=intent,
        merge_config=merge_config,
    )
    
    job = Job(
        id=job_id,
        type=job_type,
        queue=queue,
        priority=priority,
        status=JobStatus.QUEUED,
        payload=payload,
        attempts=0,
        max_attempts=5,
        created_at=now,
        updated_at=now,
    )
    
    # Write to Firestore
    doc_ref = db.collection(JOBS_COLLECTION).document(job_id)
    doc_ref.set(job.to_dict())
    
    logger.info("Created job: %s, type=%s, family=%s", 
               job_id, job_type.value, family_slug)
    
    return job


# =============================================================================
# JOB POLLING
# =============================================================================

def poll_job(worker_id: str) -> Optional[Job]:
    """
    Poll for the next available job and attempt to lease it.
    
    Queries for ready jobs ordered by queue (priority first) then priority.
    Attempts to lease atomically using transaction.
    
    Args:
        worker_id: ID of the worker polling
        
    Returns:
        Leased Job or None if no jobs available
    """
    db = get_db()
    now = datetime.utcnow()
    
    # Query for ready jobs
    # Priority queue first, then by priority descending
    query = (
        db.collection(JOBS_COLLECTION)
        .where("status", "==", JobStatus.QUEUED.value)
        .order_by("queue")  # priority < maintenance alphabetically
        .order_by("priority", direction=firestore.Query.DESCENDING)
        .limit(10)  # Get a few candidates to try
    )
    
    candidates = list(query.stream())
    
    for doc in candidates:
        data = doc.to_dict()
        
        # Check run_after
        run_after = data.get("run_after")
        if run_after and run_after > now:
            continue
        
        # Try to lease this job
        job = lease_job(doc.id, worker_id)
        if job:
            return job
    
    return None


def lease_job(job_id: str, worker_id: str) -> Optional[Job]:
    """
    Atomically lease a job if it's available.
    
    Uses transaction to check:
    - Status is QUEUED
    - run_after <= now (or null)
    - No unexpired lease
    
    Args:
        job_id: Job to lease
        worker_id: Worker acquiring the lease
        
    Returns:
        Leased Job or None if lease failed
    """
    db = get_db()
    doc_ref = db.collection(JOBS_COLLECTION).document(job_id)
    
    @firestore.transactional
    def lease_transaction(transaction, doc_ref):
        doc = doc_ref.get(transaction=transaction)
        if not doc.exists:
            return None
        
        data = doc.to_dict()
        now = datetime.utcnow()
        
        # Check status
        if data.get("status") != JobStatus.QUEUED.value:
            return None
        
        # Check run_after
        run_after = data.get("run_after")
        if run_after and run_after > now:
            return None
        
        # Check existing lease
        existing_lease = data.get("lease_expires_at")
        if existing_lease and existing_lease > now:
            return None
        
        # Acquire lease
        lease_expires = now + timedelta(seconds=LEASE_DURATION_SECS)
        
        transaction.update(doc_ref, {
            "status": JobStatus.LEASED.value,
            "lease_owner": worker_id,
            "lease_expires_at": lease_expires,
            "attempts": data.get("attempts", 0) + 1,
            "updated_at": now,
        })
        
        # Return updated job
        updated_data = data.copy()
        updated_data["status"] = JobStatus.LEASED.value
        updated_data["lease_owner"] = worker_id
        updated_data["lease_expires_at"] = lease_expires
        updated_data["attempts"] = data.get("attempts", 0) + 1
        updated_data["updated_at"] = now
        
        return Job.from_dict(updated_data)
    
    transaction = db.transaction()
    try:
        job = lease_transaction(transaction, doc_ref)
        if job:
            logger.info("Leased job: %s to worker %s", job_id, worker_id)
        return job
    except Exception as e:
        logger.warning("Failed to lease job %s: %s", job_id, e)
        return None


# =============================================================================
# JOB COMPLETION
# =============================================================================

def complete_job(
    job_id: str,
    worker_id: str,
    status: JobStatus = JobStatus.SUCCEEDED,
    result_summary: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Mark a job as completed.
    
    Args:
        job_id: Job to complete
        worker_id: Worker completing the job (for verification)
        status: Final status (SUCCEEDED, SUCCEEDED_DRY_RUN, NEEDS_REVIEW)
        result_summary: Summary of results
        
    Returns:
        True if completed successfully
    """
    db = get_db()
    doc_ref = db.collection(JOBS_COLLECTION).document(job_id)
    
    @firestore.transactional
    def complete_transaction(transaction, doc_ref):
        doc = doc_ref.get(transaction=transaction)
        if not doc.exists:
            return False
        
        data = doc.to_dict()
        
        # Verify ownership
        if data.get("lease_owner") != worker_id:
            logger.warning("Worker %s tried to complete job %s owned by %s",
                          worker_id, job_id, data.get("lease_owner"))
            return False
        
        now = datetime.utcnow()
        
        transaction.update(doc_ref, {
            "status": status.value,
            "lease_owner": None,
            "lease_expires_at": None,
            "result_summary": result_summary,
            "updated_at": now,
        })
        
        return True
    
    transaction = db.transaction()
    try:
        success = complete_transaction(transaction, doc_ref)
        if success:
            logger.info("Completed job: %s with status %s", job_id, status.value)
        return success
    except Exception as e:
        logger.error("Failed to complete job %s: %s", job_id, e)
        return False


def fail_job(
    job_id: str,
    worker_id: str,
    error: Dict[str, Any],
    is_transient: bool = True,
) -> bool:
    """
    Mark a job as failed.
    
    If transient error, will be retried (up to max_attempts).
    If deterministic error, goes to NEEDS_REVIEW.
    
    Args:
        job_id: Job that failed
        worker_id: Worker that encountered the failure
        error: Structured error info
        is_transient: True for retry-able errors, False for deterministic errors
        
    Returns:
        True if updated successfully
    """
    db = get_db()
    doc_ref = db.collection(JOBS_COLLECTION).document(job_id)
    
    @firestore.transactional
    def fail_transaction(transaction, doc_ref):
        doc = doc_ref.get(transaction=transaction)
        if not doc.exists:
            return False
        
        data = doc.to_dict()
        now = datetime.utcnow()
        
        # Verify ownership (but be lenient for recovery)
        if data.get("lease_owner") != worker_id:
            logger.warning("Worker %s failing job %s owned by %s",
                          worker_id, job_id, data.get("lease_owner"))
        
        attempts = data.get("attempts", 1)
        max_attempts = data.get("max_attempts", 5)
        
        if is_transient and attempts < max_attempts:
            # Retry with backoff
            job = Job.from_dict(data)
            backoff = job.compute_backoff_seconds()
            run_after = now + timedelta(seconds=backoff)
            
            transaction.update(doc_ref, {
                "status": JobStatus.QUEUED.value,
                "lease_owner": None,
                "lease_expires_at": None,
                "run_after": run_after,
                "last_error_at": now,
                "last_lease_owner": worker_id,
                "error": error,
                "updated_at": now,
            })
        elif is_transient:
            # Exhausted retries
            transaction.update(doc_ref, {
                "status": JobStatus.DEADLETTER.value,
                "lease_owner": None,
                "lease_expires_at": None,
                "last_error_at": now,
                "last_lease_owner": worker_id,
                "error": error,
                "updated_at": now,
            })
        else:
            # Deterministic error - needs human review
            transaction.update(doc_ref, {
                "status": JobStatus.NEEDS_REVIEW.value,
                "lease_owner": None,
                "lease_expires_at": None,
                "last_error_at": now,
                "last_lease_owner": worker_id,
                "error": error,
                "updated_at": now,
            })
        
        return True
    
    transaction = db.transaction()
    try:
        success = fail_transaction(transaction, doc_ref)
        if success:
            logger.info("Failed job: %s, transient=%s", job_id, is_transient)
        return success
    except Exception as e:
        logger.error("Failed to fail job %s: %s", job_id, e)
        return False


def retry_job(job_id: str, delay_seconds: int = 0) -> bool:
    """
    Manually retry a job (e.g., from NEEDS_REVIEW or DEADLETTER).
    
    Args:
        job_id: Job to retry
        delay_seconds: Delay before retry
        
    Returns:
        True if reset successfully
    """
    db = get_db()
    doc_ref = db.collection(JOBS_COLLECTION).document(job_id)
    
    now = datetime.utcnow()
    run_after = now + timedelta(seconds=delay_seconds) if delay_seconds else now
    
    try:
        doc_ref.update({
            "status": JobStatus.QUEUED.value,
            "lease_owner": None,
            "lease_expires_at": None,
            "run_after": run_after,
            "updated_at": now,
        })
        logger.info("Retry queued for job: %s", job_id)
        return True
    except Exception as e:
        logger.error("Failed to retry job %s: %s", job_id, e)
        return False


# =============================================================================
# FAMILY LOCKS
# =============================================================================

def acquire_family_lock(
    family_slug: str,
    job_id: str,
    worker_id: str,
    lock_duration_secs: int = LEASE_DURATION_SECS,
) -> bool:
    """
    Acquire exclusive lock on a family.
    
    Args:
        family_slug: Family to lock
        job_id: Job needing the lock
        worker_id: Worker acquiring the lock
        lock_duration_secs: Lock duration
        
    Returns:
        True if lock acquired
    """
    db = get_db()
    lock_ref = db.collection(LOCKS_COLLECTION).document(family_slug)
    
    @firestore.transactional
    def lock_transaction(transaction, lock_ref):
        doc = lock_ref.get(transaction=transaction)
        now = datetime.utcnow()
        expires = now + timedelta(seconds=lock_duration_secs)
        
        if doc.exists:
            data = doc.to_dict()
            existing_expires = data.get("expires_at")
            
            # Check if lock is expired
            if existing_expires and existing_expires > now:
                # Lock is held
                return False
        
        # Create or take over lock
        transaction.set(lock_ref, {
            "family_slug": family_slug,
            "job_id": job_id,
            "worker_id": worker_id,
            "acquired_at": now,
            "expires_at": expires,
        })
        
        return True
    
    transaction = db.transaction()
    try:
        success = lock_transaction(transaction, lock_ref)
        if success:
            logger.info("Acquired lock for family: %s (job %s)", family_slug, job_id)
        return success
    except Exception as e:
        logger.warning("Failed to acquire lock for %s: %s", family_slug, e)
        return False


def release_family_lock(family_slug: str, job_id: str, worker_id: str) -> bool:
    """
    Release a family lock.
    
    Only releases if the lock is owned by this job/worker.
    
    Args:
        family_slug: Family to unlock
        job_id: Job that held the lock
        worker_id: Worker that held the lock
        
    Returns:
        True if released
    """
    db = get_db()
    lock_ref = db.collection(LOCKS_COLLECTION).document(family_slug)
    
    @firestore.transactional
    def release_transaction(transaction, lock_ref):
        doc = lock_ref.get(transaction=transaction)
        
        if not doc.exists:
            return True  # Already released
        
        data = doc.to_dict()
        
        # Verify ownership
        if data.get("job_id") != job_id or data.get("worker_id") != worker_id:
            logger.warning("Lock ownership mismatch for %s", family_slug)
            return False
        
        transaction.delete(lock_ref)
        return True
    
    transaction = db.transaction()
    try:
        success = release_transaction(transaction, lock_ref)
        if success:
            logger.info("Released lock for family: %s", family_slug)
        return success
    except Exception as e:
        logger.warning("Failed to release lock for %s: %s", family_slug, e)
        return False


def renew_lease(job_id: str, worker_id: str) -> bool:
    """
    Renew job lease if expiring soon and still owned.
    
    Args:
        job_id: Job to renew
        worker_id: Worker that holds the lease
        
    Returns:
        True if renewed, False if lease lost or not expiring soon
    """
    db = get_db()
    doc_ref = db.collection(JOBS_COLLECTION).document(job_id)
    
    @firestore.transactional
    def renew_transaction(transaction, doc_ref):
        doc = doc_ref.get(transaction=transaction)
        if not doc.exists:
            return False
        
        data = doc.to_dict()
        now = datetime.utcnow()
        
        # Verify ownership
        if data.get("lease_owner") != worker_id:
            return False
        
        # Check if renewal needed (within margin)
        expires = data.get("lease_expires_at")
        if not expires:
            return False
        
        margin = timedelta(seconds=LEASE_RENEWAL_MARGIN_SECS)
        if expires > now + margin:
            # Not expiring soon
            return True  # Still valid, just don't need to renew
        
        # Renew
        new_expires = now + timedelta(seconds=LEASE_DURATION_SECS)
        transaction.update(doc_ref, {
            "lease_expires_at": new_expires,
            "updated_at": now,
        })
        
        return True
    
    transaction = db.transaction()
    try:
        return renew_transaction(transaction, doc_ref)
    except Exception as e:
        logger.warning("Failed to renew lease for %s: %s", job_id, e)
        return False


__all__ = [
    "create_job",
    "poll_job",
    "lease_job",
    "complete_job",
    "fail_job",
    "retry_job",
    "acquire_family_lock",
    "release_family_lock",
    "renew_lease",
]
