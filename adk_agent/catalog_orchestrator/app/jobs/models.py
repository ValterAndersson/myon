"""
Job Models - Data models for the job queue system.

Firestore Collections:
- catalog_jobs/{jobId}: Job documents
- catalog_job_runs/{jobId}/attempts/{attemptId}: Attempt logs
- catalog_locks/{family_slug}: Family locks
- catalog_changes/{changeId}: Change journal entries
- catalog_idempotency/{key}: Idempotency records
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional


class JobType(str, Enum):
    """Catalog job types."""
    # Scan jobs (read-only, emit other jobs)
    MAINTENANCE_SCAN = "MAINTENANCE_SCAN"
    DUPLICATE_DETECTION_SCAN = "DUPLICATE_DETECTION_SCAN"
    ALIAS_INVARIANT_SCAN = "ALIAS_INVARIANT_SCAN"
    
    # Family jobs (scoped to a family)
    FAMILY_AUDIT = "FAMILY_AUDIT"
    FAMILY_NORMALIZE = "FAMILY_NORMALIZE"
    FAMILY_MERGE = "FAMILY_MERGE"
    FAMILY_SPLIT = "FAMILY_SPLIT"
    FAMILY_RENAME_SLUG = "FAMILY_RENAME_SLUG"
    
    # Exercise jobs
    EXERCISE_ADD = "EXERCISE_ADD"
    TARGETED_FIX = "TARGETED_FIX"
    
    # Alias jobs
    ALIAS_REPAIR = "ALIAS_REPAIR"


class JobQueue(str, Enum):
    """Job queue lanes."""
    PRIORITY = "priority"      # User-triggered, high-priority work
    MAINTENANCE = "maintenance"  # Background scans and cleanup


class JobStatus(str, Enum):
    """Job status states."""
    QUEUED = "queued"              # Ready to be processed
    LEASED = "leased"              # Claimed by a worker
    RUNNING = "running"            # Actively being processed
    SUCCEEDED = "succeeded"        # Completed successfully
    SUCCEEDED_DRY_RUN = "succeeded_dry_run"  # Dry-run completed
    FAILED = "failed"              # Failed, may retry
    NEEDS_REVIEW = "needs_review"  # Needs human intervention
    DEADLETTER = "deadletter"      # Exhausted retries, archived
    DEFERRED = "deferred"          # Waiting for dependency


@dataclass
class JobPayload:
    """Job payload with scope and parameters."""
    family_slug: Optional[str] = None
    exercise_doc_ids: List[str] = field(default_factory=list)
    alias_slugs: List[str] = field(default_factory=list)
    mode: str = "dry_run"  # "dry_run" | "apply"
    intent: Optional[Dict[str, Any]] = None  # For EXERCISE_ADD
    merge_config: Optional[Dict[str, Any]] = None  # For FAMILY_MERGE
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to Firestore-compatible dict."""
        return {
            "family_slug": self.family_slug,
            "exercise_doc_ids": self.exercise_doc_ids,
            "alias_slugs": self.alias_slugs,
            "mode": self.mode,
            "intent": self.intent,
            "merge_config": self.merge_config,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "JobPayload":
        """Create from Firestore dict."""
        return cls(
            family_slug=data.get("family_slug"),
            exercise_doc_ids=data.get("exercise_doc_ids", []),
            alias_slugs=data.get("alias_slugs", []),
            mode=data.get("mode", "dry_run"),
            intent=data.get("intent"),
            merge_config=data.get("merge_config"),
        )


@dataclass
class Job:
    """Catalog job document model."""
    id: str
    type: JobType
    queue: JobQueue = JobQueue.PRIORITY
    priority: int = 100
    status: JobStatus = JobStatus.QUEUED
    payload: JobPayload = field(default_factory=JobPayload)
    
    # Leasing
    lease_owner: Optional[str] = None
    lease_expires_at: Optional[datetime] = None
    
    # Retries
    attempts: int = 0
    max_attempts: int = 5
    run_after: Optional[datetime] = None
    
    # Debug fields (for watchdog recovery)
    last_error_at: Optional[datetime] = None
    last_lease_owner: Optional[str] = None
    
    # Results
    result_summary: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None
    
    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to Firestore-compatible dict."""
        return {
            "id": self.id,
            "type": self.type.value if isinstance(self.type, JobType) else self.type,
            "queue": self.queue.value if isinstance(self.queue, JobQueue) else self.queue,
            "priority": self.priority,
            "status": self.status.value if isinstance(self.status, JobStatus) else self.status,
            "payload": self.payload.to_dict() if isinstance(self.payload, JobPayload) else self.payload,
            "lease_owner": self.lease_owner,
            "lease_expires_at": self.lease_expires_at,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "run_after": self.run_after,
            "last_error_at": self.last_error_at,
            "last_lease_owner": self.last_lease_owner,
            "result_summary": self.result_summary,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Job":
        """Create from Firestore dict."""
        return cls(
            id=data.get("id", ""),
            type=JobType(data["type"]) if data.get("type") else JobType.MAINTENANCE_SCAN,
            queue=JobQueue(data["queue"]) if data.get("queue") else JobQueue.PRIORITY,
            priority=data.get("priority", 100),
            status=JobStatus(data["status"]) if data.get("status") else JobStatus.QUEUED,
            payload=JobPayload.from_dict(data.get("payload", {})),
            lease_owner=data.get("lease_owner"),
            lease_expires_at=data.get("lease_expires_at"),
            attempts=data.get("attempts", 0),
            max_attempts=data.get("max_attempts", 5),
            run_after=data.get("run_after"),
            last_error_at=data.get("last_error_at"),
            last_lease_owner=data.get("last_lease_owner"),
            result_summary=data.get("result_summary"),
            error=data.get("error"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )
    
    def is_ready(self, now: Optional[datetime] = None) -> bool:
        """Check if job is ready to be processed."""
        now = now or datetime.utcnow()
        if self.status != JobStatus.QUEUED:
            return False
        if self.run_after and self.run_after > now:
            return False
        return True
    
    def compute_backoff_seconds(self) -> int:
        """
        Compute backoff delay for retry.
        
        Uses exponential backoff with jitter:
        - Base: 300 seconds (5 minutes)
        - Multiplier: 2^attempts
        - Max: 3600 seconds (1 hour)
        - Jitter: 0-60 seconds
        """
        base = 300
        delay = min(base * (2 ** self.attempts), 3600)
        jitter = random.randint(0, 60)
        return delay + jitter


@dataclass
class AttemptLog:
    """Attempt log for job execution."""
    id: str
    job_id: str
    attempt_number: int
    worker_id: str
    
    # Status
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    status: str = "running"  # running, succeeded, failed
    
    # Plan
    change_plan: Optional[Dict[str, Any]] = None
    
    # Validation
    validator_output: Optional[Dict[str, Any]] = None
    
    # Apply
    operations_applied: int = 0
    operations_skipped: int = 0
    journal_id: Optional[str] = None
    
    # Errors
    error: Optional[Dict[str, Any]] = None
    
    # Pipeline events
    events: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to Firestore-compatible dict."""
        return {
            "id": self.id,
            "job_id": self.job_id,
            "attempt_number": self.attempt_number,
            "worker_id": self.worker_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "status": self.status,
            "change_plan": self.change_plan,
            "validator_output": self.validator_output,
            "operations_applied": self.operations_applied,
            "operations_skipped": self.operations_skipped,
            "journal_id": self.journal_id,
            "error": self.error,
            "events": self.events,
        }
    
    def add_event(self, event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
        """Add a pipeline event."""
        self.events.append({
            "type": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            "data": data or {},
        })


def compute_idempotency_key(job_id: str, op_seed: str) -> str:
    """
    Compute idempotency key for an operation.
    
    Args:
        job_id: Job ID
        op_seed: Operation-specific seed (e.g., "rename_exercise:abc123:new-slug")
        
    Returns:
        Hashed idempotency key
    """
    raw = f"{job_id}:{op_seed}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


__all__ = [
    "JobType",
    "JobQueue",
    "JobStatus",
    "JobPayload",
    "Job",
    "AttemptLog",
    "compute_idempotency_key",
]
