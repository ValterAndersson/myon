# Catalog Orchestrator V2 - Deployment Guide

## Quick Start: Production Deployment

### Prerequisites

- `gcloud` CLI installed and authenticated
- Docker installed
- Project: `myon-53d85`
- Region: `europe-west1`

### 1. Create Catalog Backup (REQUIRED)

Before any automated changes, create a backup:

```bash
# Via CLI (recommended)
python cli.py backup-catalog --target exercises-v2-backup

# Or via curl
curl -X POST "https://us-central1-myon-53d85.cloudfunctions.net/duplicateCatalog" \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  -d '{"target": "exercises-v2-backup"}'
```

### 2. Build and Push Docker Image

```bash
cd adk_agent/catalog_orchestrator

# Build and push
docker build -t gcr.io/myon-53d85/catalog-worker:latest .
docker push gcr.io/myon-53d85/catalog-worker:latest
```

### 3. Deploy Cloud Run Jobs

```bash
# Deploy all 4 jobs from the YAML
gcloud run jobs replace cloud-run-job.yaml --region=europe-west1
```

This deploys:
- `catalog-worker` - Processes job queue
- `catalog-review` - LLM reviews catalog
- `catalog-cleanup` - Archives old jobs
- `catalog-watchdog` - Cleans up leases/locks

### 4. Create Cloud Scheduler Triggers

```bash
PROJECT_ID=myon-53d85
REGION=europe-west1

# Worker - every 15 minutes (processes job queue)
gcloud scheduler jobs create http trigger-catalog-worker \
    --project=$PROJECT_ID \
    --location=$REGION \
    --schedule="*/15 * * * *" \
    --uri="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/catalog-worker:run" \
    --http-method=POST \
    --oauth-service-account-email="${PROJECT_ID}@appspot.gserviceaccount.com" \
    --oauth-token-scope="https://www.googleapis.com/auth/cloud-platform"

# Review - every 3 hours (LLM catalog review) - V1.1: increased from daily
gcloud scheduler jobs create http trigger-catalog-review \
    --project=$PROJECT_ID \
    --location=$REGION \
    --schedule="0 */3 * * *" \
    --time-zone="UTC" \
    --uri="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/catalog-review:run" \
    --http-method=POST \
    --oauth-service-account-email="${PROJECT_ID}@appspot.gserviceaccount.com" \
    --oauth-token-scope="https://www.googleapis.com/auth/cloud-platform"

# Cleanup - daily at 08:00 UTC (archive old jobs)
gcloud scheduler jobs create http trigger-catalog-cleanup \
    --project=$PROJECT_ID \
    --location=$REGION \
    --schedule="0 8 * * *" \
    --time-zone="UTC" \
    --uri="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/catalog-cleanup:run" \
    --http-method=POST \
    --oauth-service-account-email="${PROJECT_ID}@appspot.gserviceaccount.com" \
    --oauth-token-scope="https://www.googleapis.com/auth/cloud-platform"

# Watchdog - every 6 hours (clean up expired leases)
gcloud scheduler jobs create http trigger-catalog-watchdog \
    --project=$PROJECT_ID \
    --location=$REGION \
    --schedule="0 */6 * * *" \
    --uri="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/catalog-watchdog:run" \
    --http-method=POST \
    --oauth-service-account-email="${PROJECT_ID}@appspot.gserviceaccount.com" \
    --oauth-token-scope="https://www.googleapis.com/auth/cloud-platform"
```

### 5. Verify Deployment

