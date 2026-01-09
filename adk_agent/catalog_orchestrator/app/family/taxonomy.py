"""
Taxonomy - Equipment naming rules and validation.

Key rules:
- When family has >1 primary equipment types, exercises MUST have equipment in name
- Equipment suffix uses canonical display name: (Barbell), (Dumbbell), etc.
- primary_equipment = equipment[0] for multi-equipment family checks
- Slug derivation is deterministic and lowercase with hyphens
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional, Set, Tuple

from app.family.models import ExerciseSummary, FamilyRegistry


# =============================================================================
# CANONICAL EQUIPMENT MAPPING
# =============================================================================

EQUIPMENT_DISPLAY_MAP: Dict[str, str] = {
    # Standard equipment
    "barbell": "Barbell",
    "dumbbell": "Dumbbell",
    "cable": "Cable",
    "machine": "Machine",
    "bodyweight": "Bodyweight",
    "kettlebell": "Kettlebell",
    "band": "Band",
    "smith_machine": "Smith Machine",
    "trap_bar": "Trap Bar",
    # Less common
    "ez_bar": "EZ Bar",
    "medicine_ball": "Medicine Ball",
    "resistance_band": "Resistance Band",
    "plate": "Plate",
    "trx": "TRX",
    "landmine": "Landmine",
    "chains": "Chains",
    "sled": "Sled",
    # Handle variations
    "smith": "Smith Machine",
    "cables": "Cable",
    "dumbbells": "Dumbbell",
    "barbells": "Barbell",
}

# Reverse map for parsing names
EQUIPMENT_REVERSE_MAP: Dict[str, str] = {
    v.lower(): k for k, v in EQUIPMENT_DISPLAY_MAP.items()
}


# =============================================================================
# DERIVATION FUNCTIONS
# =============================================================================

def derive_equipment_suffix(equipment: str) -> str:
    """
    Get the canonical display suffix for equipment.
    
    Args:
        equipment: Equipment key (e.g., "barbell", "smith_machine")
        
    Returns:
        Display name for name suffix (e.g., "Barbell", "Smith Machine")
    """
    return EQUIPMENT_DISPLAY_MAP.get(equipment.lower(), equipment.title())


def derive_canonical_name(base_name: str, equipment: Optional[str]) -> str:
    """
    Derive canonical exercise name with equipment suffix.
    
    Args:
        base_name: Base exercise name (e.g., "Deadlift")
        equipment: Primary equipment (e.g., "barbell")
        
    Returns:
        Canonical name (e.g., "Deadlift (Barbell)")
    """
    # Strip any existing equipment suffix
    clean_base = re.sub(r'\s*\([^)]+\)\s*$', '', base_name).strip()
    
    if not equipment:
        return clean_base
    
    suffix = derive_equipment_suffix(equipment)
    return f"{clean_base} ({suffix})"


def derive_name_slug(name: str) -> str:
    """
    Derive deterministic slug from exercise name.
    
    Rules:
    - Lowercase
    - Replace spaces and underscores with hyphens
    - Remove parentheses, keep content
    - Remove other special characters
    - Collapse multiple hyphens
    
    Args:
        name: Exercise name (e.g., "Deadlift (Barbell)")
        
    Returns:
        Slug (e.g., "deadlift-barbell")
    """
    # Normalize unicode
    slug = unicodedata.normalize('NFKD', name)
    slug = slug.encode('ascii', 'ignore').decode('ascii')
    
    # Remove parentheses but keep content
    slug = re.sub(r'[()]', ' ', slug)
    
    # Lowercase
    slug = slug.lower()
    
    # Replace spaces and underscores with hyphens
    slug = re.sub(r'[\s_]+', '-', slug)
    
    # Remove non-alphanumeric except hyphens
    slug = re.sub(r'[^a-z0-9-]', '', slug)
    
    # Collapse multiple hyphens
    slug = re.sub(r'-+', '-', slug)
    
    # Strip leading/trailing hyphens
    slug = slug.strip('-')
    
    return slug


def compute_primary_equipment_set(exercises: List[ExerciseSummary]) -> Set[str]:
    """
    Compute set of primary equipment types from exercises.
    
    Only uses equipment[0] for multi-equipment family determination.
    
    Args:
        exercises: List of exercise summaries
        
    Returns:
        Set of primary equipment types
    """
    return {
        ex.primary_equipment
        for ex in exercises
        if ex.primary_equipment
    }


# =============================================================================
# VALIDATION FUNCTIONS
# =============================================================================

def validate_equipment_naming(
    exercise: ExerciseSummary,
    registry: FamilyRegistry,
) -> List[Dict[str, Any]]:
    """
    Validate exercise naming against family taxonomy rules.
    
    Args:
        exercise: Exercise to validate
        registry: Family registry with equipment info
        
    Returns:
        List of validation errors (empty if valid)
    """
    errors = []
    
    # Check if family needs equipment suffixes
    if not registry.needs_equipment_suffixes():
        # Single-equipment family - no suffix required
        return errors
    
    # Multi-equipment family - validate naming
    has_suffix = exercise.has_equipment_in_name()
    
    if not has_suffix:
        errors.append({
            "code": "MISSING_EQUIPMENT_QUALIFIER",
            "message": f"Exercise '{exercise.name}' needs equipment qualifier for multi-equipment family",
            "doc_id": exercise.doc_id,
            "suggestion": derive_canonical_name(exercise.name, exercise.primary_equipment),
        })
        return errors
    
    # Has suffix - check if it matches primary equipment
    name_equipment = exercise.extract_name_equipment()
    if name_equipment:
        expected_suffix = derive_equipment_suffix(exercise.primary_equipment or "")
        if name_equipment.lower() != expected_suffix.lower():
            errors.append({
                "code": "EQUIPMENT_MISMATCH",
                "message": f"Name suffix '({name_equipment})' doesn't match primary equipment '{exercise.primary_equipment}'",
                "doc_id": exercise.doc_id,
                "expected": expected_suffix,
                "actual": name_equipment,
            })
    
    return errors


def validate_slug_derivation(exercise: ExerciseSummary) -> List[Dict[str, Any]]:
    """
    Validate that exercise slug matches derived slug from name.
    
    Args:
        exercise: Exercise to validate
        
    Returns:
        List of validation errors (empty if valid)
    """
    errors = []
    
    expected_slug = derive_name_slug(exercise.name)
    if exercise.name_slug != expected_slug:
        errors.append({
            "code": "SLUG_MISMATCH",
            "message": f"Slug '{exercise.name_slug}' doesn't match derived slug",
            "doc_id": exercise.doc_id,
            "expected": expected_slug,
            "actual": exercise.name_slug,
        })
    
    return errors


def detect_duplicate_equipment(exercises: List[ExerciseSummary]) -> List[Dict[str, Any]]:
    """
    Detect duplicate equipment variants within a family.
    
    Args:
        exercises: List of exercises in family
        
    Returns:
        List of duplicate groups
    """
    duplicates = []
    
    # Group by primary equipment
    by_equipment: Dict[str, List[ExerciseSummary]] = {}
    for ex in exercises:
        key = ex.primary_equipment or "none"
        if key not in by_equipment:
            by_equipment[key] = []
        by_equipment[key].append(ex)
    
    # Find duplicates
    for equipment, group in by_equipment.items():
        if len(group) > 1:
            duplicates.append({
                "equipment": equipment,
                "exercises": [
                    {"doc_id": ex.doc_id, "name": ex.name, "status": ex.status}
                    for ex in group
                ],
                "count": len(group),
            })
    
    return duplicates


__all__ = [
    "EQUIPMENT_DISPLAY_MAP",
    "derive_equipment_suffix",
    "derive_canonical_name",
    "derive_name_slug",
    "compute_primary_equipment_set",
    "validate_equipment_naming",
    "validate_slug_derivation",
    "detect_duplicate_equipment",
]
