"""
Catalog Write Skills - Validation and apply operations.

These are pure skill functions for validating and applying Change Plans.

Phase 0: Stub implementations.
Phase 1+: Full implementations with:
- Deterministic validators (schema, taxonomy, alias)
- Idempotent apply with journaling
- Post-write verification

Key principle: __DELETE__ sentinel translates to firestore.DELETE_FIELD.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# Apply mode gate - must be explicitly enabled
APPLY_ENABLED = os.getenv("CATALOG_APPLY_ENABLED", "false").lower() == "true"

# Sentinel for field deletion
DELETE_FIELD = "__DELETE__"


async def validate_change_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate a change plan against all deterministic validators.
    
    Validators:
    - Schema: Required fields, types, allowed values
    - Taxonomy: Equipment naming, slug derivation
    - Alias: Target existence, collision detection
    - Plan limits: Max operations, max exercises
    
    Args:
        plan: The change plan to validate
        
    Returns:
        Dict with valid flag, errors list, warnings list, compiled_diff
    """
    logger.info("validate_change_plan: job_type=%s", plan.get("job_type"))
    
    errors: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    
    # Phase 0: Basic structural validation only
    if not plan.get("job_type"):
        errors.append({
            "code": "MISSING_JOB_TYPE",
            "message": "Plan must include job_type",
        })
    
    if not plan.get("operations"):
        errors.append({
            "code": "MISSING_OPERATIONS",
            "message": "Plan must include operations array",
        })
    
    operations = plan.get("operations", [])
    
    # Check plan limits
    if len(operations) > 50:
        errors.append({
            "code": "TOO_MANY_OPERATIONS",
            "message": f"Maximum 50 operations per plan, got {len(operations)}",
        })
    
    # Count unique exercises touched
    touched_exercises = set()
    for op in operations:
        targets = op.get("targets", {})
        if "doc_id" in targets:
            touched_exercises.add(targets["doc_id"])
    
    if len(touched_exercises) > 25:
        errors.append({
            "code": "TOO_MANY_EXERCISES",
            "message": f"Maximum 25 exercises per plan, got {len(touched_exercises)}",
        })
    
    # Validate each operation has required fields
    for i, op in enumerate(operations):
        if not op.get("op_type"):
            errors.append({
                "code": "MISSING_OP_TYPE",
                "message": f"Operation {i} missing op_type",
                "operation_index": i,
            })
        
        if not op.get("idempotency_key_seed"):
            warnings.append({
                "code": "MISSING_IDEMPOTENCY_KEY",
                "message": f"Operation {i} missing idempotency_key_seed",
                "operation_index": i,
            })
    
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "compiled_diff": None,  # Phase 1+: Preview of changes
    }


async def apply_change_plan(
    plan: Dict[str, Any],
    idempotency_prefix: str,
    mode: str = "dry_run",
) -> Dict[str, Any]:
    """
    Apply a validated change plan.
    
    Gated by CATALOG_APPLY_ENABLED environment variable.
    
    Args:
        plan: The validated change plan
        idempotency_prefix: Prefix for idempotency keys
        mode: "dry_run" or "apply"
        
    Returns:
        Dict with applied flag, operation counts, journal_id
    """
    logger.info("apply_change_plan: mode=%s, apply_enabled=%s", mode, APPLY_ENABLED)
    
    if mode == "dry_run":
        return {
            "applied": False,
            "reason": "dry_run mode - changes not applied",
            "would_apply": len(plan.get("operations", [])),
        }
    
    if not APPLY_ENABLED:
        return {
            "applied": False,
            "reason": "CATALOG_APPLY_ENABLED not set",
            "would_apply": len(plan.get("operations", [])),
        }
    
    # Phase 0: Mock apply
    return {
        "applied": False,
        "reason": "Phase 0 stub - no actual writes",
        "operations_applied": 0,
        "operations_skipped": 0,
        "journal_id": None,
    }


__all__ = [
    "validate_change_plan",
    "apply_change_plan",
    "DELETE_FIELD",
    "APPLY_ENABLED",
]
