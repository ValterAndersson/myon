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
        query: Optional[str] = None,
        primary_muscle: Optional[str] = None,
        muscle_group: Optional[str] = None,
        category: Optional[str] = None,
        equipment: Optional[str] = None,
        split: Optional[str] = None,
        movement_type: Optional[str] = None,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """Search the exercises catalog from Firestore."""
        params = []
        if query:
            params.append(f"query={query}")
        if primary_muscle:
            params.append(f"primaryMuscle={primary_muscle}")
        if muscle_group:
            params.append(f"muscleGroup={muscle_group}")
        if category:
            params.append(f"category={category}")
        if equipment:
            params.append(f"equipment={equipment}")
        if split:
            params.append(f"split={split}")
        if movement_type:
            params.append(f"movementType={movement_type}")
        params.append(f"limit={limit}")
        query_string = "&".join(params)
        return self._http.get(f"searchExercises?{query_string}")
