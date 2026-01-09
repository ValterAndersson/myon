"""
Change Journal - Durable record of all catalog mutations.

Uses catalog_changes/{changeId} collection to store:
- job_id, attempt_id
- operations with before/after snapshots
- timestamps, rationale
- idempotency keys

This enables audit trail and potential rollback.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from google.cloud import firestore

logger = logging.getLogger(__name__)

# Collection name
CHANGES_COLLECTION = "catalog_changes"

# Initialize Firestore client lazily
_db: Optional[firestore.Client] = None


def _get_db() -> firestore.Client:
    """Get or initialize Firestore client."""
    global _db
    if _db is None:
        _db = firestore.Client()
    return _db


class ChangeJournal:
    """
    Journal for recording catalog changes.
    
    Each journal entry represents a set of operations from a job attempt.
    """
    
    def __init__(self, job_id: str, attempt_id: Optional[str] = None):
        """
        Initialize journal for a job.
        
        Args:
            job_id: Job ID
            attempt_id: Attempt ID (auto-generated if not provided)
        """
        self.job_id = job_id
        self.attempt_id = attempt_id or str(uuid.uuid4())[:8]
        self.db = _get_db()
        self.operations: List[Dict[str, Any]] = []
        self.started_at = datetime.utcnow()
    
    def record_operation(
        self,
        operation_index: int,
        operation_type: str,
        targets: List[str],
        before: Optional[Dict[str, Any]] = None,
        after: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
        rationale: str = "",
        success: bool = True,
        error: Optional[str] = None,
    ) -> None:
        """
        Record a single operation in the journal.
        
        Args:
            operation_index: Index in the plan
            operation_type: Type of operation
            targets: Affected doc_ids
            before: Snapshot before mutation
            after: State after mutation
            idempotency_key: Key for idempotency
            rationale: Reason for operation
            success: Whether operation succeeded
            error: Error message if failed
        """
        self.operations.append({
            "operation_index": operation_index,
            "operation_type": operation_type,
            "targets": targets,
            "before": before,
            "after": after,
            "idempotency_key": idempotency_key,
            "rationale": rationale,
            "success": success,
            "error": error,
            "executed_at": datetime.utcnow(),
        })
    
    def save(self, result_summary: Optional[str] = None) -> str:
        """
        Save the journal entry to Firestore.
        
        Args:
            result_summary: Summary of the overall result
            
        Returns:
            Change ID
        """
        change_id = f"{self.job_id}_{self.attempt_id}"
        doc_ref = self.db.collection(CHANGES_COLLECTION).document(change_id)
        
        data = {
            "change_id": change_id,
            "job_id": self.job_id,
            "attempt_id": self.attempt_id,
            "operations": self.operations,
            "operation_count": len(self.operations),
            "successful_count": sum(1 for op in self.operations if op.get("success")),
            "failed_count": sum(1 for op in self.operations if not op.get("success")),
            "started_at": self.started_at,
            "completed_at": datetime.utcnow(),
            "result_summary": result_summary,
        }
        
        doc_ref.set(data)
        logger.info("Saved journal entry: %s with %d operations", change_id, len(self.operations))
        
        return change_id
    
    def get_targets(self) -> List[str]:
        """Get all unique targets from operations."""
        targets = set()
        for op in self.operations:
            targets.update(op.get("targets", []))
        return list(targets)


def record_change(
    job_id: str,
    operation_index: int,
    operation_type: str,
    targets: List[str],
    before: Optional[Dict[str, Any]] = None,
    after: Optional[Dict[str, Any]] = None,
    idempotency_key: Optional[str] = None,
    rationale: str = "",
) -> str:
    """
    Record a single change directly.
    
    Creates a journal entry for a single operation.
    For batch operations, use ChangeJournal class.
    
    Returns:
        Change ID
    """
    journal = ChangeJournal(job_id)
    journal.record_operation(
        operation_index=operation_index,
        operation_type=operation_type,
        targets=targets,
        before=before,
        after=after,
        idempotency_key=idempotency_key,
        rationale=rationale,
    )
    return journal.save()


def get_job_changes(job_id: str) -> List[Dict[str, Any]]:
    """
    Get all journal entries for a job.
    
    Args:
        job_id: Job ID
        
    Returns:
        List of journal entries
    """
    db = _get_db()
    query = (
        db.collection(CHANGES_COLLECTION)
        .where("job_id", "==", job_id)
        .order_by("started_at")
    )
    
    return [doc.to_dict() for doc in query.stream()]


def get_target_history(doc_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Get change history for a specific document.
    
    Args:
        doc_id: Document ID to search for
        limit: Maximum entries to return
        
    Returns:
        List of changes affecting this document
    """
    db = _get_db()
    
    # Note: Firestore doesn't support array-contains on nested arrays
    # This is a simplified implementation; for production, consider
    # denormalizing target tracking
    query = (
        db.collection(CHANGES_COLLECTION)
        .order_by("completed_at", direction=firestore.Query.DESCENDING)
        .limit(limit * 5)  # Over-fetch since we filter client-side
    )
    
    results = []
    for doc in query.stream():
        data = doc.to_dict()
        for op in data.get("operations", []):
            if doc_id in op.get("targets", []):
                results.append({
                    "change_id": data.get("change_id"),
                    "job_id": data.get("job_id"),
                    "operation": op,
                    "completed_at": data.get("completed_at"),
                })
                break
        
        if len(results) >= limit:
            break
    
    return results


__all__ = [
    "ChangeJournal",
    "record_change",
    "get_job_changes",
    "get_target_history",
]
