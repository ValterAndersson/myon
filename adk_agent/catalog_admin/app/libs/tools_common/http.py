from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence

import requests


@dataclass
class HttpClient:
    base_url: str
    api_key: Optional[str] = None
    bearer_token: Optional[str] = None
    user_id: Optional[str] = None
    timeout_seconds: int = 30
    max_retries: int = 3
    backoff_factor: float = 0.5
    retry_statuses: Sequence[int] = (429, 500, 502, 503, 504)

    def _retryable(self, status_code: int) -> bool:
        return status_code in set(int(s) for s in self.retry_statuses)

    def _sleep(self, attempt: int) -> None:
        delay = self.backoff_factor * (2 ** attempt)
        jitter = 0.05 * delay
        time.sleep(delay + jitter)

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
        return self._execute_with_retries(
            lambda: requests.get(
                url,
                params=params or {},
                headers=self._headers(headers),
                timeout=self.timeout_seconds,
            )
        )

    def post(self, path: str, json_body: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        url = self._url(path)
        return self._execute_with_retries(
            lambda: requests.post(
                url,
                json=json_body or {},
                headers=self._headers(headers),
                timeout=self.timeout_seconds,
            )
        )

    def _execute_with_retries(self, req_callable) -> Dict[str, Any]:  # type: ignore[no-untyped-def]
        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = req_callable()
                # Short-circuit success
                if resp.status_code < 400:
                    return self._handle_response(resp)
                if not self._retryable(resp.status_code):
                    return self._handle_response(resp)
                last_error = requests.HTTPError(resp.text, response=resp)
            except requests.Timeout as e:
                last_error = e
            except requests.RequestException as e:
                last_error = e
            if attempt < self.max_retries:
                self._sleep(attempt)
                continue
        if last_error:
            raise last_error
        # Should not reach here
        raise RuntimeError("HttpClient failed without raising last_error")

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
            # Firebase Functions often returns { success, error }
            err = data.get("error") if isinstance(data, dict) else None
            message = err.get("message") if isinstance(err, dict) else (text or f"HTTP {resp.status_code}")
            raise requests.HTTPError(message, response=resp)
        return data if isinstance(data, dict) else {"data": data}


