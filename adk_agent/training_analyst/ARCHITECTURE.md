# Training Analyst Service Architecture

## Overview

The Training Analyst Service provides automated AI-powered analysis of user training data. It runs as a set of Cloud Run Jobs that process analysis jobs from a Firestore queue.

## Components

### Job Queue (`app/jobs/`)

Firestore-backed job queue with lease-based concurrency control.

**Collection**: `training_analysis_jobs`

**Job Types**:
- `POST_WORKOUT`: Immediate post-workout analysis
- `DAILY_BRIEF`: Daily readiness assessment
- `WEEKLY_REVIEW`: Weekly comprehensive review

**Key Files**:
- `models.py`: Job, JobPayload, JobStatus, JobType
- `queue.py`: Job creation, polling, leasing, completion
- `watchdog.py`: Stuck job recovery

**Job Lifecycle**:
1. `QUEUED` → Created, ready to process
2. `LEASED` → Claimed by worker
3. `RUNNING` → Actively processing
4. `SUCCEEDED` or `FAILED` → Terminal states

**No Family Locks**: Unlike catalog_orchestrator, training analysis jobs are user-scoped and don't require family locks (no conflicts).

### Analyzers (`app/analyzers/`)

Three specialized analyzers with distinct data budgets and LLM models.

**Base Analyzer** (`base.py`):
- Shared LLM client (`google.genai` SDK with Vertex AI backend)
- Structured logging
- JSON response parsing (response_mime_type="application/json")

**Post-Workout Analyzer** (`post_workout.py`):
- Model: `gemini-2.5-pro` (temperature=0.2)
- Budget: ~8KB
- Reads: trimmed workout + 4 weeks rollups + exercise series
- Writes: `users/{uid}/analysis_insights/{autoId}` (TTL 7 days)
- Output: summary, typed highlights, severity-flagged issues, confidence-scored recommendations
- Recommendation types: `progression`, `deload`, `swap`, `volume_adjust`, `rep_progression`, `intensity_adjust`
- Uses double progression model: reps increase before weight increase when user hasn't hit target reps
- Optional output fields: `suggested_weight`, `target_reps`, `target_rir`, `sets_delta`

**Daily Brief Analyzer** (`daily_brief.py`):
- Model: `gemini-2.5-flash` (temperature=0.3)
- Budget: ~3KB
- Reads: next template + current week rollup + latest insights
- Writes: `users/{uid}/daily_briefs/{YYYY-MM-DD}` (TTL 7 days)
- Output: readiness level, fatigue flags per muscle group, adjustment suggestions

**Weekly Review Analyzer** (`weekly_review.py`):
- Model: `gemini-2.5-pro` (temperature=0.2)
- Budget: ~35KB
- Reads: 12 weeks rollups + top 10 exercise series + 8 muscle group series
- Writes: `users/{uid}/weekly_reviews/{YYYY-WNN}` (TTL 30 days)
- Output: training load delta, muscle balance, exercise trends, progression candidates, stalled exercises
- `progression_candidates` includes `target_reps` (for rep progression) and `suggested_weight` (for weight progression)
- `stalled_exercises` includes `target_reps` and `suggested_weight` fields mapped to `suggested_action`
- All stalled exercise actions now processed: `increase_weight`, `deload`, `swap`, `vary_rep_range`
- `muscle_balance` data used for routine-scoped recommendations and readiness derivation

**Data Budget Strategy**: NEVER pass raw workout docs, set_facts, or full history to LLM. Only use pre-aggregated data (analytics_rollups, series_*).

### Workers (`workers/`)

Three Cloud Run Jobs for bounded execution.

**Analyst Worker** (`analyst_worker.py`):
- Polls for jobs (exits if none)
- Routes to appropriate analyzer
- Heartbeat for lease renewal
- Graceful shutdown on signals
- Bounded execution (MAX_JOBS_PER_RUN, MAX_SECONDS_PER_RUN)

**Scheduler** (`scheduler.py`):
- Runs daily at 6 AM
- Creates WEEKLY_REVIEW jobs on Sundays
- Filters users with recent workouts
- Daily brief scheduling removed (2026-02-20): readiness data is now derived from weekly review muscle_balance in the workout brief builder

