"""
client.py - Agent → Firebase Functions HTTP Client

PURPOSE:
HTTP client for Agent to call Firebase Functions. This is the primary way
the agent reads and writes data. All methods call Firebase Cloud Functions
which then interact with Firestore.

ARCHITECTURE CONTEXT:
┌─────────────────────────────┐       ┌─────────────────────────────────┐
│ Agent (Vertex AI)           │       │ Firebase Functions              │
│                             │       │                                 │
│ PlannerAgent                │       │ Canvas APIs:                    │
│ CoachAgent     ────────────►│──────►│   proposeCards, bootstrapCanvas │
│ CopilotAgent               │       │   emitEvent                     │
│                             │       │                                 │
│ Uses:                       │       │ User APIs:                      │
│   CanvasFunctionsClient     │       │   getUser, getUserPreferences   │
│   (this file)               │       │   getUserWorkouts               │
│                             │       │                                 │
└─────────────────────────────┘       │ Exercise APIs:                  │
                                      │   searchExercises               │
                                      │                                 │
                                      │ Template APIs:                  │
                                      │   getTemplate, getUserTemplates │
                                      │   createTemplateFromPlan        │
                                      │   patchTemplate                 │
                                      │                                 │
                                      │ Routine APIs:                   │
                                      │   getRoutine, getUserRoutines   │
                                      │   getActiveRoutine, patchRoutine│
                                      │   setActiveRoutine              │
                                      │                                 │
                                      │ Planning APIs:                  │
                                      │   getPlanningContext            │
                                      │   getNextWorkout                │
                                      │                                 │
                                      │ Training Analysis APIs:         │
                                      │   getAnalysisSummary            │
                                      └─────────────────────────────────┘

KEY METHOD → FIREBASE FUNCTION MAPPING:
- propose_cards() → firebase_functions/functions/canvas/propose-cards.js
- bootstrap_canvas() → firebase_functions/functions/canvas/bootstrap-canvas.js
- emit_event() → firebase_functions/functions/canvas/emit-event.js
- get_user() → firebase_functions/functions/user/get-user.js
- get_user_preferences() → firebase_functions/functions/user/get-user-preferences.js
- get_user_workouts() → firebase_functions/functions/workouts/get-user-workouts.js
- search_exercises() → firebase_functions/functions/exercises/search-exercises.js
- get_planning_context() → firebase_functions/functions/agents/get-planning-context.js
- get_next_workout() → firebase_functions/functions/routines/get-next-workout.js
- get_template() → firebase_functions/functions/templates/get-template.js
- create_template_from_plan() → firebase_functions/functions/templates/create-template-from-plan.js
- patch_template() → firebase_functions/functions/templates/patch-template.js
- patch_routine() → firebase_functions/functions/routines/patch-routine.js
- get_analysis_summary() → firebase_functions/functions/training/get-analysis-summary.js

HOW IT'S USED BY AGENTS:
Agent tools (planner_tools.py, coach_tools.py, etc.) wrap this client and
expose methods as FunctionTool instances that the LLM can call:

  from ..libs.tools_canvas.client import CanvasFunctionsClient
  
  client = CanvasFunctionsClient(
      base_url="https://us-central1-myon-53d85.cloudfunctions.net",
      api_key="myon-agent-key-2024"
  )
  result = client.search_exercises(muscle_group="chest", limit=10)

RELATED FILES:
- agents/tools/planner_tools.py: Uses this client for planning tools
- agents/tools/coach_tools.py: Uses this client for coaching tools
- agents/tools/copilot_tools.py: Uses this client for copilot tools
- agents/tools/analysis_tools.py: Uses this client for analytics tools
- libs/tools_common/http.py: Underlying HTTP implementation

AUTHENTICATION:
- api_key: Static API key for server-to-server auth
- bearer_token: Firebase ID token (when used from iOS via proxy)
- user_id: X-User-Id header for user context

"""

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
        fields: str = "full",
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
        if fields and fields != "full":
            params.append(f"fields={fields}")
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
    # Token-Safe Training Analytics v2 (Callable Functions)
    # See: docs/TRAINING_ANALYTICS_API_V2_SPEC.md
    # ============================================================================

    def get_muscle_group_summary(
        self,
        user_id: str,
        muscle_group: str,
        *,
        window_weeks: int = 12,
        include_distribution: bool = False,
    ) -> Dict[str, Any]:
        """Get comprehensive muscle group progress summary for coaching.
        
        This is the PREFERRED endpoint for answering "How is my X developing?"
        questions. Returns bounded, token-safe data with weekly series, top 
        exercises, and deterministic flags (plateau, deload, overreach).
        
        Valid muscle_groups:
            chest, back, shoulders, arms, core, legs, glutes,
            hip_flexors, calves, forearms, neck, cardio
        
        Args:
            user_id: User ID
            muscle_group: Canonical muscle group ID (e.g., "chest", "back")
            window_weeks: Number of weeks to analyze (1-52, default 12)
            include_distribution: Include rep range distribution
            
        Returns:
            {
                "success": true,
                "data": {
                    "muscle_group": "chest",
                    "display_name": "Chest",
                    "weekly_points": [
                        {"week_start": "2024-01-08", "sets": 12, "volume": 5400, ...}
                    ],
                    "top_exercises": [
                        {"exercise_id": "...", "exercise_name": "Bench Press", "effective_volume": 2700, "sets": 6}
                    ],
                    "summary": {
                        "total_weeks_with_data": 8,
                        "avg_weekly_volume": 5400,
                        "avg_weekly_sets": 12
                    },
                    "flags": {
                        "plateau": false,
                        "deload": false,
                        "overreach": false
                    }
                }
            }
            
        Error Recovery:
            - Returns empty weekly_points if no data
            - Validates muscle_group against taxonomy, returns 400 if invalid
        """
        return self._http.post("getMuscleGroupSummary", {
            "userId": user_id,
            "muscle_group": muscle_group,
            "window_weeks": window_weeks,
            "include_distribution": include_distribution,
        })

    def get_muscle_summary(
        self,
        user_id: str,
        muscle: str,
        *,
        window_weeks: int = 12,
    ) -> Dict[str, Any]:
        """Get individual muscle progress summary for detailed coaching.
        
        Use this for specific muscle questions like "How are my rhomboids?"
        or "How is my front delt developing?"
        
        Valid muscles (examples):
            pectoralis_major, pectoralis_minor, latissimus_dorsi, rhomboids,
            trapezius_upper, trapezius_middle, trapezius_lower, erector_spinae,
            deltoid_anterior, deltoid_lateral, deltoid_posterior, rotator_cuff,
            biceps_brachii, triceps_brachii, brachialis, brachioradialis,
            rectus_abdominis, obliques, transverse_abdominis,
            quadriceps, hamstrings, gluteus_maximus, gluteus_medius,
            gastrocnemius, soleus, tibialis_anterior
            
        Args:
            user_id: User ID
            muscle: Canonical muscle ID (e.g., "rhomboids", "deltoid_anterior")
            window_weeks: Number of weeks to analyze (1-52, default 12)
            
        Returns:
            Same structure as get_muscle_group_summary but for individual muscle
            
        Error Recovery:
            - Returns 400 with valid muscle list if muscle ID is invalid
        """
        return self._http.post("getMuscleSummary", {
            "userId": user_id,
            "muscle": muscle,
            "window_weeks": window_weeks,
        })

    def get_exercise_summary(
        self,
        user_id: str,
        exercise_id: Optional[str] = None,
        exercise_name: Optional[str] = None,
        *,
        window_weeks: int = 12,
    ) -> Dict[str, Any]:
        """Get exercise progress summary with PR tracking.
        
        Use for questions like "How is my bench press progressing?"
        Includes last session recap and PR markers.
        
        ACCEPTS EITHER exercise_id OR exercise_name:
        - exercise_id: Direct lookup by catalog ID
        - exercise_name: Fuzzy name search (e.g., "bench press", "squats")
        
        Args:
            user_id: User ID
            exercise_id: Exercise ID from catalog (optional if exercise_name provided)
            exercise_name: Exercise name for fuzzy search (e.g., "bench press")
            window_weeks: Number of weeks to analyze (1-52, default 12)
            
        Returns:
            {
                "success": true,
                "data": {
                    "exercise_id": "...",
                    "exercise_name": "Bench Press",
                    "matched": true,  // false if name search found no match
                    "weekly_points": [...],
                    "last_session": [
                        {"set_index": 0, "reps": 5, "weight_kg": 100, "e1rm": 116}
                    ],
                    "pr_markers": {
                        "all_time_e1rm": 125,
                        "window_e1rm": 120
                    },
                    "flags": {"plateau": false}
                }
            }
        """
        body: Dict[str, Any] = {
            "userId": user_id,
            "window_weeks": window_weeks,
        }
        if exercise_id:
            body["exercise_id"] = exercise_id
        elif exercise_name:
            body["exercise_name"] = exercise_name
        return self._http.post("getExerciseSummary", body)

    def query_sets(
        self,
        user_id: str,
        *,
        muscle_group: Optional[str] = None,
        muscle: Optional[str] = None,
        exercise_ids: Optional[List[str]] = None,
        exercise_name: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        include_warmups: bool = False,
        limit: int = 50,
        cursor: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Query individual set facts with filters - for drilldown only.
        
        EXACTLY ONE target filter is required: muscle_group, muscle, exercise_ids, or exercise_name.
        Use this only when you need raw set data for evidence. Prefer summary
        endpoints for general questions.
        
        Args:
            user_id: User ID
            muscle_group: Filter by muscle group (mutually exclusive with other targets)
            muscle: Filter by specific muscle (mutually exclusive with other targets)  
            exercise_ids: Filter by exercise IDs, max 10 (mutually exclusive with other targets)
            exercise_name: Filter by exercise name (fuzzy search, e.g., "bench press")
                Searches user's training history for matching exercise names.
            start: Start date YYYY-MM-DD
            end: End date YYYY-MM-DD
            include_warmups: Include warmup sets (default false)
            limit: Max results per page (default 50, max 200)
            cursor: Pagination cursor from previous response
            
        Returns:
            {
                "success": true,
                "data": [
                    {
                        "set_id": "...",
                        "workout_date": "2024-01-15",
                        "exercise_name": "Bench Press",
                        "reps": 5,
                        "weight_kg": 100,
                        "rir": 2,
                        "volume": 500,
                        "e1rm": 116
                    }
                ],
                "next_cursor": "...",
                "truncated": false,
                "meta": {"returned": 50, "limit": 50}
            }
            
        Error Recovery:
            - Returns 400 if zero or multiple targets provided
            - Validates muscle_group/muscle against taxonomy
        """
        target: Dict[str, Any] = {}
        if muscle_group:
            target["muscle_group"] = muscle_group
        if muscle:
            target["muscle"] = muscle
        if exercise_ids:
            target["exercise_ids"] = exercise_ids[:10]
        if exercise_name:
            target["exercise_name"] = exercise_name
        
        body: Dict[str, Any] = {
            "userId": user_id,
            "target": target,
            "limit": min(limit, 200),
        }
        if start:
            body["start"] = start
        if end:
            body["end"] = end
        if include_warmups:
            body["effort"] = {"include_warmups": True}
        if cursor:
            body["cursor"] = cursor
            
        return self._http.post("querySets", body)

    def get_active_snapshot_lite(self, user_id: str) -> Dict[str, Any]:
        """Get minimal active workout state for agent context.
        
        Use instead of full getActiveWorkout to avoid token bloat.
        Returns only essential fields needed to understand workout status.
        
        Returns:
            {
                "success": true,
                "data": {
                    "has_active_workout": true,
                    "workout_id": "...",
                    "status": "in_progress",
                    "start_time": "2024-01-15T10:00:00Z",
                    "current_exercise": {
                        "exercise_id": "...",
                        "exercise_name": "Bench Press"
                    },
                    "next_set_index": 2,
                    "totals": {
                        "completed_sets": 8,
                        "total_sets": 24,
                        "completed_exercises": 2,
                        "total_exercises": 6
                    }
                }
            }
        """
        return self._http.post("getActiveSnapshotLite", {"userId": user_id})

    def get_active_events(
        self,
        user_id: str,
        *,
        workout_id: Optional[str] = None,
        after_version: Optional[int] = None,
        limit: int = 20,
        cursor: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get paginated workout events for incremental updates.

        Use to track changes in active workout without re-reading full state.
        Events include: set_logged, exercise_added, exercise_swapped, etc.

        Args:
            user_id: User ID
            workout_id: Specific workout (defaults to current active)
            after_version: Get events after this version number
            limit: Max events per page (default 20, max 50)
            cursor: Pagination cursor from previous response

        Returns:
            {
                "success": true,
                "data": [
                    {
                        "type": "set_logged",
                        "version": 5,
                        "payload": {"exercise_id": "...", "set_index": 0, ...},
                        "created_at": "2024-01-15T10:30:00Z"
                    }
                ],
                "next_cursor": "...",
                "truncated": false
            }
        """
        body: Dict[str, Any] = {
            "userId": user_id,
            "limit": min(limit, 50),
        }
        if workout_id:
            body["workout_id"] = workout_id
        if after_version is not None:
            body["after_version"] = after_version
        if cursor:
            body["cursor"] = cursor
        return self._http.post("getActiveEvents", body)

    # ============================================================================
    # Training Analysis APIs (Pre-computed Insights)
    # ============================================================================

    def get_analysis_summary(
        self,
        user_id: str,
        *,
        sections: Optional[List[str]] = None,
        date: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Get pre-computed training analysis summaries.

        Returns AI-generated insights, daily briefs, and weekly reviews.
        Use this instead of computing from raw data for faster responses.

        Valid sections:
            - "insights": Recent analysis_insights (last 7 days)
            - "daily_brief": Today's training readiness brief
            - "weekly_review": Most recent weekly progression review

        Args:
            user_id: User ID
            sections: Which sections to include (default: all)
            date: Date for daily_brief (YYYY-MM-DD, defaults to today)
            limit: Max insights to return (for "insights" section)

        Returns:
            {
                "success": true,
                "data": {
                    "insights": [
                        {
                            "id": "...",
                            "created_at": "...",
                            "insight_type": "plateau",
                            "summary": "...",
                            "details": {...},
                            "recommendations": [...]
                        }
                    ],
                    "daily_brief": {
                        "date": "2024-01-15",
                        "readiness_score": 0.85,
                        "recommendations": [...],
                        "upcoming_workout_suggestion": {...}
                    },
                    "weekly_review": {
                        "week_id": "2024-01-08",
                        "progression_summary": "...",
                        "volume_trends": {...},
                        "intensity_metrics": {...},
                        "recommendations": [...]
                    }
                }
            }
        """
        body: Dict[str, Any] = {
            "userId": user_id,
        }
        if sections:
            body["sections"] = sections
        if date:
            body["date"] = date
        if limit is not None:
            body["limit"] = limit
        return self._http.post("getAnalysisSummary", body)

    # ============================================================================
    # Active Workout APIs (Workout Mode)
    # ============================================================================

    def get_active_workout(self, user_id: str) -> Dict[str, Any]:
        """Get the user's active workout with full state.

        Uses requireFlexibleAuth — userId from X-User-Id header.
        Returns { success: true, workout: {...} | null }.
        """
        return self._http.post(
            "getActiveWorkout", {},
            headers={"X-User-Id": user_id},
        )

    def log_set(
        self,
        user_id: str,
        workout_id: str,
        exercise_instance_id: str,
        set_id: str,
        *,
        reps: int,
        weight_kg: float,
        rir: Optional[int] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Log a completed set in an active workout.

        Matches LogSetSchemaV2 in validators.js — snake_case fields,
        nested values object, required idempotency_key.
        """
        import uuid
        body = {
            "workout_id": workout_id,
            "exercise_instance_id": exercise_instance_id,
            "set_id": set_id,
            "values": {
                "weight": weight_kg,
                "reps": reps,
                "rir": rir if rir is not None else 0,
            },
            "idempotency_key": idempotency_key or str(uuid.uuid4()),
        }
        return self._http.post(
            "logSet", body,
            headers={"X-User-Id": user_id},
        )

    def swap_exercise(
        self,
        user_id: str,
        workout_id: str,
        exercise_instance_id: str,
        new_exercise_id: str,
    ) -> Dict[str, Any]:
        """Swap an exercise in the active workout.

        Handler expects: workout_id, from_exercise_id, to_exercise_id.
        """
        return self._http.post(
            "swapExercise",
            {
                "workout_id": workout_id,
                "from_exercise_id": exercise_instance_id,
                "to_exercise_id": new_exercise_id,
            },
            headers={"X-User-Id": user_id},
        )

    def complete_active_workout(self, user_id: str, workout_id: str) -> Dict[str, Any]:
        """Complete an active workout and archive it."""
        return self._http.post(
            "completeActiveWorkout",
            {"workout_id": workout_id},
            headers={"X-User-Id": user_id},
        )
