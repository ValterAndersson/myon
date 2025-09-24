"""
Standalone Firebase Functions Client for multi_agent_system.
This is a copy without relative imports to avoid pulling in app/__init__.py
which imports Agent Engine SDK components.
"""
from __future__ import annotations

import json
import requests
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class FirebaseFunctionsClient:
    base_url: str
    api_key: Optional[str] = None
    bearer_token: Optional[str] = None
    user_id: Optional[str] = None
    timeout_seconds: int = 30

    def __post_init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
        })
        if self.api_key:
            self.session.headers["X-API-Key"] = self.api_key
        if self.bearer_token:
            self.session.headers["Authorization"] = f"Bearer {self.bearer_token}"
        if self.user_id:
            self.session.headers["X-User-Id"] = self.user_id

    def _request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict[str, Any]:
        url = f"{self.base_url.rstrip('/')}/{endpoint}"
        
        kwargs = {"timeout": self.timeout_seconds}
        if data is not None:
            kwargs["json"] = data
            
        response = self.session.request(method, url, **kwargs)
        
        # Handle non-JSON responses
        if response.status_code == 204:
            return {}
            
        try:
            result = response.json()
        except json.JSONDecodeError:
            if response.status_code >= 400:
                raise Exception(f"HTTP {response.status_code}: {response.text}")
            return {"response": response.text}
            
        if response.status_code >= 400:
            error_msg = result.get("error", result.get("message", str(result)))
            raise Exception(f"HTTP {response.status_code}: {error_msg}")
            
        return result

    def get(self, endpoint: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """GET request with optional query parameters"""
        if params:
            query = "&".join(f"{k}={v}" for k, v in params.items())
            endpoint = f"{endpoint}?{query}" if "?" not in endpoint else f"{endpoint}&{query}"
        return self._request("GET", endpoint)

    def post(self, endpoint: str, data: Optional[Dict] = None) -> Dict[str, Any]:
        return self._request("POST", endpoint, data)

    # --- Health ---
    def health(self) -> Dict[str, Any]:
        return self.get("health")

    # --- Exercises ---
    def get_exercise(self, exerciseId: Optional[str] = None, name: Optional[str] = None, slug: Optional[str] = None) -> Dict[str, Any]:
        params = {}
        if exerciseId:
            params["exerciseId"] = exerciseId
        if name:
            params["name"] = name
        if slug:
            params["slug"] = slug
        
        query = "&".join(f"{k}={v}" for k, v in params.items())
        endpoint = f"getExercise?{query}" if query else "getExercise"
        return self.get(endpoint)

    def get_exercises(self, limit: int = 100, offset: int = 0, approved_only: bool = False) -> Dict[str, Any]:
        endpoint = f"getExercises?limit={limit}&offset={offset}"
        if approved_only:
            endpoint += "&approved_only=true"
        return self.get(endpoint)

    def upsert_exercise(self, exercise: Dict[str, Any]) -> Dict[str, Any]:
        return self.post("upsertExercise", exercise)

    def refine_exercise(self, exerciseId: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        return self.post("refineExercise", {"exerciseId": exerciseId, "updates": updates})

    def approve_exercise(self, exerciseId: str) -> Dict[str, Any]:
        return self.post("approveExercise", {"exerciseId": exerciseId})

    def ensure_exercise_exists(self, name: str) -> Dict[str, Any]:
        return self.post("ensureExerciseExists", {"name": name})

    def merge_exercises(self, source_id: str, target_id: str) -> Dict[str, Any]:
        return self.post("mergeExercises", {"sourceId": source_id, "targetId": target_id})

    def search_exercises(self, query: str, limit: int = 10) -> Dict[str, Any]:
        return self.post("searchExercises", {"query": query, "limit": limit})

    def resolve_exercise(self, query: str) -> Dict[str, Any]:
        return self.post("resolveExercise", {"query": query})

    # --- Aliases ---
    def suggest_aliases(self, exerciseId: str, limit: int = 5) -> Dict[str, Any]:
        return self.post("suggestAliases", {"exerciseId": exerciseId, "limit": limit})

    def search_aliases(self, query: str, limit: int = 10) -> Dict[str, Any]:
        return self.post("searchAliases", {"query": query, "limit": limit})

    def upsert_alias(self, exerciseId: str, alias: str) -> Dict[str, Any]:
        return self.post("upsertAlias", {"exerciseId": exerciseId, "alias": alias})

    def delete_alias(self, exerciseId: str, alias: str) -> Dict[str, Any]:
        return self.post("deleteAlias", {"exerciseId": exerciseId, "alias": alias})

    # --- Families ---
    def list_families(self) -> Dict[str, Any]:
        return self.get("listFamilies")

    def suggest_family_variant(self, name: str) -> Dict[str, Any]:
        return self.post("suggestFamilyVariant", {"name": name})

    # --- Catalog ---
    def normalize_catalog(self, limit: int = 100) -> Dict[str, Any]:
        return self.post("normalizeCatalog", {"limit": limit})

    def normalize_catalog_page(self, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        return self.post("normalizeCatalogPage", {"limit": limit, "offset": offset})
