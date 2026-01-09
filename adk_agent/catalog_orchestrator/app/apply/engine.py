"""
Apply Engine - Execute Change Plans with idempotency and journaling.

This is the core mutation engine. It:
1. Checks idempotency for each operation
2. Takes before-snapshots
3. Applies mutations atomically
4. Records in journal
5. Verifies post-state

Key rules:
- doc_id is authoritative (Firestore document ID)
- __DELETE__ sentinel maps to firestore.DELETE_FIELD
- All operations are idempotent under retry
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from google.cloud import firestore

from app.plans.models import ChangePlan, Operation, OperationType
from app.apply.idempotency import IdempotencyGuard
from app.apply.journal import ChangeJournal

logger = logging.getLogger(__name__)

# Collections
EXERCISES_COLLECTION = "exercises"
ALIASES_COLLECTION = "exercise_aliases"

# Sentinel for field deletion
DELETE_SENTINEL = "__DELETE__"

# Initialize Firestore client lazily
_db: Optional[firestore.Client] = None


def _get_db() -> firestore.Client:
    """Get or initialize Firestore client."""
    global _db
    if _db is None:
        _db = firestore.Client()
    return _db


@dataclass
class ApplyResult:
    """Result of applying a Change Plan."""
    success: bool
    applied_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    change_id: Optional[str] = None
    errors: List[Dict[str, Any]] = field(default_factory=list)
    operations_applied: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "applied_count": self.applied_count,
            "skipped_count": self.skipped_count,
            "failed_count": self.failed_count,
            "change_id": self.change_id,
            "errors": self.errors,
            "operations_applied": self.operations_applied,
        }


class ApplyEngine:
    """
    Engine for applying Change Plans.
    
    Uses idempotency guard and journaling for safe execution.
    """
    
    def __init__(self, job_id: str, attempt_id: Optional[str] = None):
        """
        Initialize engine for a job.
        
        Args:
            job_id: Job ID
            attempt_id: Attempt ID
        """
        self.job_id = job_id
        self.db = _get_db()
        self.idempotency = IdempotencyGuard(job_id)
        self.journal = ChangeJournal(job_id, attempt_id)
    
    def apply(self, plan: ChangePlan) -> ApplyResult:
        """
        Apply a Change Plan.
        
        Args:
            plan: Validated Change Plan
            
        Returns:
            ApplyResult with counts and errors
        """
        logger.info("Applying plan: job=%s, operations=%d", 
                   self.job_id, len(plan.operations))
        
        result = ApplyResult(success=True)
        
        for idx, operation in enumerate(plan.operations):
            if operation.op_type == OperationType.NO_CHANGE:
                result.skipped_count += 1
                continue
            
            try:
                op_result = self._apply_operation(idx, operation)
                
                if op_result.get("skipped"):
                    result.skipped_count += 1
                elif op_result.get("success"):
                    result.applied_count += 1
                    result.operations_applied.append({
                        "index": idx,
                        "op_type": operation.op_type.value,
                        "targets": operation.targets,
                    })
                else:
                    result.failed_count += 1
                    result.errors.append(op_result.get("error", {}))
                    
            except Exception as e:
                logger.exception("Operation %d failed: %s", idx, e)
                result.failed_count += 1
                result.errors.append({
                    "operation_index": idx,
                    "error": str(e),
                    "type": type(e).__name__,
                })
        
        # Save journal
        result.change_id = self.journal.save(
            result_summary=f"Applied {result.applied_count}, skipped {result.skipped_count}, failed {result.failed_count}"
        )
        
        result.success = result.failed_count == 0
        return result
    
    def _apply_operation(self, idx: int, operation: Operation) -> Dict[str, Any]:
        """
        Apply a single operation.
        
        Args:
            idx: Operation index
            operation: Operation to apply
            
        Returns:
            Result dict with success/skipped/error
        """
        # Check idempotency
        idempotency_seed = operation.idempotency_key_seed or f"op_{idx}"
        should_execute, key = self.idempotency.check_and_record(
            idempotency_seed, idx, operation.op_type.value, operation.targets
        )
        
        if not should_execute:
            logger.info("Skipping operation %d (already executed)", idx)
            return {"skipped": True, "reason": "idempotency"}
        
        # Dispatch to handler
        handlers = {
            OperationType.RENAME_EXERCISE: self._apply_rename_exercise,
            OperationType.PATCH_FIELDS: self._apply_patch_fields,
            OperationType.UPSERT_ALIAS: self._apply_upsert_alias,
            OperationType.DELETE_ALIAS: self._apply_delete_alias,
            OperationType.CREATE_EXERCISE: self._apply_create_exercise,
            OperationType.DEPRECATE_EXERCISE: self._apply_deprecate_exercise,
            OperationType.REASSIGN_FAMILY: self._apply_reassign_family,
            OperationType.UPDATE_FAMILY_REGISTRY: self._apply_update_registry,
        }
        
        handler = handlers.get(operation.op_type)
        if not handler:
            return {
                "success": False,
                "error": {"code": "UNSUPPORTED_OP", "message": f"No handler for {operation.op_type}"},
            }
        
        result = handler(idx, operation)
        
        # Record idempotency
        self.idempotency.record_execution(
            key, operation.op_type.value, operation.targets,
            result="success" if result.get("success") else "failed"
        )
        
        return result
    
    def _apply_rename_exercise(self, idx: int, op: Operation) -> Dict[str, Any]:
        """Apply RENAME_EXERCISE operation."""
        if not op.targets or not op.after:
            return {"success": False, "error": {"code": "INVALID_OP", "message": "Missing targets or after"}}
        
        doc_id = op.targets[0]
        doc_ref = self.db.collection(EXERCISES_COLLECTION).document(doc_id)
        
        # Get before snapshot
        before_doc = doc_ref.get()
        if not before_doc.exists:
            return {"success": False, "error": {"code": "DOC_NOT_FOUND", "message": f"Exercise {doc_id} not found"}}
        
        before_data = before_doc.to_dict()
        
        # Build update
        update = {
            "name": op.after.get("name"),
            "name_slug": op.after.get("name_slug"),
            "updated_at": datetime.utcnow(),
        }
        
        # Apply update
        doc_ref.update(update)
        
        # Record in journal
        self.journal.record_operation(
            operation_index=idx,
            operation_type=op.op_type.value,
            targets=[doc_id],
            before={"name": before_data.get("name"), "name_slug": before_data.get("name_slug")},
            after=update,
            idempotency_key=op.idempotency_key_seed,
            rationale=op.rationale,
        )
        
        logger.info("Renamed exercise %s: %s → %s", doc_id, before_data.get("name"), op.after.get("name"))
        return {"success": True}
    
    def _apply_patch_fields(self, idx: int, op: Operation) -> Dict[str, Any]:
        """Apply PATCH_FIELDS operation."""
        if not op.targets or not op.patch:
            return {"success": False, "error": {"code": "INVALID_OP", "message": "Missing targets or patch"}}
        
        doc_id = op.targets[0]
        doc_ref = self.db.collection(EXERCISES_COLLECTION).document(doc_id)
        
        # Get before snapshot
        before_doc = doc_ref.get()
        if not before_doc.exists:
            return {"success": False, "error": {"code": "DOC_NOT_FOUND", "message": f"Exercise {doc_id} not found"}}
        
        before_data = before_doc.to_dict()
        
        # Build update, handling DELETE_SENTINEL
        update = {}
        for field, value in op.patch.items():
            if value == DELETE_SENTINEL:
                update[field] = firestore.DELETE_FIELD
            else:
                update[field] = value
        
        update["updated_at"] = datetime.utcnow()
        
        # Apply update
        doc_ref.update(update)
        
        # Record in journal
        self.journal.record_operation(
            operation_index=idx,
            operation_type=op.op_type.value,
            targets=[doc_id],
            before={k: before_data.get(k) for k in op.patch.keys()},
            after=op.patch,
            idempotency_key=op.idempotency_key_seed,
            rationale=op.rationale,
        )
        
        logger.info("Patched exercise %s: %d fields", doc_id, len(op.patch))
        return {"success": True}
    
    def _apply_upsert_alias(self, idx: int, op: Operation) -> Dict[str, Any]:
        """Apply UPSERT_ALIAS operation."""
        if not op.targets or not op.patch:
            return {"success": False, "error": {"code": "INVALID_OP", "message": "Missing targets or patch"}}
        
        alias_slug = op.targets[0]
        doc_ref = self.db.collection(ALIASES_COLLECTION).document(alias_slug)
        
        # Get before snapshot
        before_doc = doc_ref.get()
        before_data = before_doc.to_dict() if before_doc.exists else None
        
        # Build alias document
        alias_data = {
            "alias_slug": alias_slug,
            "exercise_id": op.patch.get("exercise_id"),
            "family_slug": op.patch.get("family_slug"),
            "updated_at": datetime.utcnow(),
        }
        
        if not before_doc.exists:
            alias_data["created_at"] = datetime.utcnow()
        
        # Apply upsert
        doc_ref.set(alias_data, merge=True)
        
        # Record in journal
        self.journal.record_operation(
            operation_index=idx,
            operation_type=op.op_type.value,
            targets=[alias_slug],
            before=before_data,
            after=alias_data,
            idempotency_key=op.idempotency_key_seed,
            rationale=op.rationale,
        )
        
        logger.info("Upserted alias %s → %s", alias_slug, op.patch.get("exercise_id"))
        return {"success": True}
    
    def _apply_delete_alias(self, idx: int, op: Operation) -> Dict[str, Any]:
        """Apply DELETE_ALIAS operation."""
        if not op.targets:
            return {"success": False, "error": {"code": "INVALID_OP", "message": "Missing targets"}}
        
        alias_slug = op.targets[0]
        doc_ref = self.db.collection(ALIASES_COLLECTION).document(alias_slug)
        
        # Get before snapshot
        before_doc = doc_ref.get()
        before_data = before_doc.to_dict() if before_doc.exists else None
        
        if not before_doc.exists:
            logger.warning("Alias %s not found for deletion", alias_slug)
            return {"success": True}  # Idempotent: already deleted
        
        # Delete
        doc_ref.delete()
        
        # Record in journal
        self.journal.record_operation(
            operation_index=idx,
            operation_type=op.op_type.value,
            targets=[alias_slug],
            before=before_data,
            after=None,
            idempotency_key=op.idempotency_key_seed,
            rationale=op.rationale,
        )
        
        logger.info("Deleted alias %s", alias_slug)
        return {"success": True}
    
    def _apply_create_exercise(self, idx: int, op: Operation) -> Dict[str, Any]:
        """Apply CREATE_EXERCISE operation."""
        if not op.patch:
            return {"success": False, "error": {"code": "INVALID_OP", "message": "Missing patch"}}
        
        # Generate doc ID if not provided
        doc_id = op.targets[0] if op.targets else None
        
        if doc_id:
            doc_ref = self.db.collection(EXERCISES_COLLECTION).document(doc_id)
        else:
            doc_ref = self.db.collection(EXERCISES_COLLECTION).document()
            doc_id = doc_ref.id
        
        # Check if already exists
        existing = doc_ref.get()
        if existing.exists:
            logger.warning("Exercise %s already exists", doc_id)
            return {"success": True}  # Idempotent
        
        # Build exercise document
        exercise_data = dict(op.patch)
        exercise_data["created_at"] = datetime.utcnow()
        exercise_data["updated_at"] = datetime.utcnow()
        exercise_data["status"] = exercise_data.get("status", "approved")
        
        # Create
        doc_ref.set(exercise_data)
        
        # Record in journal
        self.journal.record_operation(
            operation_index=idx,
            operation_type=op.op_type.value,
            targets=[doc_id],
            before=None,
            after=exercise_data,
            idempotency_key=op.idempotency_key_seed,
            rationale=op.rationale,
        )
        
        logger.info("Created exercise %s: %s", doc_id, exercise_data.get("name"))
        return {"success": True, "doc_id": doc_id}
    
    def _apply_deprecate_exercise(self, idx: int, op: Operation) -> Dict[str, Any]:
        """Apply DEPRECATE_EXERCISE operation."""
        if not op.targets:
            return {"success": False, "error": {"code": "INVALID_OP", "message": "Missing targets"}}
        
        doc_id = op.targets[0]
        doc_ref = self.db.collection(EXERCISES_COLLECTION).document(doc_id)
        
        # Get before snapshot
        before_doc = doc_ref.get()
        if not before_doc.exists:
            return {"success": False, "error": {"code": "DOC_NOT_FOUND", "message": f"Exercise {doc_id} not found"}}
        
        before_data = before_doc.to_dict()
        
        # Update status
        update = {
            "status": "deprecated",
            "deprecated_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        
        doc_ref.update(update)
        
        # Record in journal
        self.journal.record_operation(
            operation_index=idx,
            operation_type=op.op_type.value,
            targets=[doc_id],
            before={"status": before_data.get("status")},
            after=update,
            idempotency_key=op.idempotency_key_seed,
            rationale=op.rationale,
        )
        
        logger.info("Deprecated exercise %s", doc_id)
        return {"success": True}
    
    def _apply_reassign_family(self, idx: int, op: Operation) -> Dict[str, Any]:
        """Apply REASSIGN_FAMILY operation."""
        if not op.targets or not op.patch:
            return {"success": False, "error": {"code": "INVALID_OP", "message": "Missing targets or patch"}}
        
        new_family_slug = op.patch.get("family_slug")
        if not new_family_slug:
            return {"success": False, "error": {"code": "INVALID_OP", "message": "Missing family_slug in patch"}}
        
        for doc_id in op.targets:
            doc_ref = self.db.collection(EXERCISES_COLLECTION).document(doc_id)
            doc_ref.update({
                "family_slug": new_family_slug,
                "updated_at": datetime.utcnow(),
            })
        
        # Record in journal
        self.journal.record_operation(
            operation_index=idx,
            operation_type=op.op_type.value,
            targets=op.targets,
            before=None,
            after={"family_slug": new_family_slug},
            idempotency_key=op.idempotency_key_seed,
            rationale=op.rationale,
        )
        
        logger.info("Reassigned %d exercises to family %s", len(op.targets), new_family_slug)
        return {"success": True}
    
    def _apply_update_registry(self, idx: int, op: Operation) -> Dict[str, Any]:
        """Apply UPDATE_FAMILY_REGISTRY operation."""
        from app.family.registry import upsert_family_registry, FamilyRegistry
        
        if not op.targets or not op.patch:
            return {"success": False, "error": {"code": "INVALID_OP", "message": "Missing targets or patch"}}
        
        family_slug = op.targets[0]
        
        # Build registry from patch
        registry = FamilyRegistry(
            family_slug=family_slug,
            base_name=op.patch.get("base_name", family_slug),
            **{k: v for k, v in op.patch.items() if k not in ["family_slug", "base_name"]}
        )
        
        upsert_family_registry(registry)
        
        # Record in journal
        self.journal.record_operation(
            operation_index=idx,
            operation_type=op.op_type.value,
            targets=[family_slug],
            before=None,
            after=op.patch,
            idempotency_key=op.idempotency_key_seed,
            rationale=op.rationale,
        )
        
        logger.info("Updated family registry %s", family_slug)
        return {"success": True}
    
    def apply_with_verify(self, plan: ChangePlan) -> ApplyResult:
        """
        Apply a Change Plan and verify post-state.
        
        Args:
            plan: Validated Change Plan
            
        Returns:
            ApplyResult with verification status
        """
        result = self.apply(plan)
        
        if result.success:
            result = verify_post_state(self, plan, result)
        
        return result


def apply_change_plan(
    plan: ChangePlan,
    job_id: Optional[str] = None,
    attempt_id: Optional[str] = None,
    verify: bool = False,
) -> ApplyResult:
    """
    Apply a Change Plan.
    
    Convenience function.
    
    Args:
        plan: Validated Change Plan
        job_id: Job ID (defaults to plan.job_id)
        attempt_id: Attempt ID
        verify: If True, run post-verification after apply
        
    Returns:
        ApplyResult
    """
    job_id = job_id or plan.job_id
    engine = ApplyEngine(job_id, attempt_id)
    
    if verify:
        return engine.apply_with_verify(plan)
    return engine.apply(plan)


def verify_post_state(
    engine: ApplyEngine,
    plan: ChangePlan,
    result: ApplyResult,
) -> ApplyResult:
    """
    Verify post-state after apply.
    
    Re-fetches affected documents and runs validation.
    
    Args:
        engine: ApplyEngine instance
        plan: Original change plan
        result: Apply result to enhance
        
    Returns:
        ApplyResult with verification status
    """
    from app.plans.models import ValidationResult
    
    if not result.success:
        return result
    
    # Re-fetch affected documents
    affected_doc_ids = set()
    for op in result.operations_applied:
        affected_doc_ids.update(op.get("targets", []))
    
    if not affected_doc_ids:
        result.verification_passed = True
        return result
    
    # Fetch current state
    post_state = {}
    for doc_id in affected_doc_ids:
        doc_ref = engine.db.collection(EXERCISES_COLLECTION).document(doc_id)
        doc = doc_ref.get()
        if doc.exists:
            post_state[doc_id] = doc.to_dict()
    
    # Verify expected fields exist
    verification_errors = []
    
    for idx, op in enumerate(plan.operations):
        if op.op_type == OperationType.RENAME_EXERCISE and op.after:
            for doc_id in op.targets:
                current = post_state.get(doc_id, {})
                expected_name = op.after.get("name")
                if current.get("name") != expected_name:
                    verification_errors.append({
                        "operation_index": idx,
                        "doc_id": doc_id,
                        "error": f"Name mismatch: expected '{expected_name}', got '{current.get('name')}'",
                    })
        
        elif op.op_type == OperationType.PATCH_FIELDS and op.patch:
            for doc_id in op.targets:
                current = post_state.get(doc_id, {})
                for field, expected in op.patch.items():
                    if expected == "__DELETE__":
                        if field in current:
                            verification_errors.append({
                                "operation_index": idx,
                                "doc_id": doc_id,
                                "error": f"Field '{field}' should have been deleted",
                            })
                    elif current.get(field) != expected:
                        verification_errors.append({
                            "operation_index": idx,
                            "doc_id": doc_id,
                            "error": f"Field '{field}' mismatch: expected '{expected}', got '{current.get(field)}'",
                        })
    
    result.verification_passed = len(verification_errors) == 0
    result.verification_errors = verification_errors
    
    if not result.verification_passed:
        result.needs_repair = True
        logger.warning("Post-verify failed with %d errors", len(verification_errors))
    
    return result


__all__ = [
    "ApplyEngine",
    "apply_change_plan",
    "ApplyResult",
    "DELETE_SENTINEL",
]
