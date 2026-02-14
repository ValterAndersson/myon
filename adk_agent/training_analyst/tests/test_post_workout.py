"""Tests for post-workout analyzer."""

import pytest
from datetime import datetime, timedelta


def test_import_analyzer():
    """Test that analyzers can be imported."""
    from app.analyzers.post_workout import PostWorkoutAnalyzer
    from app.analyzers.daily_brief import DailyBriefAnalyzer
    from app.analyzers.weekly_review import WeeklyReviewAnalyzer

    assert PostWorkoutAnalyzer is not None
    assert DailyBriefAnalyzer is not None
    assert WeeklyReviewAnalyzer is not None


def test_import_models():
    """Test that models can be imported."""
    from app.jobs.models import Job, JobType, JobStatus, JobPayload

    assert Job is not None
    assert JobType is not None
    assert JobStatus is not None
    assert JobPayload is not None


def test_job_lifecycle():
    """Test job model lifecycle methods."""
    from app.jobs.models import Job, JobType, JobStatus, JobPayload

    payload = JobPayload(user_id="test_user", workout_id="test_workout")
    job = Job(
        id="test_job",
        type=JobType.POST_WORKOUT,
        status=JobStatus.QUEUED,
        payload=payload,
    )

    # Test ready check
    assert job.is_ready()

    # Test backoff computation
    job.attempts = 1
    backoff = job.compute_backoff_seconds()
    assert 300 <= backoff <= 720  # Base 300s * 2 + jitter

    # Test dict conversion
    job_dict = job.to_dict()
    assert job_dict["type"] == "POST_WORKOUT"
    assert job_dict["status"] == "queued"
    assert job_dict["payload"]["user_id"] == "test_user"

    # Test from_dict
    restored = Job.from_dict(job_dict)
    assert restored.id == job.id
    assert restored.type == job.type
