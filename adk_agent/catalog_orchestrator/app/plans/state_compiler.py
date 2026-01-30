"""
State Compiler - Compile plans against family snapshot to produce post-state.

The PlanCompiler simulates applying operations to a FamilySnapshot and
produces a CompiledPlan with the expected post-state. This enables:
- Pre-apply validation against post-state (not raw ops)
- Collision detection (slug collisions, alias conflicts)
- Diff computation for dry-run preview

Uses the same path utilities as ApplyEngine for consistent semantics.
"""

from __future__ import annotations

import logging
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from app.plans.models import ChangePlan, Operation, OperationType, ValidationResult
from app.apply.paths import (
    DELETE_SENTINEL,
    apply_patch,
    get_in,
    set_in,
)

logger = logging.getLogger(__name__)


@dataclass
class ExerciseDoc:
    """
    Minimal exercise document for snapshot.

    V1.2: Updated to use new schema with muscles object instead of
    legacy primary_muscles/secondary_muscles fields.

    Note: 'status' is kept for backwards compatibility with DEPRECATE_EXERCISE
    operations but is being phased out via SCHEMA_CLEANUP jobs.
    """
    doc_id: str
    name: str
    name_slug: str
    family_slug: str
    equipment: List[str] = field(default_factory=list)
    category: str = "compound"
    muscles: Dict[str, Any] = field(default_factory=lambda: {
        "primary": [],
        "secondary": [],
        "category": [],
        "contribution": {},
    })
    metadata: Dict[str, Any] = field(default_factory=lambda: {
        "level": "intermediate",
    })
    movement: Dict[str, Any] = field(default_factory=dict)
    # Legacy field - kept for DEPRECATE_EXERCISE simulation
    status: Optional[str] = None

    @property
    def primary_equipment(self) -> Optional[str]:
        """Get primary equipment (first in array)."""
        return self.equipment[0] if self.equipment else None

    @property
    def primary_muscles(self) -> List[str]:
        """Backwards compatibility: get primary muscles from muscles object."""
        return self.muscles.get("primary", [])

    @property
    def secondary_muscles(self) -> List[str]:
        """Backwards compatibility: get secondary muscles from muscles object."""
        return self.muscles.get("secondary", [])

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "doc_id": self.doc_id,
            "name": self.name,
            "name_slug": self.name_slug,
            "family_slug": self.family_slug,
            "equipment": self.equipment,
            "category": self.category,
            "muscles": self.muscles,
            "metadata": self.metadata,
            "movement": self.movement,
        }
        # Only include status if set (for backwards compatibility)
        if self.status is not None:
            result["status"] = self.status
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExerciseDoc":
        # Handle both new schema (muscles.primary) and legacy (primary_muscles)
        muscles = data.get("muscles")
        if muscles is None:
            # Legacy schema - convert to new format
            muscles = {
                "primary": data.get("primary_muscles", []),
                "secondary": data.get("secondary_muscles", []),
                "category": [],
                "contribution": {},
            }

        return cls(
            doc_id=data.get("doc_id") or data.get("id", ""),
            name=data.get("name", ""),
            name_slug=data.get("name_slug", ""),
            family_slug=data.get("family_slug", ""),
            equipment=data.get("equipment", []),
            category=data.get("category", "compound"),
            muscles=muscles,
            metadata=data.get("metadata", {"level": "intermediate"}),
            movement=data.get("movement", {}),
            status=data.get("status"),
        )


@dataclass
class AliasDoc:
    """Alias document for snapshot."""
    alias_slug: str
    exercise_id: Optional[str] = None
    family_slug: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {"alias_slug": self.alias_slug}
        if self.exercise_id:
            result["exercise_id"] = self.exercise_id
        if self.family_slug:
            result["family_slug"] = self.family_slug
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AliasDoc":
        return cls(
            alias_slug=data.get("alias_slug", ""),
            exercise_id=data.get("exercise_id"),
            family_slug=data.get("family_slug"),
        )
    
    def is_valid(self) -> bool:
        """Check one-of invariant: exactly one of exercise_id XOR family_slug."""
        has_exercise = bool(self.exercise_id)
        has_family = bool(self.family_slug)
        return has_exercise != has_family  # XOR


