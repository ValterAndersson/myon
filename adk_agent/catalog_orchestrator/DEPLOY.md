# Catalog Orchestrator Deployment Guide

## Prerequisites

- Google Cloud SDK (`gcloud`) installed and configured
- Docker installed (for building container images)
- Project with Firestore enabled

## Local Development (Emulator)

The fastest way to test the worker without touching production Firestore is using the Firebase Emulator.

### Prerequisites

```bash
# Install Firebase CLI if not present
npm install -g firebase-tools
```

### Quick Start

```bash
cd adk_agent/catalog_orchestrator

# Terminal 1: Start Firestore emulator
make emulator-start

# Terminal 2: Seed test data and run worker
make emulator-seed
make worker-emulator-apply  # Full read/write to emulator
```

### What This Does

1. Starts Firestore emulator at `localhost:8080`
2. Creates test exercise data
3. Runs worker against emulator (not production)
4. You can verify writes in emulator UI at `http://localhost:4000`

### Testing Modes

| Command | Firestore | Writes | Use Case |
|---------|-----------|--------|----------|
| `make worker-local` | Production | Dry-run | Safe local testing |
| `make worker-emulator` | Emulator | Dry-run | Test job queue logic |
| `make worker-emulator-apply` | Emulator | **Enabled** | Full integration test |

### Testing Without LLM

If you want to skip LLM calls entirely for faster iteration, set:

```bash
export SKIP_LLM=true
make worker-emulator
```

The worker will use stub responses instead of calling Gemini.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      TRIGGERS                               │
├─────────────────────────────────────────────────────────────┤
│  CLI / Admin UI → create_job() → catalog_jobs/{jobId}       │
│  Cloud Scheduler → Cloud Run Job (every 10-30 min)          │
│  Cloud Scheduler → Watchdog (every 5 min)                   │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                      WORKER                                 │
├─────────────────────────────────────────────────────────────┤
│  Cloud Run Job: catalog-worker                              │
│  - Polls catalog_jobs for queued jobs                       │
│  - Acquires lease + family lock                             │
│  - Executes job via shell agent                             │
│  - Env: CATALOG_APPLY_ENABLED=true (prod only)              │
│  - Timeout: 15 minutes                                      │
└─────────────────────────────────────────────────────────────┘
```

## Service Account Permissions

### Runtime Service Account (for Cloud Run Jobs)

The Cloud Run Job runtime service account needs:

| Permission | Reason |
|------------|--------|
| `roles/datastore.user` | Read/write Firestore collections |
| `roles/logging.logWriter` | Write structured logs |

**Setup:**
```bash
# Use default compute service account or create dedicated one
PROJECT_ID=your-project-id
SA_NAME=catalog-worker
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

# Create service account
gcloud iam service-accounts create $SA_NAME \
    --display-name="Catalog Worker"

# Grant Firestore access
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/datastore.user"

# Grant logging access
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/logging.logWriter"
```

### Trigger Service Account (for Cloud Scheduler / CLI)

If triggering Cloud Run Jobs from Cloud Scheduler or programmatically:

| Permission | Reason |
|------------|--------|
| `roles/run.invoker` | Execute Cloud Run Jobs |
| `roles/iam.serviceAccountUser` | Act as the runtime SA (if different) |

**Setup:**
```bash
# Grant scheduler service account ability to trigger jobs
SCHEDULER_SA="service-${PROJECT_NUMBER}@gcp-sa-cloudscheduler.iam.gserviceaccount.com"

gcloud run jobs add-iam-policy-binding catalog-worker \
    --region=europe-west1 \
    --member="serviceAccount:${SCHEDULER_SA}" \
    --role="roles/run.invoker"
```

## Deployment Steps

### 1. Build and Push Container

```bash
cd adk_agent/catalog_orchestrator

# Set project
export PROJECT_ID=your-project-id
export REGION=europe-west1

