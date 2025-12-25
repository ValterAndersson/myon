from __future__ import annotations

import datetime as dt
from typing import Any, Dict

from .libs.tools_firebase.client import FirebaseFunctionsClient


class JournalWriter:
    def __init__(self, client: FirebaseFunctionsClient):
        self.client = client

    def write(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            **entry,
            "timestamp": entry.get("timestamp") or dt.datetime.utcnow().isoformat(),
        }
        return self.client.journal_change(payload)
