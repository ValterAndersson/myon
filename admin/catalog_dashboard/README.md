# Catalog Admin Dashboard

A lightweight admin dashboard for monitoring and managing the Catalog Orchestrator system.

## Features

### Catalog Orchestrator Tab
- **Queue Metrics**: Pending, running, succeeded, failed job counts
- **Cloud Run Jobs**: View status, run count, last execution with **manual trigger buttons**
- **Job Tooltips**: Hover on [?] to see job description, default parameters, and schedule
- **Scheduled Triggers**: View next run times for all scheduled jobs
- **Recent Queue Jobs**: Latest catalog jobs in the Firestore queue

### Run History Tab
- **Execution History**: View completed jobs with duration and status
- **Change Details**: Click a row to expand and see field-level changes (before/after)
- **Summaries**: View LLM-generated summaries of what was changed

### Logs Tab
- **Real-time Streaming**: Stream logs from Cloud Logging via SSE
- **Job Filtering**: Filter by specific job (worker, review, cleanup, watchdog)
- **Severity Coloring**: ERROR=red, WARNING=yellow, INFO=white

## Quick Start (Local)

```bash
cd admin/catalog_dashboard

# Install dependencies
pip3 install -r requirements.txt

# Authenticate with GCP (pick one)
gcloud auth application-default login          # interactive
export GOOGLE_APPLICATION_CREDENTIALS=$GCP_SA_KEY  # service account key

# Run locally
DEBUG=true python3 app.py

# Open http://localhost:8080
```

## Deploy to GCP

### 1. Re-authenticate
```bash
gcloud auth login
```

### 2. Deploy to Cloud Run
```bash
cd admin/catalog_dashboard
gcloud run deploy admin-dashboard \
    --source . \
    --region europe-west1 \
    --project myon-53d85 \
    --no-allow-unauthenticated \
    --service-account myon-53d85@appspot.gserviceaccount.com \
    --memory 512Mi \
    --cpu 1 \
    --timeout 300
```

### 3. Grant Access to mrhalycon@gmail.com Only
```bash
gcloud run services add-iam-policy-binding admin-dashboard \
    --region=europe-west1 \
    --project=myon-53d85 \
    --member="user:mrhalycon@gmail.com" \
    --role="roles/run.invoker"
```

### 4. Grant Service Account Permissions
```bash
SA=myon-53d85@appspot.gserviceaccount.com

gcloud projects add-iam-policy-binding myon-53d85 \
    --member="serviceAccount:$SA" \
    --role="roles/cloudscheduler.viewer"

gcloud projects add-iam-policy-binding myon-53d85 \
    --member="serviceAccount:$SA" \
    --role="roles/run.viewer"

gcloud projects add-iam-policy-binding myon-53d85 \
    --member="serviceAccount:$SA" \
    --role="roles/run.invoker"

gcloud projects add-iam-policy-binding myon-53d85 \
    --member="serviceAccount:$SA" \
    --role="roles/logging.viewer"
```

### 5. Access the Dashboard

Option A - Via gcloud proxy:
```bash
# Get service URL
URL=$(gcloud run services describe admin-dashboard --region=europe-west1 --format='value(status.url)')

# Get identity token and access
TOKEN=$(gcloud auth print-identity-token)
curl -H "Authorization: Bearer $TOKEN" $URL
```

Option B - Via browser with Cloud Run Proxy:
```bash
gcloud run services proxy admin-dashboard --region=europe-west1
# Opens http://localhost:8080
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/scheduler/jobs` | GET | Cloud Scheduler trigger statuses |
| `/api/cloudrun/jobs` | GET | Cloud Run Job execution status |
| `/api/cloudrun/jobs/<name>/trigger` | POST | Manually trigger a job |
| `/api/firestore/queue` | GET | Firestore job queue stats |
| `/api/firestore/run-history` | GET | Recent run history with changes |
| `/api/firestore/changes` | GET | Catalog change log |
| `/api/logs/stream` | GET (SSE) | Real-time log streaming |
| `/api/logs/recent` | GET | Recent logs (non-streaming) |
| `/api/status` | GET | Overall system health |

## Files

```
admin/catalog_dashboard/
├── app.py              # Flask backend
├── templates/
│   └── index.html      # Frontend UI
├── static/             # Static assets
├── requirements.txt    # Python dependencies
├── Dockerfile          # Container build
├── DEPLOY.md           # Detailed deployment guide
└── README.md           # This file
```

## Configuration

| Env Variable | Default | Description |
|--------------|---------|-------------|
| `GOOGLE_CLOUD_PROJECT` | `myon-53d85` | GCP project ID |
| `CLOUD_RUN_REGION` | `europe-west1` | Cloud Run region |
| `PORT` | `8080` | Server port |
| `DEBUG` | `false` | Enable debug mode |
