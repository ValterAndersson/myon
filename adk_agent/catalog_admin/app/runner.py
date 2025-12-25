from __future__ import annotations

import logging
import os
import random
import time
from typing import Any, Dict, List

from .action_planner import ActionPlanner
from .action_schema import ActionPlan, Lane, Mode, Target, TargetType
from .cooldown import CooldownTracker
from .journal import JournalWriter
from .locks import LockManager
from .policy_middleware import PolicyConfig, PolicyMiddleware
from .tasks import CatalogTask, DeterministicShardScheduler, TaskQueue
from .libs.tools_firebase.client import FirebaseFunctionsClient

logger = logging.getLogger("catalog_autopilot")


def _client() -> FirebaseFunctionsClient:
    base_url = os.getenv("MYON_FUNCTIONS_BASE_URL", "https://us-central1-myon-53d85.cloudfunctions.net")
    api_key = os.getenv("FIREBASE_API_KEY")
    bearer = os.getenv("FIREBASE_ID_TOKEN")
    user_id = os.getenv("PIPELINE_USER_ID") or os.getenv("X_USER_ID") or "catalog_autopilot"
    return FirebaseFunctionsClient(base_url=base_url, api_key=api_key, bearer_token=bearer, user_id=user_id)


def _hash_family(name: str, total: int) -> int:
    return hash(name) % total


def fetch_exercise_snapshot(client: FirebaseFunctionsClient, exercise_id: str) -> Dict[str, Any]:
    resp = client.get_exercise(exerciseId=exercise_id)
    data = resp.get("data") if isinstance(resp, dict) else None
    if isinstance(data, dict) and data.get("exercise"):
        return data.get("exercise")
    return resp.get("exercise") if isinstance(resp, dict) else {}


def fetch_shard(client: FirebaseFunctionsClient, shard_index: int, shard_total: int, page_size: int = 200) -> List[Dict[str, Any]]:
    resp = client.search_exercises(limit=page_size, canonicalOnly=True)  # type: ignore[arg-type]
    items = resp.get("data", {}).get("items", []) if isinstance(resp, dict) else []
    return [ex for ex in items if _hash_family(str(ex.get("family_slug")), shard_total) == shard_index]


def apply_actions(plan: ActionPlan, actions, client: FirebaseFunctionsClient, lock_manager: LockManager, journal: JournalWriter) -> List[Dict[str, Any]]:  # type: ignore[no-untyped-def]
    results: List[Dict[str, Any]] = []
    for action in actions:
        if plan.mode == Mode.dry_run:
            results.append({"status": "skipped", "reason": "dry_run", "action": action.op_type.value})
            continue
        if action.op_type.value.startswith("upsert_exercise"):
            lock = lock_manager.acquire(action.after.get("family_slug") or action.after.get("id", "unknown"))
            if not lock:
                results.append({"status": "deferred", "reason": "lock_unavailable", "action": action.op_type.value})
                continue
            resp = client.upsert_exercise(
                action.after,
                idempotency_key=action.idempotency_key,
                plan_hash=action.plan_hash,
                lock_token=lock.token,
            )
            journal.write(
                {
                    "action": action.op_type.value,
                    "target": plan.target.model_dump(mode="json"),
                    "idempotency_key": action.idempotency_key,
                    "plan_hash": action.plan_hash,
                    "lane": plan.lane.value,
                    "mode": plan.mode.value,
                    "before": action.before,
                    "after": action.after,
                }
            )
            lock_manager.release(lock)
            results.append(resp)
        elif action.op_type == action.op_type.upsert_alias:
            resp = client.upsert_alias(
                action.after.get("alias_slug"),
                action.after.get("exercise_id"),
                action.after.get("family_slug"),
                idempotency_key=action.idempotency_key,
                plan_hash=action.plan_hash,
            )
            journal.write(
                {
                    "action": action.op_type.value,
                    "target": plan.target.model_dump(mode="json"),
                    "idempotency_key": action.idempotency_key,
                    "plan_hash": action.plan_hash,
                    "lane": plan.lane.value,
                    "mode": plan.mode.value,
                    "before": action.before,
                    "after": action.after,
                }
            )
            results.append(resp)
        elif action.op_type == action.op_type.delete_alias:
            resp = client.delete_alias(
                action.before.get("alias_slug") or action.after.get("alias_slug"),
                idempotency_key=action.idempotency_key,
                plan_hash=action.plan_hash,
            )
            journal.write(
                {
                    "action": action.op_type.value,
                    "target": plan.target.model_dump(mode="json"),
                    "idempotency_key": action.idempotency_key,
                    "plan_hash": action.plan_hash,
                    "lane": plan.lane.value,
                    "mode": plan.mode.value,
                    "before": action.before,
                    "after": action.after,
                }
            )
            results.append(resp)
        else:
            results.append({"status": "noop", "action": action.op_type.value})
    return results


