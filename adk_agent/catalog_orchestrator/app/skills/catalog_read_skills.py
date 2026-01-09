"""
Catalog Read Skills - Token-safe read operations for catalog data.

These are pure skill functions (not ADK tools). They are called by the
tool wrappers in app/shell/tools.py.

Uses the family package for Firestore operations and taxonomy rules.

Key principle: doc_id (Firestore document ID) is authoritative, not the 
exercise.id field inside the document.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from google.cloud import firestore

logger = logging.getLogger(__name__)

# Initialize Firestore client lazily
_db: Optional[firestore.Client] = None


def _get_db() -> firestore.Client:
    """Get or initialize Firestore client."""
    global _db
    if _db is None:
        _db = firestore.Client()
    return _db


async def get_family_summary(family_slug: str) -> Dict[str, Any]:
    """
    Get summary of a family.
    
    Returns token-safe summary with minimal fields per exercise.
    Includes naming issues and duplicate detection.
    
    Args:
        family_slug: Family to summarize
        
    Returns:
        Summary with exercise list, equipment types, conflict flags
    """
    from app.family.registry import get_family_summary as _get_summary
    
    logger.info("get_family_summary: family=%s", family_slug)
    
    try:
        summary = _get_summary(family_slug)
        summary["success"] = True
        return summary
    except Exception as e:
        logger.error("get_family_summary failed: %s", e)
        return {
            "success": False,
            "error": str(e),
            "family_slug": family_slug,
        }


async def get_exercises_batch(doc_ids: List[str]) -> Dict[str, Any]:
    """
    Get full exercise documents by Firestore document IDs.
    
    Args:
        doc_ids: List of document IDs (max 25)
        
    Returns:
        Dict with exercises (doc_id → document) and missing (list of not found)
    """
    logger.info("get_exercises_batch: count=%d", len(doc_ids))
    
    if len(doc_ids) > 25:
        return {
            "success": False,
            "error": "Maximum 25 doc_ids per batch",
            "exercises": {},
            "missing": doc_ids,
        }
    
    if not doc_ids:
        return {
            "success": True,
            "exercises": {},
            "missing": [],
        }
    
    try:
        db = _get_db()
        exercises = {}
        missing = []
        
        for doc_id in doc_ids:
            doc_ref = db.collection("exercises").document(doc_id)
            doc = doc_ref.get()
            
            if doc.exists:
                data = doc.to_dict()
                data["doc_id"] = doc.id  # Ensure doc_id is present
                exercises[doc.id] = data
            else:
                missing.append(doc_id)
        
        return {
            "success": True,
            "exercises": exercises,
            "missing": missing,
        }
    except Exception as e:
        logger.error("get_exercises_batch failed: %s", e)
        return {
            "success": False,
            "error": str(e),
            "exercises": {},
            "missing": doc_ids,
        }


async def get_family_aliases(family_slug: str) -> Dict[str, Any]:
    """
    Get all aliases that target exercises in a family.
    
    Args:
        family_slug: Family to get aliases for
        
    Returns:
        Dict with aliases list and exercise_aliases mapping
    """
    logger.info("get_family_aliases: family=%s", family_slug)
    
    try:
        from app.family.registry import get_family_exercises
        
        db = _get_db()
        exercises = get_family_exercises(family_slug)
        
        if not exercises:
            return {
                "success": True,
                "family_slug": family_slug,
                "aliases": [],
                "exercise_aliases": {},
            }
        
        # Get doc_ids
        doc_ids = [ex.doc_id for ex in exercises]
        
        # Query aliases that point to these exercises
        aliases = []
        exercise_aliases: Dict[str, List[str]] = {doc_id: [] for doc_id in doc_ids}
        
        # Query by exercise_id
        for doc_id in doc_ids:
            query = (
                db.collection("exercise_aliases")
                .where("exercise_id", "==", doc_id)
            )
            for doc in query.stream():
                alias_data = doc.to_dict()
                alias_data["alias_slug"] = doc.id
                aliases.append(alias_data)
                exercise_aliases[doc_id].append(doc.id)
        
        # Also query by family_slug
        query = (
            db.collection("exercise_aliases")
            .where("family_slug", "==", family_slug)
        )
        for doc in query.stream():
            alias_data = doc.to_dict()
            alias_data["alias_slug"] = doc.id
            alias_data["is_family_alias"] = True
            aliases.append(alias_data)
        
        return {
            "success": True,
            "family_slug": family_slug,
            "aliases": aliases,
            "exercise_aliases": exercise_aliases,
        }
    except Exception as e:
        logger.error("get_family_aliases failed: %s", e)
        return {
            "success": False,
            "error": str(e),
            "family_slug": family_slug,
            "aliases": [],
            "exercise_aliases": {},
        }


async def get_family_registry(family_slug: str) -> Dict[str, Any]:
    """
    Get the family registry entry.
    
    Args:
        family_slug: Family to look up
        
    Returns:
        Dict with exists flag and registry data
    """
    from app.family.registry import get_family_registry as _get_registry
    
    logger.info("get_family_registry: family=%s", family_slug)
    
    try:
        registry = _get_registry(family_slug)
        
        if registry:
            return {
                "success": True,
                "exists": True,
                "registry": registry.to_dict(),
            }
        else:
            return {
                "success": True,
                "exists": False,
                "registry": None,
            }
    except Exception as e:
        logger.error("get_family_registry failed: %s", e)
        return {
            "success": False,
            "error": str(e),
            "exists": False,
            "registry": None,
        }


async def list_families_summary(
    min_size: int = 1,
    limit: int = 50,
    status_filter: Optional[str] = None,
) -> Dict[str, Any]:
    """
    List families with summary stats.
    
    Groups exercises by family_slug and returns summaries.
    
    Args:
        min_size: Minimum exercises per family
        limit: Maximum families to return
        status_filter: Filter by registry status
        
    Returns:
        Dict with families list and total count
    """
    logger.info("list_families_summary: min_size=%d, limit=%d", min_size, limit)
    
    try:
        db = _get_db()
        
        # Get distinct family_slugs with counts
        # Note: Firestore doesn't support GROUP BY, so we do this client-side
        # For production, consider a Cloud Function or aggregation
        
        query = db.collection("exercises").select(["family_slug"])
        
        family_counts: Dict[str, int] = {}
        for doc in query.stream():
            data = doc.to_dict()
            slug = data.get("family_slug", "")
            if slug:
                family_counts[slug] = family_counts.get(slug, 0) + 1
        
        # Filter by min_size
        families = [
            {"family_slug": slug, "exercise_count": count}
            for slug, count in family_counts.items()
            if count >= min_size
        ]
        
        # Sort by count descending
        families.sort(key=lambda f: f["exercise_count"], reverse=True)
        
        # Apply limit
        families = families[:limit]
        
        return {
            "success": True,
            "families": families,
            "total": len(family_counts),
            "returned": len(families),
        }
    except Exception as e:
        logger.error("list_families_summary failed: %s", e)
        return {
            "success": False,
            "error": str(e),
            "families": [],
            "total": 0,
        }


__all__ = [
    "get_family_summary",
    "get_exercises_batch",
    "get_family_aliases",
    "get_family_registry",
    "list_families_summary",
]
