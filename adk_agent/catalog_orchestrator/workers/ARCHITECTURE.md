# Catalog Workers — Module Architecture

Cloud Run Job entry points for automated exercise catalog curation. Each worker runs as a separate Cloud Run Job on a schedule (configured via Cloud Scheduler).

## File Inventory

| File | Purpose |
|------|---------|
| `catalog_worker.py` | Main worker: polls `catalog_jobs` queue, dispatches to `app/jobs/executor.py`. Also supports `watchdog` mode (pass as CLI arg) for cleaning up expired leases. Uses `gemini-2.5-flash` for LLM operations. |

## Cloud Run Jobs

| Job | YAML | Schedule | Entry Point |
|-----|------|----------|-------------|
| `catalog-worker` | `cloud-run-worker.yaml` | Every 15 min | `python workers/catalog_worker.py` |
| `catalog-review` | `cloud-run-review.yaml` | Every 3 hours | `python -m app.reviewer.scheduled_review` |
| `catalog-cleanup` | `cloud-run-cleanup.yaml` | Daily 08:00 UTC | `python cli.py cleanup-jobs --apply` |
| `catalog-watchdog` | `cloud-run-watchdog.yaml` | Every 6 hours | `python workers/catalog_worker.py watchdog` |

## Job Queue Interaction

```
Firestore: catalog_jobs/{jobId}
    → status: "queued" | "leased" | "running" | "succeeded" | "failed" | "needs_review"
    → type: TARGETED_FIX | CATALOG_ENRICH_FIELD | EXERCISE_ADD | ... (15 types)
    → payload: { family_slug, exercise_doc_ids[], mode, enrichment_spec?, ... }

catalog_worker.py:
    1. Polls for status="queued" jobs (priority queue first, then maintenance)
    2. Acquires lease (sets lease_owner, lease_expires_at)
    3. Dispatches to app/jobs/executor.py
    4. Updates status to "succeeded" or "failed"
    5. Records run summary in catalog_run_summaries
```

## Import Boundary

Cloud Run workers MUST NOT import from `app.shell.tools` or `app.shell.agent` — those
modules depend on `google.adk` which is only available in the Agent Engine runtime.

- Job context: import from `app.jobs.context` (NOT `app.shell.context`)
- Job execution: import from `app.jobs.executor` (NOT `app.shell.agent`)
- Docker image uses `worker_requirements.txt` (NOT `agent_engine_requirements.txt`)

## Cross-References

- Orchestrator core: `adk_agent/catalog_orchestrator/app/`
- Job context: `app/jobs/context.py` (JobContext, contextvars)
- Job executor: `app/jobs/executor.py` (central dispatcher)
- Deploy: `make deploy` (builds Docker, pushes to GCR, deploys all 4 jobs)
- Makefile targets: `make deploy`, `make test`, `make worker-local`
