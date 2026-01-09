"""
Family Package - Family model and registry operations.

This package provides:
- models: FamilyRegistry, ExerciseSummary data models
- registry: Family registry CRUD operations
- taxonomy: Equipment naming rules and validation
"""

from app.family.models import (
    FamilyRegistry,
    ExerciseSummary,
    FamilyStatus,
)

from app.family.registry import (
    get_family_registry,
    upsert_family_registry,
    list_family_registries,
)

from app.family.taxonomy import (
    EQUIPMENT_DISPLAY_MAP,
    derive_equipment_suffix,
    derive_canonical_name,
    derive_name_slug,
    validate_equipment_naming,
    compute_primary_equipment_set,
)


__all__ = [
    # Models
    "FamilyRegistry",
    "ExerciseSummary",
    "FamilyStatus",
    # Registry
    "get_family_registry",
    "upsert_family_registry",
    "list_family_registries",
    # Taxonomy
    "EQUIPMENT_DISPLAY_MAP",
    "derive_equipment_suffix",
    "derive_canonical_name",
    "derive_name_slug",
    "validate_equipment_naming",
    "compute_primary_equipment_set",
]