```bash
# List deployed jobs
gcloud run jobs list --region=$REGION

# Trigger worker manually to test
gcloud run jobs execute catalog-worker --region=$REGION --wait

# Check logs
gcloud logging read "resource.type=cloud_run_job AND resource.labels.job_name=catalog-worker" --limit=20
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      Cloud Scheduler                            │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ daily-review │  │ process-jobs │  │ daily-cleanup        │  │
│  │ 03:00 UTC    │  │ */15 min     │  │ 08:00 UTC            │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘  │
│         │ 0 */6           │                      │              │
│         │ watchdog        │                      │              │
└─────────┼─────────────────┼──────────────────────┼──────────────┘
          ▼                 ▼                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Cloud Run Jobs                               │
├─────────────────────────────────────────────────────────────────┤
│  ┌────────────────┐  ┌────────────────┐  ┌──────────────────┐  │
│  │ catalog-review │  │ catalog-worker │  │ catalog-cleanup  │  │
│  │ 4h timeout     │  │ 3h timeout     │  │ 1h timeout       │  │
│  │                │  │ APPLY=true     │  │                  │  │
│  └────────────────┘  └────────────────┘  └──────────────────┘  │
│                                                                 │
│  ┌────────────────┐                                             │
│  │ catalog-watchdog│                                            │
│  │ 30m timeout    │                                             │
│  └────────────────┘                                             │
└─────────────────────────────────────────────────────────────────┘
          │                 │                      │
          ▼                 ▼                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Firestore                                  │
├─────────────────────────────────────────────────────────────────┤
│  catalog_jobs         │ Job queue                               │
│  catalog_run_history  │ Audit log (permanent)                   │
│  catalog_run_summary  │ Daily aggregates                        │
│  catalog_changes      │ Mutation journal                        │
│  exercises            │ Exercise catalog                        │
└─────────────────────────────────────────────────────────────────┘
```

## Scheduled Jobs Summary

| Job | Schedule | Timeout | What It Does |
|-----|----------|---------|--------------|
| **catalog-worker** | Every 15 min | 3h | Processes job queue (unlimited jobs per run) |
| **catalog-review** | Every 3 hours | 4h | LLM reviews 1000 exercises, creates fix/enrich/add jobs (V1.1: was daily) |
| **catalog-cleanup** | Daily 08:00 UTC | 1h | Archives jobs >7 days, deletes from queue |
| **catalog-watchdog** | Every 6 hours | 30m | Cleans up expired leases, dead locks |

---

## Monitoring

### CLI Commands

```bash
# Queue status
python cli.py queue-stats

# Recent jobs
python cli.py list-jobs --limit 20

# Job details
python cli.py job-status <job-id>

# Run history
python cli.py run-history --limit 50

# Daily summary
python cli.py daily-summary

# Audit trail
python cli.py list-changes --limit 10
```

### Cloud Logging Queries

```
# All worker events
resource.type="cloud_run_job" AND resource.labels.job_name="catalog-worker"

# Completed jobs
jsonPayload.event="job_completed"

# Failures
jsonPayload.event="job_failed"
```

---

## Service Account Permissions

The Cloud Run service account needs:

| Role | Purpose |
|------|---------|
| `roles/datastore.user` | Read/write Firestore |
| `roles/aiplatform.user` | Call Vertex AI (Gemini) |
| `roles/logging.logWriter` | Write structured logs |

```bash
PROJECT_ID=myon-53d85
SA_EMAIL="${PROJECT_ID}@appspot.gserviceaccount.com"

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/datastore.user"

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/aiplatform.user"
```

---

## Troubleshooting

### Worker exits with "no_jobs_available"
This is expected - worker exits immediately when queue is empty. No cost.

### Review job timeout
Increase `--max-exercises` limit or increase timeout in `cloud-run-job.yaml`.

### Apply gate blocked
Check that `CATALOG_APPLY_ENABLED=true` in Cloud Run Job config.

### LLM rate limits
The review job uses Gemini 2.5 Pro for reasoning. If hitting rate limits, reduce batch size in `scheduled_review.py`.

---

## Local Development

### Emulator Testing

```bash
# Terminal 1: Start emulator
cd firebase_functions && firebase emulators:start --only firestore

# Terminal 2: Run worker against emulator
cd adk_agent/catalog_orchestrator
FIRESTORE_EMULATOR_HOST="localhost:8080" python cli.py run-worker --apply
```

### Dry-Run Review

```bash
python cli.py run-review --max-exercises 50 -v
```

### Manual Job Creation

```bash
# Add exercise
python cli.py insert-exercise --base-name "Lateral Raise" --equipment cable --mode apply

# Run worker
python cli.py run-worker --apply
```
