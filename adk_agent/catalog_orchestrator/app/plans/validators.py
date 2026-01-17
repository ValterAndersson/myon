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
# MERGE SAFETY VALIDATION
# =============================================================================

def validate_merge_safety(
    plan: ChangePlan,
    source_exercises: List[ExerciseSummary],
    target_exercises: List[ExerciseSummary],
) -> ValidationResult:
    """
    Validate that FAMILY_MERGE operations are safe.
    
    Rules:
    - Source and target must be different families
    - No equipment conflicts that would create duplicates
    - Exercises being moved must have valid data
    
    Args:
        plan: Change plan (should be FAMILY_MERGE type)
        source_exercises: Exercises in source family
        target_exercises: Exercises in target family
        
    Returns:
        ValidationResult with errors and warnings
    """
    result = ValidationResult(valid=True)
    
    # Build target equipment set
    target_equipment = {ex.primary_equipment for ex in target_exercises if ex.primary_equipment}
    
    # Check for equipment conflicts
    for idx, op in enumerate(plan.operations):
        if op.op_type == OperationType.REASSIGN_FAMILY:
            # Find exercises being moved that would conflict
            for doc_id in op.targets:
                source_ex = next((ex for ex in source_exercises if ex.doc_id == doc_id), None)
                if source_ex and source_ex.primary_equipment in target_equipment:
                    result.add_error(
                        "MERGE_EQUIPMENT_CONFLICT",
                        f"Exercise '{source_ex.name}' has equipment '{source_ex.primary_equipment}' "
                        f"which already exists in target family",
                        operation_index=idx,
                        doc_id=doc_id,
                        suggestion="Merge or deprecate one of the conflicting exercises first",
                    )
    
    # Warn if source exercises have missing data
    for ex in source_exercises:
        if not ex.name_slug:
            result.add_warning(
                "MISSING_SLUG",
                f"Source exercise {ex.doc_id} is missing name_slug",
                doc_id=ex.doc_id,
            )
    
    return result


# =============================================================================
# COMPILED PLAN VALIDATION (POST-STATE)
# =============================================================================

