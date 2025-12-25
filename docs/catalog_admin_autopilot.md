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

Schema validation feedback:
- `validate_action_plan_payload` (in `app/action_schema.py`) turns any raw plan payload into either a parsed `ActionPlan` or a
  structured error object that echoes the attempted payload, the expected JSON schema, and machine-readable validation errors
  (path, message, type, offending input). This lets upstream LLM steps regenerate a compliant plan when they drift off schema.

## Policy middleware
`PolicyMiddleware` enforces:
- Lane allowlists for tiers (realtime: 0/1, batch: 0/1; tier2/3 feature flagged).
- Cooldown blocking (`COOLDOWN_DAYS` env, default 7) to avoid oscillation.
- Lint improvement gate for batch lane (`LINT_THRESHOLD`, default 0.05).
- Field path validation and risk gating.

Rejected actions return machine-readable reasons. No tool call bypasses this layer.

## Locking, idempotency, and journaling
- The Firebase client now accepts `idempotency_key`, `plan_hash`, and `lock_token` for exercise and alias mutations. Server-side enforcement is expected on the Functions boundary.
- `LockManager` acquires per-family leases via Functions (`acquireCatalogLock`, `renewCatalogLock`, `releaseCatalogLock`) and the runner now acquires the same lock for alias upserts/deletes to avoid cross-family collisions.
- `JournalWriter` emits structured change records through `catalogJournal`, including the mutated `field_path` for downstream cooldown tracking.

## Task queue and runners
- `TaskQueue` wraps Functions endpoints to enqueue/lease/complete catalog tasks.
- `DeterministicShardScheduler` enqueues N shard tasks for the daily batch run using a stable SHA-256 hash of `family_slug` to keep shards sticky across runs.
- `runner.py` provides:
  - `run_worker()` to pull tasks, generate action plans, apply policy, and execute mutations with locks and journaling.
  - `enqueue_realtime_task(exercise_id)` for Firestore triggers to push new exercises.
  - `schedule_daily_shards()` for cron-style daily scheduling.
  - Shard fetches bypass cache (`skipCache=true`) to avoid stale slices and request a broader page to reduce missed entities per shard.

## Motion GIF generation lane
- `MotionGifAgent` (opt-in via `ENABLE_MEDIA_AGENT=1`) requests a moving GIF from the Google image LLMs through the Functions boundary (`generateExerciseGif`).
- Deterministic knobs:
  - Stable prompt scaffold built from exercise name, movement type, and coaching cues.
  - Fixed style tag (`MEDIA_STYLE_TAG`, default `studio-motion`).
  - Seed derived from exercise id + style to keep frames consistent across reruns.
  - Storage prefix (`MEDIA_STORAGE_PREFIX`) sent to Functions so assets land in a predictable bucket path.
- Allowed lanes are restricted to batch by default; set `MEDIA_AGENT_REALTIME=1` to allow realtime lane generation.
- When a GIF is missing, the planner appends an `attach_motion_gif` action that simply upserts the returned asset metadata into the exercise while preserving the plan hash/idempotency guardrails.

## Linting and cooldown
- `lint.py` provides deterministic scoring of required fields, banned phrases, and cue richness.
- `CooldownTracker` records per-field timestamps to block style churn across and within runs; the runner updates cooldown state after successful mutations so later tasks in the same loop see the block immediately.

## Defaults and feature flags
- Batch lane defaults to dry run; enable apply via `ENABLE_BATCH_APPLY=1`.
- Tier2/3 are disabled by default; enable explicitly via `ENABLE_TIER2` / `ENABLE_TIER3`.
- Cooldown and lint thresholds are environment-controlled to fail closed when unset.

## Expected behavior
- Re-running batch on an unchanged catalog yields mostly `noop` actions because lint improvement and cooldown gates block churn.
- Realtime tasks auto-apply Tier 0/1 fixes with idempotent, locked writes and journaling.
- All mutations are accompanied by plan hashes and idempotency keys so retries and duplicates are safe.