def process_task(task: CatalogTask, client: FirebaseFunctionsClient, policy: PolicyMiddleware, lock_manager: LockManager, journal: JournalWriter) -> Dict[str, Any]:
    lane = Lane(task.lane)
    mode = Mode(task.mode)
    target = Target(
        type=TargetType(task.target_type),
        id=task.target_id,
        shard_index=(task.shard or {}).get("index"),
        shard_total=(task.shard or {}).get("total"),
    )
    planner = ActionPlanner(lane)
    tracker = CooldownTracker(policy.config.cooldown_days)

    if target.type == TargetType.exercise:
        exercise = fetch_exercise_snapshot(client, target.id)
        plan = planner.build_plan_for_exercise(target, exercise, mode=mode)
        policy_result = policy.enforce_batch_dampening(plan, tracker)
        applied = apply_actions(plan, policy_result.approved_actions, client, lock_manager, journal)
        return {
            "plan": plan.model_dump(mode="json"),
            "approved": [a.model_dump(mode="json") for a in policy_result.approved_actions],
            "applied": applied,
            "rejected": policy_result.rejected,
        }

    if target.type == TargetType.shard:
        exercises = fetch_shard(client, target.shard_index or 0, target.shard_total or 1)
        shard_results: List[Dict[str, Any]] = []
        for ex in exercises:
            sub_target = Target(type=TargetType.exercise, id=str(ex.get("id")))
            sub_plan = planner.build_plan_for_exercise(sub_target, ex, mode=mode)
            policy_result = policy.enforce_batch_dampening(sub_plan, tracker)
            applied = apply_actions(sub_plan, policy_result.approved_actions, client, lock_manager, journal)
            shard_results.append(
                {
                    "exercise_id": ex.get("id"),
                    "plan": sub_plan.model_dump(mode="json"),
                    "applied": applied,
                    "rejected": policy_result.rejected,
                }
            )
        return {"status": "shard_complete", "items": shard_results}

    exercise = fetch_exercise_snapshot(client, target.id)
    plan = planner.build_plan_for_exercise(target, exercise, mode=mode)
    policy_result = policy.enforce_batch_dampening(plan, tracker)
    applied = apply_actions(plan, policy_result.approved_actions, client, lock_manager, journal)
    return {
        "plan": plan.model_dump(mode="json"),
        "approved": [a.model_dump(mode="json") for a in policy_result.approved_actions],
        "applied": applied,
        "rejected": policy_result.rejected,
    }


def run_worker(loop: bool = False, sleep_seconds: int = 5) -> None:
    client = _client()
    queue = TaskQueue(client)
    lock_manager = LockManager(client)
    journal = JournalWriter(client)
    policy = PolicyMiddleware(
        PolicyConfig(
            enable_batch_apply=os.getenv("ENABLE_BATCH_APPLY", "0") == "1",
            enable_tier2=os.getenv("ENABLE_TIER2", "0") == "1",
            enable_tier3=os.getenv("ENABLE_TIER3", "0") == "1",
            cooldown_days=int(os.getenv("COOLDOWN_DAYS", "7")),
            lint_threshold=float(os.getenv("LINT_THRESHOLD", "0.05")),
        )
    )
    worker_id = os.getenv("WORKER_ID", f"worker-{random.randint(1000,9999)}")
    while True:
        task = queue.lease(worker_id)
        if not task:
            if not loop:
                break
            time.sleep(sleep_seconds)
            continue
        try:
            result = process_task(task, client, policy, lock_manager, journal)
            queue.complete(task.task_id, result)
        except Exception as e:  # pragma: no cover - safety net
            logger.exception({"task": task.task_id, "error": str(e)})
            queue.fail(task.task_id, {"code": "unhandled", "message": str(e)})
        if not loop:
            break


def enqueue_realtime_task(exercise_id: str, mode: str = "apply") -> CatalogTask:
    client = _client()
    queue = TaskQueue(client)
    return queue.enqueue(
        lane="realtime",
        reason="exercise_created",
        target_type="exercise",
        target_id=exercise_id,
        mode=mode,
    )


def schedule_daily_shards(shards: int = 32, mode: str = "dry_run") -> List[CatalogTask]:
    client = _client()
    scheduler = DeterministicShardScheduler(client, shards=shards)
    return scheduler.schedule_daily(mode=mode)


if __name__ == "__main__":
    run_worker(loop=False)
