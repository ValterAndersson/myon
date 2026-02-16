#!/usr/bin/env bash
# ==========================================================================
# Povver Landing — Deploy to EC2 via SCP
# ==========================================================================
#
# Usage:
#   ./deploy.sh
#
# Prerequisites:
#   - SSH access to the EC2 instance (PEM key at ~/.ssh/povver-rsa.pem or
#     set POVVER_PEM to the key path)
#   - nginx running on the instance with web root at /usr/share/nginx/html/

set -euo pipefail

HOST="ec2-user@ec2-34-244-201-109.eu-west-1.compute.amazonaws.com"
PEM="${POVVER_PEM:-$HOME/.ssh/povver-rsa.pem}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SSH_OPTS="-i ${PEM} -o StrictHostKeyChecking=no"

if [ ! -f "${PEM}" ]; then
  echo "Error: PEM key not found at ${PEM}"
  echo "Set POVVER_PEM to the correct path or copy it to ~/.ssh/povver-rsa.pem"
  exit 1
fi

echo "Deploying landing page to ${HOST}..."

# Upload all site files to /tmp on the instance
scp ${SSH_OPTS} \
  "${SCRIPT_DIR}/index.html" \
  "${SCRIPT_DIR}/styles.css" \
  "${SCRIPT_DIR}/script.js" \
  "${SCRIPT_DIR}/robots.txt" \
  "${HOST}:/tmp/"

# Upload assets
scp ${SSH_OPTS} -r "${SCRIPT_DIR}/assets/" "${HOST}:/tmp/landing-assets/"

# Move files into nginx web root (requires sudo)
ssh ${SSH_OPTS} "${HOST}" "
  sudo cp /tmp/index.html /tmp/styles.css /tmp/script.js /tmp/robots.txt /usr/share/nginx/html/
  sudo cp -r /tmp/landing-assets/* /usr/share/nginx/html/assets/
  rm -rf /tmp/landing-assets /tmp/index.html /tmp/styles.css /tmp/script.js /tmp/robots.txt
"

echo "Deploy complete. Site live at https://povver.ai"
