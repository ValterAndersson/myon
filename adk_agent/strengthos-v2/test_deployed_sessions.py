#!/usr/bin/env python3
"""Test session persistence with deployed agent."""

import json
import os
import asyncio
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google import auth
import aiohttp

# Load deployment metadata
with open('deployment_metadata.json', 'r') as f:
    metadata = json.load(f)
    AGENT_ENGINE_ID = metadata['remote_agent_engine_id'].split('/')[-1]

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "myon-53d85")
LOCATION = "us-central1"
USER_ID = "Y4SJuNPOasaltF7TuKm1QCT7JIA3"

async def get_auth_token():
    """Get authentication token for API calls."""
    credentials, _ = auth.default(
        scopes=['https://www.googleapis.com/auth/cloud-platform']
    )
    
    # Refresh credentials
    auth_req = Request()
    credentials.refresh(auth_req)
    
    return credentials.token

async def call_agent_api(message: str, session_id: str = None):
    """Call the deployed agent API directly."""
    url = f"https://{LOCATION}-aiplatform.googleapis.com/v1beta1/projects/{PROJECT_ID}/locations/{LOCATION}/reasoningEngines/{AGENT_ENGINE_ID}:streamQuery"
    
    token = await get_auth_token()
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    
    data = {
        "class_method": "stream_query",
        "stream": True,
        "input": {
            "user_id": USER_ID,
            "message": message
        }
    }
    
    if session_id:
        data["input"]["session_id"] = session_id
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=data) as resp:
            print(f"\nStatus: {resp.status}")
            response_text = await resp.text()
            
            if resp.status == 200:
                # Parse streaming response
                lines = response_text.strip().split('\n')
                events = []
                returned_session_id = None
                
                for line in lines:
                    if line.strip():
                        try:
                            event = json.loads(line)
                            events.append(event)
                            
                            # Extract session ID from events
                            if 'actions' in event and 'session_id' in event.get('actions', {}):
                                returned_session_id = event['actions']['session_id']
                        except json.JSONDecodeError:
                            print(f"Failed to parse line: {line}")
                
                # Extract final response text
                response_text = ""
                for event in events:
                    if event.get('content', {}).get('parts'):
                        for part in event['content']['parts']:
                            if 'text' in part:
                                response_text = part['text']
                
                return response_text, returned_session_id or session_id
            else:
                print(f"Error response: {response_text}")
                return None, None

async def test_session_persistence():
    """Test if sessions persist across multiple calls."""
    print("🧪 Testing session persistence with deployed agent...")
    print(f"Agent Engine ID: {AGENT_ENGINE_ID}")
    print(f"User ID: {USER_ID}\n")
    
    # First message - no session ID
    print("1️⃣ First message (no session ID):")
    response1, session_id1 = await call_agent_api(
        "Can you evaluate my last workout?"
    )
    print(f"Response: {response1}")
    print(f"Session ID: {session_id1}")
    
    if not session_id1:
        print("❌ No session ID returned from first call")
        return
    
    # Second message - with session ID
    print(f"\n2️⃣ Second message (with session ID: {session_id1}):")
    response2, session_id2 = await call_agent_api(
        "What about the workout before that?",
        session_id=session_id1
    )
    print(f"Response: {response2}")
    print(f"Session ID: {session_id2}")
    
    # Check if the agent remembers the context
    if response2 and "don't have" not in response2.lower():
        print("\n✅ Session persistence appears to be working!")
    else:
        print("\n❌ Session persistence is NOT working - agent doesn't remember context")
    
    # Third message - test explicit session management
    print(f"\n3️⃣ Third message (continuing conversation):")
    response3, session_id3 = await call_agent_api(
        "How many workouts have we discussed so far?",
        session_id=session_id2
    )
    print(f"Response: {response3}")
    print(f"Session ID: {session_id3}")

async def main():
    """Run the test."""
    try:
        await test_session_persistence()
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main()) 