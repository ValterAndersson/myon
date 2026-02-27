#!/usr/bin/env bash
# deploy-schedulers.sh — Create Cloud Scheduler triggers for Training Analyst
#
# These triggers invoke Cloud Run Jobs on schedule.
# Jobs must be deployed first (make deploy).
#
# Usage: ./deploy-schedulers.sh [--delete-first]

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-myon-53d85}"
REGION="${REGION:-europe-west1}"
SA_EMAIL="ai-agents@${PROJECT_ID}.iam.gserviceaccount.com"

echo "=== Training Analyst — Cloud Scheduler Setup ==="
echo "Project: $PROJECT_ID"
echo "Region:  $REGION"
echo "SA:      $SA_EMAIL"
echo ""

if [[ "${1:-}" == "--delete-first" ]]; then
  echo "Deleting existing scheduler jobs..."
  gcloud scheduler jobs delete trigger-training-analyst-scheduler --location="$REGION" --project="$PROJECT_ID" --quiet 2>/dev/null || true
  gcloud scheduler jobs delete trigger-training-analyst-worker --location="$REGION" --project="$PROJECT_ID" --quiet 2>/dev/null || true
  gcloud scheduler jobs delete trigger-training-analyst-watchdog --location="$REGION" --project="$PROJECT_ID" --quiet 2>/dev/null || true
  echo ""
fi

echo "1/3 Creating scheduler trigger (daily 6 AM UTC — creates weekly jobs on Sundays)..."
gcloud scheduler jobs create http trigger-training-analyst-scheduler \
  --project="$PROJECT_ID" \
  --location="$REGION" \
  --schedule="0 6 * * *" \
  --uri="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/training-analyst-scheduler:run" \
  --http-method=POST \
  --oauth-service-account-email="$SA_EMAIL" \
  --oauth-token-scope="https://www.googleapis.com/auth/cloud-platform" \
  --description="Trigger training-analyst-scheduler Cloud Run Job"

echo "2/3 Creating worker trigger (every 15 min — processes job queue)..."
gcloud scheduler jobs create http trigger-training-analyst-worker \
  --project="$PROJECT_ID" \
  --location="$REGION" \
  --schedule="*/15 * * * *" \
  --uri="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/training-analyst-worker:run" \
  --http-method=POST \
  --oauth-service-account-email="$SA_EMAIL" \
  --oauth-token-scope="https://www.googleapis.com/auth/cloud-platform" \
  --description="Trigger training-analyst-worker Cloud Run Job"

echo "3/3 Creating watchdog trigger (every 6 hours — recovers stuck jobs)..."
gcloud scheduler jobs create http trigger-training-analyst-watchdog \
  --project="$PROJECT_ID" \
  --location="$REGION" \
  --schedule="0 */6 * * *" \
  --uri="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/training-analyst-watchdog:run" \
  --http-method=POST \
  --oauth-service-account-email="$SA_EMAIL" \
  --oauth-token-scope="https://www.googleapis.com/auth/cloud-platform" \
  --description="Trigger training-analyst-watchdog Cloud Run Job"

echo ""
echo "=== Done. Verify with: gcloud scheduler jobs list --location=$REGION --project=$PROJECT_ID ==="
