"""
Compatibility shim — JobContext has moved to app.jobs.context.

This re-export exists so app.shell.agent and app.shell.tools continue to
work without modification. New code should import from app.jobs.context.
"""

from app.jobs.context import (  # noqa: F401
    JobContext,
    JobMode,
    JobStatus,
    set_current_job_context,
    get_current_job_context,
    clear_current_job_context,
)

__all__ = [
    "JobContext",
    "JobMode",
    "JobStatus",
    "set_current_job_context",
    "get_current_job_context",
    "clear_current_job_context",
]
