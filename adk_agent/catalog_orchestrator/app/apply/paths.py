"""
Path Utilities - Canonical dotted path handling for patches.

Shared by PlanCompiler (simulation), ApplyEngine (Firestore), and validators.

Rules:
- Dotted paths like "metadata.difficulty" update nested fields
- Array indexing is NOT allowed (e.g., "equipment[0]")
- Only allowlisted paths can be patched
- __DELETE__ sentinel marks field deletion
"""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Dict, List, Optional, Set, Tuple

# Sentinel for field deletion
DELETE_SENTINEL = "__DELETE__"

# Allowlisted paths for exercise documents
# Flat fields that can be patched directly
ALLOWED_FLAT_PATHS: Set[str] = {
    "name",
    "name_slug",
    "family_slug",
    "status",
    "category",
    "description",
    "instructions",
    "tips",
    "common_mistakes",
    # Alias document fields (also validated via this path)
    "exercise_id",
    "alias_slug",
    # --- V1.1: Fields used by enrichment ---
    "muscles",
    "movement",
    "execution_notes",
    "suitability_notes",
    "coaching_cues",
    "variant_key",
    "created_by",
    "version",
    # --- V1.2: Holistic enrichment fields ---
    "muscles.primary",
    "muscles.secondary",
    "muscles.category",
    "movement.type",
    "movement.split",
    "metadata.level",
    "metadata.plane_of_motion",
    "metadata.unilateral",
    # --- V1.3: Top-level enrichment fields (LLM output format) ---
    "family",
    "difficulty",
    "movement_type",
    "plane_of_motion",
    "force_type",
    "bilateral",
}

# Array fields - whole-array replace only (not element-wise)
ALLOWED_ARRAY_PATHS: Set[str] = {
    "equipment",
    "primary_muscles",
    "secondary_muscles",
    "movement_pattern",
    "tags",
    "programming_use_cases",
    # --- V1.1: Additional array fields ---
    "stimulus_tags",
    "alias_slugs",
    "aliases",
    "images",
}

# Deep map paths - allowed nested updates via dotted path
ALLOWED_DEEP_PATHS_PREFIX: Set[str] = {
    "metadata.",
    "enriched_",
    "stimulus_tags.",
    "muscle_contributions.",
}

# Regex to detect array indexing (not allowed)
ARRAY_INDEX_PATTERN = re.compile(r'\[\d+\]')


class PathValidationError(Exception):
    """Raised when path validation fails."""
    
    def __init__(self, path: str, reason: str):
        super().__init__(f"Invalid path '{path}': {reason}")
        self.path = path
        self.reason = reason


def validate_path(path: str) -> Tuple[bool, Optional[str]]:
    """
    Validate a patch path against allowlist.
    
    Args:
        path: Dotted path like "metadata.difficulty"
        
    Returns:
        (valid, error_message or None)
    """
    if not path:
        return False, "Empty path"
    
    # Check for array indexing
    if ARRAY_INDEX_PATTERN.search(path):
        return False, "Array indexing not allowed"
    
    # Check if it's a flat allowed path
    if path in ALLOWED_FLAT_PATHS:
        return True, None
    
    # Check if it's an array path
    if path in ALLOWED_ARRAY_PATHS:
        return True, None
    
    # Check if it matches a deep path prefix
    for prefix in ALLOWED_DEEP_PATHS_PREFIX:
        if path.startswith(prefix):
            return True, None
    
    # Special paths that are always allowed
    if path in ("updated_at", "created_at"):
        return True, None
    
    return False, f"Path not in allowlist"


def require_valid_path(path: str) -> None:
    """
    Validate path and raise if invalid.
    
    Raises:
        PathValidationError: If path is not allowed
    """
    valid, error = validate_path(path)
    if not valid:
        raise PathValidationError(path, error)


def validate_patch_paths(patch: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    Validate all paths in a patch dict.
    
    Args:
        patch: Dict of path -> value
        
    Returns:
        List of validation errors (empty if all valid)
    """
    errors = []
    for path in patch.keys():
        valid, error = validate_path(path)
        if not valid:
            errors.append({"path": path, "error": error})
    return errors


def get_in(obj: Dict[str, Any], path: str) -> Any:
    """
    Get value at dotted path from nested dict.
    
    Args:
        obj: Dict to read from
        path: Dotted path like "metadata.difficulty"
        
    Returns:
        Value at path, or None if not found
    """
    if not obj:
        return None
    
    parts = path.split(".")
    current = obj
    
    for part in parts:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
        if current is None:
            return None
    
    return current


def set_in(obj: Dict[str, Any], path: str, value: Any) -> Dict[str, Any]:
    """
    Set value at dotted path in nested dict, returning new dict.
    
    Does NOT mutate original. Creates intermediate dicts as needed.
    
    Args:
        obj: Dict to update
        path: Dotted path like "metadata.difficulty"
        value: Value to set (use DELETE_SENTINEL to delete)
        
    Returns:
        New dict with value set
    """
    result = deepcopy(obj) if obj else {}
    parts = path.split(".")
    
    if len(parts) == 1:
        if value is DELETE_SENTINEL:
            result.pop(path, None)
        else:
            result[path] = value
        return result
    
    # Navigate to parent, creating dicts as needed
    current = result
    for part in parts[:-1]:
        if part not in current or not isinstance(current.get(part), dict):
            current[part] = {}
        current = current[part]
    
    # Set or delete the leaf
    leaf = parts[-1]
    if value is DELETE_SENTINEL:
        current.pop(leaf, None)
    else:
        current[leaf] = value
    
    return result


def apply_patch(obj: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply a patch dict to object, returning new object.
    
    Args:
        obj: Original dict
        patch: Dict of path -> value
        
    Returns:
        New dict with all patches applied
    """
    result = deepcopy(obj) if obj else {}
    
    for path, value in patch.items():
        result = set_in(result, path, value)
    
    return result


def compute_diff(before: Dict[str, Any], after: Dict[str, Any], paths: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Compute diff for specific paths.
    
    Args:
        before: Original dict
        after: Updated dict
        paths: Paths to compare
        
    Returns:
        Dict of path -> {"before": val, "after": val} for changed paths
    """
    diff = {}
    for path in paths:
        before_val = get_in(before, path)
        after_val = get_in(after, path)
        if before_val != after_val:
            diff[path] = {"before": before_val, "after": after_val}
    return diff


def flatten_for_firestore(patch: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert patch dict to Firestore update format.
    
    Dotted paths are already correct for Firestore.
    DELETE_SENTINEL is converted to firestore.DELETE_FIELD.
    
    Args:
        patch: Patch dict with dotted paths
        
    Returns:
        Dict ready for Firestore update()
    """
    from google.cloud import firestore
    
    result = {}
    for path, value in patch.items():
        if value is DELETE_SENTINEL or value == DELETE_SENTINEL:
            result[path] = firestore.DELETE_FIELD
        else:
            result[path] = value
    
    return result


__all__ = [
    "DELETE_SENTINEL",
    "ALLOWED_FLAT_PATHS",
    "ALLOWED_ARRAY_PATHS",
    "ALLOWED_DEEP_PATHS_PREFIX",
    "PathValidationError",
    "validate_path",
    "require_valid_path",
    "validate_patch_paths",
    "get_in",
    "set_in",
    "apply_patch",
    "compute_diff",
    "flatten_for_firestore",
]
