"""
Catalog Worker - Job processing worker for Catalog Orchestrator.

This worker:
1. Polls for available jobs (exits immediately if none)
2. Acquires job lease and family lock
3. Starts heartbeat for lease renewal
4. Executes job via shell agent
5. Releases lock and completes job

Designed to run as a Cloud Run Job - bounded execution, no long-lived polling.

Execution contract:
- Process up to MAX_JOBS_PER_RUN jobs
- Exit when time budget (deadline) is exhausted
- Exit immediately if no jobs available (no sleep-retry)
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
MAX_JOBS_PER_RUN = int(os.getenv("MAX_JOBS_PER_RUN", "10"))
MAX_SECONDS_PER_RUN = int(os.getenv("MAX_SECONDS_PER_RUN", "840"))  # 14 min
SAFETY_MARGIN_SECS = int(os.getenv("SAFETY_MARGIN_SECS", "60"))  # 1 min buffer
HEARTBEAT_INTERVAL_SECS = int(os.getenv("HEARTBEAT_INTERVAL_SECS", "60"))

# Apply mode gate
APPLY_ENABLED = os.getenv("CATALOG_APPLY_ENABLED", "false").lower() == "true"


def log_event(
    event: str,
    job_id: Optional[str] = None,
    job_type: Optional[str] = None,
    family_slug: Optional[str] = None,
    attempt: Optional[int] = None,
    duration_ms: Optional[int] = None,
    **extra: Any,
) -> None:
    """
    Log a structured event.
    
    Uses JSON for Cloud Logging compatibility.
    """
    record = {
        "event": event,
        "worker_id": WORKER_ID,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }
    
    if job_id:
        record["job_id"] = job_id
    if job_type:
        record["job_type"] = job_type
    if family_slug:
        record["family_slug"] = family_slug
    if attempt is not None:
        record["attempt"] = attempt
    if duration_ms is not None:
        record["duration_ms"] = duration_ms
    
    record.update(extra)
    
    # Log as JSON for structured logging
    logger.info(json.dumps(record))


class HeartbeatThread:
    """Background thread for lease renewal."""
    
    def __init__(self, job_id: str, worker_id: str, family_slug: Optional[str] = None):
        self.job_id = job_id
        self.worker_id = worker_id
        self.family_slug = family_slug
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
        """Heartbeat loop - renew job lease and family lock."""
        from app.jobs.queue import renew_lease, renew_family_lock, LockLostError
        
        while not self._stop.wait(HEARTBEAT_INTERVAL_SECS):
            try:
                # Renew job lease
                renewed = renew_lease(self.job_id, self.worker_id)
                if not renewed:
                    log_event("lease_renewal_failed", job_id=self.job_id)
                
                # Renew family lock if held
                if self.family_slug:
                    try:
                        renew_family_lock(
                            self.family_slug,
                            self.job_id,
                            self.worker_id,
                        )
                    except LockLostError as e:
                        log_event(
                            "lock_lost",
                            job_id=self.job_id,
                            family_slug=self.family_slug,
                            error=str(e),
                        )
                        
            except Exception as e:
                log_event("heartbeat_error", job_id=self.job_id, error=str(e))


class CatalogWorker:
    """
    Catalog job processing worker.
    
    Bounded execution: processes up to MAX_JOBS_PER_RUN jobs within
    MAX_SECONDS_PER_RUN time budget, then exits.
    
    No long-lived polling - exits immediately if no jobs available.
    """
    
    def __init__(self, worker_id: Optional[str] = None):
        """
        Initialize worker.
        
        Args:
            worker_id: Unique worker identifier
        """
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
            apply_enabled=APPLY_ENABLED,
            max_jobs=MAX_JOBS_PER_RUN,
            deadline_secs=MAX_SECONDS_PER_RUN - SAFETY_MARGIN_SECS,
        )
        
        self.running = True
        
        # Setup signal handlers for graceful shutdown
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
        """
        Check if we're within time budget.
        
        Returns:
            True if we can continue, False if we should exit
        """
        if time.time() > self._deadline:
            log_event("deadline_reached", reason="time_budget_exhausted")
            return False
        return True
    
    def _run_loop(self):
        """
        Main worker loop.
        
        Exit conditions:
        - No jobs available (exit immediately, no retry)
        - MAX_JOBS_PER_RUN reached
        - Deadline exceeded
        - Signal received
        """
        from app.jobs.queue import poll_job
        
        jobs_this_run = 0
        
        while self.running and jobs_this_run < MAX_JOBS_PER_RUN:
            # Check time budget before polling
            if not self._check_deadline():
                break
            
            try:
                job = poll_job(self.worker_id)
            except Exception as e:
                log_event("poll_error", error=str(e), error_type=type(e).__name__)
                # Exit on poll error, don't retry
                break
            
            if job is None:
                # No jobs available - exit immediately, no sleep-retry
                log_event("no_jobs_available", action="exiting")
                break
            
            # Check time budget before processing
            if not self._check_deadline():
                # Return job to queue (it was leased but we can't process)
                log_event(
                    "job_returned",
                    job_id=job.id,
                    reason="deadline_reached",
                )
                # Job will be reclaimed by watchdog after lease expires
                break
            
            success = self._process_job(job)
            
            if success:
                self.jobs_processed += 1
            else:
                self.jobs_failed += 1
            
            jobs_this_run += 1
    
    def _process_job(self, job) -> bool:
        """
        Process a single job with full lifecycle.
        
        Args:
            job: Job model from poll_job
            
        Returns:
            True if job succeeded, False otherwise
        """
        from app.jobs.queue import (
            acquire_family_lock,
            release_family_lock,
            complete_job,
            fail_job,
            mark_job_running,
            LockLostError,
        )
        from app.jobs.models import JobStatus
        from app.shell.agent import execute_job
        from app.shell.context import JobContext, set_current_job_context, clear_current_job_context
        
        job_id = job.id
        job_type = job.type.value
        family_slug = job.payload.family_slug
        mode = job.payload.mode
        attempt = job.attempts
        
        self._current_job_id = job_id
        start_time = time.time()
        
        log_event(
            "job_started",
            job_id=job_id,
            job_type=job_type,
            family_slug=family_slug,
            attempt=attempt,
            mode=mode,
        )
        
        # Check apply mode gate
        if mode == "apply" and not APPLY_ENABLED:
            log_event(
                "job_rejected",
                job_id=job_id,
                reason="apply_disabled",
            )
            fail_job(
                job_id,
                self.worker_id,
                {
                    "code": "APPLY_DISABLED",
                    "message": "CATALOG_APPLY_ENABLED not set",
                },
                is_transient=False,
            )
            return False
        
        # Acquire family lock if needed
        lock_acquired = False
        if family_slug and self._job_needs_lock(job.type):
            lock_acquired = acquire_family_lock(family_slug, job_id, self.worker_id)
            if not lock_acquired:
                log_event(
                    "lock_contention",
                    job_id=job_id,
                    family_slug=family_slug,
                )
                fail_job(
                    job_id,
                    self.worker_id,
                    {
                        "code": "LOCK_CONTENTION",
                        "message": f"Could not acquire lock for family {family_slug}",
                    },
                    is_transient=True,
                )
                return False
        
        # Transition to RUNNING before any writes
        try:
            mark_job_running(job_id, self.worker_id)
        except LockLostError as e:
            log_event(
                "job_lease_lost",
                job_id=job_id,
                error=str(e),
            )
            if lock_acquired:
                release_family_lock(family_slug, job_id, self.worker_id)
            return False
        
        # Start heartbeat
        heartbeat = HeartbeatThread(job_id, self.worker_id, family_slug)
        heartbeat.start()
        
        try:
            # Set job context
            ctx = JobContext.from_job(job.to_dict(), self.worker_id)
            set_current_job_context(ctx)
            
            # Execute the job
            result = execute_job(job.to_dict(), self.worker_id)
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            if result.get("success"):
                # Determine final status
                if mode == "dry_run":
                    final_status = JobStatus.SUCCEEDED_DRY_RUN
                else:
                    final_status = JobStatus.SUCCEEDED
                
                complete_job(job_id, self.worker_id, final_status, result)
                
                log_event(
                    "job_completed",
                    job_id=job_id,
                    job_type=job_type,
                    family_slug=family_slug,
                    status=final_status.value,
                    duration_ms=duration_ms,
                )
                return True
            else:
                # Job failed
                error = result.get("error", {"message": "Unknown error"})
                is_transient = result.get("is_transient", True)
                fail_job(job_id, self.worker_id, error, is_transient)
                
                log_event(
                    "job_failed",
                    job_id=job_id,
                    job_type=job_type,
                    family_slug=family_slug,
                    error=error,
                    is_transient=is_transient,
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
                is_transient=True,
            )
            return False
        finally:
            # Stop heartbeat
            heartbeat.stop()
            
            # Release family lock
            if lock_acquired:
                release_family_lock(family_slug, job_id, self.worker_id)
            
            # Clear context
            clear_current_job_context()
            self._current_job_id = None
    
    def _job_needs_lock(self, job_type) -> bool:
        """Check if job type requires family lock."""
        from app.jobs.models import JobType
        
        # Jobs that mutate family data need locks
        lock_required_types = {
            JobType.FAMILY_NORMALIZE,
            JobType.FAMILY_MERGE,
            JobType.FAMILY_SPLIT,
            JobType.FAMILY_RENAME_SLUG,
            JobType.EXERCISE_ADD,
            JobType.TARGETED_FIX,
            JobType.ALIAS_REPAIR,
            JobType.CATALOG_ENRICH_FIELD,
        }
        return job_type in lock_required_types


def run_worker():
    """Entry point for running the worker."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",  # JSON logs, no extra formatting
    )
    
    worker = CatalogWorker()
    worker.start()


def run_watchdog():
    """Entry point for running watchdog as a scheduled task."""
    from app.jobs.watchdog import run_watchdog as _run_watchdog
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
    )
    
    # Run in non-dry-run mode for actual cleanup
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
