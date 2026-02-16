#!/usr/bin/env bash
# ==========================================================================
# Povver Landing — Deploy to AWS S3 + CloudFront
# ==========================================================================
#
# Usage:
#   ./deploy.sh
#
# Prerequisites:
#   - AWS CLI configured with appropriate credentials
#   - S3_BUCKET and CLOUDFRONT_DISTRIBUTION_ID set as env vars or below
#
# Before first deploy, manually set up:
#   - S3 bucket with static website hosting
#   - CloudFront distribution with HTTPS
#   - ACM certificate for povver.ai (us-east-1)
#   - Route53 A-record alias → CloudFront

set -euo pipefail

S3_BUCKET="${S3_BUCKET:-s3://povver-landing}"
CLOUDFRONT_DISTRIBUTION_ID="${CLOUDFRONT_DISTRIBUTION_ID:-}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Deploying landing page to ${S3_BUCKET}..."

# Sync HTML with short cache
aws s3 cp "${SCRIPT_DIR}/index.html" "${S3_BUCKET}/index.html" \
  --content-type "text/html" \
  --cache-control "max-age=3600"

# Sync CSS with long cache
aws s3 cp "${SCRIPT_DIR}/styles.css" "${S3_BUCKET}/styles.css" \
  --content-type "text/css" \
  --cache-control "max-age=31536000"

# Sync JS with long cache
aws s3 cp "${SCRIPT_DIR}/script.js" "${S3_BUCKET}/script.js" \
  --content-type "application/javascript" \
  --cache-control "max-age=31536000"

# Sync assets with long cache
if [ -d "${SCRIPT_DIR}/assets" ]; then
  aws s3 sync "${SCRIPT_DIR}/assets" "${S3_BUCKET}/assets/" \
    --cache-control "max-age=31536000"
fi

echo "S3 sync complete."

# Invalidate CloudFront cache
if [ -n "${CLOUDFRONT_DISTRIBUTION_ID}" ]; then
  echo "Invalidating CloudFront distribution ${CLOUDFRONT_DISTRIBUTION_ID}..."
  aws cloudfront create-invalidation \
    --distribution-id "${CLOUDFRONT_DISTRIBUTION_ID}" \
    --paths "/index.html" "/styles.css" "/script.js"
  echo "CloudFront invalidation submitted."
else
  echo "CLOUDFRONT_DISTRIBUTION_ID not set — skipping CDN invalidation."
fi

echo "Deploy complete."
