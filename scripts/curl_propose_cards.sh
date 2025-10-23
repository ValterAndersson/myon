#!/usr/bin/env bash
set -euo pipefail

BASE="https://us-central1-myon-53d85.cloudfunctions.net"
API_KEY="${MYON_API_KEY:-myon-agent-key-2024}"
USER_ID="${1:?usage: $0 <userId> <canvasId> [text]}"; shift || true
CANVAS_ID="${1:?usage: $0 <userId> <canvasId> [text]}"; shift || true
TEXT="${1:-ping from script}"
CID="qa-propose-$(uuidgen || echo $RANDOM)"

curl -sS -X POST "$BASE/proposeCards" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -H "X-User-Id: $USER_ID" \
  -H "X-Correlation-Id: $CID" \
  -d "{ \"canvasId\": \"$CANVAS_ID\", \"cards\": [{ \"type\": \"inline-info\", \"lane\": \"analysis\", \"content\": { \"text\": \"$TEXT\" } }] }" | jq .


