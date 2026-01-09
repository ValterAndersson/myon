"""
Change Plan Models - Structured output contract for LLM-generated plans.

The LLM does NOT directly mutate Firestore. It produces a structured ChangePlan
that deterministic validators gate before apply.

Key rules:
- All mutations use doc_id (Firestore document ID), not exercise.id
- __DELETE__ sentinel maps to firestore.DELETE_FIELD
- Each operation includes idempotency_key_seed for safe retries
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class OperationType(str, Enum):
    """Types of catalog operations."""
    # Exercise operations
    RENAME_EXERCISE = "rename_exercise"
    PATCH_FIELDS = "patch_fields"
    MERGE_EXERCISES = "merge_exercises"
    CREATE_EXERCISE = "create_exercise"
    DEPRECATE_EXERCISE = "deprecate_exercise"
    
    # Alias operations
    UPSERT_ALIAS = "upsert_alias"
    DELETE_ALIAS = "delete_alias"
    
    # Family operations
    REASSIGN_FAMILY = "reassign_family"
    DEPRECATE_FAMILY = "deprecate_family"
    UPDATE_FAMILY_REGISTRY = "update_family_registry"
    
    # No-op (audit only)
    NO_CHANGE = "no_change"


class RiskLevel(str, Enum):
    """Risk assessment for operations."""
    LOW = "low"           # Metadata updates, safe
    MEDIUM = "medium"     # Name changes, alias updates
    HIGH = "high"         # Merges, family reassignments
    CRITICAL = "critical" # Destructive operations


@dataclass
class Operation:
    """
    Single atomic operation in a Change Plan.
    
    Each operation must:
    - Use doc_id (not exercise.id) for targeting
    - Include idempotency_key_seed for safe retries
    - Include rationale for audit trail
    """
    op_type: OperationType
    targets: List[str]  # doc_ids or alias_slugs
    
    # For PATCH_FIELDS
    patch: Optional[Dict[str, Any]] = None
    
    # For renames
    before: Optional[Dict[str, Any]] = None
    after: Optional[Dict[str, Any]] = None
    
    # For merges
    primary_doc_id: Optional[str] = None
    secondary_doc_ids: Optional[List[str]] = None
    
    # Idempotency
    idempotency_key_seed: Optional[str] = None
    
    # Metadata
    rationale: str = ""
    risk_level: RiskLevel = RiskLevel.LOW
    
    # Expected post-state for verification
    expected_post_state: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to serializable dict."""
        return {
            "op_type": self.op_type.value if isinstance(self.op_type, OperationType) else self.op_type,
            "targets": self.targets,
            "patch": self.patch,
            "before": self.before,
            "after": self.after,
            "primary_doc_id": self.primary_doc_id,
            "secondary_doc_ids": self.secondary_doc_ids,
            "idempotency_key_seed": self.idempotency_key_seed,
            "rationale": self.rationale,
            "risk_level": self.risk_level.value if isinstance(self.risk_level, RiskLevel) else self.risk_level,
            "expected_post_state": self.expected_post_state,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Operation":
        """Create from dict."""
        op_type_raw = data.get("op_type", "no_change")
        try:
            op_type = OperationType(op_type_raw)
        except ValueError:
            op_type = OperationType.NO_CHANGE
        
        risk_raw = data.get("risk_level", "low")
        try:
            risk = RiskLevel(risk_raw)
        except ValueError:
            risk = RiskLevel.LOW
        
        return cls(
            op_type=op_type,
            targets=data.get("targets", []),
            patch=data.get("patch"),
            before=data.get("before"),
            after=data.get("after"),
            primary_doc_id=data.get("primary_doc_id"),
            secondary_doc_ids=data.get("secondary_doc_ids"),
            idempotency_key_seed=data.get("idempotency_key_seed"),
            rationale=data.get("rationale", ""),
            risk_level=risk,
            expected_post_state=data.get("expected_post_state"),
        )


@dataclass
class ChangePlan:
    """
    Structured Change Plan - output contract for LLM.
    
    The LLM produces this structure; deterministic validators
    check it before apply engine executes.
    """
    job_id: str
    job_type: str
    scope: Dict[str, Any]  # family_slug, exercise_doc_ids, etc.
    
    # Explicit assumptions (for transparency)
    assumptions: List[str] = field(default_factory=list)
    
    # Operations to apply
    operations: List[Operation] = field(default_factory=list)
    
    # Overall risk assessment
    max_risk_level: RiskLevel = RiskLevel.LOW
    
    # Expected post-state checks
    expected_post_state_checks: List[Dict[str, Any]] = field(default_factory=list)
    
    # Metadata
    created_at: Optional[datetime] = None
    version: str = "1.0"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to serializable dict."""
        return {
            "job_id": self.job_id,
            "job_type": self.job_type,
            "scope": self.scope,
            "assumptions": self.assumptions,
            "operations": [op.to_dict() for op in self.operations],
            "max_risk_level": self.max_risk_level.value if isinstance(self.max_risk_level, RiskLevel) else self.max_risk_level,
            "expected_post_state_checks": self.expected_post_state_checks,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "version": self.version,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChangePlan":
        """Create from dict."""
        risk_raw = data.get("max_risk_level", "low")
        try:
            risk = RiskLevel(risk_raw)
        except ValueError:
            risk = RiskLevel.LOW
        
        return cls(
            job_id=data.get("job_id", ""),
            job_type=data.get("job_type", ""),
            scope=data.get("scope", {}),
            assumptions=data.get("assumptions", []),
            operations=[Operation.from_dict(op) for op in data.get("operations", [])],
            max_risk_level=risk,
            expected_post_state_checks=data.get("expected_post_state_checks", []),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None,
            version=data.get("version", "1.0"),
        )
    
    def is_empty(self) -> bool:
        """Check if plan has no operations."""
        return len(self.operations) == 0
    
    def is_audit_only(self) -> bool:
        """Check if plan is audit-only (no mutations)."""
        return all(op.op_type == OperationType.NO_CHANGE for op in self.operations)
    
    def operation_count(self) -> int:
        """Count mutation operations (excluding NO_CHANGE)."""
        return sum(1 for op in self.operations if op.op_type != OperationType.NO_CHANGE)


@dataclass
class ValidationError:
    """Single validation error."""
    code: str
    message: str
    severity: str = "error"  # "error", "warning"
    
    # Context
    operation_index: Optional[int] = None
    doc_id: Optional[str] = None
    field: Optional[str] = None
    
    # Fix suggestion
    suggestion: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
            "operation_index": self.operation_index,
            "doc_id": self.doc_id,
            "field": self.field,
            "suggestion": self.suggestion,
        }


@dataclass
class ValidationResult:
    """Result of validating a Change Plan."""
    valid: bool
    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[ValidationError] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": [e.to_dict() for e in self.errors],
            "warnings": [w.to_dict() for w in self.warnings],
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
        }
    
    def add_error(self, code: str, message: str, **kwargs) -> None:
        """Add an error."""
        self.errors.append(ValidationError(
            code=code,
            message=message,
            severity="error",
            **kwargs
        ))
        self.valid = False
    
    def add_warning(self, code: str, message: str, **kwargs) -> None:
        """Add a warning."""
        self.warnings.append(ValidationError(
            code=code,
            message=message,
            severity="warning",
            **kwargs
        ))


__all__ = [
    "OperationType",
    "RiskLevel",
    "Operation",
    "ChangePlan",
    "ValidationError",
    "ValidationResult",
]
