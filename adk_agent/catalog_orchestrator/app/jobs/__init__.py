"""
Jobs Package - Job queue, models, and operations.

This package provides:
- models: Job and attempt data models
- queue: Job queue operations (create, lease, complete)
- watchdog: Self-healing for stuck jobs and locks
"""

from app.jobs.models import (
    Job,
    JobType,
    JobQueue,
    JobStatus,
    JobPayload,
    AttemptLog,
)

from app.jobs.queue import (
    create_job,
    poll_job,
    lease_job,
    complete_job,
    fail_job,
    retry_job,
)

from app.jobs.watchdog import (
    recover_stuck_jobs,
    cleanup_expired_locks,
    cleanup_idempotency_records,
)


__all__ = [
    # Models
    "Job",
    "JobType",
    "JobQueue",
    "JobStatus",
    "JobPayload",
    "AttemptLog",
    # Queue
    "create_job",
    "poll_job",
    "lease_job",
    "complete_job",
    "fail_job",
    "retry_job",
    # Watchdog
    "recover_stuck_jobs",
    "cleanup_expired_locks",
    "cleanup_idempotency_records",
]
