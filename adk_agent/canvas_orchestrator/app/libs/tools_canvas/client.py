from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, List

from ..tools_common.http import HttpClient


@dataclass
class CanvasFunctionsClient:
    base_url: str
    api_key: Optional[str] = None
    bearer_token: Optional[str] = None
    user_id: Optional[str] = None
    timeout_seconds: int = 30

    def __post_init__(self) -> None:
        self._http = HttpClient(
            base_url=self.base_url,
            api_key=self.api_key,
            bearer_token=self.bearer_token,
            user_id=self.user_id,
            timeout_seconds=self.timeout_seconds,
        )

    def propose_cards(
        self,
        canvas_id: str,
        cards: List[Dict[str, Any]],
        *,
        user_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        headers: Dict[str, str] = {}
        if correlation_id:
            headers["X-Correlation-Id"] = correlation_id
        if user_id:
            headers["X-User-Id"] = user_id
        # Also pass correlationId in body for clients that read body (server side extracts header first)
        body: Dict[str, Any] = {"canvasId": canvas_id, "cards": cards}
        if correlation_id:
            body["correlationId"] = correlation_id
        return self._http.post("proposeCards", body, headers=headers or None)

    def bootstrap_canvas(self, user_id: str, purpose: str) -> Dict[str, Any]:
        return self._http.post("bootstrapCanvas", {"userId": user_id, "purpose": purpose})
    
    def check_pending_response(self, user_id: str, canvas_id: str) -> Dict[str, Any]:
        """Check for pending user responses."""
        return self._http.post("checkPendingResponse", {
            "userId": user_id,
            "canvasId": canvas_id
        })
    
    def get_user(self, user_id: str) -> Dict[str, Any]:
        """Get comprehensive user profile data."""
        return self._http.post("getUser", {"userId": user_id})
    
    def get_user_preferences(self, user_id: str) -> Dict[str, Any]:
        """Get user preferences and settings."""
        return self._http.post("getUserPreferences", {"userId": user_id})
    
    def get_user_workouts(self, user_id: str, limit: int = 50) -> Dict[str, Any]:
        """Get user's workout history."""
        return self._http.post("getUserWorkouts", {
            "userId": user_id,
            "limit": limit
        })

    def emit_event(
        self,
        user_id: str,
        canvas_id: str,
        event_type: str,
        payload: Optional[Dict[str, Any]] = None,
        *,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Write a debug event to the canvas events collection."""
        headers: Dict[str, str] = {}
        if correlation_id:
            headers["X-Correlation-Id"] = correlation_id
        body: Dict[str, Any] = {
            "userId": user_id,
            "canvasId": canvas_id,
            "type": event_type,
            "payload": payload or {},
        }
        if correlation_id:
            body["correlationId"] = correlation_id
        return self._http.post("emitEvent", body, headers=headers or None)

    def search_exercises(
        self,
        *,
        muscle_group: Optional[str] = None,
        movement_type: Optional[str] = None,
        category: Optional[str] = None,
        equipment: Optional[str] = None,
        split: Optional[str] = None,
        difficulty: Optional[str] = None,
        query: Optional[str] = None,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """Search the exercises catalog from Firestore.
        
        Filterable fields (with actual values from catalog):
        
        muscle_group (muscles.category): Body part category - MOST RELIABLE FILTER
            Values: "chest", "back", "legs", "shoulders", "arms", "core", "glutes",
                    "quadriceps", "hamstrings", "biceps", "triceps", "calves", "forearms"
        
        movement_type (movement.type): Movement pattern - USE FOR PUSH/PULL/LEGS
            Values: "push", "pull", "hinge", "squat", "lunge", "carry", "core", "rotation", "other"
        
        category: Exercise complexity
            Values: "compound", "isolation", "bodyweight", "assistance", "olympic lift"
        
        equipment: Equipment required (comma-separated for multiple)
            Values: "barbell", "dumbbell", "cable", "machine", "bodyweight", 
                    "bench", "ez bar", "band", "pull-up bar", "trap bar"
        
        split (movement.split): Body region - NOT FOR PUSH/PULL (use movement_type instead)
            Values: "upper", "lower", "core", "full"
        
        difficulty (metadata.level): Experience level
            Values: "beginner", "intermediate", "advanced"
        
        query: Free text search (searches name, description, muscles, equipment)
        """
        params = []
        if muscle_group:
            params.append(f"muscleGroup={muscle_group}")
        if movement_type:
            params.append(f"movementType={movement_type}")
        if category:
            params.append(f"category={category}")
        if equipment:
            params.append(f"equipment={equipment}")
        if split:
            params.append(f"split={split}")
        if difficulty:
            params.append(f"difficulty={difficulty}")
        if query:
            params.append(f"query={query}")
        params.append(f"limit={limit}")
        query_string = "&".join(params)
        return self._http.get(f"searchExercises?{query_string}")

    # ============================================================================
    # Routine & Template APIs (added for continuous programming)
    # ============================================================================

    def get_planning_context(
        self,
        user_id: str,
        *,
        include_templates: bool = True,
        include_template_exercises: bool = True,
        include_recent_workouts: bool = True,
        workout_limit: int = 5,
    ) -> Dict[str, Any]:
        """Get composite planning context: user, routine, next workout, templates."""
        return self._http.post("getPlanningContext", {
            "userId": user_id,
            "includeTemplates": include_templates,
            "includeTemplateExercises": include_template_exercises,
            "includeRecentWorkouts": include_recent_workouts,
            "workoutLimit": workout_limit,
        })

    def get_next_workout(self, user_id: str) -> Dict[str, Any]:
        """Get deterministic next workout template from active routine."""
        return self._http.post("getNextWorkout", {"userId": user_id})

    def get_template(self, user_id: str, template_id: str) -> Dict[str, Any]:
        """Get a specific template with full exercise details."""
        return self._http.post("getTemplate", {
            "userId": user_id,
            "templateId": template_id,
        })

    def get_user_templates(self, user_id: str) -> Dict[str, Any]:
        """Get all templates for a user."""
        return self._http.post("getUserTemplates", {"userId": user_id})

    def create_template_from_plan(
        self,
        user_id: str,
        *,
        mode: str,  # "create" or "update"
        plan: Dict[str, Any],
        name: Optional[str] = None,
        description: Optional[str] = None,
        target_template_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Convert a session_plan to a template (create new or update existing)."""
        body: Dict[str, Any] = {
            "userId": user_id,
            "mode": mode,
            "plan": plan,
        }
        if name:
            body["name"] = name
        if description:
            body["description"] = description
        if target_template_id:
            body["targetTemplateId"] = target_template_id
        if idempotency_key:
            body["idempotencyKey"] = idempotency_key
        return self._http.post("createTemplateFromPlan", body)

    def patch_template(
        self,
        user_id: str,
        template_id: str,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        exercises: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Patch a template with narrow allowlist fields."""
        body: Dict[str, Any] = {
            "userId": user_id,
            "templateId": template_id,
        }
        if name is not None:
            body["name"] = name
        if description is not None:
            body["description"] = description
        if exercises is not None:
            body["exercises"] = exercises
        return self._http.post("patchTemplate", body)

    def patch_routine(
        self,
        user_id: str,
        routine_id: str,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        frequency: Optional[int] = None,
        template_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Patch a routine with narrow allowlist fields."""
        body: Dict[str, Any] = {
            "userId": user_id,
            "routineId": routine_id,
        }
        if name is not None:
            body["name"] = name
        if description is not None:
            body["description"] = description
        if frequency is not None:
            body["frequency"] = frequency
        if template_ids is not None:
            body["templateIds"] = template_ids
        return self._http.post("patchRoutine", body)

    def get_routine(self, user_id: str, routine_id: str) -> Dict[str, Any]:
        """Get a specific routine."""
        return self._http.post("getRoutine", {
            "userId": user_id,
            "routineId": routine_id,
        })

    def get_active_routine(self, user_id: str) -> Dict[str, Any]:
        """Get the user's active routine."""
        return self._http.post("getActiveRoutine", {"userId": user_id})

    def get_user_routines(self, user_id: str) -> Dict[str, Any]:
        """Get all routines for a user."""
        return self._http.post("getUserRoutines", {"userId": user_id})

    def create_routine(
        self,
        user_id: str,
        name: str,
        template_ids: List[str],
        *,
        description: Optional[str] = None,
        frequency: int = 3,
    ) -> Dict[str, Any]:
        """Create a new routine."""
        body: Dict[str, Any] = {
            "userId": user_id,
            "name": name,
            "templateIds": template_ids,
            "frequency": frequency,
        }
        if description:
            body["description"] = description
        return self._http.post("createRoutine", body)

    def update_routine(
        self,
        user_id: str,
        routine_id: str,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        template_ids: Optional[List[str]] = None,
        frequency: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Update a routine (full update)."""
        body: Dict[str, Any] = {
            "userId": user_id,
            "routineId": routine_id,
        }
        if name is not None:
            body["name"] = name
        if description is not None:
            body["description"] = description
        if template_ids is not None:
            body["templateIds"] = template_ids
        if frequency is not None:
            body["frequency"] = frequency
        return self._http.post("updateRoutine", body)

    def delete_routine(self, user_id: str, routine_id: str) -> Dict[str, Any]:
        """Delete a routine."""
        return self._http.post("deleteRoutine", {
            "userId": user_id,
            "routineId": routine_id,
        })

    def set_active_routine(self, user_id: str, routine_id: str) -> Dict[str, Any]:
        """Set the user's active routine."""
        return self._http.post("setActiveRoutine", {
            "userId": user_id,
            "routineId": routine_id,
        })

    # ============================================================================
    # Analytics APIs (for Analysis Agent)
    # ============================================================================

    def get_analytics_features(
        self,
        user_id: str,
        *,
        mode: str = "weekly",
        weeks: int = 8,
        exercise_ids: Optional[List[str]] = None,
        muscles: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Get analytics features for analysis agent.
        
        Fetches time series and rollups for progress analysis.
        
        Args:
            user_id: User ID
            mode: "weekly" (default), "week", "range", or "daily"
            weeks: Number of weeks to fetch (1-52, default 8)
            exercise_ids: Optional list of exercise IDs for per-exercise series
            muscles: Optional list of muscle names for per-muscle series
            
        Returns:
            {
                userId, mode, period_weeks, weekIds,
                rollups: [{ id, total_sets, total_reps, total_weight, 
                           intensity: { hard_sets_total, load_per_muscle, ... },
                           fatigue: { muscles, systemic },
                           summary: { muscle_groups, muscles } }],
                series_muscle: { [muscle]: [{ week, sets, volume, hard_sets, load }] },
                series_exercise: { [exerciseId]: { days, e1rm, vol, e1rm_slope, vol_slope } }
            }
        """
        body: Dict[str, Any] = {
            "userId": user_id,
            "mode": mode,
            "weeks": weeks,
        }
        if exercise_ids:
            body["exerciseIds"] = exercise_ids[:50]  # API limit
        if muscles:
            body["muscles"] = muscles[:50]  # API limit
        return self._http.post("getAnalyticsFeatures", body)
