# Admin Dashboard Deployment Guide

## Quick Deploy (After Auth)

```bash
# 1. Authenticate
gcloud auth login

# 2. Deploy to Cloud Run (no public access)
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

## Secure Access Setup (IAP Alternative)

Since Cloud Run doesn't directly support IAP, we use IAM + Cloud Run Invoker:

### Option A: Direct IAM (Recommended for Single User)

Grant invoker access to mrhalycon@gmail.com only:

```bash
# Grant Cloud Run Invoker role to specific user
gcloud run services add-iam-policy-binding admin-dashboard \
    --region=europe-west1 \
    --project=myon-53d85 \
    --member="user:mrhalycon@gmail.com" \
    --role="roles/run.invoker"
```

Then access via:
```bash
# Get the service URL
gcloud run services describe admin-dashboard \
    --region=europe-west1 \
    --project=myon-53d85 \
    --format='value(status.url)'
```

To access, you'll need to authenticate your browser request:
1. Install Google Cloud SDK
2. Run `gcloud auth login` with mrhalycon@gmail.com
3. Use `gcloud auth print-identity-token` to get a token
4. Access the URL with the Authorization header

### Option B: Proxy via Load Balancer + IAP

For browser-based access without tokens:

```bash
# 1. Create a serverless NEG
gcloud compute network-endpoint-groups create admin-dashboard-neg \
    --region=europe-west1 \
    --network-endpoint-type=serverless \
    --cloud-run-service=admin-dashboard \
    --project=myon-53d85

# 2. Create backend service
gcloud compute backend-services create admin-dashboard-backend \
    --load-balancing-scheme=EXTERNAL \
    --global \
    --project=myon-53d85

gcloud compute backend-services add-backend admin-dashboard-backend \
    --global \
    --network-endpoint-group=admin-dashboard-neg \
    --network-endpoint-group-region=europe-west1 \
    --project=myon-53d85

# 3. Create URL map
gcloud compute url-maps create admin-dashboard-urlmap \
    --default-service=admin-dashboard-backend \
    --project=myon-53d85

# 4. Create HTTPS proxy (requires SSL cert)
# ... see full GCP documentation for HTTPS LB + IAP setup
```

### Option C: Cloud Run with Firebase Auth (Easiest)

Add Firebase Auth to the dashboard itself:
1. Add Firebase JS SDK to index.html
2. Add Google Sign-In button
3. Validate user email in backend
4. Allow only mrhalycon@gmail.com

## Verify Deployment

```bash
# Check service status
gcloud run services describe admin-dashboard \
    --region=europe-west1 \
    --project=myon-53d85

# View logs
gcloud run logs read --service=admin-dashboard \
    --region=europe-west1 \
    --project=myon-53d85 \
    --limit=50
```

## Service Account Permissions

The service account needs these roles:
- `roles/datastore.viewer` - Read Firestore
- `roles/cloudscheduler.viewer` - View scheduler jobs
- `roles/run.viewer` - View Cloud Run jobs
- `roles/run.invoker` - Trigger Cloud Run jobs
- `roles/logging.viewer` - Read Cloud Logging

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
