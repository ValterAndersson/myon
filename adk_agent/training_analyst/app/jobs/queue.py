"""
Job Queue - Firestore-backed job queue operations.

All operations use Firestore transactions for atomicity.
No family locks needed (user-scoped jobs don't conflict).

Collections:
- training_analysis_jobs/{jobId}: Job documents
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from google.cloud import firestore

from app.config import JOBS_COLLECTION, LEASE_DURATION_SECS, LEASE_RENEWAL_MARGIN_SECS
from app.firestore_client import get_db
from app.jobs.models import Job, JobPayload, JobStatus, JobType

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    """Return timezone-aware UTC datetime for Firestore compatibility."""
    return datetime.now(timezone.utc)


def _make_naive(dt: datetime) -> datetime:
    """Convert timezone-aware datetime to naive UTC datetime for comparison."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt


# =============================================================================
# JOB CREATION
# =============================================================================

def create_job(
    job_type: JobType,
    user_id: str,
    workout_id: Optional[str] = None,
    window_weeks: Optional[int] = None,
    week_ending: Optional[str] = None,
) -> Job:
    """
    Create a new job in the queue.

    Args:
        job_type: Type of analysis job
        user_id: User ID for the analysis
        workout_id: Workout ID (for POST_WORKOUT)
        window_weeks: Number of weeks to analyze (for WEEKLY_REVIEW)
        week_ending: Week ending date YYYY-MM-DD (for WEEKLY_REVIEW)

    Returns:
        Created Job object
    """
    db = get_db()

    job_id = f"job-{uuid.uuid4().hex[:12]}"
    now = datetime.utcnow()

    payload = JobPayload(
        user_id=user_id,
        workout_id=workout_id,
        window_weeks=window_weeks,
        week_ending=week_ending,
    )

    job = Job(
        id=job_id,
        type=job_type,
        status=JobStatus.QUEUED,
        payload=payload,
        attempts=0,
        max_attempts=3,
        created_at=now,
        updated_at=now,
    )

    # Write to Firestore
    doc_ref = db.collection(JOBS_COLLECTION).document(job_id)
    doc_ref.set(job.to_dict())

    logger.info("Created job: %s, type=%s, user=%s",
               job_id, job_type.value, user_id)

    return job


# =============================================================================
# JOB POLLING
# =============================================================================

def poll_job(worker_id: str) -> Optional[Job]:
    """
    Poll for the next available job and attempt to lease it.

    Queries for ready jobs ordered by created_at.
    Attempts to lease atomically using transaction.

    Args:
        worker_id: ID of the worker polling

    Returns:
        Leased Job or None if no jobs available
    """
    db = get_db()
    now = datetime.utcnow()

    # Query for ready jobs
    query = (
        db.collection(JOBS_COLLECTION)
        .where("status", "==", JobStatus.QUEUED.value)
        .order_by("created_at")
        .limit(10)
    )

    candidates = list(query.stream())

    for doc in candidates:
        data = doc.to_dict()

        # Check run_after
        run_after = _make_naive(data.get("run_after"))
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
        run_after = _make_naive(data.get("run_after"))
        if run_after and run_after > now:
            return None

        # Check existing lease
        existing_lease = _make_naive(data.get("lease_expires_at"))
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
        # Use Firestore doc ID as authoritative — jobs created via .add()
        # don't have an 'id' field in the document body.
        updated_data = data.copy()
        updated_data["id"] = job_id
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
) -> bool:
    """
    Mark a job as completed.

    Args:
        job_id: Job to complete
        worker_id: Worker completing the job (for verification)

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
            "status": JobStatus.SUCCEEDED.value,
            "lease_owner": None,
            "lease_expires_at": None,
            "updated_at": now,
        })

        return True

    transaction = db.transaction()
    try:
        success = complete_transaction(transaction, doc_ref)
        if success:
            logger.info("Completed job: %s", job_id)
        return success
    except Exception as e:
        logger.error("Failed to complete job %s: %s", job_id, e)
        return False


def fail_job(
    job_id: str,
    worker_id: str,
    error: Dict[str, Any],
) -> bool:
    """
    Mark a job as failed.

    Will be retried if attempts < max_attempts.

    Args:
        job_id: Job that failed
        worker_id: Worker that encountered the failure
        error: Structured error info

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

        # Verify ownership (lenient for recovery)
        if data.get("lease_owner") != worker_id:
            logger.warning("Worker %s failing job %s owned by %s",
                          worker_id, job_id, data.get("lease_owner"))

        attempts = data.get("attempts", 1)
        max_attempts = data.get("max_attempts", 3)

        if attempts < max_attempts:
            # Retry with backoff
            data["id"] = job_id
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
        else:
            # Exhausted retries
            transaction.update(doc_ref, {
                "status": JobStatus.FAILED.value,
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
            logger.info("Failed job: %s", job_id)
        return success
    except Exception as e:
        logger.error("Failed to fail job %s: %s", job_id, e)
        return False


def mark_job_running(job_id: str, worker_id: str) -> bool:
    """
    Transition job from LEASED to RUNNING.

    This MUST be called before any writes begin.

    Args:
        job_id: Job to transition
        worker_id: Worker that holds the lease

    Returns:
        True if transitioned successfully

    Raises:
        LockLostError: If job is not in leased state or owned by different worker
    """
    db = get_db()
    doc_ref = db.collection(JOBS_COLLECTION).document(job_id)

    @firestore.transactional
    def running_transaction(transaction, doc_ref):
        doc = doc_ref.get(transaction=transaction)
        if not doc.exists:
            raise LockLostError(f"Job {job_id} not found")

        data = doc.to_dict()
        now = datetime.utcnow()

        # Verify ownership
        if data.get("lease_owner") != worker_id:
            raise LockLostError(
                f"Job {job_id} owned by {data.get('lease_owner')}, not {worker_id}"
            )

        # Verify status is LEASED or already RUNNING
        status = data.get("status")
        if status == JobStatus.RUNNING.value:
            return True

        if status != JobStatus.LEASED.value:
            raise LockLostError(
                f"Job {job_id} status is {status}, expected LEASED"
            )

        # Transition to RUNNING
        transaction.update(doc_ref, {
            "status": JobStatus.RUNNING.value,
            "started_at": now,
            "updated_at": now,
        })

        return True

    transaction = db.transaction()
    try:
        success = running_transaction(transaction, doc_ref)
        if success:
            logger.info("Job %s transitioned to RUNNING", job_id)
        return success
    except LockLostError:
        raise
    except Exception as e:
        logger.error("Failed to mark job %s running: %s", job_id, e)
        raise LockLostError(f"Failed to transition job {job_id}: {e}")


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

        # Check if renewal needed
        expires = _make_naive(data.get("lease_expires_at"))
        if not expires:
            return False

        margin = timedelta(seconds=LEASE_RENEWAL_MARGIN_SECS)
        if expires > now + margin:
            return True

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


class LockLostError(Exception):
    """Raised when a lease is lost."""
    pass


__all__ = [
    "create_job",
    "poll_job",
    "lease_job",
    "complete_job",
    "fail_job",
    "mark_job_running",
    "renew_lease",
    "LockLostError",
]
