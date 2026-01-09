"""
Plan Compiler - Compile LLM output to structured Change Plan.

The compiler takes raw JSON from LLM and produces a validated ChangePlan.
It also generates idempotency keys and derives missing fields.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.plans.models import (
    ChangePlan,
    Operation,
    OperationType,
    RiskLevel,
    ValidationResult,
)
from app.family.taxonomy import derive_name_slug

logger = logging.getLogger(__name__)


def compile_change_plan(
    raw_plan: Dict[str, Any],
    job_id: str,
    job_type: str,
) -> tuple[ChangePlan, ValidationResult]:
    """
    Compile raw LLM output to structured ChangePlan.
    
    Steps:
    1. Parse and normalize structure
    2. Generate idempotency keys
    3. Derive missing fields (slugs, etc.)
    4. Validate structure
    
    Args:
        raw_plan: Raw JSON from LLM
        job_id: Job ID for idempotency key generation
        job_type: Job type
        
    Returns:
        Tuple of (ChangePlan, ValidationResult)
    """
    result = ValidationResult(valid=True)
    
    # Parse operations
    raw_operations = raw_plan.get("operations", [])
    operations: List[Operation] = []
    
    for idx, raw_op in enumerate(raw_operations):
        op, op_errors = _compile_operation(raw_op, job_id, idx)
        if op:
            operations.append(op)
        for err in op_errors:
            result.add_error(err["code"], err["message"], operation_index=idx)
    
    # Build ChangePlan
    scope = raw_plan.get("scope", {})
    if not scope and "family_slug" in raw_plan:
        scope = {"family_slug": raw_plan["family_slug"]}
    
    plan = ChangePlan(
        job_id=job_id,
        job_type=job_type,
        scope=scope,
        assumptions=raw_plan.get("assumptions", []),
        operations=operations,
        max_risk_level=_compute_max_risk(operations),
        expected_post_state_checks=raw_plan.get("expected_post_state_checks", []),
        created_at=datetime.utcnow(),
        version="1.0",
    )
    
    return plan, result


def _compile_operation(
    raw_op: Dict[str, Any],
    job_id: str,
    index: int,
) -> tuple[Optional[Operation], List[Dict[str, str]]]:
    """
    Compile a single operation.
    
    Returns:
        Tuple of (Operation or None, list of errors)
    """
    errors = []
    
    # Parse op_type
    op_type_raw = raw_op.get("op_type", "no_change")
    try:
        op_type = OperationType(op_type_raw)
    except ValueError:
        errors.append({
            "code": "INVALID_OP_TYPE",
            "message": f"Unknown operation type: {op_type_raw}",
        })
        op_type = OperationType.NO_CHANGE
    
    # Get targets
    targets = raw_op.get("targets", [])
    if not targets and raw_op.get("doc_id"):
        targets = [raw_op["doc_id"]]
    
    # Parse risk level
    risk_raw = raw_op.get("risk_level", "low")
    try:
        risk = RiskLevel(risk_raw)
    except ValueError:
        risk = RiskLevel.LOW
    
    # Generate idempotency key if missing
    idempotency_seed = raw_op.get("idempotency_key_seed")
    if not idempotency_seed:
        idempotency_seed = _generate_idempotency_seed(job_id, index, raw_op)
    
    # Derive slugs in patch if name is present
    patch = raw_op.get("patch")
    if patch and "name" in patch and "name_slug" not in patch:
        patch["name_slug"] = derive_name_slug(patch["name"])
    
    after = raw_op.get("after")
    if after and "name" in after and "name_slug" not in after:
        after["name_slug"] = derive_name_slug(after["name"])
    
    op = Operation(
        op_type=op_type,
        targets=targets,
        patch=patch,
        before=raw_op.get("before"),
        after=after,
        primary_doc_id=raw_op.get("primary_doc_id"),
        secondary_doc_ids=raw_op.get("secondary_doc_ids"),
        idempotency_key_seed=idempotency_seed,
        rationale=raw_op.get("rationale", ""),
        risk_level=risk,
        expected_post_state=raw_op.get("expected_post_state"),
    )
    
    return op, errors


def _generate_idempotency_seed(
    job_id: str,
    index: int,
    raw_op: Dict[str, Any],
) -> str:
    """
    Generate idempotency key seed from operation content.
    
    Uses hash of job_id + index + key operation fields.
    """
    components = [
        job_id,
        str(index),
        raw_op.get("op_type", ""),
        json.dumps(raw_op.get("targets", []), sort_keys=True),
    ]
    
    if raw_op.get("patch"):
        components.append(json.dumps(raw_op["patch"], sort_keys=True))
    if raw_op.get("after"):
        components.append(json.dumps(raw_op["after"], sort_keys=True))
    
    raw = ":".join(components)
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def _compute_max_risk(operations: List[Operation]) -> RiskLevel:
    """Compute maximum risk level across operations."""
    risk_order = [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]
    max_risk = RiskLevel.LOW
    
    for op in operations:
        if risk_order.index(op.risk_level) > risk_order.index(max_risk):
            max_risk = op.risk_level
    
    return max_risk


def validate_plan_structure(plan: ChangePlan) -> ValidationResult:
    """
    Validate basic plan structure (independent of data).
    
    This is a quick check before running full validators.
    
    Args:
        plan: Change plan to validate
        
    Returns:
        ValidationResult
    """
    result = ValidationResult(valid=True)
    
    # Check job_id
    if not plan.job_id:
        result.add_error("MISSING_JOB_ID", "Plan missing job_id")
    
    # Check job_type
    if not plan.job_type:
        result.add_error("MISSING_JOB_TYPE", "Plan missing job_type")
    
    # Check scope
    if not plan.scope:
        result.add_warning("MISSING_SCOPE", "Plan has empty scope")
    
    # Check operations
    for idx, op in enumerate(plan.operations):
        if not op.targets and op.op_type != OperationType.NO_CHANGE:
            result.add_error(
                "MISSING_TARGETS",
                f"Operation {op.op_type.value} has no targets",
                operation_index=idx,
            )
    
    return result


def create_audit_plan(
    job_id: str,
    family_slug: str,
    findings: List[Dict[str, Any]],
) -> ChangePlan:
    """
    Create an audit-only plan (no mutations).
    
    Used for FAMILY_AUDIT jobs that only report issues.
    
    Args:
        job_id: Job ID
        family_slug: Family being audited
        findings: List of audit findings
        
    Returns:
        ChangePlan with NO_CHANGE operations
    """
    operations = []
    
    for finding in findings:
        operations.append(Operation(
            op_type=OperationType.NO_CHANGE,
            targets=finding.get("doc_ids", []),
            rationale=finding.get("description", ""),
            risk_level=RiskLevel.LOW,
        ))
    
    return ChangePlan(
        job_id=job_id,
        job_type="FAMILY_AUDIT",
        scope={"family_slug": family_slug},
        assumptions=["Audit-only, no mutations"],
        operations=operations,
        max_risk_level=RiskLevel.LOW,
        created_at=datetime.utcnow(),
    )


def create_normalize_plan(
    job_id: str,
    family_slug: str,
    renames: List[Dict[str, Any]],
    alias_updates: List[Dict[str, Any]],
) -> ChangePlan:
    """
    Create a normalization plan.
    
    Used for FAMILY_NORMALIZE jobs.
    
    Args:
        job_id: Job ID
        family_slug: Family being normalized
        renames: List of rename operations
        alias_updates: List of alias operations
        
    Returns:
        ChangePlan with RENAME_EXERCISE and UPSERT_ALIAS operations
    """
    operations = []
    
    # Add rename operations
    for idx, rename in enumerate(renames):
        operations.append(Operation(
            op_type=OperationType.RENAME_EXERCISE,
            targets=[rename["doc_id"]],
            before={"name": rename["old_name"], "name_slug": rename.get("old_slug")},
            after={"name": rename["new_name"], "name_slug": derive_name_slug(rename["new_name"])},
            idempotency_key_seed=_generate_idempotency_seed(job_id, idx, {
                "op_type": "rename_exercise",
                "targets": [rename["doc_id"]],
                "after": {"name": rename["new_name"]},
            }),
            rationale=rename.get("rationale", "Normalize to equipment-qualified name"),
            risk_level=RiskLevel.MEDIUM,
        ))
    
    # Add alias operations
    for idx, alias in enumerate(alias_updates):
        op_idx = len(renames) + idx
        operations.append(Operation(
            op_type=OperationType.UPSERT_ALIAS,
            targets=[alias["alias_slug"]],
            patch={
                "exercise_id": alias["exercise_id"],
                "family_slug": family_slug,
            },
            idempotency_key_seed=_generate_idempotency_seed(job_id, op_idx, {
                "op_type": "upsert_alias",
                "targets": [alias["alias_slug"]],
            }),
            rationale=alias.get("rationale", "Add alias for old slug"),
            risk_level=RiskLevel.LOW,
        ))
    
    return ChangePlan(
        job_id=job_id,
        job_type="FAMILY_NORMALIZE",
        scope={"family_slug": family_slug},
        assumptions=[
            "Multi-equipment family requires equipment qualifiers in names",
            "Old slugs become aliases to new canonical exercises",
        ],
        operations=operations,
        max_risk_level=RiskLevel.MEDIUM if renames else RiskLevel.LOW,
        created_at=datetime.utcnow(),
    )


__all__ = [
    "compile_change_plan",
    "validate_plan_structure",
    "create_audit_plan",
    "create_normalize_plan",
]
