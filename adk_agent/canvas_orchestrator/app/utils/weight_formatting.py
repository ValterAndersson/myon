"""
Weight formatting utilities.

Shared weight formatting functions used across workout, copilot, and progression skills.
Provides consistent weight display in user's preferred unit (kg or lbs).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def format_weight(kg_value: float, weight_unit: str = "kg") -> str:
    """
    Format a weight value in the user's preferred unit.

    Args:
        kg_value: Weight in kilograms
        weight_unit: Target unit ("kg" or "lbs")

    Returns:
        Formatted weight string (e.g., "80kg", "175lbs")
    """
    if weight_unit == "lbs":
        lbs = kg_value * 2.20462
        # Round to nearest 5 for clean display
        rounded = round(lbs / 5) * 5
        if rounded == int(rounded):
            return f"{int(rounded)}lbs"
        return f"{rounded:.1f}lbs"
    else:
        if kg_value == int(kg_value):
            return f"{int(kg_value)}kg"
        return f"{kg_value:.1f}kg"


def get_weight_unit() -> str:
    """
    Get cached weight unit for the current request.

    Imports from workout_skills to access the cached unit. This function
    performs a lazy import to avoid circular dependencies.

    Returns "kg" if planning context hasn't been fetched yet (cold start).

    Returns:
        Weight unit string ("kg" or "lbs")
    """
    try:
        # Lazy import to avoid circular dependency
        from app.skills.workout_skills import get_weight_unit as _get_unit
        return _get_unit()
    except Exception:
        return "kg"
