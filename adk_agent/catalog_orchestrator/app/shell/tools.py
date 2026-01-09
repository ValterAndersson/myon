"""
Catalog Tools - Tool definitions for CatalogShellAgent.

Phase 0: Stub implementations that return mock data.
Phase 1+: Full implementations backed by Firestore reads/writes.

Tool categories:
- Read tools: Family/exercise summaries, aliases
- Write tools: Apply change plans (gated by validation)

Security:
- Tool signatures do NOT include admin identity in arguments
- Context is retrieved from contextvars (set in job processing)
- All writes go through deterministic validation before apply
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from google.adk.tools import FunctionTool

from app.shell.context import get_current_job_context

logger = logging.getLogger(__name__)


# =============================================================================
# READ TOOLS (Catalog Data)
# =============================================================================

def tool_get_family_summary(*, family_slug: str) -> Dict[str, Any]:
    """
    Get summary of a family: exercise count, equipment types, names.
    
    This is a token-safe summary - does NOT include full exercise details.
    Use tool_get_exercises_batch for full details on specific exercises.
    
    Args:
        family_slug: The family to summarize (e.g., "deadlift", "bench_press")
    
    Returns:
        Summary with:
        - family_slug: The family identifier
        - exercise_count: Number of exercises in family
        - exercises: List of {doc_id, name, name_slug, equipment, status}
        - primary_equipment_set: Set of primary equipment types
        - has_equipment_conflicts: True if naming needs normalization
    """
    ctx = get_current_job_context()
    logger.info("tool_get_family_summary: family=%s, job=%s", family_slug, ctx.job_id)
    
    # Phase 0: Return mock data
    return {
        "success": True,
        "family_slug": family_slug,
        "exercise_count": 0,
        "exercises": [],
        "primary_equipment_set": [],
        "has_equipment_conflicts": False,
        "_mock": True,
        "_display": {
            "running": f"Loading family '{family_slug}'",
            "complete": f"Loaded family '{family_slug}' (0 exercises)"
        }
    }


def tool_get_exercises_batch(*, doc_ids: List[str]) -> Dict[str, Any]:
    """
    Get full exercise documents by their Firestore document IDs.
    
    Use this for detailed analysis of specific exercises.
    Prefer tool_get_family_summary for initial overview.
    
    Args:
        doc_ids: List of Firestore document IDs (max 25)
    
    Returns:
        exercises: Dict mapping doc_id → full exercise document
        missing: List of doc_ids that were not found
    """
    ctx = get_current_job_context()
    logger.info("tool_get_exercises_batch: count=%d, job=%s", len(doc_ids), ctx.job_id)
    
    if len(doc_ids) > 25:
        return {"success": False, "error": "Maximum 25 doc_ids per batch"}
    
    # Phase 0: Return mock data
    return {
        "success": True,
        "exercises": {},
        "missing": doc_ids,
        "_mock": True,
        "_display": {
            "running": f"Fetching {len(doc_ids)} exercises",
            "complete": f"Fetched 0 exercises"
        }
    }


def tool_get_family_aliases(*, family_slug: str) -> Dict[str, Any]:
    """
    Get all aliases that target exercises in a family.
    
    Args:
        family_slug: The family to get aliases for
    
    Returns:
        aliases: List of {alias_slug, exercise_id, family_slug, is_ambiguous}
        exercise_aliases: Dict mapping doc_id → list of alias_slugs
    """
    ctx = get_current_job_context()
    logger.info("tool_get_family_aliases: family=%s, job=%s", family_slug, ctx.job_id)
    
    # Phase 0: Return mock data
    return {
        "success": True,
        "family_slug": family_slug,
        "aliases": [],
        "exercise_aliases": {},
        "_mock": True,
        "_display": {
            "running": f"Loading aliases for '{family_slug}'",
            "complete": f"Loaded 0 aliases"
        }
    }


def tool_get_family_registry(*, family_slug: str) -> Dict[str, Any]:
    """
    Get the family registry entry (if exists).
    
    Args:
        family_slug: The family to look up
    
    Returns:
        exists: Whether registry entry exists
        registry: Family registry data if exists
    """
    ctx = get_current_job_context()
    logger.info("tool_get_family_registry: family=%s, job=%s", family_slug, ctx.job_id)
    
    # Phase 0: Return mock data
    return {
        "success": True,
        "exists": False,
        "registry": None,
        "_mock": True,
        "_display": {
            "running": f"Checking registry for '{family_slug}'",
            "complete": f"Registry: not found"
        }
    }


def tool_list_families_summary(
    *,
    min_size: int = 1,
    limit: int = 50,
    status_filter: Optional[str] = None,
) -> Dict[str, Any]:
    """
    List families with summary stats.
    
    Args:
        min_size: Minimum exercises per family (default 1)
        limit: Maximum families to return (default 50)
        status_filter: Filter by registry status (active, needs_review, deprecated)
    
    Returns:
        families: List of family summaries
    """
    ctx = get_current_job_context()
    logger.info("tool_list_families_summary: job=%s", ctx.job_id)
    
    # Phase 0: Return mock data
    return {
        "success": True,
        "families": [],
        "total": 0,
        "_mock": True,
        "_display": {
            "running": "Listing families",
            "complete": "Found 0 families"
        }
    }


# =============================================================================
# WRITE TOOLS (Change Plan Application)
# =============================================================================

def tool_validate_change_plan(*, plan: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate a change plan without applying it.
    
    Runs all deterministic validators:
    - Schema validation
    - Taxonomy validation (equipment naming)
    - Alias validation
    - Plan limits (max ops, max exercises)
    
    Args:
        plan: The change plan to validate
    
    Returns:
        valid: Whether plan passes all validators
        errors: List of validation errors
        warnings: List of validation warnings
        compiled_diff: Preview of what would change
    """
    ctx = get_current_job_context()
    logger.info("tool_validate_change_plan: job=%s", ctx.job_id)
    
    # Phase 0: Return mock validation
    return {
        "success": True,
        "valid": True,
        "errors": [],
        "warnings": [],
        "compiled_diff": None,
        "_mock": True,
        "_display": {
            "running": "Validating change plan",
            "complete": "Validation passed"
        }
    }


