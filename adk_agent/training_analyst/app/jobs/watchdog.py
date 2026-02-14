"""
Watchdog - Self-healing for stuck jobs.

Key responsibilities:
1. Recover stuck jobs (lease expired but status still leased/running)
2. No family locks to clean up (user-scoped jobs)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict

from app.config import JOBS_COLLECTION
from app.firestore_client import get_db
from app.jobs.models import Job, JobStatus

logger = logging.getLogger(__name__)


def _make_naive(dt: datetime) -> datetime:
    """Convert timezone-aware datetime to naive UTC datetime for comparison."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt


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

    stuck_statuses = [JobStatus.LEASED.value, JobStatus.RUNNING.value]

    results = {
        "found": 0,
        "recovered": 0,
        "failed": 0,
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
                recovered = _recover_single_job(db, doc.id, data, now)
                if recovered == "recovered":
                    results["recovered"] += 1
                elif recovered == "failed":
                    results["failed"] += 1
            except Exception as e:
                logger.error("Failed to recover job %s: %s", job_id, e)
                results["errors"] += 1

    logger.info("Watchdog: found=%d stuck jobs, recovered=%d, failed=%d",
               results["found"], results["recovered"], results["failed"])

    return results


def _recover_single_job(
    db,
    job_id: str,
    data: Dict[str, Any],
    now: datetime,
) -> str:
    """
    Recover a single stuck job.

    Returns:
        "recovered" if re-queued, "failed" if exhausted retries
    """
    doc_ref = db.collection(JOBS_COLLECTION).document(job_id)

    attempts = data.get("attempts", 1)
    max_attempts = data.get("max_attempts", 3)

    if attempts >= max_attempts:
        # Exhausted retries
        doc_ref.update({
            "status": JobStatus.FAILED.value,
            "lease_owner": None,
            "lease_expires_at": None,
            "last_error_at": now,
            "error": {
                "code": "LEASE_EXPIRED",
                "message": f"Job stuck after {attempts} attempts, lease expired",
            },
            "updated_at": now,
        })
        logger.info("Marked job as failed: %s (attempts=%d)", job_id, attempts)
        return "failed"
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


def run_watchdog(dry_run: bool = True) -> Dict[str, Any]:
    """
    Run all watchdog tasks.

    Args:
        dry_run: If True, only report what would be done

    Returns:
        Results from stuck job recovery
    """
    logger.info("Running watchdog (dry_run=%s)", dry_run)

    results = {
        "stuck_jobs": recover_stuck_jobs(dry_run),
    }

    return results


__all__ = [
    "recover_stuck_jobs",
    "run_watchdog",
]
