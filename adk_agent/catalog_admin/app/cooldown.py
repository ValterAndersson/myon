from __future__ import annotations

import datetime as dt
from typing import Dict


class CooldownTracker:
    def __init__(self, cooldown_days: int = 7) -> None:
        self.cooldown_days = cooldown_days
        self.last_applied: Dict[str, dt.datetime] = {}

    def load_from_journal(self, entries) -> None:
        for entry in entries or []:
            path = entry.get("field_path")
            ts = entry.get("timestamp")
            if not path or not ts:
                continue
            try:
                when = dt.datetime.fromisoformat(ts)
                self.last_applied[path] = when
            except Exception:
                continue

    def is_blocked(self, field_path: str, now: dt.datetime | None = None) -> bool:
        now = now or dt.datetime.utcnow()
        last = self.last_applied.get(field_path)
        if not last:
            return False
        return now - last < dt.timedelta(days=self.cooldown_days)

    def record(self, field_path: str, applied_at: dt.datetime | None = None) -> None:
        self.last_applied[field_path] = applied_at or dt.datetime.utcnow()
