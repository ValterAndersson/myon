# Catalog Admin Autopilot

This document summarizes the deterministic, safety-first autopilot lanes introduced for the Catalog Admin agent.

## Lanes and risk tiers
- **Realtime lane**: Processes single exercises as they are created. Allows Tier 0 (format/lint fixes) and Tier 1 (safe alias upserts). Defaults to `mode=apply` because policy gates all writes.
- **Batch lane**: Deterministic shards (`hash(family_slug) % N`) run daily. Defaults to `dry_run` and applies Tier 0/1 only when lint improvement exceeds threshold and cooldown allows.

## Action plan schema
All LLM or heuristic outputs must conform to the `ActionPlan` model in `adk_agent/catalog_admin/app/action_schema.py`:

```json
{
  "lane": "realtime|batch",
  "mode": "dry_run|apply",
  "target": { "type": "exercise|family|alias|shard", "id": "string" },
  "actions": [
    {
      "op_type": "upsert_exercise|upsert_alias|delete_alias|normalize_page|noop",
      "risk_tier": 0,
      "field_path": "string",
      "before": {},
      "after": {},
      "evidence_tag": "enum",
      "confidence": 0.0,
      "idempotency_key": "string",
      "plan_hash": "string"
    }
  ],
  "summary": { "lint_before": 0.0, "lint_after": 0.0, "improvement": 0.0, "cooldown_blocked": false, "reasons": [] }
}
```

Key guardrails:
- `field_path` is whitelisted; aliases must use `alias:` prefix.
- `risk_tier` must match `op_type` (see `OPERATION_RISK_TIERS`).
- `noop` is valid and expected when no lint improvement is possible.

## Policy middleware
`PolicyMiddleware` enforces:
- Lane allowlists for tiers (realtime: 0/1, batch: 0/1; tier2/3 feature flagged).
- Cooldown blocking (`COOLDOWN_DAYS` env, default 7) to avoid oscillation.
- Lint improvement gate for batch lane (`LINT_THRESHOLD`, default 0.05).
- Field path validation and risk gating.

Rejected actions return machine-readable reasons. No tool call bypasses this layer.

## Locking, idempotency, and journaling
- The Firebase client now accepts `idempotency_key`, `plan_hash`, and `lock_token` for exercise and alias mutations. Server-side enforcement is expected on the Functions boundary.
- `LockManager` acquires per-family leases via Functions (`acquireCatalogLock`, `renewCatalogLock`, `releaseCatalogLock`).
- `JournalWriter` emits structured change records through `catalogJournal`.

## Task queue and runners
- `TaskQueue` wraps Functions endpoints to enqueue/lease/complete catalog tasks.
- `DeterministicShardScheduler` enqueues N shard tasks for the daily batch run.
- `runner.py` provides:
  - `run_worker()` to pull tasks, generate action plans, apply policy, and execute mutations with locks and journaling.
  - `enqueue_realtime_task(exercise_id)` for Firestore triggers to push new exercises.
  - `schedule_daily_shards()` for cron-style daily scheduling.

## Linting and cooldown
- `lint.py` provides deterministic scoring of required fields, banned phrases, and cue richness.
- `CooldownTracker` records per-field timestamps to block style churn across runs.

## Defaults and feature flags
- Batch lane defaults to dry run; enable apply via `ENABLE_BATCH_APPLY=1`.
- Tier2/3 are disabled by default; enable explicitly via `ENABLE_TIER2` / `ENABLE_TIER3`.
- Cooldown and lint thresholds are environment-controlled to fail closed when unset.

## Expected behavior
- Re-running batch on an unchanged catalog yields mostly `noop` actions because lint improvement and cooldown gates block churn.
- Realtime tasks auto-apply Tier 0/1 fixes with idempotent, locked writes and journaling.
- All mutations are accompanied by plan hashes and idempotency keys so retries and duplicates are safe.
