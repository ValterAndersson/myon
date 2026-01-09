"""
Validators - Deterministic validators for Change Plans.

These validators GATE all writes. They run BEFORE apply engine.

Key validators:
1. Schema validation - required fields, types
2. Taxonomy validation - equipment naming rules
3. Alias validation - no collisions, valid targets
4. Family collision validation - no duplicates within family

All validators are deterministic - same input = same output.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.plans.models import (
    ChangePlan,
    Operation,
    OperationType,
    ValidationResult,
)
from app.family.models import ExerciseSummary, FamilyRegistry
from app.family.taxonomy import (
    derive_name_slug,
    derive_canonical_name,
    EQUIPMENT_DISPLAY_MAP,
)

logger = logging.getLogger(__name__)


# =============================================================================
# SCHEMA VALIDATION
# =============================================================================

# Required fields for exercise documents (strict core)
REQUIRED_EXERCISE_FIELDS = {
    "name": str,
    "name_slug": str,
    "family_slug": str,
    "status": str,
}

# Known fields that should not be rejected (warn-only for unknown)
KNOWN_EXERCISE_FIELDS = {
    "name", "name_slug", "family_slug", "status",
    "equipment", "primary_muscles", "secondary_muscles",
    "force", "mechanic", "level", "category",
    "instructions", "tips", "images", "created_at", "updated_at",
    # Enriched fields (warn-only until schema reconciled)
    "enriched_instructions", "enriched_tips", "enriched_cues",
    "enriched_at", "enriched_by",
}


def validate_schema(
    plan: ChangePlan,
    exercises: Dict[str, Dict[str, Any]],
) -> ValidationResult:
    """
    Validate schema compliance for all operations.
    
    Args:
        plan: Change plan to validate
        exercises: Current exercise documents (doc_id → data)
        
    Returns:
        ValidationResult with errors and warnings
    """
    result = ValidationResult(valid=True)
    
    for idx, op in enumerate(plan.operations):
        if op.op_type == OperationType.NO_CHANGE:
            continue
        
        # Validate PATCH_FIELDS
        if op.op_type == OperationType.PATCH_FIELDS:
            if not op.patch:
                result.add_error(
                    "EMPTY_PATCH",
                    "PATCH_FIELDS operation has no patch data",
                    operation_index=idx,
                )
                continue
            
            for doc_id in op.targets:
                _validate_patch_schema(result, idx, doc_id, op.patch, exercises.get(doc_id, {}))
        
        # Validate RENAME_EXERCISE
        if op.op_type == OperationType.RENAME_EXERCISE:
            if not op.after:
                result.add_error(
                    "MISSING_AFTER",
                    "RENAME_EXERCISE missing 'after' field",
                    operation_index=idx,
                )
            elif "name" not in op.after:
                result.add_error(
                    "MISSING_NAME",
                    "RENAME_EXERCISE 'after' missing 'name'",
                    operation_index=idx,
                )
        
        # Validate CREATE_EXERCISE
        if op.op_type == OperationType.CREATE_EXERCISE:
            if not op.patch:
                result.add_error(
                    "MISSING_CREATE_DATA",
                    "CREATE_EXERCISE missing patch data",
                    operation_index=idx,
                )
            else:
                for field, field_type in REQUIRED_EXERCISE_FIELDS.items():
                    if field not in op.patch:
                        result.add_error(
                            "MISSING_REQUIRED_FIELD",
                            f"CREATE_EXERCISE missing required field: {field}",
                            operation_index=idx,
                            field=field,
                        )
        
        # Validate idempotency key
        if op.op_type != OperationType.NO_CHANGE and not op.idempotency_key_seed:
            result.add_warning(
                "MISSING_IDEMPOTENCY_KEY",
                f"Operation {op.op_type.value} missing idempotency_key_seed",
                operation_index=idx,
            )
    
    return result


def _validate_patch_schema(
    result: ValidationResult,
    op_idx: int,
    doc_id: str,
    patch: Dict[str, Any],
    current: Dict[str, Any],
) -> None:
    """Validate a patch against schema rules."""
    for field, value in patch.items():
        if field not in KNOWN_EXERCISE_FIELDS:
            result.add_warning(
                "UNKNOWN_FIELD",
                f"Unknown field in patch: {field}",
                operation_index=op_idx,
                doc_id=doc_id,
                field=field,
            )
        
        # Check __DELETE__ sentinel
        if value == "__DELETE__":
            if field in REQUIRED_EXERCISE_FIELDS:
                result.add_error(
                    "CANNOT_DELETE_REQUIRED",
                    f"Cannot delete required field: {field}",
                    operation_index=op_idx,
                    doc_id=doc_id,
                    field=field,
                )


# =============================================================================
# TAXONOMY VALIDATION
# =============================================================================

def validate_taxonomy(
    plan: ChangePlan,
    registry: FamilyRegistry,
    exercises: List[ExerciseSummary],
) -> ValidationResult:
    """
    Validate taxonomy rules for all operations.
    
    Key rules:
    - Multi-equipment families require equipment qualifiers in names
    - Equipment suffixes must use canonical display names
    - Slugs must match derived slugs from names
    
    Args:
        plan: Change plan to validate
        registry: Family registry
        exercises: Current exercises in family
        
    Returns:
        ValidationResult with errors and warnings
    """
    result = ValidationResult(valid=True)
    
    for idx, op in enumerate(plan.operations):
        if op.op_type in (OperationType.RENAME_EXERCISE, OperationType.PATCH_FIELDS, OperationType.CREATE_EXERCISE):
            _validate_operation_taxonomy(result, idx, op, registry)
    
    return result


def _validate_operation_taxonomy(
    result: ValidationResult,
    op_idx: int,
    op: Operation,
    registry: FamilyRegistry,
) -> None:
    """Validate taxonomy for a single operation."""
    # Get name from operation
    name = None
    equipment = None
    
    if op.op_type == OperationType.RENAME_EXERCISE and op.after:
        name = op.after.get("name")
        equipment = op.after.get("equipment", [])
    elif op.op_type in (OperationType.PATCH_FIELDS, OperationType.CREATE_EXERCISE) and op.patch:
        name = op.patch.get("name")
        equipment = op.patch.get("equipment", [])
    
    if not name:
        return
    
    # Check equipment qualifier requirement
    if registry.needs_equipment_suffixes():
        has_qualifier = "(" in name and ")" in name
        if not has_qualifier:
            primary = equipment[0] if equipment else "unknown"
            result.add_error(
                "MISSING_EQUIPMENT_QUALIFIER",
                f"Name '{name}' needs equipment qualifier for multi-equipment family",
                operation_index=op_idx,
                suggestion=derive_canonical_name(name, primary),
            )
    
    # Check slug derivation
    if op.patch and "name_slug" in op.patch:
        expected_slug = derive_name_slug(name)
        actual_slug = op.patch["name_slug"]
        if actual_slug != expected_slug:
            result.add_error(
                "SLUG_MISMATCH",
                f"Slug '{actual_slug}' doesn't match derived slug '{expected_slug}'",
                operation_index=op_idx,
                suggestion=f"Use name_slug: {expected_slug}",
            )


# =============================================================================
# ALIAS VALIDATION
# =============================================================================

def validate_aliases(
    plan: ChangePlan,
    existing_aliases: Dict[str, str],  # alias_slug → exercise_doc_id
) -> ValidationResult:
    """
    Validate alias operations.
    
    Rules:
    - UPSERT_ALIAS must not overwrite existing alias pointing to different exercise
    - DELETE_ALIAS must exist
    
    Args:
        plan: Change plan to validate
        existing_aliases: Current alias mappings
        
    Returns:
        ValidationResult with errors and warnings
    """
    result = ValidationResult(valid=True)
    
    for idx, op in enumerate(plan.operations):
        if op.op_type == OperationType.UPSERT_ALIAS:
            _validate_upsert_alias(result, idx, op, existing_aliases)
        elif op.op_type == OperationType.DELETE_ALIAS:
            _validate_delete_alias(result, idx, op, existing_aliases)
    
    return result


def _validate_upsert_alias(
    result: ValidationResult,
    op_idx: int,
    op: Operation,
    existing_aliases: Dict[str, str],
) -> None:
    """Validate UPSERT_ALIAS operation."""
    if not op.patch:
        result.add_error(
            "MISSING_ALIAS_DATA",
            "UPSERT_ALIAS missing patch data",
            operation_index=op_idx,
        )
        return
    
    alias_slug = op.targets[0] if op.targets else None
    target_exercise_id = op.patch.get("exercise_id")
    
    if not alias_slug:
        result.add_error(
            "MISSING_ALIAS_SLUG",
            "UPSERT_ALIAS missing alias_slug in targets",
            operation_index=op_idx,
        )
        return
    
    if not target_exercise_id:
        result.add_error(
            "MISSING_TARGET_EXERCISE",
            "UPSERT_ALIAS missing exercise_id in patch",
            operation_index=op_idx,
        )
        return
    
    # Check for collision
    existing_target = existing_aliases.get(alias_slug)
    if existing_target and existing_target != target_exercise_id:
        result.add_error(
            "ALIAS_COLLISION",
            f"Alias '{alias_slug}' already points to different exercise: {existing_target}",
            operation_index=op_idx,
            suggestion="Delete existing alias first or choose different alias_slug",
        )


def _validate_delete_alias(
    result: ValidationResult,
    op_idx: int,
    op: Operation,
    existing_aliases: Dict[str, str],
) -> None:
    """Validate DELETE_ALIAS operation."""
    alias_slug = op.targets[0] if op.targets else None
    
    if not alias_slug:
        result.add_error(
            "MISSING_ALIAS_SLUG",
            "DELETE_ALIAS missing alias_slug in targets",
            operation_index=op_idx,
        )
        return
    
    if alias_slug not in existing_aliases:
        result.add_warning(
            "ALIAS_NOT_FOUND",
            f"Alias '{alias_slug}' does not exist (may have been deleted)",
            operation_index=op_idx,
        )


# =============================================================================
# FAMILY COLLISION VALIDATION
# =============================================================================

def validate_family_collision(
    plan: ChangePlan,
    exercises: List[ExerciseSummary],
) -> ValidationResult:
    """
    Validate that plan doesn't create duplicate equipment variants.
    
    Rule: Within a family, each primary equipment type should have only one exercise.
    
    Args:
        plan: Change plan to validate
        exercises: Current exercises in family
        
    Returns:
        ValidationResult with errors and warnings
    """
    result = ValidationResult(valid=True)
    
    # Build current equipment set
    current_equipment: Dict[str, str] = {}  # equipment → doc_id
    for ex in exercises:
        if ex.primary_equipment:
            current_equipment[ex.primary_equipment] = ex.doc_id
    
    # Check CREATE operations
    for idx, op in enumerate(plan.operations):
        if op.op_type == OperationType.CREATE_EXERCISE and op.patch:
            equipment = op.patch.get("equipment", [])
            primary = equipment[0] if equipment else None
            
            if primary and primary in current_equipment:
                result.add_error(
                    "DUPLICATE_EQUIPMENT_VARIANT",
                    f"Family already has exercise with equipment '{primary}': {current_equipment[primary]}",
                    operation_index=idx,
                    suggestion="Use MERGE_EXERCISES instead, or choose different equipment",
                )
    
    return result


# =============================================================================
# COMBINED VALIDATION
# =============================================================================

def validate_change_plan(
    plan: ChangePlan,
    exercises: Dict[str, Dict[str, Any]],
    exercise_summaries: List[ExerciseSummary],
    registry: FamilyRegistry,
    aliases: Dict[str, str],
) -> ValidationResult:
    """
    Run all validators on a Change Plan.
    
    Args:
        plan: Change plan to validate
        exercises: Full exercise documents (doc_id → data)
        exercise_summaries: Token-safe summaries
        registry: Family registry
        aliases: Alias mappings (alias_slug → exercise_doc_id)
        
    Returns:
        Combined ValidationResult
    """
    combined = ValidationResult(valid=True)
    
    # Schema validation
    schema_result = validate_schema(plan, exercises)
    combined.errors.extend(schema_result.errors)
    combined.warnings.extend(schema_result.warnings)
    
    # Taxonomy validation
    taxonomy_result = validate_taxonomy(plan, registry, exercise_summaries)
    combined.errors.extend(taxonomy_result.errors)
    combined.warnings.extend(taxonomy_result.warnings)
    
    # Alias validation
    alias_result = validate_aliases(plan, aliases)
    combined.errors.extend(alias_result.errors)
    combined.warnings.extend(alias_result.warnings)
    
    # Family collision validation
    collision_result = validate_family_collision(plan, exercise_summaries)
    combined.errors.extend(collision_result.errors)
    combined.warnings.extend(collision_result.warnings)
    
    # Update valid flag
    combined.valid = len(combined.errors) == 0
    
    logger.info("Validated plan: valid=%s, errors=%d, warnings=%d",
               combined.valid, len(combined.errors), len(combined.warnings))
    
    return combined


__all__ = [
    "validate_schema",
    "validate_taxonomy",
    "validate_aliases",
    "validate_family_collision",
    "validate_change_plan",
]
