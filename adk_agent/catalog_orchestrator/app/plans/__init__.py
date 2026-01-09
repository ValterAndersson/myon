"""
Plans Package - Change Plan schema and operations.

This package provides:
- models: ChangePlan, Operation data models
- compiler: Compile LLM output to structured ChangePlan
- validators: Deterministic validators for plans
"""

from app.plans.models import (
    ChangePlan,
    Operation,
    OperationType,
    RiskLevel,
    ValidationResult,
    ValidationError,
)

from app.plans.compiler import (
    compile_change_plan,
    validate_plan_structure,
)

from app.plans.validators import (
    validate_schema,
    validate_taxonomy,
    validate_aliases,
    validate_family_collision,
    validate_change_plan,
)


__all__ = [
    # Models
    "ChangePlan",
    "Operation",
    "OperationType",
    "RiskLevel",
    "ValidationResult",
    "ValidationError",
    # Compiler
    "compile_change_plan",
    "validate_plan_structure",
    # Validators
    "validate_schema",
    "validate_taxonomy",
    "validate_aliases",
    "validate_family_collision",
    "validate_change_plan",
]
