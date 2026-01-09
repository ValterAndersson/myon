"""
Family Registry - Firestore operations for exercise_families collection.

The registry stores governance metadata for exercise families.
In Phase 2: advisory (populated from exercises)
In Phase 3+: authoritative (normalization derives from registry)
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from google.cloud import firestore

from app.family.models import FamilyRegistry, FamilyStatus, ExerciseSummary

logger = logging.getLogger(__name__)

# Collection names
FAMILIES_COLLECTION = "exercise_families"
EXERCISES_COLLECTION = "exercises"

# Initialize Firestore client lazily
_db: Optional[firestore.Client] = None


def get_db() -> firestore.Client:
    """Get or initialize Firestore client."""
    global _db
    if _db is None:
        _db = firestore.Client()
    return _db


def get_family_registry(family_slug: str) -> Optional[FamilyRegistry]:
    """
    Get family registry entry.
    
    Args:
        family_slug: Family to look up
        
    Returns:
        FamilyRegistry or None if not found
    """
    db = get_db()
    doc_ref = db.collection(FAMILIES_COLLECTION).document(family_slug)
    doc = doc_ref.get()
    
    if not doc.exists:
        return None
    
    return FamilyRegistry.from_dict(doc.to_dict())


def upsert_family_registry(registry: FamilyRegistry) -> bool:
    """
    Create or update family registry entry.
    
    Args:
        registry: FamilyRegistry to upsert
        
    Returns:
        True if successful
    """
    db = get_db()
    doc_ref = db.collection(FAMILIES_COLLECTION).document(registry.family_slug)
    
    now = datetime.utcnow()
    data = registry.to_dict()
    data["updated_at"] = now
    
    # Check if exists for created_at
    existing = doc_ref.get()
    if not existing.exists:
        data["created_at"] = now
    
    doc_ref.set(data, merge=True)
    logger.info("Upserted family registry: %s", registry.family_slug)
    return True


def list_family_registries(
    status_filter: Optional[FamilyStatus] = None,
    limit: int = 100,
) -> List[FamilyRegistry]:
    """
    List family registry entries.
    
    Args:
        status_filter: Filter by status
        limit: Maximum entries to return
        
    Returns:
        List of FamilyRegistry
    """
    db = get_db()
    query = db.collection(FAMILIES_COLLECTION)
    
    if status_filter:
        query = query.where("status", "==", status_filter.value)
    
    query = query.limit(limit)
    
    return [
        FamilyRegistry.from_dict(doc.to_dict())
        for doc in query.stream()
    ]


def get_family_exercises(family_slug: str) -> List[ExerciseSummary]:
    """
    Get all exercises for a family.
    
    Args:
        family_slug: Family to fetch
        
    Returns:
        List of ExerciseSummary (token-safe projections)
    """
    db = get_db()
    query = (
        db.collection(EXERCISES_COLLECTION)
        .where("family_slug", "==", family_slug)
    )
    
    exercises = []
    for doc in query.stream():
        exercises.append(ExerciseSummary.from_doc(doc.id, doc.to_dict()))
    
    return exercises


def get_or_create_family_registry(family_slug: str) -> FamilyRegistry:
    """
    Get or create family registry, deriving from exercises if needed.
    
    In Phase 2 (advisory mode), we derive registry from existing exercises
    if the registry doesn't exist.
    
    Args:
        family_slug: Family to get/create
        
    Returns:
        FamilyRegistry (existing or newly created)
    """
    # Try to get existing
    registry = get_family_registry(family_slug)
    if registry:
        return registry
    
    # Derive from exercises
    exercises = get_family_exercises(family_slug)
    registry = FamilyRegistry.from_exercises(family_slug, exercises)
    
    # Save it
    upsert_family_registry(registry)
    
    return registry


def get_family_summary(family_slug: str) -> Dict[str, Any]:
    """
    Get complete family summary for agent consumption.
    
    Returns token-safe summary with:
    - Family registry info
    - Exercise list (minimal fields)
    - Equipment analysis
    - Naming issues detected
    
    Args:
        family_slug: Family to summarize
        
    Returns:
        Summary dict
    """
    from app.family.taxonomy import (
        compute_primary_equipment_set,
        validate_equipment_naming,
        detect_duplicate_equipment,
    )
    
    exercises = get_family_exercises(family_slug)
    registry = get_or_create_family_registry(family_slug)
    
    # Update registry with current exercise data
    primary_set = compute_primary_equipment_set(exercises)
    registry.primary_equipment_set = primary_set
    registry.exercise_count = len(exercises)
    
    # Detect naming issues
    naming_errors = []
    for ex in exercises:
        errors = validate_equipment_naming(ex, registry)
        naming_errors.extend(errors)
    
    # Detect duplicates
    duplicates = detect_duplicate_equipment(exercises)
    
    return {
        "family_slug": family_slug,
        "base_name": registry.base_name,
        "status": registry.status.value,
        "exercise_count": len(exercises),
        "exercises": [ex.to_dict() for ex in exercises],
        "primary_equipment_set": list(primary_set),
        "allowed_equipments": registry.allowed_equipments,
        "is_multi_equipment": registry.is_multi_equipment(),
        "needs_equipment_suffixes": registry.needs_equipment_suffixes(),
        "naming_errors": naming_errors,
        "duplicate_equipment": duplicates,
        "registry_exists": get_family_registry(family_slug) is not None,
    }


__all__ = [
    "get_family_registry",
    "upsert_family_registry",
    "list_family_registries",
    "get_family_exercises",
    "get_or_create_family_registry",
    "get_family_summary",
]
