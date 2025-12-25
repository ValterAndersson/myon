from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .libs.tools_firebase.client import FirebaseFunctionsClient


@dataclass
class CatalogTask:
    task_id: str
    lane: str
    reason: str
    target_type: str
    target_id: str
    shard: Optional[Dict[str, int]] = None
    mode: str = "dry_run"
    status: str = "queued"
    attempts: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    last_error: Optional[Dict[str, str]] = None


class TaskQueue:
    def __init__(self, client: FirebaseFunctionsClient):
        self.client = client

    def enqueue(self, lane: str, reason: str, target_type: str, target_id: str, shard: Optional[Dict[str, int]] = None, mode: str = "dry_run") -> CatalogTask:
        task_id = str(uuid.uuid4())
        payload = {
            "task_id": task_id,
            "lane": lane,
            "reason": reason,
            "target_type": target_type,
            "target_id": target_id,
            "shard": shard,
            "mode": mode,
            "status": "queued",
        }
        self.client.enqueue_task(payload)
        return CatalogTask(task_id=task_id, lane=lane, reason=reason, target_type=target_type, target_id=target_id, shard=shard, mode=mode)

    def lease(self, worker_id: str) -> Optional[CatalogTask]:
        res = self.client.lease_task(worker_id)
        task = res.get("task") if isinstance(res, dict) else None
        if not task:
            return None
        return CatalogTask(**task)

    def complete(self, task_id: str, result: Dict[str, Any]) -> None:  # type: ignore[no-untyped-def]
        self.client.complete_task(task_id, result)

    def fail(self, task_id: str, error: Dict[str, str], retry_at: Optional[str] = None) -> None:
        self.client.fail_task(task_id, error, retry_at=retry_at)


class DeterministicShardScheduler:
    def __init__(self, client: FirebaseFunctionsClient, shards: int = 32, queue: Optional[TaskQueue] = None):
        self.client = client
        self.shards = shards
        self.queue = queue or TaskQueue(client)

    def schedule_daily(self, mode: str = "dry_run") -> List[CatalogTask]:
        tasks: List[CatalogTask] = []
        for idx in range(self.shards):
            shard_info = {"index": idx, "total": self.shards}
            tasks.append(self.queue.enqueue("batch", "daily_scan", "shard", f"shard-{idx}", shard=shard_info, mode=mode))
        return tasks
