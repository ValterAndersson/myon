# Jobs Module — Architecture

Job queue, execution, context management, and self-healing for the Catalog Orchestrator. This is the engine that processes all catalog curation work.

## File Inventory

| File | Purpose |
|------|---------|
| `__init__.py` | Package exports: context, models, queue, watchdog. |
| `context.py` | **Canonical** `JobContext` + `contextvars` for per-job isolation. Cloud Run workers import from here (not `app.shell.context`). |
| `models.py` | `Job`, `JobType` (15 types), `JobQueue`, `JobStatus`, `JobPayload`, `AttemptLog` dataclasses. |
| `queue.py` | Queue operations: `create_job`, `poll_job`, `lease_job`, `complete_job`, `fail_job`, `retry_job`. Priority queue polled first, then maintenance. |
| `executor.py` | Central dispatcher. Routes `Job` → handler by `JobType`. Includes repair loop, enrichment sharding, and post-enrichment scanner check. |
| `handlers.py` | Additional handlers: family split, family rename, alias repair, merge candidate. |
| `run_history.py` | Execution audit trail. Writes to `catalog_run_summaries`, provides `get_run_history()` and `get_daily_summary()`. |
| `watchdog.py` | Self-healing: `recover_stuck_jobs()` (expired leases → queued), `cleanup_expired_locks()`, `cleanup_idempotency_records()`. |

## Context Management

```
ContextVar: _job_context_var (per-request isolation)
    │
    ├── set_current_job_context(ctx)   # Called at job start
    ├── get_current_job_context()      # Used by skills/handlers
    └── clear_current_job_context()    # Called at job end
```

**Why `contextvars`:** Cloud Run workers may process concurrent requests (Vertex AI Agent Engine is serverless). Module-level globals would leak state across requests. `ContextVar` provides thread-safe, async-safe isolation.

**Import boundary:** Cloud Run workers import `JobContext` from `app.jobs.context`. The `app.shell.context` module re-exports these for the ADK agent (which runs on Agent Engine with `google.adk` available). Workers must never import `app.shell.*`.

## Job Execution Flow

```
catalog_worker.py
    │
    ├── poll_job()              # Priority queue first, then maintenance
    ├── lease_job()             # Sets lease_owner, lease_expires_at
    ├── set_current_job_context()
    │
    ▼
executor.py: execute(job)
    │
    ├── Route by JobType → handler function
    ├── Handler builds ChangePlan
    ├── ApplyEngine executes plan (if mode=apply)
    │
    ├── Post-enrichment check (for CATALOG_ENRICH_FIELD_SHARD):
    │   └── heuristic_score_exercise() on updated doc
    │       └── Logs warning if still fails scanner (observability only)
    │
    ├── complete_job() on success
    └── fail_job() on error
```

## Post-Enrichment Validation

After holistic enrichment, `executor.py` runs `heuristic_score_exercise()` from the quality scanner on the updated exercise data. This is **observability only** — it logs a warning if the exercise still fails quality checks after enrichment, but does not block the write. The `scanner_fail` count is included in the job result summary.

## Key Design Decisions

**Priority queue first.** `poll_job()` checks the priority queue before maintenance. This ensures user-triggered jobs (EXERCISE_ADD, TARGETED_FIX) run before background enrichment.

**Lease-based concurrency.** Jobs are "leased" to a worker with an expiry timestamp. If the worker crashes, the watchdog resets expired leases back to "queued" for retry.

**Repair loop.** `execute_with_repair_loop()` retries failed executions up to `max_repairs` times (default: 3). On each retry, the LLM analyzes validation errors and suggests fixes. If repairs are exhausted, the job is set to `needs_review`.

## Cross-References

- Cloud Run worker: `workers/catalog_worker.py` (imports from this package)
- Shell agent shim: `app/shell/context.py` (re-exports `JobContext` for ADK agent)
- Apply engine: `app/apply/engine.py` (executes ChangePlans built by handlers)
- Quality scanner: `app/reviewer/quality_scanner.py` (post-enrichment check)
- Enrichment engine: `app/enrichment/engine.py` (called by executor for ENRICH shards)
