# Catalog Admin Agent: Robustness and Determinism Review

This document synthesizes the earlier review deliverables (system map, bottlenecks, failure modes, determinism spec, autopilot proposal, and tests) with an additional focus on the current agent instructions/prompts. It emphasizes ways to keep LLM reasoning valuable while constraining effects through strict schemas and policy layers.

## A) System map (call graph and boundaries)
- **Invocation paths**
  - CLI smoke tests call `FirebaseFunctionsClient` directly for health/list/search operations and bypass the agent stack.
  - The orchestrator exposes LLM tools and remote Firebase tools via `google.adk.tools.FunctionTool` definitions; all mutate/read calls go through `_client()` which wraps Firebase Functions HTTP endpoints.
- **Agent flow**
  - `tool_llm_fetch_catalog` pulls canonical exercises and families, optionally repairing missing fields by re-fetching details per exercise ID.
  - `tool_llm_analyst` routes issues to role specialists (content/biomechanics/anatomy/programming), re-runs the analyst on refreshed data, and then auto-invokes the approver when possible.
- **State mutations**
  - Writes funnel through Firebase tools such as `upsert_exercise`, `upsert_alias`, `delete_alias`, `mergeExercises`, and `normalize_catalog_page`.
- **Failure boundaries**
  - Firebase Functions are the remote boundary; the HTTP client currently issues single-shot requests without built-in retries, idempotency, or caching.

## B) Bottlenecks and concrete fixes
1. **Sequential mandatory workflow**: Analyst → specialists → analyst (verify) → approver always runs, even when no high-severity issues exist. This forces extra LLM calls and catalog refreshes.
   - *Fix*: Gate specialist routing and re-verification on high/critical issues; batch/paginate catalog fetches so clean runs avoid redundant passes.
2. **Chatty detail repair during fetch**: Catalog fetch re-queries up to 50 exercises individually to repair missing fields, adding latency and tool cost.
   - *Fix*: Memoize per-run exercise detail lookups, short-circuit when names/descriptions are present, or add a batch detail endpoint; cap retries with jitter.
3. **No HTTP resilience**: Firebase HTTP calls lack retry/backoff/timeouts, so transient 429/5xx abort runs and leave partial work.
   - *Fix*: Add a resilient HTTP wrapper with configurable retry/backoff + per-call timeouts; expose defaults via environment variables and plumb through `_client()`.
4. **Deployment without automation hooks**: Agent Engine deploy emits metadata but no scheduler/health runner.
   - *Fix*: Provide a runner module for scheduled/queued execution with health pings and run records; document flags for dry-run/apply.

## C) Failure modes and safety measures
| Failure mode | Impact | Detectability | Prevention | Recovery |
| --- | --- | --- | --- | --- |
| Transient Firebase errors during writes | Partial mutations; stuck runs | Low (exceptions only) | Retries/backoff; idempotency keys per operation | Replay failed ops with same keys; mark failed batches |
| Non-idempotent merges/alias upserts | Duplicate/incorrect links | Medium (logs only) | Hash-based idempotency keys; change journal with before/after | Roll back via journal or reapply corrected payloads |
| LLM-driven destructive actions without guardrails | Data loss across families | Low (silent) | Policy layer requiring evidence + dry-run; deny cross-family merges | Restore from backups; replay change plan |
| Concurrent runs on same family | Conflicting edits | Low | Per-family lock/lease around mutating tools; defer when locked | Retry deferred families; reconcile using journal |
| Schema drift or malformed exercise payloads | Corrupt records | Medium | Strict schema validation before upserts; refuse invalid payloads | Fix schema errors offline and re-run validator + upsert |

