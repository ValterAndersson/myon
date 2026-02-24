#!/usr/bin/env bash
# ==========================================================================
# Povver Landing — Deploy to EC2 via SCP
# ==========================================================================
#
# Usage:
#   cd landing && ./deploy.sh
#
# PEM key resolution (first match wins):
#   1. $POVVER_PEM          (env var override)
#   2. ./povver-rsa.pem     (co-located with this script)
#   3. ~/.ssh/povver-rsa.pem
#
# The EC2 instance runs nginx on Amazon Linux 2023.
# Web root: /usr/share/nginx/html/
# Domain:   povver.ai (Route53 A record)

set -euo pipefail

HOST="ec2-user@ec2-34-244-201-109.eu-west-1.compute.amazonaws.com"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CACHE_BUST="$(date +%s)"

# --- Resolve PEM key ---
if [ -n "${POVVER_PEM:-}" ] && [ -f "${POVVER_PEM}" ]; then
  PEM="${POVVER_PEM}"
elif [ -f "${SCRIPT_DIR}/povver-rsa.pem" ]; then
  PEM="${SCRIPT_DIR}/povver-rsa.pem"
elif [ -f "$HOME/.ssh/povver-rsa.pem" ]; then
  PEM="$HOME/.ssh/povver-rsa.pem"
else
  echo "Error: PEM key not found. Looked in:"
  echo "  1. \$POVVER_PEM (${POVVER_PEM:-not set})"
  echo "  2. ${SCRIPT_DIR}/povver-rsa.pem"
  echo "  3. $HOME/.ssh/povver-rsa.pem"
  exit 1
fi

echo "Using PEM key: ${PEM}"
echo "Deploying landing page to ${HOST}..."

# --- Stamp cache-busting query strings into HTML before upload ---
# Work on a temp copy so the source files stay clean.
STAGE=$(mktemp -d)
trap 'rm -rf "${STAGE}"' EXIT

cp "${SCRIPT_DIR}/index.html" "${STAGE}/index.html"
# Replace ?v=<anything> and bare .png"/.css" refs with ?v=<timestamp>
sed -i '' -E "s/\.png(\?v=[0-9]+)?\"/.png?v=${CACHE_BUST}\"/g" "${STAGE}/index.html"
sed -i '' -E "s/\.css(\?v=[0-9]+)?\"/.css?v=${CACHE_BUST}\"/g" "${STAGE}/index.html"
sed -i '' -E "s/\.js(\?v=[0-9]+)?\"/.js?v=${CACHE_BUST}\"/g"   "${STAGE}/index.html"

# --- Upload site files ---
scp -i "${PEM}" -o StrictHostKeyChecking=no \
  "${STAGE}/index.html" \
  "${SCRIPT_DIR}/privacy.html" \
  "${SCRIPT_DIR}/tos.html" \
  "${SCRIPT_DIR}/styles.css" \
  "${SCRIPT_DIR}/legal.css" \
  "${SCRIPT_DIR}/script.js" \
  "${SCRIPT_DIR}/robots.txt" \
  "${HOST}:/tmp/"

# --- Upload assets via rsync (avoids scp -r directory nesting issues) ---
rsync -az -e "ssh -i ${PEM} -o StrictHostKeyChecking=no" \
  "${SCRIPT_DIR}/assets/" "${HOST}:/tmp/landing-assets/"

# --- Move into nginx web root ---
ssh -i "${PEM}" -o StrictHostKeyChecking=no "${HOST}" "
  sudo cp /tmp/index.html /tmp/privacy.html /tmp/tos.html /tmp/styles.css /tmp/legal.css /tmp/script.js /tmp/robots.txt /usr/share/nginx/html/
  sudo rm -rf /usr/share/nginx/html/assets/
  sudo cp -r /tmp/landing-assets /usr/share/nginx/html/assets
  rm -rf /tmp/landing-assets /tmp/index.html /tmp/privacy.html /tmp/tos.html /tmp/styles.css /tmp/legal.css /tmp/script.js /tmp/robots.txt
"

echo "Deploy complete (cache bust: ${CACHE_BUST}). Site live at https://povver.ai"