**Watchdog** (`watchdog.py`):
- Recovers stuck jobs (expired leases)
- Re-queues with exponential backoff
- Marks as failed after max_attempts (3)

## Cloud Run Jobs

Three jobs deployed to `europe-west1`:

1. **training-analyst-worker**
   - Triggered by Cloud Scheduler every 15 minutes
   - Processes analysis jobs
   - 1 hour timeout, 2Gi memory

2. **training-analyst-scheduler**
   - Triggered daily at 6 AM
   - Creates daily/weekly jobs
   - 30 minute timeout, 512Mi memory

3. **training-analyst-watchdog**
   - Triggered hourly
   - Recovers stuck jobs
   - 30 minute timeout, 512Mi memory

## Deployment

```bash
# Build and push Docker image
make docker-push

# Deploy all jobs
make deploy

# Trigger manually
make trigger-worker
make trigger-scheduler
make trigger-watchdog
```

## Local Testing

```bash
# Install dependencies
make install

# Run worker locally
make worker-local

# Run scheduler locally
make scheduler-local

# Run watchdog locally
make watchdog-local
```

## Backfill

For generating historical analysis (e.g., after onboarding a user or importing workout history), use the two-step backfill process:

**Step 1 — Rebuild analytics foundation:**
```bash
FIREBASE_SERVICE_ACCOUNT_PATH=$FIREBASE_SA_KEY \
  node scripts/backfill_set_facts.js --user <userId> --rebuild-series
```

This populates `set_facts`, `series_exercises`, `series_muscle_groups`, `series_muscles`, and `analytics_rollups` from raw workout data.

**Step 2 — Enqueue analysis jobs:**
```bash
FIREBASE_SERVICE_ACCOUNT_PATH=$FIREBASE_SA_KEY \
  node scripts/backfill_analysis_jobs.js --user <userId> --months 3
```

Creates idempotent jobs with deterministic IDs (`bf-pw-{hash}`, `bf-wr-{hash}`, `bf-db-{hash}`). Safe to re-run — overwrites rather than duplicates.

**Step 3 — Process jobs:**
```bash
GOOGLE_APPLICATION_CREDENTIALS=$GCP_SA_KEY \
  PYTHONPATH=adk_agent/training_analyst \
  python3 adk_agent/training_analyst/workers/analyst_worker.py
```

Or trigger the Cloud Run Job: `make trigger-worker`

**Backfill script options:**
- `--user <userId>` or `--all-users`: Target scope
- `--months <n>`: Window (default: 3)
- `--skip-workouts`, `--skip-weekly`, `--skip-daily`: Skip specific job types
- `--dry-run`: Preview without writing

**Required Firestore index**: `training_analysis_jobs` composite index on `status` (ASC) + `created_at` (ASC). The worker will fail with a `FailedPrecondition` error if this index doesn't exist. Create it via:
```bash
gcloud firestore indexes composite create \
  --collection-group=training_analysis_jobs \
  --field-config field-path=status,order=ASCENDING \
  --field-config field-path=created_at,order=ASCENDING \
  --project=myon-53d85
```

## Key Differences from Catalog Orchestrator

1. **No family locks**: User-scoped jobs don't conflict
2. **Simpler status enum**: No dry_run/needs_review/deadletter
3. **Max attempts = 3**: Lower retry count
4. **Different LLM SDK**: google.genai with Vertex AI backend (not ADK Agent SDK)
5. **Data budget focus**: All reads are from aggregated collections

## Security

- All reads/writes scoped to `user_id` from job payload
- No client-provided userId (jobs created server-side)
- Output documents have TTL for automatic cleanup
- All LLM calls use JSON response mode

## Monitoring

Structured JSON logs for:
- `worker_started` / `worker_stopped`
- `job_started` / `job_completed` / `job_failed`
- `heartbeat_started` / `heartbeat_stopped`
- `analyzer_*` events

All logs include:
- `worker_id`, `job_id`, `job_type`, `user_id`
- `duration_ms` for timing
- `attempt` for retry tracking
