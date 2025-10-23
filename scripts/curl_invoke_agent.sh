#!/usr/bin/env bash
set -euo pipefail

BASE="https://us-central1-myon-53d85.cloudfunctions.net"
USER_ID="${1:?usage: $0 <userId> <canvasId> <message> <firebaseIdToken>}"; shift
CANVAS_ID="${1:?usage: $0 <userId> <canvasId> <message> <firebaseIdToken>}"; shift
MESSAGE="${1:?usage: $0 <userId> <canvasId> <message> <firebaseIdToken>}"; shift
ID_TOKEN="${1:?usage: $0 <userId> <canvasId> <message> <firebaseIdToken>}"; shift
CID="qa-orchestrator-$(uuidgen || echo $RANDOM)"

curl -sS -X POST "$BASE/invokeCanvasOrchestrator" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ID_TOKEN" \
  -d "{ \"userId\": \"$USER_ID\", \"canvasId\": \"$CANVAS_ID\", \"message\": \"$MESSAGE\", \"correlationId\": \"$CID\" }" | jq .


