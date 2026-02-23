"""Job models for training analysis queue."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, Optional


class JobType(str, Enum):
    """Training analysis job types."""
    POST_WORKOUT = "POST_WORKOUT"
    WEEKLY_REVIEW = "WEEKLY_REVIEW"


class JobStatus(str, Enum):
    """Job status states."""
    QUEUED = "queued"
    LEASED = "leased"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass
class JobPayload:
    """Job payload with user ID and analysis parameters."""
    user_id: str
    workout_id: Optional[str] = None  # For POST_WORKOUT
    window_weeks: Optional[int] = None  # For WEEKLY_REVIEW
    week_ending: Optional[str] = None  # For WEEKLY_REVIEW (YYYY-MM-DD)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to Firestore-compatible dict."""
        return {
            "user_id": self.user_id,
            "workout_id": self.workout_id,
            "window_weeks": self.window_weeks,
            "week_ending": self.week_ending,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "JobPayload":
        """Create from Firestore dict."""
        return cls(
            user_id=data.get("user_id", ""),
            workout_id=data.get("workout_id"),
            window_weeks=data.get("window_weeks"),
            week_ending=data.get("week_ending"),
        )


@dataclass
class Job:
    """Training analysis job document model."""
    id: str
    type: JobType
    status: JobStatus = JobStatus.QUEUED
    payload: JobPayload = field(default_factory=lambda: JobPayload(user_id=""))

    # Leasing
    lease_owner: Optional[str] = None
    lease_expires_at: Optional[datetime] = None

    # Retries
    attempts: int = 0
    max_attempts: int = 3
    run_after: Optional[datetime] = None

    # Execution tracking
    started_at: Optional[datetime] = None

    # Debug fields
    last_error_at: Optional[datetime] = None
    last_lease_owner: Optional[str] = None

    # Results
    error: Optional[Dict[str, Any]] = None

    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to Firestore-compatible dict."""
        return {
            "id": self.id,
            "type": self.type.value if isinstance(self.type, JobType) else self.type,
            "status": self.status.value if isinstance(self.status, JobStatus) else self.status,
            "payload": self.payload.to_dict() if isinstance(self.payload, JobPayload) else self.payload,
            "lease_owner": self.lease_owner,
            "lease_expires_at": self.lease_expires_at,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "run_after": self.run_after,
            "started_at": self.started_at,
            "last_error_at": self.last_error_at,
            "last_lease_owner": self.last_lease_owner,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Job":
        """Create from Firestore dict."""
        # Handle unknown job types gracefully (e.g., legacy DAILY_BRIEF jobs)
        job_type = None
        raw_type = data.get("type")
        if raw_type:
            try:
                job_type = JobType(raw_type)
            except ValueError:
                # Unknown type - set to None instead of crashing
                job_type = None

        return cls(
            id=data.get("id", ""),
            type=job_type,
            status=JobStatus(data["status"]) if data.get("status") else JobStatus.QUEUED,
            payload=JobPayload.from_dict(data.get("payload", {})),
            lease_owner=data.get("lease_owner"),
            lease_expires_at=data.get("lease_expires_at"),
            attempts=data.get("attempts", 0),
            max_attempts=data.get("max_attempts", 3),
            run_after=data.get("run_after"),
            started_at=data.get("started_at"),
            last_error_at=data.get("last_error_at"),
            last_lease_owner=data.get("last_lease_owner"),
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

        Exponential backoff with jitter:
        - Base: 300 seconds (5 minutes)
        - Multiplier: 2^attempts
        - Max: 1800 seconds (30 minutes)
        - Jitter: 0-60 seconds
        """
        base = 300
        delay = min(base * (2 ** self.attempts), 1800)
        jitter = random.randint(0, 60)
        return delay + jitter


__all__ = [
    "JobType",
    "JobStatus",
    "JobPayload",
    "Job",
]
