"""
Training Analyst Worker - Job processing worker.

This worker:
1. Polls for available jobs (exits immediately if none)
2. Acquires job lease
3. Starts heartbeat for lease renewal
4. Executes job via appropriate analyzer
5. Completes job

Designed to run as a Cloud Run Job - bounded execution, no long-lived polling.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import threading
import time
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Worker configuration
WORKER_ID = os.getenv("WORKER_ID", f"worker-{uuid.uuid4().hex[:8]}")
MAX_JOBS_PER_RUN = int(os.getenv("MAX_JOBS_PER_RUN", "0"))  # 0 = unlimited
MAX_SECONDS_PER_RUN = int(os.getenv("MAX_SECONDS_PER_RUN", "0"))  # 0 = no deadline
SAFETY_MARGIN_SECS = int(os.getenv("SAFETY_MARGIN_SECS", "60"))
HEARTBEAT_INTERVAL_SECS = int(os.getenv("HEARTBEAT_INTERVAL_SECS", "60"))
INTER_JOB_DELAY_SECS = int(os.getenv("INTER_JOB_DELAY_SECS", "0"))  # delay between jobs


def log_event(
    event: str,
    job_id: Optional[str] = None,
    job_type: Optional[str] = None,
    user_id: Optional[str] = None,
    attempt: Optional[int] = None,
    duration_ms: Optional[int] = None,
    **extra: Any,
) -> None:
    """Log a structured event."""
    record = {
        "event": event,
        "worker_id": WORKER_ID,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

    if job_id:
        record["job_id"] = job_id
    if job_type:
        record["job_type"] = job_type
    if user_id:
        record["user_id"] = user_id
    if attempt is not None:
        record["attempt"] = attempt
    if duration_ms is not None:
        record["duration_ms"] = duration_ms

    record.update(extra)
    logger.info(json.dumps(record))


class HeartbeatThread:
    """Background thread for lease renewal during long-running analyzer jobs.

    Prevents lease expiration while the analyzer is still working. Without this,
    jobs running longer than the lease TTL (5 min default) would be reclaimed by
    the watchdog and re-queued, causing duplicate analysis runs.
    Stops automatically when the worker calls stop() after job completion/failure.
    """

    def __init__(self, job_id: str, worker_id: str):
        self.job_id = job_id
        self.worker_id = worker_id
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self):
        """Start the heartbeat thread."""
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        log_event("heartbeat_started", job_id=self.job_id)

    def stop(self):
        """Stop the heartbeat thread."""
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        log_event("heartbeat_stopped", job_id=self.job_id)

    def _loop(self):
        """Heartbeat loop - renew job lease."""
        from app.jobs.queue import renew_lease

        while not self._stop.wait(HEARTBEAT_INTERVAL_SECS):
            try:
                renewed = renew_lease(self.job_id, self.worker_id)
                if not renewed:
                    log_event("lease_renewal_failed", job_id=self.job_id)
            except Exception as e:
                log_event("heartbeat_error", job_id=self.job_id, error=str(e))


class AnalystWorker:
    """Training analyst job processing worker."""

    def __init__(self, worker_id: Optional[str] = None):
        self.worker_id = worker_id or WORKER_ID
        self.running = False
        self.jobs_processed = 0
        self.jobs_failed = 0
        self._current_job_id: Optional[str] = None
        self._deadline: float = 0.0
        self._start_time: float = 0.0

    def start(self):
        """Start the worker (bounded execution)."""
        self._start_time = time.time()
        self._deadline = self._start_time + MAX_SECONDS_PER_RUN - SAFETY_MARGIN_SECS

        log_event(
            "worker_started",
            max_jobs=MAX_JOBS_PER_RUN,
            deadline_secs=MAX_SECONDS_PER_RUN - SAFETY_MARGIN_SECS,
        )

        self.running = True

        # Setup signal handlers
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        try:
            self._run_loop()
        finally:
            self.running = False

            duration_ms = int((time.time() - self._start_time) * 1000)
            log_event(
                "worker_stopped",
                jobs_processed=self.jobs_processed,
                jobs_failed=self.jobs_failed,
                duration_ms=duration_ms,
            )

    def stop(self):
        """Signal the worker to stop."""
        log_event("worker_stopping", reason="signal")
        self.running = False

    def _handle_signal(self, signum, frame):
        """Handle shutdown signals."""
        log_event("signal_received", signal=signum)
        self.stop()

    def _check_deadline(self) -> bool:
        """Check if we're within time budget."""
        if MAX_SECONDS_PER_RUN == 0:
            return True

        if time.time() > self._deadline:
            log_event("deadline_reached", reason="time_budget_exhausted")
            return False
        return True

    def _run_loop(self):
        """Main worker loop."""
        from app.jobs.queue import poll_job

        jobs_this_run = 0

        while self.running and (MAX_JOBS_PER_RUN == 0 or jobs_this_run < MAX_JOBS_PER_RUN):
            if not self._check_deadline():
                break

            try:
                job = poll_job(self.worker_id)
            except Exception as e:
                log_event("poll_error", error=str(e), error_type=type(e).__name__)
                break

            if job is None:
                log_event("no_jobs_available", action="exiting")
                break

            if not self._check_deadline():
                log_event(
                    "job_returned",
                    job_id=job.id,
                    reason="deadline_reached",
                )
                break

            success = self._process_job(job)

            if success:
                self.jobs_processed += 1
            else:
                self.jobs_failed += 1

            jobs_this_run += 1

            if INTER_JOB_DELAY_SECS > 0 and self.running:
                time.sleep(INTER_JOB_DELAY_SECS)

    def _process_job(self, job) -> bool:
        """Process a single job with full lifecycle."""
        from app.jobs.queue import (
            complete_job,
            fail_job,
            mark_job_running,
            LockLostError,
        )

        job_id = job.id
        job_type = job.type.value if job.type else "UNKNOWN"
        user_id = job.payload.user_id
        attempt = job.attempts

        self._current_job_id = job_id
        start_time = time.time()

        log_event(
            "job_started",
            job_id=job_id,
            job_type=job_type,
            user_id=user_id,
            attempt=attempt,
        )

        # Transition to RUNNING
        try:
            mark_job_running(job_id, self.worker_id)
        except LockLostError as e:
            log_event(
                "job_lease_lost",
                job_id=job_id,
                error=str(e),
            )
            return False

        # Start heartbeat
        heartbeat = HeartbeatThread(job_id, self.worker_id)
        heartbeat.start()

        try:
            # Execute the job
            result = self._execute_job(job)

            duration_ms = int((time.time() - start_time) * 1000)

            if result.get("success"):
                complete_job(job_id, self.worker_id)

                log_event(
                    "job_completed",
                    job_id=job_id,
                    job_type=job_type,
                    user_id=user_id,
                    duration_ms=duration_ms,
                )
                return True
            else:
                error = result.get("error", {"message": "Unknown error"})
                fail_job(job_id, self.worker_id, error)

                log_event(
                    "job_failed",
                    job_id=job_id,
                    job_type=job_type,
                    user_id=user_id,
                    error=error,
                    duration_ms=duration_ms,
                )
                return False

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)

            log_event(
                "job_exception",
                job_id=job_id,
                job_type=job_type,
                error=str(e),
                error_type=type(e).__name__,
                duration_ms=duration_ms,
            )

            fail_job(
                job_id,
                self.worker_id,
                {
                    "code": "EXCEPTION",
                    "message": str(e),
                    "type": type(e).__name__,
                },
            )
            return False
        finally:
            heartbeat.stop()
            self._current_job_id = None

    def _execute_job(self, job) -> Dict[str, Any]:
        """Execute job using appropriate analyzer."""
        from app.analyzers.post_workout import PostWorkoutAnalyzer
        from app.analyzers.weekly_review import WeeklyReviewAnalyzer
        from app.jobs.models import JobType

        try:
            if job.type == JobType.POST_WORKOUT:
                analyzer = PostWorkoutAnalyzer()
                return analyzer.analyze(
                    user_id=job.payload.user_id,
                    workout_id=job.payload.workout_id,
                )
            elif job.type == JobType.WEEKLY_REVIEW:
                analyzer = WeeklyReviewAnalyzer()
                return analyzer.analyze(
                    user_id=job.payload.user_id,
                    window_weeks=job.payload.window_weeks or 12,
                    week_ending=job.payload.week_ending,
                )
            else:
                # Unknown job type (e.g., legacy DAILY_BRIEF)
                log_event(
                    "unknown_job_type",
                    job_id=job.id,
                    job_type=str(job.type) if job.type else "None",
                    user_id=job.payload.user_id,
                )
                return {
                    "success": False,
                    "error": {
                        "code": "UNKNOWN_JOB_TYPE",
                        "message": f"Unknown job type: {job.type}",
                    },
                }
        except Exception as e:
            return {
                "success": False,
                "error": {
                    "code": "ANALYZER_ERROR",
                    "message": str(e),
                    "type": type(e).__name__,
                },
            }


def run_worker():
    """Entry point for running the worker."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
    )

    worker = AnalystWorker()
    worker.start()


def run_watchdog():
    """Entry point for running watchdog as a scheduled task."""
    from app.jobs.watchdog import run_watchdog as _run_watchdog

    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
    )

    dry_run = os.getenv("WATCHDOG_DRY_RUN", "true").lower() == "true"

    log_event("watchdog_started", dry_run=dry_run)

    results = _run_watchdog(dry_run=dry_run)

    log_event("watchdog_completed", results=results)
    return results


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "watchdog":
        run_watchdog()
    else:
        run_worker()
