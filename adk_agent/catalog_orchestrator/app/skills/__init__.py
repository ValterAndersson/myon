"""
Catalog Skills - Pure skill functions for catalog operations.

Skills are "pure" functions that implement catalog logic without
ADK tool wrappers. The tools in app/shell/tools.py wrap these skills.

Skill categories:
- read_skills: Fetch exercises, families, aliases (token-safe)
- write_skills: Validate and apply change plans
- validation_skills: Deterministic validators
"""

from app.skills.catalog_read_skills import (
    get_family_summary,
    get_exercises_batch,
    get_family_aliases,
    get_family_registry,
    list_families_summary,
)

from app.skills.catalog_write_skills import (
    validate_change_plan,
    apply_change_plan,
)


__all__ = [
    # Read skills
    "get_family_summary",
    "get_exercises_batch",
    "get_family_aliases",
    "get_family_registry",
    "list_families_summary",
    # Write skills
    "validate_change_plan",
    "apply_change_plan",
]
