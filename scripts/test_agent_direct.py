#!/usr/bin/env python3
"""Test the agent directly with proper context."""

import os
import sys
import json

# Add the agent module to path
sys.path.insert(0, '/Users/valterandersson/Documents/myon/adk_agent/canvas_orchestrator')

# Set up environment
os.environ['MYON_API_KEY'] = 'myon-agent-key-2024'
os.environ['TEST_CANVAS_ID'] = 'test_direct_canvas'
os.environ['X_USER_ID'] = 'xLRyVOI0XKSFsTXSFbGSvui8FJf2'

from app.orchestrator import tool_publish_clarify_questions

# Test the function directly
print("Testing tool_publish_clarify_questions directly...")
print(f"Canvas ID: {os.environ['TEST_CANVAS_ID']}")
print(f"User ID: {os.environ['X_USER_ID']}")

result = tool_publish_clarify_questions(
    question=["What is your primary fitness goal?"],
    canvas_id="test_direct_canvas",
    user_id="xLRyVOI0XKSFsTXSFbGSvui8FJf2"
)

print(f"\nResult: {json.dumps(result, indent=2)}")

if result.get("ok"):
    print("\n✅ Success! Cards published.")
else:
    print(f"\n❌ Failed: {result.get('error')}")