@dataclass
class FamilySnapshot:
    """
    Snapshot of a family's state.
    
    Contains exercises and aliases relevant to the operation scope.
    Used as input to PlanCompiler for post-state simulation.
    """
    family_slug: str
    exercises: Dict[str, ExerciseDoc] = field(default_factory=dict)
    aliases: Dict[str, AliasDoc] = field(default_factory=dict)
    registry: Optional[Dict[str, Any]] = None
    
    def get_primary_equipment_set(self) -> Set[str]:
        """
        Get set of primary equipment (equipment[0]) across all exercises.
        
        This is the correct way to determine if family is multi-equipment.
        """
        return {
            ex.primary_equipment
            for ex in self.exercises.values()
            if ex.primary_equipment and ex.status != "deprecated"
        }
    
    def is_multi_equipment(self) -> bool:
        """Check if family has multiple primary equipment types."""
        return len(self.get_primary_equipment_set()) > 1
    
    def get_exercise_slugs(self) -> Set[str]:
        """Get all name_slugs in snapshot."""
        return {ex.name_slug for ex in self.exercises.values()}
    
    def get_alias_slugs(self) -> Set[str]:
        """Get all alias_slugs in snapshot."""
        return set(self.aliases.keys())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "family_slug": self.family_slug,
            "exercises": {k: v.to_dict() for k, v in self.exercises.items()},
            "aliases": {k: v.to_dict() for k, v in self.aliases.items()},
            "registry": self.registry,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FamilySnapshot":
        return cls(
            family_slug=data.get("family_slug", ""),
            exercises={
                k: ExerciseDoc.from_dict(v)
                for k, v in data.get("exercises", {}).items()
            },
            aliases={
                k: AliasDoc.from_dict(v)
                for k, v in data.get("aliases", {}).items()
            },
            registry=data.get("registry"),
        )


@dataclass
class OperationDiff:
    """Diff for a single operation."""
    operation_index: int
    op_type: str
    targets: List[str]
    changes: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "operation_index": self.operation_index,
            "op_type": self.op_type,
            "targets": self.targets,
            "changes": self.changes,
        }


@dataclass
class CompiledPlan:
    """
    Result of compiling a ChangePlan against a FamilySnapshot.
    
    Contains the expected post-state for validation.
    """
    plan: ChangePlan
    before_state: FamilySnapshot
    post_state: FamilySnapshot
    diffs: List[OperationDiff] = field(default_factory=list)
    primary_equipment_set: Set[str] = field(default_factory=set)
    slugs_touched: Set[str] = field(default_factory=set)
    aliases_touched: Set[str] = field(default_factory=set)
    compilation_errors: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_job_id": self.plan.job_id,
            "plan_job_type": self.plan.job_type,
            "before_state": self.before_state.to_dict(),
            "post_state": self.post_state.to_dict(),
            "diffs": [d.to_dict() for d in self.diffs],
            "primary_equipment_set": list(self.primary_equipment_set),
            "slugs_touched": list(self.slugs_touched),
            "aliases_touched": list(self.aliases_touched),
            "compilation_errors": self.compilation_errors,
        }


