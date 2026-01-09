"""
Apply Package - Idempotent apply engine with journaling and backups.

This package provides:
- engine: Main apply engine for executing Change Plans
- idempotency: Idempotency guard to prevent duplicate operations
- journal: Change journaling for audit trail
- backup: Document backup snapshots for rollback
"""

from app.apply.engine import (
    ApplyEngine,
    apply_change_plan,
    ApplyResult,
)

from app.apply.idempotency import (
    IdempotencyGuard,
    check_idempotency,
    record_operation,
)

from app.apply.journal import (
    ChangeJournal,
    record_change,
    get_job_changes,
)


__all__ = [
    # Engine
    "ApplyEngine",
    "apply_change_plan",
    "ApplyResult",
    # Idempotency
    "IdempotencyGuard",
    "check_idempotency",
    "record_operation",
    # Journal
    "ChangeJournal",
    "record_change",
    "get_job_changes",
]
