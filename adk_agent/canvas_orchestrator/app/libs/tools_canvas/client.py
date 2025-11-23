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
    
    def get_analytics_features(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Proxy to getAnalyticsFeatures for analytics summaries."""
        return self._http.post("getAnalyticsFeatures", payload)

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


