"""
Catalog Worker - Job processing worker for Catalog Orchestrator.

This worker:
1. Polls for available jobs
2. Acquires job lease and family lock
3. Starts heartbeat for lease renewal
4. Executes job via shell agent
5. Releases lock and completes job

Designed to run as a Cloud Run Job or similar containerized environment.
"""

from __future__ import annotations

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
POLL_INTERVAL_SECS = int(os.getenv("POLL_INTERVAL_SECS", "10"))
MAX_JOBS_PER_RUN = int(os.getenv("MAX_JOBS_PER_RUN", "10"))
HEARTBEAT_INTERVAL_SECS = int(os.getenv("HEARTBEAT_INTERVAL_SECS", "60"))

# Apply mode gate
APPLY_ENABLED = os.getenv("CATALOG_APPLY_ENABLED", "false").lower() == "true"


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
        logger.debug("Heartbeat started for job %s", self.job_id)
    
    def stop(self):
        """Stop the heartbeat thread."""
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        logger.debug("Heartbeat stopped for job %s", self.job_id)
    
    def _loop(self):
        """Heartbeat loop."""
        from app.jobs.queue import renew_lease
        
        while not self._stop.wait(HEARTBEAT_INTERVAL_SECS):
            try:
                renewed = renew_lease(self.job_id, self.worker_id)
                if not renewed:
                    logger.warning("Failed to renew lease for job %s", self.job_id)
            except Exception as e:
                logger.warning("Heartbeat error: %s", e)


class CatalogWorker:
    """
    Catalog job processing worker.
    
    Polls for jobs, acquires leases/locks, executes via agent, handles failures.
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
    
    def start(self):
        """Start the worker loop."""
        logger.info("Worker %s starting (apply_enabled=%s)", 
                   self.worker_id, APPLY_ENABLED)
        self.running = True
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)
        
        try:
            self._run_loop()
        finally:
            self.running = False
            logger.info("Worker %s stopped. Processed: %d, Failed: %d",
                       self.worker_id, self.jobs_processed, self.jobs_failed)
    
    def stop(self):
        """Signal the worker to stop."""
        logger.info("Worker %s stopping", self.worker_id)
        self.running = False
    
    def _handle_signal(self, signum, frame):
        """Handle shutdown signals."""
        logger.info("Received signal %d, stopping worker", signum)
        self.stop()
    
    def _run_loop(self):
        """Main worker loop."""
        from app.jobs.queue import poll_job
        
        jobs_this_run = 0
        
        while self.running and jobs_this_run < MAX_JOBS_PER_RUN:
            try:
                job = poll_job(self.worker_id)
            except Exception as e:
                logger.error("Poll error: %s", e)
                time.sleep(POLL_INTERVAL_SECS)
                continue
            
            if job is None:
                logger.debug("No jobs available, sleeping %ds", POLL_INTERVAL_SECS)
                time.sleep(POLL_INTERVAL_SECS)
                continue
            
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
        )
        from app.jobs.models import JobStatus
        from app.shell.agent import execute_job
        from app.shell.context import JobContext, set_current_job_context, clear_current_job_context
        
        job_id = job.id
        family_slug = job.payload.family_slug
        mode = job.payload.mode
        
        self._current_job_id = job_id
        logger.info("Processing job: %s, type=%s, family=%s, mode=%s",
                   job_id, job.type.value, family_slug, mode)
        
        # Check apply mode gate
        if mode == "apply" and not APPLY_ENABLED:
            logger.warning("Apply mode disabled for job %s", job_id)
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
                logger.warning("Failed to acquire lock for family %s", family_slug)
                # Retry later
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
        
        # Start heartbeat
        heartbeat = HeartbeatThread(job_id, self.worker_id, family_slug)
        heartbeat.start()
        
        try:
            # Set job context
            ctx = JobContext.from_job(job.to_dict(), self.worker_id)
            set_current_job_context(ctx)
            
            # Execute the job
            result = execute_job(job.to_dict(), self.worker_id)
            
            if result.get("success"):
                # Determine final status
                if mode == "dry_run":
                    final_status = JobStatus.SUCCEEDED_DRY_RUN
                else:
                    final_status = JobStatus.SUCCEEDED
                
                complete_job(job_id, self.worker_id, final_status, result)
                logger.info("Job %s completed with status %s", job_id, final_status.value)
                return True
            else:
                # Job failed
                error = result.get("error", {"message": "Unknown error"})
                is_transient = result.get("is_transient", True)
                fail_job(job_id, self.worker_id, error, is_transient)
                logger.warning("Job %s failed: %s", job_id, error)
                return False
                
        except Exception as e:
            logger.exception("Job %s raised exception", job_id)
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
        }
        return job_type in lock_required_types


def run_worker():
    """Entry point for running the worker."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    worker = CatalogWorker()
    worker.start()


def run_watchdog():
    """Entry point for running watchdog as a scheduled task."""
    from app.jobs.watchdog import run_watchdog as _run_watchdog
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # Run in non-dry-run mode for actual cleanup
    dry_run = os.getenv("WATCHDOG_DRY_RUN", "true").lower() == "true"
    results = _run_watchdog(dry_run=dry_run)
    
    logger.info("Watchdog complete: %s", results)
    return results


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "watchdog":
        run_watchdog()
    else:
        run_worker()