def validate_compiled_plan(compiled: "CompiledPlan") -> ValidationResult:
    """
    Validate a compiled plan against its post-state.
    
    This is the PRIMARY validation that gates writes. It validates
    the 4 core invariants against the simulated post-state, not raw ops.
    
    4 Core Invariants:
    1. Schema / required fields (for creates/patches touching required fields)
    2. Taxonomy / naming (equipment suffix when multi-equipment)
    3. Slug + alias uniqueness (no collisions in post_state)
    4. Alias one-of + target exists
    
    Args:
        compiled: CompiledPlan from PlanCompiler
        
    Returns:
        ValidationResult with all errors and warnings
    """
    from app.plans.state_compiler import CompiledPlan, ExerciseDoc, AliasDoc
    
    result = ValidationResult(valid=True)
    post = compiled.post_state
    
    # Check compilation errors first
    if compiled.compilation_errors:
        for err in compiled.compilation_errors:
            result.add_error(
                "COMPILATION_ERROR",
                err.get("error", "Unknown compilation error"),
                operation_index=err.get("operation_index"),
            )
    
    # ==========================================================================
    # INVARIANT 1: Schema / required fields
    # ==========================================================================
    for doc_id, exercise in post.exercises.items():
        # Required fields check
        if not exercise.name:
            result.add_error(
                "MISSING_REQUIRED_FIELD",
                f"Exercise {doc_id} missing required field: name",
                doc_id=doc_id,
                field="name",
            )
        if not exercise.name_slug:
            result.add_error(
                "MISSING_REQUIRED_FIELD",
                f"Exercise {doc_id} missing required field: name_slug",
                doc_id=doc_id,
                field="name_slug",
            )
        if not exercise.family_slug:
            result.add_error(
                "MISSING_REQUIRED_FIELD",
                f"Exercise {doc_id} missing required field: family_slug",
                doc_id=doc_id,
                field="family_slug",
            )
        if not exercise.status:
            result.add_error(
                "MISSING_REQUIRED_FIELD",
                f"Exercise {doc_id} missing required field: status",
                doc_id=doc_id,
                field="status",
            )
    
    # ==========================================================================
    # INVARIANT 2: Taxonomy / naming (equipment suffix when multi-equipment)
    # ==========================================================================
    # Use equipment[0] (primary_equipment) to determine if multi-equipment
    primary_equipment_set = compiled.primary_equipment_set
    is_multi_equipment = len(primary_equipment_set) > 1
    
    if is_multi_equipment:
        for doc_id, exercise in post.exercises.items():
            if exercise.status == "deprecated":
                continue  # Skip deprecated
            
            # Check if name has equipment qualifier
            has_qualifier = "(" in exercise.name and ")" in exercise.name
            if not has_qualifier and exercise.primary_equipment:
                result.add_error(
                    "MISSING_EQUIPMENT_QUALIFIER",
                    f"Multi-equipment family requires equipment qualifier in name: '{exercise.name}'",
                    doc_id=doc_id,
                    suggestion=f"{exercise.name} ({EQUIPMENT_DISPLAY_MAP.get(exercise.primary_equipment, exercise.primary_equipment)})",
                )
    
    # ==========================================================================
    # INVARIANT 3: Slug + alias uniqueness
    # ==========================================================================
    # Check slug collisions among exercises
    slug_owners: Dict[str, str] = {}  # name_slug → doc_id
    for doc_id, exercise in post.exercises.items():
        if not exercise.name_slug:
            continue
        
        if exercise.name_slug in slug_owners:
            other_id = slug_owners[exercise.name_slug]
            result.add_error(
                "SLUG_COLLISION",
                f"Slug '{exercise.name_slug}' used by both {other_id} and {doc_id}",
                doc_id=doc_id,
                field="name_slug",
            )
        else:
            slug_owners[exercise.name_slug] = doc_id
    
    # Check alias slug uniqueness (alias_slug should not conflict with exercise slugs or other aliases)
    alias_slugs_seen: Dict[str, bool] = {}
    for alias_slug, alias in post.aliases.items():
        if alias_slug in alias_slugs_seen:
            result.add_error(
                "DUPLICATE_ALIAS",
                f"Alias '{alias_slug}' appears multiple times",
                field="alias_slug",
            )
        alias_slugs_seen[alias_slug] = True
    
    # ==========================================================================
    # INVARIANT 4: Alias one-of + target exists
    # ==========================================================================
    exercise_ids = set(post.exercises.keys())
    
    for alias_slug, alias in post.aliases.items():
        # One-of check: exactly one of exercise_id XOR family_slug
        has_exercise = bool(alias.exercise_id)
        has_family = bool(alias.family_slug)
        
        if has_exercise and has_family:
            result.add_error(
                "ALIAS_BOTH_FIELDS",
                f"Alias '{alias_slug}' cannot have both exercise_id and family_slug",
                field="alias_slug",
            )
        elif not has_exercise and not has_family:
            result.add_error(
                "ALIAS_NO_TARGET",
                f"Alias '{alias_slug}' must have exercise_id or family_slug",
                field="alias_slug",
            )
        
        # Target exists check
        if has_exercise and alias.exercise_id not in exercise_ids:
            # Exercise might be outside snapshot, warn rather than error
            result.add_warning(
                "ALIAS_TARGET_NOT_IN_SNAPSHOT",
                f"Alias '{alias_slug}' points to exercise '{alias.exercise_id}' not in snapshot",
                field="exercise_id",
            )
        
        if has_family and alias.family_slug != post.family_slug:
            # Family-level alias pointing to different family
            result.add_warning(
                "ALIAS_FAMILY_MISMATCH",
                f"Alias '{alias_slug}' points to family '{alias.family_slug}' but snapshot is for '{post.family_slug}'",
                field="family_slug",
            )
    
    # Update valid flag
    result.valid = len(result.errors) == 0
    
    logger.info(
        "Validated compiled plan: valid=%s, errors=%d, warnings=%d",
        result.valid, len(result.errors), len(result.warnings)
    )
    
    return result


def validate_global_slug_uniqueness(
    compiled: "CompiledPlan",
) -> ValidationResult:
    """
    Validate that slugs touched in plan don't collide with catalog outside snapshot.
    
    This is a targeted lookup for slugs in the plan diff, not a full scan.
    Call this BEFORE apply to catch global collisions.
    
    Args:
        compiled: CompiledPlan with slugs_touched set
        
    Returns:
        ValidationResult with collision errors
    """
    from google.cloud import firestore
    
    result = ValidationResult(valid=True)
    
    if not compiled.slugs_touched:
        return result
    
    db = firestore.Client()
    exercises_in_snapshot = set(compiled.post_state.exercises.keys())
    
    # Check each touched slug
    for name_slug in compiled.slugs_touched:
        # Skip if this is a doc_id (likely already in snapshot)
        if name_slug in exercises_in_snapshot:
            continue
        
        # Query for exercises with this slug outside the snapshot
        query = db.collection("exercises").where("name_slug", "==", name_slug).limit(1)
        for doc in query.stream():
            if doc.id not in exercises_in_snapshot:
                result.add_error(
                    "GLOBAL_SLUG_COLLISION",
                    f"Slug '{name_slug}' already exists in catalog (doc: {doc.id})",
                    field="name_slug",
                    doc_id=doc.id,
                )
    
    # Check alias collisions
    for alias_slug in compiled.aliases_touched:
        if alias_slug in compiled.post_state.aliases:
            continue  # Already in our plan
        
        alias_doc = db.collection("exercise_aliases").document(alias_slug).get()
        if alias_doc.exists:
            result.add_error(
                "GLOBAL_ALIAS_COLLISION",
                f"Alias '{alias_slug}' already exists in catalog",
                field="alias_slug",
            )
    
    result.valid = len(result.errors) == 0
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
    "validate_merge_safety",
    "validate_change_plan",
    "validate_compiled_plan",
    "validate_global_slug_uniqueness",
]
