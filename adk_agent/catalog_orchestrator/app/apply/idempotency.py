"""
Idempotency Guard - Prevent duplicate operation execution.

Uses catalog_idempotency/{key} collection to track completed operations.
Operations with matching idempotency keys are skipped.

Key format: {job_id}:{operation_index}:{content_hash}
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from google.cloud import firestore

logger = logging.getLogger(__name__)

# Collection name
IDEMPOTENCY_COLLECTION = "catalog_idempotency"

# TTL for idempotency records (7 days)
IDEMPOTENCY_TTL_DAYS = 7

# Initialize Firestore client lazily
_db: Optional[firestore.Client] = None


def _get_db() -> firestore.Client:
    """Get or initialize Firestore client."""
    global _db
    if _db is None:
        _db = firestore.Client()
    return _db


class IdempotencyGuard:
    """
    Guard against duplicate operation execution.
    
    Uses Firestore collection to track completed operations.
    """
    
    def __init__(self, job_id: str):
        """
        Initialize guard for a job.
        
        Args:
            job_id: Job ID for scoping
        """
        self.job_id = job_id
        self.db = _get_db()
        self._checked: Dict[str, bool] = {}
    
    def compute_key(self, idempotency_seed: str, operation_index: int) -> str:
        """
        Compute the full idempotency key.
        
        Args:
            idempotency_seed: Seed from operation
            operation_index: Index in plan
            
        Returns:
            Full idempotency key
        """
        return f"{self.job_id}:{operation_index}:{idempotency_seed}"
    
    def is_executed(self, key: str) -> bool:
        """
        Check if operation was already executed.
        
        Args:
            key: Idempotency key
            
        Returns:
            True if already executed
        """
        if key in self._checked:
            return self._checked[key]
        
        doc_ref = self.db.collection(IDEMPOTENCY_COLLECTION).document(key)
        doc = doc_ref.get()
        
        result = doc.exists
        self._checked[key] = result
        
        if result:
            logger.info("Idempotency hit: %s already executed", key)
        
        return result
    
    def record_execution(
        self,
        key: str,
        operation_type: str,
        targets: list,
        result: str = "success",
    ) -> bool:
        """
        Record that an operation was executed.
        
        Args:
            key: Idempotency key
            operation_type: Type of operation
            targets: Affected targets
            result: Execution result
            
        Returns:
            True if recorded successfully
        """
        doc_ref = self.db.collection(IDEMPOTENCY_COLLECTION).document(key)
        
        data = {
            "job_id": self.job_id,
            "key": key,
            "operation_type": operation_type,
            "targets": targets,
            "result": result,
            "executed_at": datetime.utcnow(),
            "expires_at": datetime.utcnow() + timedelta(days=IDEMPOTENCY_TTL_DAYS),
        }
        
        doc_ref.set(data)
        self._checked[key] = True
        
        logger.debug("Recorded idempotency: %s", key)
        return True
    
    def check_and_record(
        self,
        idempotency_seed: str,
        operation_index: int,
        operation_type: str,
        targets: list,
    ) -> tuple[bool, str]:
        """
        Check if operation is executable and record intent.
        
        Returns:
            Tuple of (should_execute, key)
        """
        key = self.compute_key(idempotency_seed, operation_index)
        
        if self.is_executed(key):
            return False, key
        
        return True, key


def check_idempotency(job_id: str, idempotency_seed: str, operation_index: int) -> bool:
    """
    Check if operation was already executed.
    
    Convenience function for simple checks.
    
    Args:
        job_id: Job ID
        idempotency_seed: Seed from operation
        operation_index: Index in plan
        
    Returns:
        True if NOT executed (should proceed)
    """
    guard = IdempotencyGuard(job_id)
    key = guard.compute_key(idempotency_seed, operation_index)
    return not guard.is_executed(key)


def record_operation(
    job_id: str,
    idempotency_seed: str,
    operation_index: int,
    operation_type: str,
    targets: list,
    result: str = "success",
) -> bool:
    """
    Record that an operation was executed.
    
    Convenience function.
    
    Args:
        job_id: Job ID
        idempotency_seed: Seed from operation
        operation_index: Index in plan
        operation_type: Type of operation
        targets: Affected targets
        result: Execution result
        
    Returns:
        True if recorded
    """
    guard = IdempotencyGuard(job_id)
    key = guard.compute_key(idempotency_seed, operation_index)
    return guard.record_execution(key, operation_type, targets, result)


def cleanup_expired_idempotency_records(batch_size: int = 100) -> int:
    """
    Clean up expired idempotency records.
    
    Called by watchdog.
    
    Args:
        batch_size: Maximum records to delete
        
    Returns:
        Number of records deleted
    """
    db = _get_db()
    now = datetime.utcnow()
    
    query = (
        db.collection(IDEMPOTENCY_COLLECTION)
        .where("expires_at", "<", now)
        .limit(batch_size)
    )
    
    deleted = 0
    for doc in query.stream():
        doc.reference.delete()
        deleted += 1
    
    if deleted > 0:
        logger.info("Cleaned up %d expired idempotency records", deleted)
    
    return deleted


__all__ = [
    "IdempotencyGuard",
    "check_idempotency",
    "record_operation",
    "cleanup_expired_idempotency_records",
]
