from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests


@dataclass
class HttpClient:
    base_url: str
    api_key: Optional[str] = None
    bearer_token: Optional[str] = None
    user_id: Optional[str] = None
    timeout_seconds: int = 30

    def _headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        headers: Dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        if self.user_id:
            headers["X-User-Id"] = self.user_id
        if extra:
            headers.update(extra)
        return headers

    def _url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        base = self.base_url.rstrip("/")
        p = path.lstrip("/")
        return f"{base}/{p}"

    def get(self, path: str, params: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        url = self._url(path)
        resp = requests.get(url, params=params or {}, headers=self._headers(headers), timeout=self.timeout_seconds)
        return self._handle_response(resp)

    def post(self, path: str, json_body: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        url = self._url(path)
        resp = requests.post(url, json=json_body or {}, headers=self._headers(headers), timeout=self.timeout_seconds)
        return self._handle_response(resp)

    @staticmethod
    def _handle_response(resp: requests.Response) -> Dict[str, Any]:
        content_type = resp.headers.get("Content-Type", "")
        text = resp.text
        try:
            data = resp.json()
        except Exception:
            # Try parse ndjson last line or fallback to raw
            if "event-stream" in content_type or ("\n" in text and text.strip().startswith("{")):
                try:
                    data = json.loads(text.strip().split("\n")[-1])
                except Exception:
                    data = {"raw": text}
            else:
                data = {"raw": text}

        if resp.status_code >= 400:
            err = data.get("error") if isinstance(data, dict) else None
            message = err.get("message") if isinstance(err, dict) else (text or f"HTTP {resp.status_code}")
            raise requests.HTTPError(message, response=resp)
        return data if isinstance(data, dict) else {"data": data}
