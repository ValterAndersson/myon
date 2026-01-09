"""
Leasing - Job lease, family lock, and heartbeat management.

Phase 0: Interface stubs with no-op implementations.
Phase 1: Full Firestore-backed implementations with:
- Transactional lease/lock acquisition
- Conditional heartbeat renewal (check ownership)
- Lease/lock expiry with margin-based renewal

Key invariants:
- Lease renewal only if still owned by this worker
- Lock renewal only if job_id and worker_id match
- Watchdog uses lease_expires_at as single source of truth
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


class LeaseHeartbeat:
    """
    Periodically renews job lease and family lock during execution.
    
    Phase 0: No-op implementation (interfaces only).
    Phase 1: Background thread renews leases with conditional updates.
    
    Key behaviors:
    - Renews only if lease expires in < 2 minutes (margin-based)
    - Checks ownership before renewal (prevents race conditions)
    - Stops cleanly when job completes
    """
    
    def __init__(
        self,
        job_id: str,
        worker_id: str,
        family_slug: Optional[str] = None,
        interval_secs: int = 60,
    ):
        """
        Initialize heartbeat.
        
        Args:
            job_id: Job being processed
            worker_id: Worker processing the job
            family_slug: Family being locked (if any)
            interval_secs: How often to check/renew (default 60s)
        """
        self.job_id = job_id
        self.worker_id = worker_id
        self.family_slug = family_slug
        self.interval = interval_secs
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._running = False
    
    def start(self) -> None:
        """Start the heartbeat thread."""
        if self._running:
            return
        
        self._stop.clear()
        self._thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._thread.start()
        self._running = True
        logger.debug("Heartbeat started for job %s", self.job_id)
    
    def stop(self) -> None:
        """Stop the heartbeat thread."""
        if not self._running:
            return
        
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        self._running = False
        logger.debug("Heartbeat stopped for job %s", self.job_id)
    
    def _heartbeat_loop(self) -> None:
        """Background loop that renews leases periodically."""
        while not self._stop.wait(self.interval):
            try:
                self._maybe_renew_lease()
                if self.family_slug:
                    self._maybe_renew_lock()
            except Exception as e:
                logger.warning("Heartbeat renewal failed: %s", e)
    
    def _maybe_renew_lease(self) -> bool:
        """
        Renew job lease if expiring soon and still owned.
        
        Phase 0: No-op, returns True.
        Phase 1: Transactional conditional update.
        """
        # Phase 0: No-op
        logger.debug("Heartbeat: would renew lease for job %s", self.job_id)
        return True
    
    def _maybe_renew_lock(self) -> bool:
        """
        Renew family lock if expiring soon and still owned.
        
        Phase 0: No-op, returns True.
        Phase 1: Transactional conditional update.
        """
        # Phase 0: No-op
        logger.debug("Heartbeat: would renew lock for family %s", self.family_slug)
        return True


class FamilyLock:
    """
    Exclusive lock on a family for mutation operations.
    
    Phase 0: No-op implementation (always succeeds).
    Phase 1: Firestore-backed with transactional acquisition.
    
    Key behaviors:
    - Atomic acquire: either create or take over expired lock
    - Only one job can hold lock at a time
    - Expired locks can be taken over
    """
    
    def __init__(self, family_slug: str, job_id: str, worker_id: str):
        """
        Initialize family lock.
        
        Args:
            family_slug: Family to lock
            job_id: Job that needs the lock
            worker_id: Worker acquiring the lock
        """
        self.family_slug = family_slug
        self.job_id = job_id
        self.worker_id = worker_id
        self._acquired = False
    
    def acquire(self) -> bool:
        """
        Atomically acquire the family lock.
        
        Phase 0: No-op, always returns True.
        Phase 1: Transactional Firestore create-or-takeover.
        
        Returns:
            True if lock acquired, False if held by another active job
        """
        # Phase 0: No-op
        logger.debug("FamilyLock: would acquire lock for %s (job %s)", 
                    self.family_slug, self.job_id)
        self._acquired = True
        return True
    
    def release(self) -> None:
        """
        Release the family lock.
        
        Phase 0: No-op.
        Phase 1: Delete lock document if still owned.
        """
        # Phase 0: No-op
        if self._acquired:
            logger.debug("FamilyLock: would release lock for %s", self.family_slug)
            self._acquired = False
    
    def renew(self) -> bool:
        """
        Extend lock expiry if still owned.
        
        Phase 0: No-op, returns True.
        Phase 1: Conditional update checking ownership.
        
        Returns:
            True if renewed, False if lock lost
        """
        # Phase 0: No-op
        if self._acquired:
            logger.debug("FamilyLock: would renew lock for %s", self.family_slug)
            return True
        return False
    
    @property
    def is_acquired(self) -> bool:
        """Check if lock is currently held."""
        return self._acquired


class JobLease:
    """
    Job lease management for worker ownership.
    
    Phase 0: No-op implementation (always succeeds).
    Phase 1: Firestore-backed with transactional acquisition.
    
    Key behaviors:
    - Atomic lease: check status + run_after + existing lease in one txn
    - Updates status to 'leased' on acquire
    - Updates status to 'running' when execution starts
    - Conditional renewal checks ownership
    """
    
    def __init__(self, job_id: str, worker_id: str, lease_duration_secs: int = 300):
        """
        Initialize job lease.
        
        Args:
            job_id: Job to lease
            worker_id: Worker acquiring the lease
            lease_duration_secs: Lease duration (default 5 minutes)
        """
        self.job_id = job_id
        self.worker_id = worker_id
        self.lease_duration = timedelta(seconds=lease_duration_secs)
        self._acquired = False
        self._expires_at: Optional[datetime] = None
    
    def acquire(self) -> bool:
        """
        Atomically acquire the job lease.
        
        Phase 0: No-op, always returns True.
        Phase 1: Transactional Firestore update:
        - Check status in ["queued"]
        - Check run_after <= now
        - Check lease_expires_at is None or expired
        - Set lease_owner, lease_expires_at, status='leased'
        
        Returns:
            True if lease acquired, False otherwise
        """
        # Phase 0: No-op
        logger.debug("JobLease: would acquire lease for job %s", self.job_id)
        self._acquired = True
        self._expires_at = datetime.utcnow() + self.lease_duration
        return True
    
    def renew(self) -> bool:
        """
        Extend lease if still owned and expiring soon.
        
        Phase 0: No-op, returns True.
        Phase 1: Conditional update:
        - Only renew if lease_expires_at < now + 2 minutes (margin)
        - Only renew if lease_owner == this worker
        - Only renew if status in ['leased', 'running']
        
        Returns:
            True if renewed, False if lease lost or not expiring soon
        """
        # Phase 0: No-op
        if self._acquired:
            logger.debug("JobLease: would renew lease for job %s", self.job_id)
            self._expires_at = datetime.utcnow() + self.lease_duration
            return True
        return False
    
    def mark_running(self) -> bool:
        """
        Transition job status from 'leased' to 'running'.
        
        Phase 0: No-op, returns True.
        Phase 1: Conditional update checking ownership.
        
        Returns:
            True if transitioned, False if lease lost
        """
        # Phase 0: No-op
        if self._acquired:
            logger.debug("JobLease: would mark job %s as running", self.job_id)
            return True
        return False
    
    def release(self, final_status: str = "succeeded") -> None:
        """
        Release the lease and set final status.
        
        Phase 0: No-op.
        Phase 1: Update job with final status, clear lease fields.
        
        Args:
            final_status: Status to set (succeeded, failed, needs_review, etc.)
        """
        # Phase 0: No-op
        if self._acquired:
            logger.debug("JobLease: would release lease for job %s with status %s",
                        self.job_id, final_status)
            self._acquired = False
            self._expires_at = None
    
    @property
    def is_acquired(self) -> bool:
        """Check if lease is currently held."""
        return self._acquired
    
    @property
    def expires_at(self) -> Optional[datetime]:
        """Get lease expiration time."""
        return self._expires_at


__all__ = [
    "LeaseHeartbeat",
    "FamilyLock",
    "JobLease",
]
