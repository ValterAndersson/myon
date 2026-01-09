"""
Family Models - Data models for family registry and exercise summaries.

Firestore Collections:
- exercise_families/{family_slug}: Family registry (advisory, becomes authoritative)
- exercises/{doc_id}: Exercise documents (doc_id is authoritative)

Key design decisions:
- FamilyRegistry.base_name is ADVISORY in Phase 2, authoritative in Phase 3+
- doc_id (Firestore document ID) is authoritative for exercise identity
- primary_equipment = equipment[0] for multi-equipment checks
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set


class FamilyStatus(str, Enum):
    """Family registry status."""
    ACTIVE = "active"
    NEEDS_REVIEW = "needs_review"
    DEPRECATED = "deprecated"
    MERGED_INTO = "merged_into"


@dataclass
class ExerciseSummary:
    """
    Token-safe exercise summary for family operations.
    
    This is a minimal projection of exercise documents to reduce
    token usage when working with families.
    """
    doc_id: str
    name: str
    name_slug: str
    family_slug: str
    equipment: List[str] = field(default_factory=list)
    status: str = "approved"
    
    # Derived fields
    primary_equipment: Optional[str] = None
    
    def __post_init__(self):
        """Derive primary equipment from equipment list."""
        if self.equipment and not self.primary_equipment:
            self.primary_equipment = self.equipment[0]
    
    @classmethod
    def from_doc(cls, doc_id: str, data: Dict[str, Any]) -> "ExerciseSummary":
        """
        Create from Firestore document.
        
        Args:
            doc_id: Firestore document ID (authoritative)
            data: Document data
            
        Returns:
            ExerciseSummary
        """
        equipment = data.get("equipment", [])
        return cls(
            doc_id=doc_id,
            name=data.get("name", ""),
            name_slug=data.get("name_slug", ""),
            family_slug=data.get("family_slug", ""),
            equipment=equipment,
            status=data.get("status", "approved"),
            primary_equipment=equipment[0] if equipment else None,
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "doc_id": self.doc_id,
            "name": self.name,
            "name_slug": self.name_slug,
            "family_slug": self.family_slug,
            "equipment": self.equipment,
            "status": self.status,
            "primary_equipment": self.primary_equipment,
        }
    
    def has_equipment_in_name(self) -> bool:
        """Check if name includes equipment qualifier."""
        return "(" in self.name and ")" in self.name
    
    def extract_name_equipment(self) -> Optional[str]:
        """
        Extract equipment from name if present.
        
        Returns:
            Equipment string from name (e.g., "Barbell") or None
        """
        match = re.search(r'\(([^)]+)\)$', self.name)
        return match.group(1) if match else None


@dataclass
class FamilyRegistry:
    """
    Family registry entry.
    
    This is governance metadata, NOT a parent exercise.
    In Phase 2: advisory (derived from exercise names)
    In Phase 3+: authoritative (normalization derives from registry)
    """
    family_slug: str
    base_name: str
    status: FamilyStatus = FamilyStatus.ACTIVE
    
    # Equipment tracking
    allowed_equipments: List[str] = field(default_factory=list)
    primary_equipment_set: Set[str] = field(default_factory=set)
    
    # Counts (denormalized for efficiency)
    exercise_count: int = 0
    
    # Migration state
    merged_into: Optional[str] = None
    
    # Notes
    notes: Optional[str] = None
    known_collisions: List[str] = field(default_factory=list)
    
    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to Firestore-compatible dict."""
        return {
            "family_slug": self.family_slug,
            "base_name": self.base_name,
            "status": self.status.value if isinstance(self.status, FamilyStatus) else self.status,
            "allowed_equipments": self.allowed_equipments,
            "primary_equipment_set": list(self.primary_equipment_set),
            "exercise_count": self.exercise_count,
            "merged_into": self.merged_into,
            "notes": self.notes,
            "known_collisions": self.known_collisions,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FamilyRegistry":
        """Create from Firestore dict."""
        status_raw = data.get("status", "active")
        try:
            status = FamilyStatus(status_raw)
        except ValueError:
            status = FamilyStatus.ACTIVE
        
        return cls(
            family_slug=data.get("family_slug", ""),
            base_name=data.get("base_name", ""),
            status=status,
            allowed_equipments=data.get("allowed_equipments", []),
            primary_equipment_set=set(data.get("primary_equipment_set", [])),
            exercise_count=data.get("exercise_count", 0),
            merged_into=data.get("merged_into"),
            notes=data.get("notes"),
            known_collisions=data.get("known_collisions", []),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )
    
    @classmethod
    def from_exercises(
        cls,
        family_slug: str,
        exercises: List[ExerciseSummary],
    ) -> "FamilyRegistry":
        """
        Derive registry from existing exercises (Phase 2 advisory mode).
        
        Args:
            family_slug: Family slug
            exercises: List of exercise summaries
            
        Returns:
            FamilyRegistry derived from exercises
        """
        if not exercises:
            return cls(family_slug=family_slug, base_name=family_slug.replace("_", " ").title())
        
        # Compute primary equipment set
        primary_set = set()
        all_equipment = set()
        for ex in exercises:
            if ex.primary_equipment:
                primary_set.add(ex.primary_equipment)
            all_equipment.update(ex.equipment)
        
        # Derive base name from first exercise (strip equipment suffix)
        first_name = exercises[0].name
        base_name = re.sub(r'\s*\([^)]+\)\s*$', '', first_name).strip()
        
        return cls(
            family_slug=family_slug,
            base_name=base_name,
            status=FamilyStatus.ACTIVE,
            allowed_equipments=sorted(all_equipment),
            primary_equipment_set=primary_set,
            exercise_count=len(exercises),
        )
    
    def is_multi_equipment(self) -> bool:
        """Check if family has multiple primary equipment types."""
        return len(self.primary_equipment_set) > 1
    
    def needs_equipment_suffixes(self) -> bool:
        """Check if exercises need equipment suffixes in names."""
        return self.is_multi_equipment()


__all__ = [
    "FamilyStatus",
    "ExerciseSummary",
    "FamilyRegistry",
]
