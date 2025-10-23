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