# Build and push
make docker-push PROJECT_ID=$PROJECT_ID
```

### 2. Deploy Cloud Run Jobs

```bash
# Deploy worker and watchdog
make deploy-jobs PROJECT_ID=$PROJECT_ID REGION=$REGION
```

### 3. Create Cloud Scheduler Triggers

```bash
# Maintenance worker (every 15 minutes)
gcloud scheduler jobs create http trigger-catalog-worker \
    --location=$REGION \
    --schedule="*/15 * * * *" \
    --uri="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/catalog-worker:run" \
    --http-method=POST \
    --oauth-service-account-email="${SCHEDULER_SA}"

# Watchdog (every 5 minutes)
gcloud scheduler jobs create http trigger-catalog-watchdog \
    --location=$REGION \
    --schedule="*/5 * * * *" \
    --uri="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/catalog-watchdog:run" \
    --http-method=POST \
    --oauth-service-account-email="${SCHEDULER_SA}"
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_JOBS_PER_RUN` | 10 | Max jobs to process per execution |
| `MAX_SECONDS_PER_RUN` | 840 | Time budget (14 min) |
| `SAFETY_MARGIN_SECS` | 60 | Buffer before timeout |
| `CATALOG_APPLY_ENABLED` | false | **Set to `true` only in production** |
| `WATCHDOG_DRY_RUN` | true | Set to `false` for actual cleanup |

## Testing Sequence

### 1. Staging (Dry-Run Only)

```bash
# Create a job
python cli.py insert-exercise --base-name "Test Exercise" --equipment dumbbell

# Trigger worker
make trigger-worker PROJECT_ID=$PROJECT_ID REGION=$REGION

# Check status
python cli.py job-status job-xxx
```

### 2. Verify Apply Gate

Create an apply-mode job with `CATALOG_APPLY_ENABLED=false`:

```bash
python cli.py insert-exercise --base-name "Test" --equipment barbell --mode apply
make trigger-worker
# Should fail with APPLY_GATE_BLOCKED error
```

### 3. Production (Apply Mode)

1. Update Cloud Run Job env: `CATALOG_APPLY_ENABLED=true`
2. Create job with `--mode apply`
3. Verify writes in Firestore

## Firestore Collections

The worker reads/writes these collections:

| Collection | Purpose |
|------------|---------|
| `catalog_jobs` | Job queue |
| `catalog_locks` | Family-level locks |
| `catalog_job_runs` | Attempt logs (subcollection) |
| `catalog_changes` | Mutation journal |
| `exercises` | Exercise documents |
| `exercise_aliases` | Alias mappings |
| `exercise_families` | Family registry |

## Firestore Indexes

Indexes will be auto-discovered when running against staging. When Firestore returns an error like:

```
The query requires an index. You can create it here: https://console.firebase.google.com/...
```

Click the link to create the index, then add to `firestore.indexes.json`.

## Troubleshooting

### Worker exits immediately with "no_jobs_available"

This is expected behavior. The worker exits fast when the queue is empty.

### Lock contention errors

Multiple workers may contend for the same family lock. The job will be retried automatically.

### Apply gate blocked

Set `CATALOG_APPLY_ENABLED=true` in the Cloud Run Job environment.

### Lease renewal failed

The job took too long. Increase `MAX_SECONDS_PER_RUN` or reduce job scope.

## Monitoring

### Structured Logs

All worker events are logged as JSON:

```json
{
  "event": "job_completed",
  "worker_id": "worker-abc123",
  "job_id": "job-xyz789",
  "job_type": "EXERCISE_ADD",
  "family_slug": "lateral-raise",
  "duration_ms": 12345
}
```

Query in Cloud Logging:
```
resource.type="cloud_run_job"
jsonPayload.event="job_completed"
```

### Key Metrics to Monitor

- Jobs processed per run
- Failed job rate
- Average job duration
- Lock contention rate
- Watchdog cleanup counts