class PlanCompiler:
    """
    Compile a ChangePlan against a FamilySnapshot to produce post-state.
    
    The compiler simulates applying all operations in order and produces
    the expected post-state. This enables pre-apply validation.
    """
    
    def __init__(self):
        self.errors: List[Dict[str, Any]] = []
    
    def compile(
        self,
        plan: ChangePlan,
        snapshot: FamilySnapshot,
    ) -> CompiledPlan:
        """
        Compile a plan against a snapshot.
        
        Args:
            plan: Change plan to compile
            snapshot: Current state snapshot
            
        Returns:
            CompiledPlan with post-state
        """
        self.errors = []
        
        # Deep copy snapshot for post-state mutation
        post_state = FamilySnapshot(
            family_slug=snapshot.family_slug,
            exercises={k: deepcopy(v) for k, v in snapshot.exercises.items()},
            aliases={k: deepcopy(v) for k, v in snapshot.aliases.items()},
            registry=deepcopy(snapshot.registry) if snapshot.registry else None,
        )
        
        diffs = []
        slugs_touched = set()
        aliases_touched = set()
        
        for idx, op in enumerate(plan.operations):
            if op.op_type == OperationType.NO_CHANGE:
                continue
            
            try:
                diff = self._apply_op_to_state(idx, op, post_state)
                if diff:
                    diffs.append(diff)
                    slugs_touched.update(diff.targets)
                    
                    # Track alias touches
                    if op.op_type in (OperationType.UPSERT_ALIAS, OperationType.DELETE_ALIAS):
                        aliases_touched.update(diff.targets)
                        
            except Exception as e:
                self.errors.append({
                    "operation_index": idx,
                    "error": str(e),
                    "type": type(e).__name__,
                })
        
        return CompiledPlan(
            plan=plan,
            before_state=snapshot,
            post_state=post_state,
            diffs=diffs,
            primary_equipment_set=post_state.get_primary_equipment_set(),
            slugs_touched=slugs_touched,
            aliases_touched=aliases_touched,
            compilation_errors=self.errors,
        )
    
    def _apply_op_to_state(
        self,
        idx: int,
        op: Operation,
        state: FamilySnapshot,
    ) -> Optional[OperationDiff]:
        """Apply a single operation to state, returning diff."""
        
        handlers = {
            OperationType.RENAME_EXERCISE: self._sim_rename_exercise,
            OperationType.PATCH_FIELDS: self._sim_patch_fields,
            OperationType.UPSERT_ALIAS: self._sim_upsert_alias,
            OperationType.DELETE_ALIAS: self._sim_delete_alias,
            OperationType.CREATE_EXERCISE: self._sim_create_exercise,
            OperationType.DEPRECATE_EXERCISE: self._sim_deprecate_exercise,
            OperationType.REASSIGN_FAMILY: self._sim_reassign_family,
        }
        
        handler = handlers.get(op.op_type)
        if not handler:
            return None
        
        return handler(idx, op, state)
    
    def _sim_rename_exercise(
        self,
        idx: int,
        op: Operation,
        state: FamilySnapshot,
    ) -> Optional[OperationDiff]:
        """Simulate RENAME_EXERCISE."""
        if not op.targets or not op.after:
            return None
        
        doc_id = op.targets[0]
        exercise = state.exercises.get(doc_id)
        
        if not exercise:
            self.errors.append({
                "operation_index": idx,
                "error": f"Exercise {doc_id} not in snapshot",
            })
            return None
        
        changes = {}
        
        old_name = exercise.name
        old_slug = exercise.name_slug
        new_name = op.after.get("name", old_name)
        new_slug = op.after.get("name_slug", old_slug)
        
        if old_name != new_name:
            changes["name"] = {"before": old_name, "after": new_name}
            exercise.name = new_name
        
        if old_slug != new_slug:
            changes["name_slug"] = {"before": old_slug, "after": new_slug}
            exercise.name_slug = new_slug
        
        return OperationDiff(
            operation_index=idx,
            op_type=op.op_type.value,
            targets=[doc_id],
            changes=changes,
        )
    
    def _sim_patch_fields(
        self,
        idx: int,
        op: Operation,
        state: FamilySnapshot,
    ) -> Optional[OperationDiff]:
        """Simulate PATCH_FIELDS using dotted path semantics."""
        if not op.targets or not op.patch:
            return None
        
        doc_id = op.targets[0]
        exercise = state.exercises.get(doc_id)
        
        if not exercise:
            self.errors.append({
                "operation_index": idx,
                "error": f"Exercise {doc_id} not in snapshot",
            })
            return None
        
        changes = {}
        exercise_dict = exercise.to_dict()
        
        for path, value in op.patch.items():
            before_val = get_in(exercise_dict, path)
            
            if value == DELETE_SENTINEL:
                changes[path] = {"before": before_val, "after": None}
                exercise_dict = set_in(exercise_dict, path, DELETE_SENTINEL)
            else:
                changes[path] = {"before": before_val, "after": value}
                exercise_dict = set_in(exercise_dict, path, value)
        
        # Update exercise from dict (new schema)
        exercise.name = exercise_dict.get("name", exercise.name)
        exercise.name_slug = exercise_dict.get("name_slug", exercise.name_slug)
        exercise.family_slug = exercise_dict.get("family_slug", exercise.family_slug)
        exercise.equipment = exercise_dict.get("equipment", exercise.equipment)
        exercise.category = exercise_dict.get("category", exercise.category)
        exercise.muscles = exercise_dict.get("muscles", exercise.muscles)
        exercise.metadata = exercise_dict.get("metadata", exercise.metadata)
        exercise.movement = exercise_dict.get("movement", exercise.movement)
        
        return OperationDiff(
            operation_index=idx,
            op_type=op.op_type.value,
            targets=[doc_id],
            changes=changes,
        )
    
    def _sim_upsert_alias(
        self,
        idx: int,
        op: Operation,
        state: FamilySnapshot,
    ) -> Optional[OperationDiff]:
        """Simulate UPSERT_ALIAS."""
        if not op.targets or not op.patch:
            return None
        
        alias_slug = op.targets[0]
        existing = state.aliases.get(alias_slug)
        
        exercise_id = op.patch.get("exercise_id")
        family_slug = op.patch.get("family_slug")
        
        changes = {}
        
        if existing:
            changes["exercise_id"] = {
                "before": existing.exercise_id,
                "after": exercise_id,
            }
            changes["family_slug"] = {
                "before": existing.family_slug,
                "after": family_slug,
            }
        else:
            changes["exercise_id"] = {"before": None, "after": exercise_id}
            changes["family_slug"] = {"before": None, "after": family_slug}
        
        # Update or create alias
        state.aliases[alias_slug] = AliasDoc(
            alias_slug=alias_slug,
            exercise_id=exercise_id,
            family_slug=family_slug,
        )
        
        return OperationDiff(
            operation_index=idx,
            op_type=op.op_type.value,
            targets=[alias_slug],
            changes=changes,
        )
    
    def _sim_delete_alias(
        self,
        idx: int,
        op: Operation,
        state: FamilySnapshot,
    ) -> Optional[OperationDiff]:
        """Simulate DELETE_ALIAS."""
        if not op.targets:
            return None
        
        alias_slug = op.targets[0]
        existing = state.aliases.get(alias_slug)
        
        if not existing:
            return None  # Already deleted
        
        changes = {
            "exercise_id": {"before": existing.exercise_id, "after": None},
            "family_slug": {"before": existing.family_slug, "after": None},
        }
        
        del state.aliases[alias_slug]
        
        return OperationDiff(
            operation_index=idx,
            op_type=op.op_type.value,
            targets=[alias_slug],
            changes=changes,
        )
    
    def _sim_create_exercise(
        self,
        idx: int,
        op: Operation,
        state: FamilySnapshot,
    ) -> Optional[OperationDiff]:
        """Simulate CREATE_EXERCISE."""
        if not op.patch:
            return None
        
        from app.apply.engine import derive_deterministic_doc_id
        
        family_slug = op.patch.get("family_slug", "")
        name_slug = op.patch.get("name_slug", "")
        
        if op.targets:
            doc_id = op.targets[0]
        else:
            doc_id = derive_deterministic_doc_id(family_slug, name_slug)
        
        # Check if already exists
        if doc_id in state.exercises:
            return None  # Idempotent
        
        # Handle both new schema (muscles) and legacy (primary_muscles)
        muscles = op.patch.get("muscles")
        if muscles is None:
            muscles = {
                "primary": op.patch.get("primary_muscles", []),
                "secondary": op.patch.get("secondary_muscles", []),
                "category": [],
                "contribution": {},
            }

        exercise = ExerciseDoc(
            doc_id=doc_id,
            name=op.patch.get("name", ""),
            name_slug=name_slug,
            family_slug=family_slug,
            equipment=op.patch.get("equipment", []),
            category=op.patch.get("category", "compound"),
            muscles=muscles,
            metadata=op.patch.get("metadata", {"level": "intermediate"}),
            movement=op.patch.get("movement", {}),
            status=op.patch.get("status"),
        )
        
        state.exercises[doc_id] = exercise
        
        changes = {k: {"before": None, "after": v} for k, v in op.patch.items()}
        
        return OperationDiff(
            operation_index=idx,
            op_type=op.op_type.value,
            targets=[doc_id],
            changes=changes,
        )
    
    def _sim_deprecate_exercise(
        self,
        idx: int,
        op: Operation,
        state: FamilySnapshot,
    ) -> Optional[OperationDiff]:
        """Simulate DEPRECATE_EXERCISE."""
        if not op.targets:
            return None
        
        doc_id = op.targets[0]
        exercise = state.exercises.get(doc_id)
        
        if not exercise:
            return None
        
        changes = {"status": {"before": exercise.status, "after": "deprecated"}}
        exercise.status = "deprecated"
        
        return OperationDiff(
            operation_index=idx,
            op_type=op.op_type.value,
            targets=[doc_id],
            changes=changes,
        )
    
    def _sim_reassign_family(
        self,
        idx: int,
        op: Operation,
        state: FamilySnapshot,
    ) -> Optional[OperationDiff]:
        """Simulate REASSIGN_FAMILY."""
        if not op.targets or not op.patch:
            return None
        
        new_family = op.patch.get("family_slug")
        if not new_family:
            return None
        
        changes = {}
        
        for doc_id in op.targets:
            exercise = state.exercises.get(doc_id)
            if exercise:
                changes[doc_id] = {
                    "family_slug": {
                        "before": exercise.family_slug,
                        "after": new_family,
                    }
                }
                exercise.family_slug = new_family
        
        return OperationDiff(
            operation_index=idx,
            op_type=op.op_type.value,
            targets=op.targets,
            changes=changes,
        )