def tool_apply_change_plan(
    *,
    plan: Dict[str, Any],
    idempotency_prefix: str,
) -> Dict[str, Any]:
    """
    Apply a validated change plan.
    
    IMPORTANT: This tool is gated by CATALOG_APPLY_ENABLED environment variable.
    In dry-run mode, returns what would be applied without making changes.
    
    Args:
        plan: The change plan to apply
        idempotency_prefix: Prefix for idempotency keys (usually job_id)
    
    Returns:
        applied: Whether changes were applied
        operations_applied: Number of operations applied
        operations_skipped: Number already applied (idempotent)
        journal_id: ID of the journal entry created
    """
    ctx = get_current_job_context()
    logger.info("tool_apply_change_plan: job=%s, mode=%s", ctx.job_id, ctx.mode)
    
    if not ctx.is_apply_mode():
        return {
            "success": True,
            "applied": False,
            "reason": "dry_run mode - changes not applied",
            "would_apply": len(plan.get("operations", [])),
            "_display": {
                "running": "Simulating change plan",
                "complete": "Dry-run complete (no changes made)"
            }
        }
    
    # Phase 0: Return mock apply
    return {
        "success": True,
        "applied": False,
        "reason": "Phase 0 mock - no actual writes",
        "operations_applied": 0,
        "operations_skipped": 0,
        "journal_id": None,
        "_mock": True,
        "_display": {
            "running": "Applying change plan",
            "complete": "Applied 0 operations (mock)"
        }
    }


# =============================================================================
# TOOL REGISTRY
# =============================================================================

all_tools = [
    # Read tools
    FunctionTool(func=tool_get_family_summary),
    FunctionTool(func=tool_get_exercises_batch),
    FunctionTool(func=tool_get_family_aliases),
    FunctionTool(func=tool_get_family_registry),
    FunctionTool(func=tool_list_families_summary),
    
    # Write tools
    FunctionTool(func=tool_validate_change_plan),
    FunctionTool(func=tool_apply_change_plan),
]


__all__ = [
    "all_tools",
    # Read tools
    "tool_get_family_summary",
    "tool_get_exercises_batch",
    "tool_get_family_aliases",
    "tool_get_family_registry",
    "tool_list_families_summary",
    # Write tools
    "tool_validate_change_plan",
    "tool_apply_change_plan",
]
