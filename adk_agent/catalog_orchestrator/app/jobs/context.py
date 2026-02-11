"""
JobContext - Per-job context using contextvars.

Thread-safe, async-safe storage for the Catalog Orchestrator
concurrent serverless environment.

CRITICAL: Never use module-level globals for request state.
ContextVars provide proper request isolation.

Key difference from Canvas Orchestrator:
- Canvas uses canvas_id + user_id for per-request routing
- Catalog uses job_id + family_slug for job-scoped operations
- doc_id is authoritative (not exercise.id field)
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Optional, Literal


# =============================================================================
# CONTEXT VARIABLES (Thread-safe, Async-safe)
# =============================================================================

_job_context_var: ContextVar[Optional["JobContext"]] = ContextVar(
    "job_context",
    default=None
)


def set_current_job_context(ctx: "JobContext") -> None:
    """
    Set the context for the current job execution.
    
    MUST be called at the start of job processing, BEFORE any
    skill execution or tool calls.
    
    Args:
        ctx: JobContext for the current job
    """
    _job_context_var.set(ctx)


def get_current_job_context() -> "JobContext":
    """
    Get the context for the current job.
    
    Called by skill functions to get job_id, family_slug, mode.
    
    Returns:
        JobContext for current job
        
    Raises:
        RuntimeError: If called outside an active job context
    """
    ctx = _job_context_var.get()
    if ctx is None:
        raise RuntimeError(
            "get_current_job_context() called outside job context. "
            "Ensure set_current_job_context() is called before execution."
        )
    return ctx


def clear_current_job_context() -> None:
    """
    Clear the context after job completion.
    
    Optional cleanup - contextvars automatically reset per-task in asyncio.
    """
    _job_context_var.set(None)


JobMode = Literal["dry_run", "apply"]
JobStatus = Literal[
    "queued",
    "leased",
    "running",
    "succeeded",
    "succeeded_dry_run",
    "failed",
    "needs_review",
    "deadletter"
]


@dataclass(frozen=True)
class JobContext:
    """
    Per-job context for catalog operations.
    
    This is NOT persistent across jobs. Each job creates a new
    JobContext when it begins processing.
    
    Key design decisions:
    - doc_id is authoritative for exercise identity (not exercise.id field)
    - family_slug scopes most operations
    - mode determines whether changes are applied or previewed
    """
    job_id: str
    job_type: str
    family_slug: Optional[str]
    worker_id: str
    mode: JobMode = "dry_run"
    attempt_id: Optional[str] = None
    
    @classmethod
    def from_job(cls, job: dict, worker_id: str, attempt_id: Optional[str] = None) -> "JobContext":
        """
        Create context from a job document.
        
        Args:
            job: Job document from Firestore
            worker_id: ID of the worker processing this job
            attempt_id: ID of this attempt (for logging)
            
        Returns:
            JobContext for this job execution
        """
        payload = job.get("payload", {})
        return cls(
            job_id=job.get("id", ""),
            job_type=job.get("type", ""),
            family_slug=payload.get("family_slug"),
            worker_id=worker_id,
            mode=payload.get("mode", "dry_run"),
            attempt_id=attempt_id,
        )
    
    def is_apply_mode(self) -> bool:
        """Check if job should apply changes (not dry-run)."""
        return self.mode == "apply"
    
    def is_valid(self) -> bool:
        """Check if context has required fields."""
        return bool(self.job_id and self.job_type and self.worker_id)
    
    def __str__(self) -> str:
        """Format for logging."""
        return (
            f"JobContext(job={self.job_id}, type={self.job_type}, "
            f"family={self.family_slug}, mode={self.mode}, worker={self.worker_id})"
        )


__all__ = [
    "JobContext",
    "JobMode",
    "JobStatus",
    "set_current_job_context",
    "get_current_job_context",
    "clear_current_job_context",
]