def compile_plan(
    plan: ChangePlan,
    snapshot: FamilySnapshot,
) -> CompiledPlan:
    """
    Compile a change plan against a snapshot.
    
    Convenience function.
    
    Args:
        plan: Change plan
        snapshot: Family snapshot
        
    Returns:
        CompiledPlan with post-state
    """
    compiler = PlanCompiler()
    return compiler.compile(plan, snapshot)


def fetch_family_snapshot(family_slug: str) -> FamilySnapshot:
    """
    Fetch a family snapshot from Firestore.
    
    Args:
        family_slug: Family slug to fetch
        
    Returns:
        FamilySnapshot with exercises and aliases
    """
    from google.cloud import firestore
    
    db = firestore.Client()
    
    # Fetch exercises
    exercises = {}
    query = db.collection("exercises").where("family_slug", "==", family_slug)
    for doc in query.stream():
        data = doc.to_dict()
        data["doc_id"] = doc.id
        exercises[doc.id] = ExerciseDoc.from_dict(data)
    
    # Fetch aliases for this family's exercises
    exercise_ids = set(exercises.keys())
    aliases = {}
    
    # Also include family-level aliases
    for doc in db.collection("exercise_aliases").stream():
        data = doc.to_dict()
        data["alias_slug"] = doc.id
        
        if data.get("exercise_id") in exercise_ids or data.get("family_slug") == family_slug:
            aliases[doc.id] = AliasDoc.from_dict(data)
    
    # Fetch registry if exists
    registry = None
    registry_doc = db.collection("exercise_families").document(family_slug).get()
    if registry_doc.exists:
        registry = registry_doc.to_dict()
    
    return FamilySnapshot(
        family_slug=family_slug,
        exercises=exercises,
        aliases=aliases,
        registry=registry,
    )


__all__ = [
    "ExerciseDoc",
    "AliasDoc",
    "FamilySnapshot",
    "OperationDiff",
    "CompiledPlan",
    "PlanCompiler",
    "compile_plan",
    "fetch_family_snapshot",
]
