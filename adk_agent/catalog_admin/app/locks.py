from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from .libs.tools_firebase.client import FirebaseFunctionsClient


@dataclass
class LockHandle:
    family_slug: str
    token: str
    expires_at: float

    def is_expired(self) -> bool:
        return time.time() >= self.expires_at


class LockManager:
    def __init__(self, client: FirebaseFunctionsClient, ttl_seconds: int = 300):
        self.client = client
        self.ttl_seconds = ttl_seconds

    def acquire(self, family_slug: str) -> Optional[LockHandle]:
        resp = self.client.acquire_lock(family_slug, ttl_seconds=self.ttl_seconds)
        token = resp.get("token") if isinstance(resp, dict) else None
        if not token:
            return None
        return LockHandle(family_slug=family_slug, token=token, expires_at=time.time() + self.ttl_seconds)

    def renew(self, handle: LockHandle) -> LockHandle:
        self.client.renew_lock(handle.family_slug, handle.token, ttl_seconds=self.ttl_seconds)
        handle.expires_at = time.time() + self.ttl_seconds
        return handle

    def release(self, handle: LockHandle) -> None:
        try:
            self.client.release_lock(handle.family_slug, handle.token)
        except Exception:
            # release best-effort
            pass
