from __future__ import annotations

import json
from typing import Any, Callable, Dict, Iterable, Optional

import requests


def stream_sse(url: str, headers: Optional[Dict[str, str]] = None, data: Optional[Dict[str, Any]] = None, on_event: Optional[Callable[[Dict[str, Any]], None]] = None, timeout: int = 60) -> Iterable[Dict[str, Any]]:
    """Simple SSE/NDJSON POST stream helper.

    This helper posts JSON to the given URL and yields parsed JSON lines. If an
    on_event callback is provided, it will be invoked for each event object.
    """
    hdrs = {"Content-Type": "application/json", "Accept": "text/event-stream"}
    if headers:
        hdrs.update(headers)
    with requests.post(url, json=data or {}, headers=hdrs, stream=True, timeout=timeout) as resp:
        resp.raise_for_status()
        buffer = b""
        for chunk in resp.iter_content(chunk_size=4096):
            if not chunk:
                continue
            buffer += chunk
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                line = line.strip()
                if not line:
                    continue
                # Server may send plain JSON lines, or with 'data: ' prefix
                if line.startswith(b"data: "):
                    line = line[6:]
                try:
                    obj = json.loads(line.decode("utf-8"))
                except Exception:
                    continue
                if on_event:
                    on_event(obj)
                yield obj


