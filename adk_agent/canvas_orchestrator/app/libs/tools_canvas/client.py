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
        # Also pass correlationId and userId in body for tracing
        body: Dict[str, Any] = {"canvasId": canvas_id, "cards": cards}
        if correlation_id:
            body["correlationId"] = correlation_id
        if user_id:
            body["userId"] = user_id
        return self._http.post("proposeCards", body, headers=headers or None)

    def bootstrap_canvas(self, user_id: str, purpose: str) -> Dict[str, Any]:
        return self._http.post("bootstrapCanvas", {"userId": user_id, "purpose": purpose})

    def check_pending_response(
        self,
        user_id: str,
        canvas_id: str,
    ) -> Dict[str, Any]:
        """Ask backend if there is an unprocessed user response for this canvas."""
        body: Dict[str, Any] = {"userId": user_id, "canvasId": canvas_id}
        # Uses API key auth via HttpClient; no extra headers required
        return self._http.post("checkPendingResponse", body)

    def get_user(self, user_id: str) -> Dict[str, Any]:
        """Fetch comprehensive user profile/context."""
        return self._http.post("getUser", {"userId": user_id})

    def get_user_preferences(self, user_id: str) -> Dict[str, Any]:
        """Fetch normalized user preferences (lightweight)."""
        return self._http.post("getUserPreferences", {"userId": user_id})

    def get_user_workouts(self, user_id: str, limit: int = 50) -> Dict[str, Any]:
        """Fetch recent user workouts with analytics for planning/progress agents."""
        return self._http.post("getUserWorkouts", {"userId": user_id, "limit": limit})