## D) Determinism spec (rules and schemas)
- **Routing rules**: Only route to specialists when analyst reports *critical/high* issues for fields mapped to that role; otherwise exit after analyst.
- **Canonical identity**: Do not change `family_slug`/`variant_key` unless policy thresholds are met; never merge across families.
- **Alias policies**: Upsert only if canonical exercise exists and alias is unmapped; delete only when alias is incorrect and replacement mapping is provided.
- **Approval gating**: Auto-approve only when post-specialist analyst verification has zero high-severity issues; else emit a pending decision record.
- **Schema enforcement**: Apply JSON/pydantic schemas for exercises, aliases, and analyst/specialist reports before tool calls. Reject or request repair via schema-validator tool.
- **Dry-run first**: Every mutating operation supports `apply=False` (plan mode). Default automation to dry-run and require policy approval for apply.

## E) Autopilot implementation proposal
- **Trigger**: Scheduled batch scans (cron or Agent Engine timer) that page through families and recent search logs. Future-ready for event hooks.
- **Runner**: New `app/runner.py` orchestrates fetch → policy evaluation → apply/dry-run, with per-run caps and structured change records.
- **Locking**: Acquire per-`family_slug` leases before mutating; defer locked families.
- **Backpressure & retries**: Exponential backoff on Firebase 429/5xx; queue overflow families for next run; cap mutations per run.
- **Auditability**: Emit change journal entries (operation type, idempotency key, before/after, actor, timestamps) to durable storage.
- **Modes**: `--dry-run` (plan only), `--apply` (with journal), and shadow mode (compare proposed vs actual without writes).

## F) Test and evaluation plan
- Unit tests for policy rules, normalization helpers, and alias validation (pure functions).
- Contract tests with mocked Firebase client to cover retry/backoff and idempotency paths.
- Golden fixtures for family normalization outputs; regression harness to assert identical change plans per snapshot.
- Extended CLI smoke tests to cover dry-run autopilot and schema validation paths.

## G) Agent instruction hardening (keep reasoning, enforce outcomes)
- **Analyst**: The current prompt emphasizes thoroughness and outputs per-issue severities but allows any severity mix. Add an explicit JSON schema in the prompt with required fields and a deterministic mapping from issue field → specialist role to reduce variance while keeping reasoning-rich explanations. Lower temperature is already set; prefer batch analysis to avoid per-item variance drift.
- **Specialists**: Encode role-specific “allowed transformations” (e.g., content may edit descriptions/coaching cues; biomechanics may edit movement/equipment). Require each suggested change to include: field path, before/after, justification, and an evidence tag. Deny destructive actions without evidence.
- **Scout/Triage**: Add guardrails to avoid draft creation unless confidence exceeds a threshold and schema validation passes. Keep reasoning by asking for hypothesis + evidence, but require the final output array to match a strict schema (idempotency key, proposed action, rationale, apply flag).
- **Approver**: Constrain to binary decisions with justification referencing evidence from analyst/specialists; default to “pending/manual” when any critical issue remains or confidence is low. Emit an approval record compatible with the change journal schema.
- **Schema Validator**: Treat as a mandatory pre-flight for mutating calls; ask the LLM to return both “fixed payload” and “reasons” arrays to preserve reasoning while producing deterministic, schema-validated JSON.

## H) Pipeline robustness patterns (actionable next steps)
1. **Policy middleware**: Insert a policy layer between LLM outputs and Firebase tools that enforces schemas, checks evidence/confidence thresholds, and toggles dry-run/apply. This keeps LLM creativity for diagnosis but constrains effects.
2. **Idempotent mutations**: Generate operation hashes from `family_slug`, `variant_key`, and payload to de-dupe retries. Pass the hash to Firebase tools and the change journal.
3. **Structured change journal**: Every mutation (or proposed mutation in dry-run) emits a record `{op_type, idempotency_key, target_ids, before, after, evidence, mode, timestamp}`. Use it for auditing, rollback, and replay.
4. **Per-family locking**: Wrap mutating tools with a lock acquisition/release guard to avoid cross-run collisions; store lock tokens in the journal for traceability.
5. **Observation-first mode**: Start automation in shadow/dry-run, compare proposed change plans to human expectations, and progressively enable apply for low-risk families. This preserves LLM reasoning outputs while keeping production deterministic.

