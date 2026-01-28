"""
Apply Engine - Execute Change Plans with idempotency and journaling.

This is the core mutation engine. It:
1. Enforces apply gate (mode + env var)
2. Validates patch paths against allowlist
3. Checks idempotency for each operation
4. Takes before-snapshots
5. Applies mutations with dotted Firestore paths
6. Records in journal
7. Verifies post-state

Key rules:
- Apply gate is enforced HERE, not by callers
- Mode controls intent, env var controls capability
- doc_id is authoritative (Firestore document ID)
- Create uses deterministic IDs: {family_slug}__{name_slug}
- __DELETE__ sentinel maps to firestore.DELETE_FIELD
- All operations are idempotent under retry
- Alias docs must have exactly one of exercise_id XOR family_slug
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from google.cloud import firestore
try:
    from google.cloud.exceptions import AlreadyExists
except ImportError:
    # Fallback for different google-cloud-core versions
    from google.api_core.exceptions import AlreadyExists

from app.plans.models import ChangePlan, Operation, OperationType
from app.apply.idempotency import IdempotencyGuard
from app.apply.journal import ChangeJournal
from app.apply.gate import ApplyGateError, require_apply_gate, check_apply_gate
from app.apply.paths import (
    DELETE_SENTINEL,
    validate_patch_paths,
    flatten_for_firestore,
    get_in,
)

logger = logging.getLogger(__name__)

# Collections
EXERCISES_COLLECTION = "exercises"
ALIASES_COLLECTION = "exercise_aliases"

# Doc ID format for deterministic creates
# V1.1: Changed from "__" to "-" for cleaner, consistent slugs
DOC_ID_SEPARATOR = "-"
DOC_ID_PATTERN = re.compile(r'^[a-z0-9_-]+$')
DOC_ID_MAX_LENGTH = 128

# Initialize Firestore client lazily
_db: Optional[firestore.Client] = None


def _get_db() -> firestore.Client:
    """Get or initialize Firestore client."""
    global _db
    if _db is None:
        _db = firestore.Client()
    return _db


def derive_deterministic_doc_id(family_slug: str, name_slug: str) -> str:
    """
    Derive deterministic exercise doc ID.
    
    Format: {family_slug}__{name_slug}
    
    Args:
        family_slug: Family slug
        name_slug: Exercise name slug
        
    Returns:
        Deterministic doc ID
    """
    # Normalize slugs
    family = (family_slug or "unknown").lower().replace(" ", "_")
    name = (name_slug or "unknown").lower().replace(" ", "_")
    
    doc_id = f"{family}{DOC_ID_SEPARATOR}{name}"
    
    # Truncate if too long
    if len(doc_id) > DOC_ID_MAX_LENGTH:
        doc_id = doc_id[:DOC_ID_MAX_LENGTH]
    
    return doc_id


@dataclass
class ApplyResult:
    """Result of applying a Change Plan."""
    success: bool
    mode: str = "dry_run"
    applied_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    change_id: Optional[str] = None
    errors: List[Dict[str, Any]] = field(default_factory=list)
    operations_applied: List[Dict[str, Any]] = field(default_factory=list)
    gate_blocked: bool = False
    dry_run_preview: Optional[List[Dict[str, Any]]] = None
    verification_passed: Optional[bool] = None
    verification_errors: Optional[List[Dict[str, Any]]] = None
    needs_repair: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "success": self.success,
            "mode": self.mode,
            "applied_count": self.applied_count,
            "skipped_count": self.skipped_count,
            "failed_count": self.failed_count,
            "change_id": self.change_id,
            "errors": self.errors,
            "operations_applied": self.operations_applied,
            "gate_blocked": self.gate_blocked,
        }
        if self.dry_run_preview is not None:
            result["dry_run_preview"] = self.dry_run_preview
        if self.verification_passed is not None:
            result["verification_passed"] = self.verification_passed
            result["verification_errors"] = self.verification_errors
        if self.needs_repair:
            result["needs_repair"] = True
        return result


class ApplyEngine:
    """
    Engine for applying Change Plans.
    
    Uses idempotency guard and journaling for safe execution.
    The apply gate is enforced HERE, not by callers.
    """
    
    def __init__(
        self,
        job_id: str,
        mode: str = "dry_run",
        attempt_id: Optional[str] = None,
    ):
        """
        Initialize engine for a job.
        
        Args:
            job_id: Job ID
            mode: 'apply' or 'dry_run' (default: dry_run)
            attempt_id: Attempt ID
        """
        self.job_id = job_id
        self.mode = mode
        self.attempt_id = attempt_id
        self.db = _get_db()
        self.idempotency = IdempotencyGuard(job_id)
        self.journal = ChangeJournal(job_id, attempt_id)
    
    def apply(self, plan: ChangePlan) -> ApplyResult:
        """
        Apply a Change Plan.
        
        Gate enforcement:
        - If mode != 'apply': returns dry_run preview
        - If mode == 'apply' but env gate off: raises APPLY_GATE_BLOCKED
        - If mode == 'apply' and env gate on: applies mutations
        
        Args:
            plan: Validated Change Plan
            
        Returns:
            ApplyResult with counts and errors
            
        Raises:
            ApplyGateError: If mode='apply' but env gate is not enabled
        """
        logger.info("ApplyEngine: job=%s, mode=%s, operations=%d",
                   self.job_id, self.mode, len(plan.operations))
        
        # Mode check - dry_run returns preview only
        if self.mode != "apply":
            return self._dry_run(plan)
        
        # Apply mode - check env gate (fail fast, don't silently dry_run)
        if not check_apply_gate():
            raise ApplyGateError(
                "APPLY_GATE_BLOCKED: mode='apply' but CATALOG_APPLY_ENABLED is not set. "
                "Set CATALOG_APPLY_ENABLED=true to enable mutations.",
                gate_type="env_var",
            )
        
        # Validate all patch paths before any writes
        path_errors = self._validate_all_paths(plan)
        if path_errors:
            return ApplyResult(
                success=False,
                mode=self.mode,
                errors=[{"code": "INVALID_PATCH_PATHS", "paths": path_errors}],
            )
        
        # Apply mutations
        result = self._apply_mutations(plan)
        return result
    
    def _dry_run(self, plan: ChangePlan) -> ApplyResult:
        """
        Generate dry-run preview without mutations.
        
        Returns what would happen if applied.
        """
        preview = []
        
        for idx, op in enumerate(plan.operations):
            if op.op_type == OperationType.NO_CHANGE:
                continue
            
            preview.append({
                "index": idx,
                "op_type": op.op_type.value,
                "targets": op.targets,
                "patch": op.patch if op.patch else None,
                "before": op.before,
                "after": op.after,
                "rationale": op.rationale,
            })
        
        return ApplyResult(
            success=True,
            mode="dry_run",
            dry_run_preview=preview,
            skipped_count=len(preview),
        )
    
    def _validate_all_paths(self, plan: ChangePlan) -> List[Dict[str, str]]:
        """Validate all patch paths in plan against allowlist."""
        all_errors = []
        
        for idx, op in enumerate(plan.operations):
            if op.patch:
                errors = validate_patch_paths(op.patch)
                for err in errors:
                    err["operation_index"] = idx
                    all_errors.append(err)
        
        return all_errors
    
    def _apply_mutations(self, plan: ChangePlan) -> ApplyResult:
        """Apply all mutations in the plan."""
        result = ApplyResult(success=True, mode=self.mode)
        
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
                        "doc_id": op_result.get("doc_id"),
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
        """Apply a single operation."""
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
        
        before_doc = doc_ref.get()
        if not before_doc.exists:
            return {"success": False, "error": {"code": "DOC_NOT_FOUND", "message": f"Exercise {doc_id} not found"}}
        
        before_data = before_doc.to_dict()
        
        # Use dotted path update
        update = {
            "name": op.after.get("name"),
            "name_slug": op.after.get("name_slug"),
            "updated_at": datetime.utcnow(),
        }
        
        doc_ref.update(update)
        
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
        """Apply PATCH_FIELDS operation using dotted Firestore paths."""
        if not op.targets or not op.patch:
            return {"success": False, "error": {"code": "INVALID_OP", "message": "Missing targets or patch"}}
        
        doc_id = op.targets[0]
        doc_ref = self.db.collection(EXERCISES_COLLECTION).document(doc_id)
        
        before_doc = doc_ref.get()
        if not before_doc.exists:
            return {"success": False, "error": {"code": "DOC_NOT_FOUND", "message": f"Exercise {doc_id} not found"}}
        
        before_data = before_doc.to_dict()
        
        # Convert patch to Firestore format (dotted paths + DELETE_FIELD)
        update = flatten_for_firestore(op.patch)
        update["updated_at"] = datetime.utcnow()
        
        doc_ref.update(update)
        
        # Record before values for journal
        before_values = {}
        for path in op.patch.keys():
            before_values[path] = get_in(before_data, path)
        
        self.journal.record_operation(
            operation_index=idx,
            operation_type=op.op_type.value,
            targets=[doc_id],
            before=before_values,
            after=op.patch,
            idempotency_key=op.idempotency_key_seed,
            rationale=op.rationale,
        )
        
        logger.info("Patched exercise %s: %d fields", doc_id, len(op.patch))
        return {"success": True}
    
    def _apply_upsert_alias(self, idx: int, op: Operation) -> Dict[str, Any]:
        """
        Apply UPSERT_ALIAS operation.
        
        Enforces one-of invariant: exactly one of exercise_id XOR family_slug.
        """
        if not op.targets or not op.patch:
            return {"success": False, "error": {"code": "INVALID_OP", "message": "Missing targets or patch"}}
        
        alias_slug = op.targets[0]
        exercise_id = op.patch.get("exercise_id")
        family_slug = op.patch.get("family_slug")
        
        # Enforce one-of invariant
        if exercise_id and family_slug:
            return {
                "success": False,
                "error": {
                    "code": "ALIAS_BOTH_FIELDS",
                    "message": f"Alias {alias_slug} cannot have both exercise_id and family_slug",
                },
            }
        if not exercise_id and not family_slug:
            return {
                "success": False,
                "error": {
                    "code": "ALIAS_NO_TARGET",
                    "message": f"Alias {alias_slug} must have exercise_id or family_slug",
                },
            }
        
        doc_ref = self.db.collection(ALIASES_COLLECTION).document(alias_slug)
        before_doc = doc_ref.get()
        before_data = before_doc.to_dict() if before_doc.exists else None
        
        # Build alias document with explicit field clearing
        alias_data = {
            "alias_slug": alias_slug,
            "updated_at": datetime.utcnow(),
        }
        
        if exercise_id:
            alias_data["exercise_id"] = exercise_id
            alias_data["family_slug"] = firestore.DELETE_FIELD  # Clear other field
        else:
            alias_data["family_slug"] = family_slug
            alias_data["exercise_id"] = firestore.DELETE_FIELD  # Clear other field
        
        if not before_doc.exists:
            alias_data["created_at"] = datetime.utcnow()
        
        doc_ref.set(alias_data, merge=True)
        
        self.journal.record_operation(
            operation_index=idx,
            operation_type=op.op_type.value,
            targets=[alias_slug],
            before=before_data,
            after={"exercise_id": exercise_id, "family_slug": family_slug},
            idempotency_key=op.idempotency_key_seed,
            rationale=op.rationale,
        )
        
        target = exercise_id or family_slug
        logger.info("Upserted alias %s → %s", alias_slug, target)
        return {"success": True}
    
    def _apply_delete_alias(self, idx: int, op: Operation) -> Dict[str, Any]:
        """Apply DELETE_ALIAS operation."""
        if not op.targets:
            return {"success": False, "error": {"code": "INVALID_OP", "message": "Missing targets"}}
        
        alias_slug = op.targets[0]
        doc_ref = self.db.collection(ALIASES_COLLECTION).document(alias_slug)
        
        before_doc = doc_ref.get()
        before_data = before_doc.to_dict() if before_doc.exists else None
        
        if not before_doc.exists:
            logger.warning("Alias %s not found for deletion", alias_slug)
            return {"success": True}  # Idempotent
        
        doc_ref.delete()
        
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
        """
        Apply CREATE_EXERCISE operation.
        
        Uses deterministic doc ID for idempotency: {family_slug}__{name_slug}
        Doc ID collision is primary idempotency mechanism.
        """
        if not op.patch:
            return {"success": False, "error": {"code": "INVALID_OP", "message": "Missing patch"}}
        
        # Derive deterministic doc ID
        family_slug = op.patch.get("family_slug", "")
        name_slug = op.patch.get("name_slug", "")
        
        if op.targets:
            doc_id = op.targets[0]
        else:
            doc_id = derive_deterministic_doc_id(family_slug, name_slug)
        
        doc_ref = self.db.collection(EXERCISES_COLLECTION).document(doc_id)
        
        # Build exercise document
        exercise_data = dict(op.patch)
        exercise_data["created_at"] = datetime.utcnow()
        exercise_data["updated_at"] = datetime.utcnow()
        exercise_data["status"] = exercise_data.get("status", "approved")
        
        # Use create() for idempotency - fails if doc exists
        try:
            doc_ref.create(exercise_data)
        except AlreadyExists:
            logger.info("Exercise %s already exists (idempotent create)", doc_id)
            return {"success": True, "skipped": True, "doc_id": doc_id}
        except Exception as e:
            # Check if it's actually an AlreadyExists error
            if "already exists" in str(e).lower():
                logger.info("Exercise %s already exists (idempotent create)", doc_id)
                return {"success": True, "skipped": True, "doc_id": doc_id}
            raise
        
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
        
        before_doc = doc_ref.get()
        if not before_doc.exists:
            return {"success": False, "error": {"code": "DOC_NOT_FOUND", "message": f"Exercise {doc_id} not found"}}
        
        before_data = before_doc.to_dict()
        
        update = {
            "status": "deprecated",
            "deprecated_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        
        doc_ref.update(update)
        
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
        
        registry = FamilyRegistry(
            family_slug=family_slug,
            base_name=op.patch.get("base_name", family_slug),
            **{k: v for k, v in op.patch.items() if k not in ["family_slug", "base_name"]}
        )
        
        upsert_family_registry(registry)
        
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
        """Apply a Change Plan and verify post-state."""
        result = self.apply(plan)
        
        if result.success and result.mode == "apply":
            result = verify_post_state(self, plan, result)
        
        return result


def apply_change_plan(
    plan: ChangePlan,
    mode: str = "dry_run",
    job_id: Optional[str] = None,
    attempt_id: Optional[str] = None,
    verify: bool = False,
) -> ApplyResult:
    """
    Apply a Change Plan.
    
    Convenience function.
    
    Args:
        plan: Validated Change Plan
        mode: 'apply' or 'dry_run'
        job_id: Job ID (defaults to plan.job_id)
        attempt_id: Attempt ID
        verify: If True, run post-verification after apply
        
    Returns:
        ApplyResult
        
    Raises:
        ApplyGateError: If mode='apply' but env gate not enabled
    """
    job_id = job_id or plan.job_id
    engine = ApplyEngine(job_id, mode=mode, attempt_id=attempt_id)
    
    if verify:
        return engine.apply_with_verify(plan)
    return engine.apply(plan)


def verify_post_state(
    engine: ApplyEngine,
    plan: ChangePlan,
    result: ApplyResult,
) -> ApplyResult:
    """Verify post-state after apply."""
    if not result.success:
        return result
    
    affected_doc_ids = set()
    for op in result.operations_applied:
        affected_doc_ids.update(op.get("targets", []))
    
    if not affected_doc_ids:
        result.verification_passed = True
        return result
    
    post_state = {}
    for doc_id in affected_doc_ids:
        doc_ref = engine.db.collection(EXERCISES_COLLECTION).document(doc_id)
        doc = doc_ref.get()
        if doc.exists:
            post_state[doc_id] = doc.to_dict()
    
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
                    actual = get_in(current, field)
                    if expected == DELETE_SENTINEL:
                        if actual is not None:
                            verification_errors.append({
                                "operation_index": idx,
                                "doc_id": doc_id,
                                "error": f"Field '{field}' should have been deleted",
                            })
                    elif actual != expected:
                        verification_errors.append({
                            "operation_index": idx,
                            "doc_id": doc_id,
                            "error": f"Field '{field}' mismatch: expected '{expected}', got '{actual}'",
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
    "ApplyGateError",
    "DELETE_SENTINEL",
    "derive_deterministic_doc_id",
]
