"""
Catalog Read Skills - Token-safe read operations for catalog data.

These are pure skill functions (not ADK tools). They are called by the
tool wrappers in app/shell/tools.py.

Phase 0: Stub implementations returning mock data.
Phase 1+: Full Firestore-backed implementations.

Key principle: doc_id (Firestore document ID) is authoritative, not the 
exercise.id field inside the document.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


async def get_family_summary(family_slug: str) -> Dict[str, Any]:
    """
    Get summary of a family.
    
    Returns token-safe summary with minimal fields per exercise.
    
    Args:
        family_slug: Family to summarize
        
    Returns:
        Summary with exercise list, equipment types, conflict flags
    """
    logger.info("get_family_summary: family=%s", family_slug)
    
    # Phase 0: Return mock data
    return {
        "family_slug": family_slug,
        "exercise_count": 0,
        "exercises": [],
        "primary_equipment_set": [],
        "has_equipment_conflicts": False,
        "registry_exists": False,
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
            "error": "Maximum 25 doc_ids per batch",
            "exercises": {},
            "missing": doc_ids,
        }
    
    # Phase 0: Return mock data
    return {
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
    
    # Phase 0: Return mock data
    return {
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
    logger.info("get_family_registry: family=%s", family_slug)
    
    # Phase 0: Return mock data
    return {
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
    
    Args:
        min_size: Minimum exercises per family
        limit: Maximum families to return
        status_filter: Filter by registry status
        
    Returns:
        Dict with families list and total count
    """
    logger.info("list_families_summary: min_size=%d, limit=%d", min_size, limit)
    
    # Phase 0: Return mock data
    return {
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
