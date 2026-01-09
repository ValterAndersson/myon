"""
Catalog API Client - HTTP client for Firebase Functions catalog endpoints.

Phase 0: Stub implementation.
Phase 1+: Full implementation with retry/backoff, timeouts, structured errors.

This client is used by skills to fetch catalog data from Firebase Functions.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.libs.tools_common.http import make_request

logger = logging.getLogger(__name__)


class CatalogClient:
    """
    HTTP client for catalog Firebase Functions.
    
    All methods return structured responses with success/error indicators.
    """
    
    def __init__(self, base_url: Optional[str] = None):
        """
        Initialize client.
        
        Args:
            base_url: Base URL for Firebase Functions (defaults to env var)
        """
        import os
        self.base_url = base_url or os.getenv(
            "FIREBASE_FUNCTIONS_URL",
            "https://us-central1-PROJECT_ID.cloudfunctions.net"
        )
    
    async def get_exercises_by_family(
        self,
        family_slug: str,
        fields: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Get exercises for a family.
        
        Args:
            family_slug: Family to fetch
            fields: Optional list of fields to return (for token safety)
            
        Returns:
            Response with exercises list
        """
        # Phase 0: Stub
        logger.info("get_exercises_by_family: family=%s", family_slug)
        return {
            "success": True,
            "exercises": [],
            "_mock": True,
        }
    
    async def get_exercises_batch(
        self,
        doc_ids: List[str],
    ) -> Dict[str, Any]:
        """
        Get exercises by document IDs.
        
        Args:
            doc_ids: List of Firestore document IDs
            
        Returns:
            Response with exercises dict and missing list
        """
        # Phase 0: Stub
        logger.info("get_exercises_batch: count=%d", len(doc_ids))
        return {
            "success": True,
            "exercises": {},
            "missing": doc_ids,
            "_mock": True,
        }
    
    async def get_aliases_by_family(
        self,
        family_slug: str,
    ) -> Dict[str, Any]:
        """
        Get aliases for exercises in a family.
        
        Args:
            family_slug: Family to fetch aliases for
            
        Returns:
            Response with aliases list
        """
        # Phase 0: Stub
        logger.info("get_aliases_by_family: family=%s", family_slug)
        return {
            "success": True,
            "aliases": [],
            "_mock": True,
        }
    
    async def get_family_registry(
        self,
        family_slug: str,
    ) -> Dict[str, Any]:
        """
        Get family registry entry.
        
        Args:
            family_slug: Family to look up
            
        Returns:
            Response with exists flag and registry data
        """
        # Phase 0: Stub
        logger.info("get_family_registry: family=%s", family_slug)
        return {
            "success": True,
            "exists": False,
            "registry": None,
            "_mock": True,
        }


# Singleton instance
_client: Optional[CatalogClient] = None


def get_catalog_client() -> CatalogClient:
    """Get or create the catalog client singleton."""
    global _client
    if _client is None:
        _client = CatalogClient()
    return _client


__all__ = [
    "CatalogClient",
    "get_catalog_client",
]
