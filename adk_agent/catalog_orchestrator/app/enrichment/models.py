"""
Enrichment Models - Data models for field enrichment jobs.

EnrichmentSpec defines what to compute and how to validate output.
EnrichmentResult captures per-exercise enrichment outcomes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class EnrichmentSpec:
    """
    Specification for a field enrichment job.
    
    Defines what field to populate, how to compute it, and output constraints.
    """
    spec_id: str              # e.g. "difficulty", "fatigue_score"
    spec_version: str         # e.g. "v1" - for idempotency and reproducibility
    field_path: str           # e.g. "metadata.difficulty" or "tags.joint_stress"
    instructions: str         # LLM prompt instructions
    output_type: str          # "enum" | "string" | "number" | "boolean" | "object"
    allowed_values: Optional[List[Any]] = None  # For enum: ["beginner", "intermediate", "advanced"]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for storage."""
        return {
            "spec_id": self.spec_id,
            "spec_version": self.spec_version,
            "field_path": self.field_path,
            "instructions": self.instructions,
            "output_type": self.output_type,
            "allowed_values": self.allowed_values,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EnrichmentSpec":
        """Create from dict."""
        return cls(
            spec_id=data.get("spec_id", "unknown"),
            spec_version=data.get("spec_version", "v1"),
            field_path=data.get("field_path", ""),
            instructions=data.get("instructions", ""),
            output_type=data.get("output_type", "string"),
            allowed_values=data.get("allowed_values"),
        )
    
    def idempotency_key(self, exercise_id: str) -> str:
        """
        Generate stable idempotency key for this exercise + spec.
        
        Same spec version + exercise = same key = skip if already applied.
        """
        return f"{self.spec_id}:{self.spec_version}:{exercise_id}"
    
    def requires_reasoning(self) -> bool:
        """
        Check if this enrichment requires complex reasoning (use gemini-2.5-pro).
        
        Complex reasoning indicators:
        - Output type is object (complex structured output)
        - Instructions mention analysis, evaluation, reasoning
        - Field path suggests derived/computed value
        """
        reasoning_keywords = [
            "analyze", "evaluate", "reason", "consider",
            "based on", "assess", "determine", "infer",
            "difficulty", "fatigue", "stress", "complexity"
        ]
        
        instructions_lower = self.instructions.lower()
        has_reasoning_keywords = any(kw in instructions_lower for kw in reasoning_keywords)
        
        return self.output_type == "object" or has_reasoning_keywords


@dataclass
class EnrichmentResult:
    """
    Result of enriching a single exercise.
    """
    exercise_id: str
    spec_id: str
    spec_version: str
    
    # Outcome
    success: bool = False
    value: Optional[Any] = None
    
    # Validation
    validation_passed: bool = False
    validation_errors: List[str] = field(default_factory=list)
    
    # Metadata
    model_used: Optional[str] = None
    tokens_used: int = 0
    computed_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for logging."""
        return {
            "exercise_id": self.exercise_id,
            "spec_id": self.spec_id,
            "spec_version": self.spec_version,
            "success": self.success,
            "value": self.value,
            "validation_passed": self.validation_passed,
            "validation_errors": self.validation_errors,
            "model_used": self.model_used,
            "tokens_used": self.tokens_used,
            "computed_at": self.computed_at.isoformat() if self.computed_at else None,
        }


@dataclass
class ShardResult:
    """
    Result of processing an enrichment shard.
    """
    shard_job_id: str
    parent_job_id: Optional[str]
    spec_id: str
    
    # Counts
    total_exercises: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0  # Already had value (idempotency)
    
    # Results per exercise
    results: List[EnrichmentResult] = field(default_factory=list)
    
    # Timing
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for job result."""
        return {
            "shard_job_id": self.shard_job_id,
            "parent_job_id": self.parent_job_id,
            "spec_id": self.spec_id,
            "total_exercises": self.total_exercises,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "skipped": self.skipped,
            "results": [r.to_dict() for r in self.results],
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


__all__ = [
    "EnrichmentSpec",
    "EnrichmentResult",
    "ShardResult",
]
