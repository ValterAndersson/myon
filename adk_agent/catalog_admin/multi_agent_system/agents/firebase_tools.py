"""
Firebase Tools for LLM Agents
Provides structured tool definitions for agents to interact with Firebase.
"""

from typing import Dict, Any, List, Optional


class FirebaseTools:
    """
    Wrapper for Firebase functions that provides clear tool definitions
    for LLM agents to understand and use.
    """
    
    def __init__(self, firebase_client):
        self.client = firebase_client
    
    def get_tool_descriptions(self) -> str:
        """Get descriptions of available tools for LLM prompts."""
        return """
## Available Firebase Tools:

### Exercise Management:
- get_exercise(id/name/slug) - Retrieve a specific exercise
- get_exercises(limit) - List all exercises
- search_exercises(query, equipment, muscleGroup) - Search exercises
- upsert_exercise(exercise_data) - Create or update an exercise (include id when updating)
  - Upsert behavior: set(..., { merge: true }) on server; safe to call repeatedly; reserved aliases may 409 on conflicts.
- ensure_exercise_exists(name) - Create draft if doesn't exist
- approve_exercise(exercise_id) - Mark exercise as approved
- merge_exercises(source_id, target_id) - Merge duplicates

### Normalization:
- suggest_family_variant(name) - Get family_slug and variant_key suggestions
- normalize_catalog_page(pageSize) - Normalize a batch of exercises
- list_families(minSize) - List all exercise families

### Aliases:
- suggest_aliases(exercise) - Get alias suggestions
- upsert_alias(alias_slug, exercise_id, family_slug) - Add an alias
  - Upsert behavior: merge set; `created_at` only on first create; may return 409 via catalog endpoints on conflicts.
- search_aliases(query) - Search for aliases

### Analysis:
- resolve_exercise(query) - Find best match for a query
- refine_exercise(exercise_id, updates) - Update specific fields

When calling these tools, provide parameters as a dictionary.
"""
    
    # Exercise Management
    def get_exercise(self, exercise_id: Optional[str] = None, 
                    name: Optional[str] = None, 
                    slug: Optional[str] = None) -> Dict[str, Any]:
        """Get a specific exercise by ID, name, or slug."""
        params = {}
        if exercise_id:
            params["exerciseId"] = exercise_id
        if name:
            params["name"] = name
        if slug:
            params["slug"] = slug
        return self.client.get("getExercise", params=params)
    
    def get_exercises(self, limit: int = 200) -> Dict[str, Any]:
        """Get all exercises from the catalog."""
        result = self.client.get("getExercises", params={"limit": limit})
        if result and result.get("data"):
            return result["data"].get("items", [])
        return []
    
    def search_exercises(self, query: Optional[str] = None,
                        equipment: Optional[str] = None,
                        muscle_group: Optional[str] = None,
                        limit: int = 50) -> Dict[str, Any]:
        """Search exercises with filters."""
        params = {"limit": limit}
        if query:
            params["query"] = query
        if equipment:
            params["equipment"] = equipment
        if muscle_group:
            params["muscleGroup"] = muscle_group
        return self.client.get("searchExercises", params=params)
    
    def upsert_exercise(self, exercise_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create or update an exercise."""
        return self.client.post("upsertExercise", {"exercise": exercise_data})
    
    def ensure_exercise_exists(self, name: str, 
                             exercise_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Ensure an exercise exists, create draft if not."""
        body = {"name": name}
        if exercise_data:
            body["exercise"] = exercise_data
        return self.client.post("ensureExerciseExists", body)
    
    def approve_exercise(self, exercise_id: str) -> Dict[str, Any]:
        """Mark an exercise as approved."""
        return self.client.post("approveExercise", {"exercise_id": exercise_id})
    
    def merge_exercises(self, source_id: str, target_id: str) -> Dict[str, Any]:
        """Merge duplicate exercises."""
        return self.client.post("mergeExercises", {
            "source_id": source_id,
            "target_id": target_id
        })
    
    # Normalization Tools
    def suggest_family_variant(self, name: str, 
                              metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Get family_slug and variant_key suggestions."""
        body = {"name": name}
        if metadata:
            body["metadata"] = metadata
        return self.client.post("suggestFamilyVariant", body)
    
    def list_families(self, min_size: int = 1, limit: int = 100) -> List[Dict[str, Any]]:
        """List all exercise families."""
        result = self.client.get("listFamilies", params={
            "minSize": min_size,
            "limit": limit
        })
        if result and result.get("data"):
            return result["data"].get("families", [])
        return []
    
    # Alias Tools
    def suggest_aliases(self, exercise: Dict[str, Any]) -> List[str]:
        """Get alias suggestions for an exercise."""
        result = self.client.post("suggestAliases", {"exercise": exercise})
        if result and result.get("data"):
            return result["data"].get("suggestions", [])
        return []
    
    def upsert_alias(self, alias_slug: str, exercise_id: str, 
                    family_slug: Optional[str] = None) -> Dict[str, Any]:
        """Add an alias to an exercise."""
        body = {
            "alias_slug": alias_slug,
            "exercise_id": exercise_id
        }
        if family_slug:
            body["family_slug"] = family_slug
        
        result = self.client.post("upsertAlias", body)
        # Check if the result is successful
        if result and (result.get("ok") or result.get("success") or result.get("data")):
            return {"ok": True, "data": result}
        return result
    
    def search_aliases(self, query: str) -> List[Dict[str, Any]]:
        """Search for aliases."""
        result = self.client.get("searchAliases", params={"q": query})
        if result and result.get("data"):
            return result["data"].get("aliases", [])
        return []
    
    # Analysis Tools
    def resolve_exercise(self, query: str, 
                        context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Find the best exercise match for a query."""
        body = {"q": query}
        if context:
            body["context"] = context
        return self.client.post("resolveExercise", body)
    
    def refine_exercise(self, exercise_id: str, 
                       updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update specific fields of an exercise."""
        return self.client.post("refineExercise", {
            "exercise_id": exercise_id,
            "updates": updates
        })
