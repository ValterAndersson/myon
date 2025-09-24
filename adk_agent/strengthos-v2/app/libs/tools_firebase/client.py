from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from ..tools_common.http import HttpClient
from ..agent_core.sse import stream_sse


@dataclass
class FirebaseFunctionsClient:
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

    # --- Health ---
    def health(self) -> Dict[str, Any]:
        return self._http.get("health")

    # --- Active Workout ---
    def start_active_workout(self, plan: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._http.post("startActiveWorkout", {"plan": plan} if plan else {})

    def get_active_workout(self) -> Dict[str, Any]:
        return self._http.get("getActiveWorkout")

    def propose_session(self, constraints: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._http.post("proposeSession", {"constraints": constraints or {}})

    def prescribe_set(self, workout_id: str, exercise_id: str, set_index: int, context: Optional[Dict[str, Any]] = None, idempotency_key: Optional[str] = None) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "workout_id": workout_id,
            "exercise_id": exercise_id,
            "set_index": set_index,
            "context": context or {},
        }
        if idempotency_key:
            body["idempotency_key"] = idempotency_key
        return self._http.post("prescribeSet", body)

    def log_set(self, workout_id: str, exercise_id: str, set_index: int, actual: Dict[str, Any], idempotency_key: Optional[str] = None) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "workout_id": workout_id,
            "exercise_id": exercise_id,
            "set_index": set_index,
            "actual": actual,
        }
        if idempotency_key:
            body["idempotency_key"] = idempotency_key
        return self._http.post("logSet", body)

    def score_set(self, actual: Dict[str, Any]) -> Dict[str, Any]:
        return self._http.post("scoreSet", {"actual": actual})

    def add_exercise(self, workout_id: str, exercise_id: str, name: Optional[str] = None, position: Optional[int] = None, idempotency_key: Optional[str] = None) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "workout_id": workout_id,
            "exercise_id": exercise_id,
        }
        if name is not None:
            body["name"] = name
        if position is not None:
            body["position"] = position
        if idempotency_key:
            body["idempotency_key"] = idempotency_key
        return self._http.post("addExercise", body)

    def swap_exercise(self, workout_id: str, from_exercise_id: str, to_exercise_id: str, reason: Optional[str] = None, idempotency_key: Optional[str] = None) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "workout_id": workout_id,
            "from_exercise_id": from_exercise_id,
            "to_exercise_id": to_exercise_id,
        }
        if reason:
            body["reason"] = reason
        if idempotency_key:
            body["idempotency_key"] = idempotency_key
        return self._http.post("swapExercise", body)

    def complete_active_workout(self, workout_id: str) -> Dict[str, Any]:
        return self._http.post("completeActiveWorkout", {"workout_id": workout_id})

    def cancel_active_workout(self, workout_id: str) -> Dict[str, Any]:
        return self._http.post("cancelActiveWorkout", {"workout_id": workout_id})

    def note_active_workout(self, workout_id: str, note: str) -> Dict[str, Any]:
        return self._http.post("noteActiveWorkout", {"workout_id": workout_id, "note": note})

    # --- Exercises ---
    def get_exercise(self, *, exerciseId: Optional[str] = None, name: Optional[str] = None, slug: Optional[str] = None) -> Dict[str, Any]:
        if not any([exerciseId, name, slug]):
            raise ValueError("Provide exerciseId, name or slug")
        body: Dict[str, Any] = {}
        if exerciseId:
            body["exerciseId"] = exerciseId
        if name:
            body["name"] = name
        if slug:
            body["slug"] = slug
        return self._http.post("getExercise", body)

    def upsert_exercise(self, exercise: Dict[str, Any]) -> Dict[str, Any]:
        return self._http.post("upsertExercise", {"exercise": exercise})

    def ensure_exercise_exists(self, name: str, **extra: Any) -> Dict[str, Any]:
        payload = {"name": name}
        payload.update(extra)
        return self._http.post("ensureExerciseExists", payload)

    def search_exercises(self, **query: Any) -> Dict[str, Any]:
        return self._http.get("searchExercises", params=query)

    def list_families(self, **query: Any) -> Dict[str, Any]:
        return self._http.get("listFamilies", params=query)

    # --- Aliases ---
    def upsert_alias(self, alias_slug: str, exercise_id: str, family_slug: Optional[str] = None) -> Dict[str, Any]:
        body: Dict[str, Any] = {"alias_slug": alias_slug, "exercise_id": exercise_id}
        if family_slug:
            body["family_slug"] = family_slug
        return self._http.post("upsertAlias", body)

    def delete_alias(self, alias_slug: str) -> Dict[str, Any]:
        return self._http.post("deleteAlias", {"alias_slug": alias_slug})

    def search_aliases(self, q: str) -> Dict[str, Any]:
        return self._http.get("searchAliases", params={"q": q})

    # --- Maintenance ---
    def normalize_catalog_page(self, pageSize: int = 50, startAfterName: Optional[str] = None) -> Dict[str, Any]:
        body: Dict[str, Any] = {"pageSize": pageSize}
        if startAfterName:
            body["startAfterName"] = startAfterName
        return self._http.post("normalizeCatalogPage", body)

    # --- StrengthOS / Streaming ---
    def stream_agent_normalized_url(self) -> str:
        # The client can use this URL with an SSE implementation
        return self._http._url("streamAgentNormalized")

    def stream_agent_normalized(self, message: str, session_id: Optional[str] = None, markdown_policy: Optional[Dict[str, Any]] = None, on_event=None, timeout_seconds: int = 60):
        url = self.stream_agent_normalized_url()
        headers: Dict[str, str] = {}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        body: Dict[str, Any] = {"message": message}
        if session_id:
            body["sessionId"] = session_id
        if markdown_policy:
            body["markdown_policy"] = markdown_policy
        return stream_sse(url, headers=headers, data=body, on_event=on_event, timeout=timeout_seconds)

    # --- User ---
    def get_user(self, user_id: str) -> Dict[str, Any]:
        return self._http.get("getUser", params={"userId": user_id})

    def update_user(self, user_id: str, user_data: Dict[str, Any]) -> Dict[str, Any]:
        return self._http.post("updateUser", {"userId": user_id, "userData": user_data})

    def get_user_preferences(self, user_id: str) -> Dict[str, Any]:
        return self._http.get("getUserPreferences", params={"userId": user_id})

    def update_user_preferences(self, user_id: str, preferences: Dict[str, Any]) -> Dict[str, Any]:
        return self._http.post("updateUserPreferences", {"userId": user_id, "preferences": preferences})

    # --- Workouts (history) ---
    def get_user_workouts(self, user_id: str, **query: Any) -> Dict[str, Any]:
        params = {"userId": user_id}
        params.update(query)
        return self._http.get("getUserWorkouts", params=params)

    def get_workout(self, user_id: str, workout_id: str) -> Dict[str, Any]:
        return self._http.get("getWorkout", params={"userId": user_id, "workoutId": workout_id})

    # --- Templates ---
    def get_user_templates(self, user_id: str) -> Dict[str, Any]:
        return self._http.get("getUserTemplates", params={"userId": user_id})

    def get_template(self, user_id: str, template_id: str) -> Dict[str, Any]:
        return self._http.get("getTemplate", params={"userId": user_id, "templateId": template_id})

    def create_template(self, user_id: str, template: Dict[str, Any]) -> Dict[str, Any]:
        return self._http.post("createTemplate", {"userId": user_id, "template": template})

    def update_template(self, user_id: str, template_id: str, template: Dict[str, Any]) -> Dict[str, Any]:
        return self._http.post("updateTemplate", {"userId": user_id, "templateId": template_id, "template": template})

    def delete_template(self, user_id: str, template_id: str) -> Dict[str, Any]:
        return self._http.post("deleteTemplate", {"userId": user_id, "templateId": template_id})

    # --- Routines ---
    def get_user_routines(self, user_id: str) -> Dict[str, Any]:
        return self._http.get("getUserRoutines", params={"userId": user_id})

    def get_routine(self, user_id: str, routine_id: str) -> Dict[str, Any]:
        return self._http.get("getRoutine", params={"userId": user_id, "routineId": routine_id})

    def create_routine(self, user_id: str, routine: Dict[str, Any]) -> Dict[str, Any]:
        return self._http.post("createRoutine", {"userId": user_id, "routine": routine})

    def update_routine(self, user_id: str, routine_id: str, routine: Dict[str, Any]) -> Dict[str, Any]:
        return self._http.post("updateRoutine", {"userId": user_id, "routineId": routine_id, "routine": routine})

    def delete_routine(self, user_id: str, routine_id: str) -> Dict[str, Any]:
        return self._http.post("deleteRoutine", {"userId": user_id, "routineId": routine_id})

    def get_active_routine(self, user_id: str) -> Dict[str, Any]:
        return self._http.get("getActiveRoutine", params={"userId": user_id})

    def set_active_routine(self, user_id: str, routine_id: str) -> Dict[str, Any]:
        return self._http.post("setActiveRoutine", {"userId": user_id, "routineId": routine_id})

    # --- Generic HTTP methods for direct access ---
    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Generic GET request to any Firebase function endpoint."""
        return self._http.get(path, params=params)

    def post(self, path: str, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Generic POST request to any Firebase function endpoint."""
        return self._http.post(path, json_body=body)


