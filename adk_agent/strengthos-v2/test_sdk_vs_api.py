#!/usr/bin/env python3
"""Test to understand the difference between SDK and REST API calls."""

import json
import requests
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google import auth
from vertexai import agent_engines
import logging

# Enable detailed logging
logging.basicConfig(level=logging.DEBUG)

# Load deployment metadata
with open('deployment_metadata.json', 'r') as f:
    metadata = json.load(f)
    AGENT_ID = metadata['remote_agent_engine_id']

PROJECT_ID = AGENT_ID.split("/")[1]
LOCATION = AGENT_ID.split("/")[3]
REASONING_ENGINE_ID = AGENT_ID.split("/")[-1]

print(f"Project: {PROJECT_ID}")
print(f"Location: {LOCATION}")
print(f"Agent ID: {REASONING_ENGINE_ID}")

# Test parameters
USER_ID = "test-user-123"
SESSION_ID = "test-session-123"
MESSAGE = "Hi, this is a test"

print("\n=== Testing SDK Call ===")
try:
    agent = agent_engines.get(AGENT_ID)
    
    # Make a simple query call
    response = agent.query(
        message=MESSAGE,
        user_id=USER_ID,
        session_id=SESSION_ID
    )
    print(f"SDK Response: {response}")
except Exception as e:
    print(f"SDK Error: {e}")

print("\n=== Testing Direct REST API Call ===")
try:
    # Get auth token
    credentials, _ = auth.default(
        scopes=['https://www.googleapis.com/auth/cloud-platform']
    )
    auth_req = Request()
    credentials.refresh(auth_req)
    
    # Build URL
    url = f"https://{LOCATION}-aiplatform.googleapis.com/v1/projects/{PROJECT_ID}/locations/{LOCATION}/reasoningEngines/{REASONING_ENGINE_ID}:query"
    
    # Prepare payload - matching our Firebase function
    payload = {
        "class_method": "query",
        "input": {
            "message": MESSAGE,
            "user_id": USER_ID,
            "session_id": SESSION_ID
        }
    }
    
    print(f"URL: {url}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    
    # Make request
    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {credentials.token}",
            "Content-Type": "application/json"
        },
        json=payload
    )
    
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")
    
except Exception as e:
    print(f"REST API Error: {e}")

print("\n=== Testing stream_query endpoint ===")
try:
    # Try the streamQuery endpoint
    stream_url = f"https://{LOCATION}-aiplatform.googleapis.com/v1/projects/{PROJECT_ID}/locations/{LOCATION}/reasoningEngines/{REASONING_ENGINE_ID}:streamQuery"
    
    stream_payload = {
        "class_method": "stream_query",
        "input": {
            "message": MESSAGE,
            "user_id": USER_ID,
            "session_id": SESSION_ID
        }
    }
    
    print(f"Stream URL: {stream_url}")
    print(f"Stream Payload: {json.dumps(stream_payload, indent=2)}")
    
    response = requests.post(
        stream_url,
        headers={
            "Authorization": f"Bearer {credentials.token}",
            "Content-Type": "application/json"
        },
        json=stream_payload
    )
    
    print(f"Stream Status: {response.status_code}")
    print(f"Stream Response: {response.text[:500]}...")  # First 500 chars
    
except Exception as e:
    print(f"Stream API Error: {e}") 