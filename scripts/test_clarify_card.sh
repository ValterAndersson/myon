#!/bin/bash

# Test clarify-questions card with choice options
echo "Testing clarify-questions card with choice options..."

CANVAS_ID="test_clarify_$(date +%s)"
USER_ID="xLRyVOI0XKSFsTXSFbGSvui8FJf2"
API_KEY="myon-agent-key-2024"
CORRELATION_ID="TEST-$(uuidgen)"

echo "Canvas ID: $CANVAS_ID"
echo "User ID: $USER_ID"
echo "Correlation ID: $CORRELATION_ID"
echo ""

# Create test card payload with choice questions
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
        "title": "Quick question",
        "questions": [
          {
            "id": "q1",
            "text": "What's your primary training goal?",
            "type": "choice",
            "options": ["Build muscle", "Lose fat", "Get stronger", "Improve endurance"]
          }
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
RESPONSE=$(curl -s -X POST \
  https://us-central1-myon-53d85.cloudfunctions.net/proposeCards \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -H "X-User-Id: $USER_ID" \
  -H "X-Correlation-Id: $CORRELATION_ID" \
  -d "$PAYLOAD")

echo "Response: $RESPONSE"
echo ""

# Check if successful
if echo "$RESPONSE" | grep -q '"success":true'; then
  echo "✅ Test passed! Card created successfully."
  echo ""
  echo "To verify in iOS:"
  echo "1. Update CanvasScreen to load canvas ID: $CANVAS_ID"
  echo "2. The card should show with clickable options"
else
  echo "❌ Test failed. Response:"
  echo "$RESPONSE" | python3 -m json.tool
fi
