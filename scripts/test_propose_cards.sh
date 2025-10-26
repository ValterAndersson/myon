#!/bin/bash

# Test proposeCards function directly
echo "Testing proposeCards endpoint..."

CANVAS_ID="test_canvas_$(date +%s)"
USER_ID="xLRyVOI0XKSFsTXSFbGSvui8FJf2"
API_KEY="myon-agent-key-2024"
CORRELATION_ID="TEST-$(uuidgen)"

echo "Canvas ID: $CANVAS_ID"
echo "User ID: $USER_ID"
echo "Correlation ID: $CORRELATION_ID"
echo ""

# Create test card payload
PAYLOAD=$(cat <<EOF
{
  "canvasId": "$CANVAS_ID",
  "userId": "$USER_ID",
  "correlationId": "$CORRELATION_ID",
  "cards": [
    {
      "type": "clarify-questions",
      "lane": "analysis",
      "priority": 50,
      "content": {
        "title": "Test Questions",
        "questions": [
          {"id": "q1", "text": "What are your fitness goals?"},
          {"id": "q2", "text": "How many days per week?"}
        ]
      }
    }
  ]
}
EOF
)

echo "Sending request to proposeCards..."
echo ""

# Make the request
curl -X POST \
  https://us-central1-myon-53d85.cloudfunctions.net/proposeCards \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -H "X-User-Id: $USER_ID" \
  -H "X-Correlation-Id: $CORRELATION_ID" \
  -d "$PAYLOAD" \
  -w "\n\nHTTP Status: %{http_code}\n" \
  -v 2>&1 | grep -E "(< HTTP|< |{|})"

echo ""
echo "Test complete. Check Firestore at:"
echo "  users/$USER_ID/canvases/$CANVAS_ID"
