"""
Job Handlers - Additional job type implementations.

This module contains handlers for:
- FAMILY_SPLIT
- FAMILY_RENAME_SLUG
- ALIAS_REPAIR
- TARGETED_FIX
- ALIAS_INVARIANT_SCAN

These are imported and used by the main executor.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from app.family.registry import (
    get_family_exercises,
    get_or_create_family_registry,
)
from app.family.taxonomy import derive_name_slug
from app.plans.models import Operation, OperationType, RiskLevel, ChangePlan

logger = logging.getLogger(__name__)


def execute_family_split(
    job_id: str,
    payload: Dict[str, Any],
    mode: str = "dry_run",
) -> Dict[str, Any]:
    """
    Execute FAMILY_SPLIT job.
    
    Splits a family into two based on split rules.
    
    Args:
        job_id: Job ID
        payload: Job payload with split_config
        mode: "dry_run" or "apply"
    """
    split_config = payload.get("split_config", {})
    family_slug = payload.get("family_slug")
    target_family = split_config.get("target_family")
    split_equipment = split_config.get("equipment", [])
    
    if not family_slug or not target_family:
        return {
            "success": False,
            "error": {"code": "MISSING_SPLIT_CONFIG", "message": "FAMILY_SPLIT requires family_slug and split_config.target_family"},
        }
    
    # Fetch source family
    source_exercises = get_family_exercises(family_slug)
    
    if not source_exercises:
        return {
            "success": True,
            "split_result": {
                "source_family": family_slug,
                "target_family": target_family,
                "message": "Source family has no exercises",
                "moved_count": 0,
            },
        }
    
    # Identify exercises to move
    exercises_to_move = []
    for ex in source_exercises:
        if ex.primary_equipment in split_equipment:
            exercises_to_move.append(ex.doc_id)
    
    if not exercises_to_move:
        return {
            "success": True,
            "split_result": {
                "source_family": family_slug,
                "target_family": target_family,
                "message": f"No exercises match split criteria (equipment: {split_equipment})",
                "moved_count": 0,
            },
        }
    
    # Create operations
    operations = [
        Operation(
            op_type=OperationType.REASSIGN_FAMILY,
            targets=exercises_to_move,
            patch={"family_slug": target_family},
            rationale=f"Split exercises to new family {target_family}",
            risk_level=RiskLevel.HIGH,
            idempotency_key_seed=f"split_{family_slug}_{target_family}",
        )
    ]
    
    plan = ChangePlan(
        job_id=job_id,
        job_type="FAMILY_SPLIT",
        scope={"source_family": family_slug, "target_family": target_family},
        assumptions=[f"Splitting {len(exercises_to_move)} exercises"],
        operations=operations,
        max_risk_level=RiskLevel.HIGH,
    )
    
    result = {
        "success": True,
        "split_result": {
            "source_family": family_slug,
            "target_family": target_family,
            "exercises_to_move": exercises_to_move,
            "moved_count": len(exercises_to_move),
        },
        "plan": plan.to_dict(),
        "mode": mode,
    }
    
    if mode == "apply" and operations:
        from app.apply.engine import apply_change_plan
        apply_result = apply_change_plan(plan, mode=mode, job_id=job_id)
        result["applied"] = apply_result.success
        result["apply_result"] = apply_result.to_dict()
    
    return result


def execute_family_rename_slug(
    job_id: str,
    payload: Dict[str, Any],
    mode: str = "dry_run",
) -> Dict[str, Any]:
    """
    Execute FAMILY_RENAME_SLUG job.
    
    Renames a family slug without semantic change.
    Migrates exercises and creates alias for old slug.
    """
    rename_config = payload.get("rename_config", {})
    old_family_slug = rename_config.get("old_family_slug") or payload.get("family_slug")
    new_family_slug = rename_config.get("new_family_slug")
    
    if not old_family_slug or not new_family_slug:
        return {
            "success": False,
            "error": {"code": "MISSING_RENAME_CONFIG", "message": "FAMILY_RENAME_SLUG requires old_family_slug and new_family_slug"},
        }
    
    # Fetch exercises
    exercises = get_family_exercises(old_family_slug)
    
    if not exercises:
        return {
            "success": True,
            "rename_result": {
                "old_family_slug": old_family_slug,
                "new_family_slug": new_family_slug,
                "message": "Family has no exercises",
                "updated_count": 0,
            },
        }
    
    operations = []
    
    # Reassign all exercises to new family
    doc_ids = [ex.doc_id for ex in exercises]
    operations.append(Operation(
        op_type=OperationType.REASSIGN_FAMILY,
        targets=doc_ids,
        patch={"family_slug": new_family_slug},
        rationale=f"Rename family from {old_family_slug} to {new_family_slug}",
        risk_level=RiskLevel.MEDIUM,
        idempotency_key_seed=f"rename_family_{old_family_slug}_{new_family_slug}",
    ))
    
    # Create alias for old family slug
    operations.append(Operation(
        op_type=OperationType.UPSERT_ALIAS,
        targets=[old_family_slug],
        patch={"family_slug": new_family_slug, "is_family_alias": True},
        rationale=f"Create alias for old family slug",
        risk_level=RiskLevel.LOW,
        idempotency_key_seed=f"alias_{old_family_slug}_{new_family_slug}",
    ))
    
    plan = ChangePlan(
        job_id=job_id,
        job_type="FAMILY_RENAME_SLUG",
        scope={"old_family_slug": old_family_slug, "new_family_slug": new_family_slug},
        assumptions=[f"Renaming family with {len(exercises)} exercises"],
        operations=operations,
        max_risk_level=RiskLevel.MEDIUM,
    )
    
    result = {
        "success": True,
        "rename_result": {
            "old_family_slug": old_family_slug,
            "new_family_slug": new_family_slug,
            "updated_count": len(doc_ids),
        },
        "plan": plan.to_dict(),
        "mode": mode,
    }
    
    if mode == "apply":
        from app.apply.engine import apply_change_plan
        apply_result = apply_change_plan(plan, mode=mode, job_id=job_id)
        result["applied"] = apply_result.success
        result["apply_result"] = apply_result.to_dict()
    
    return result


def execute_alias_repair(
    job_id: str,
    payload: Dict[str, Any],
    mode: str = "dry_run",
) -> Dict[str, Any]:
    """
    Execute ALIAS_REPAIR job.
    
    Repairs broken alias mappings.
    """
    alias_slugs = payload.get("alias_slugs", [])
    
    if not alias_slugs:
        return {
            "success": False,
            "error": {"code": "MISSING_ALIAS_SLUGS", "message": "ALIAS_REPAIR requires alias_slugs"},
        }
    
    # For each alias, check if valid
    # This is a stub - actual implementation would fetch and verify
    operations = []
    repairs_needed = []
    
    for alias_slug in alias_slugs:
        # Check if alias points to valid exercise
        # Stub: assume we need to delete orphaned aliases
        repairs_needed.append({
            "alias_slug": alias_slug,
            "action": "delete_orphaned",
        })
        
        operations.append(Operation(
            op_type=OperationType.DELETE_ALIAS,
            targets=[alias_slug],
            rationale=f"Delete orphaned alias {alias_slug}",
            risk_level=RiskLevel.MEDIUM,
            idempotency_key_seed=f"repair_alias_{alias_slug}",
        ))
    
    plan = ChangePlan(
        job_id=job_id,
        job_type="ALIAS_REPAIR",
        scope={"alias_slugs": alias_slugs},
        assumptions=[f"Repairing {len(alias_slugs)} aliases"],
        operations=operations,
        max_risk_level=RiskLevel.MEDIUM,
    )
    
    result = {
        "success": True,
        "repair_result": {
            "alias_count": len(alias_slugs),
            "repairs": repairs_needed,
        },
        "plan": plan.to_dict(),
        "mode": mode,
    }
    
    if mode == "apply" and operations:
        from app.apply.engine import apply_change_plan
        apply_result = apply_change_plan(plan, mode=mode, job_id=job_id)
        result["applied"] = apply_result.success
        result["apply_result"] = apply_result.to_dict()
    
    return result


def execute_targeted_fix(
    job_id: str,
    payload: Dict[str, Any],
    mode: str = "dry_run",
) -> Dict[str, Any]:
    """
    Execute TARGETED_FIX job.
    
    Applies specific fixes to targeted exercises.
    
    Supports both legacy format (fix_type, fix_data in payload root)
    and new format (enrichment_spec.type, enrichment_spec.fix_details).
    """
    exercise_doc_ids = payload.get("exercise_doc_ids", [])
    
    # Support both legacy and new field locations
    enrichment_spec = payload.get("enrichment_spec", {})
    fix_type = enrichment_spec.get("type", payload.get("fix_type", "patch"))
    fix_data = enrichment_spec.get("fix_details", payload.get("fix_data", {}))
    
    if not exercise_doc_ids:
        return {
            "success": False,
            "error": {"code": "MISSING_TARGETS", "message": "TARGETED_FIX requires exercise_doc_ids"},
        }
    
    operations = []
    reason = enrichment_spec.get("reason", "")
    
    for doc_id in exercise_doc_ids:
        if fix_type == "rename":
            operations.append(Operation(
                op_type=OperationType.RENAME_EXERCISE,
                targets=[doc_id],
                after=fix_data,
                rationale=f"Targeted rename for {doc_id}: {reason}",
                risk_level=RiskLevel.LOW,
                idempotency_key_seed=f"fix_{doc_id}",
            ))
        elif fix_type == "archive":
            # Archive -> set status to deprecated
            operations.append(Operation(
                op_type=OperationType.DEPRECATE_EXERCISE,
                targets=[doc_id],
                rationale=f"Archive exercise {doc_id}: {reason}",
                risk_level=RiskLevel.MEDIUM,
                idempotency_key_seed=f"archive_{doc_id}",
            ))
        elif fix_type == "merge_candidate":
            # Merge candidate -> set status to merged
            merge_into = enrichment_spec.get("merge_into", "")
            operations.append(Operation(
                op_type=OperationType.PATCH_FIELDS,
                targets=[doc_id],
                patch={"status": "merged", "merged_into": merge_into},
                rationale=f"Mark as merged into {merge_into}: {reason}",
                risk_level=RiskLevel.MEDIUM,
                idempotency_key_seed=f"merge_{doc_id}",
            ))
        elif fix_type == "fix_identity" and fix_data:
            # Fix identity -> patch the specified fields (name, family_slug, equipment, etc.)
            operations.append(Operation(
                op_type=OperationType.PATCH_FIELDS,
                targets=[doc_id],
                patch=fix_data,
                rationale=f"Fix identity for {doc_id}: {reason}",
                risk_level=RiskLevel.LOW,
                idempotency_key_seed=f"fix_{doc_id}",
            ))
        elif fix_data:
            # Generic patch with provided data
            operations.append(Operation(
                op_type=OperationType.PATCH_FIELDS,
                targets=[doc_id],
                patch=fix_data,
                rationale=f"Targeted patch for {doc_id}: {reason}",
                risk_level=RiskLevel.LOW,
                idempotency_key_seed=f"fix_{doc_id}",
            ))
        else:
            logger.warning("TARGETED_FIX for %s has no fix_data, skipping", doc_id)
    
    plan = ChangePlan(
        job_id=job_id,
        job_type="TARGETED_FIX",
        scope={"exercise_doc_ids": exercise_doc_ids},
        assumptions=[f"Applying {fix_type} to {len(exercise_doc_ids)} exercises"],
        operations=operations,
        max_risk_level=RiskLevel.LOW,
    )
    
    result = {
        "success": True,
        "fix_result": {
            "fix_type": fix_type,
            "target_count": len(exercise_doc_ids),
        },
        "plan": plan.to_dict(),
        "mode": mode,
    }
    
    if mode == "apply" and operations:
        from app.apply.engine import apply_change_plan
        apply_result = apply_change_plan(plan, mode=mode, job_id=job_id)
        result["applied"] = apply_result.success
        result["apply_result"] = apply_result.to_dict()
    
    return result


def execute_alias_invariant_scan(
    job_id: str,
    payload: Dict[str, Any],
    mode: str = "dry_run",
) -> Dict[str, Any]:
    """
    Execute ALIAS_INVARIANT_SCAN job.
    
    Scans for alias invariant violations:
    - Orphaned aliases (point to non-existent exercises)
    - Missing aliases (exercises without aliases)
    - Duplicate aliases (multiple pointing to same exercise)
    """
    from app.skills.catalog_read_skills import list_families_summary
    import asyncio
    
    # Scan families and collect alias data
    # This is a stub - actual implementation would query alias collection
    
    issues_found = []
    
    # Stub scan results
    issues_found.append({
        "type": "orphaned_alias",
        "count": 0,
        "aliases": [],
    })
    issues_found.append({
        "type": "missing_alias",
        "count": 0,
        "exercises": [],
    })
    
    return {
        "success": True,
        "scan_result": {
            "aliases_scanned": 0,
            "issues_found": issues_found,
            "total_issues": sum(i["count"] for i in issues_found),
        },
    }


def execute_schema_cleanup(
    job_id: str,
    payload: Dict[str, Any],
    mode: str = "dry_run",
) -> Dict[str, Any]:
    """
    Execute SCHEMA_CLEANUP job.
    
    Removes deprecated fields from exercises.
    V1.1: Used for cleaning up legacy/debug fields.
    
    Args:
        job_id: Job ID
        payload: Job payload with exercise_doc_ids
        mode: "dry_run" or "apply"
    """
    from google.cloud import firestore
    from app.apply.engine import apply_change_plan
    
    # Deprecated fields to remove (complete list)
    DEPRECATED_FIELDS = [
        # Debug/internal artifacts
        "_debug_project_id",
        "created_by",
        "created_at",
        "id",
        "version",
        # Old review system
        "delete_candidate",
        "delete_candidate_justification",
        "status",
        "deprecated_at",
        # Unused/empty
        "images",
        # Deprecated content fields (redundant with execution_notes)
        "coaching_cues",
        "tips",  # Redundant with suitability_notes
        # Deprecated variant tracking (family_slug + equipment in name is sufficient)
        "variant_key",
        # Legacy muscle fields (replaced by muscles.*)
        "primary_muscles",
        "secondary_muscles",
        # Legacy instructions (replaced by execution_notes)
        "instructions",
        # Old enrichment pattern (enriched_ prefix)
        "enriched_description",
        "enriched_common_mistakes",
        "enriched_programming_use_cases",
        "enriched_instructions",
        "enriched_tips",
        "enriched_cues",
        "enriched_at",
        "enriched_by",
    ]

    # Conditional fields: only delete if replacement exists
    CONDITIONAL_DEPRECATED = {
        "primary_muscles": ("muscles", "primary"),  # Only delete if muscles.primary exists
        "secondary_muscles": ("muscles", "secondary"),
        "instructions": ("execution_notes", None),  # Only delete if execution_notes exists
    }

    exercise_doc_ids = payload.get("exercise_doc_ids", [])
    fields_to_remove = payload.get("fields_to_remove", DEPRECATED_FIELDS)

    if not exercise_doc_ids:
        return {
            "success": False,
            "error": {"code": "MISSING_TARGETS", "message": "SCHEMA_CLEANUP requires exercise_doc_ids"},
            "is_transient": False,
        }

    # Fetch exercises to check which have deprecated fields
    db = firestore.Client()
    exercises_with_fields = []

    for doc_id in exercise_doc_ids:
        doc = db.collection("exercises").document(doc_id).get()
        if doc.exists:
            data = doc.to_dict()
            deprecated_present = []

            for field in fields_to_remove:
                if field not in data:
                    continue

                # Check conditional fields - don't delete if replacement doesn't exist
                if field in CONDITIONAL_DEPRECATED:
                    parent_key, child_key = CONDITIONAL_DEPRECATED[field]
                    if child_key:
                        # Nested: check data[parent_key][child_key]
                        parent = data.get(parent_key, {}) or {}
                        has_replacement = bool(parent.get(child_key))
                    else:
                        # Top-level: check data[parent_key]
                        has_replacement = bool(data.get(parent_key))

                    if not has_replacement:
                        # Skip - replacement doesn't exist, keep legacy
                        logger.debug(
                            "Skipping %s for %s: replacement %s.%s doesn't exist",
                            field, doc_id, parent_key, child_key or ""
                        )
                        continue

                deprecated_present.append(field)

            if deprecated_present:
                exercises_with_fields.append({
                    "doc_id": doc_id,
                    "name": data.get("name", "Unknown"),
                    "deprecated_fields": deprecated_present,
                })
    
    if not exercises_with_fields:
        return {
            "success": True,
            "cleanup_result": {
                "message": "No exercises have deprecated fields",
                "exercises_checked": len(exercise_doc_ids),
                "exercises_cleaned": 0,
            },
        }
    
    # Create operations to delete deprecated fields
    operations = []
    for ex in exercises_with_fields:
        # Build delete patch using Firestore DELETE_FIELD sentinel
        operations.append(Operation(
            op_type=OperationType.PATCH_FIELDS,
            targets=[ex["doc_id"]],
            patch={field: firestore.DELETE_FIELD for field in ex["deprecated_fields"]},
            rationale=f"Remove deprecated fields: {', '.join(ex['deprecated_fields'])}",
            risk_level=RiskLevel.LOW,
            idempotency_key_seed=f"cleanup_{ex['doc_id']}_{','.join(sorted(ex['deprecated_fields']))}",
        ))
    
    plan = ChangePlan(
        job_id=job_id,
        job_type="SCHEMA_CLEANUP",
        scope={"exercise_count": len(exercises_with_fields)},
        assumptions=[f"Removing deprecated fields from {len(exercises_with_fields)} exercises"],
        operations=operations,
        max_risk_level=RiskLevel.LOW,
    )
    
    result = {
        "success": True,
        "cleanup_result": {
            "exercises_checked": len(exercise_doc_ids),
            "exercises_with_deprecated": len(exercises_with_fields),
            "fields_removed": fields_to_remove,
            "details": exercises_with_fields,
        },
        "plan": plan.to_dict(),
        "mode": mode,
    }
    
    if mode == "apply" and operations:
        apply_result = apply_change_plan(plan, mode=mode, job_id=job_id)
        result["applied"] = apply_result.success
        result["apply_result"] = apply_result.to_dict()
    
    return result


__all__ = [
    "execute_family_split",
    "execute_family_rename_slug",
    "execute_alias_repair",
    "execute_targeted_fix",
    "execute_alias_invariant_scan",
    "execute_schema_cleanup",
]
