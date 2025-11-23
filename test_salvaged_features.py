#!/usr/bin/env python3
"""Test script to verify all salvaged features are working."""

import os
import sys
import json
import asyncio

# Add the agent module to path
sys.path.insert(0, '/Users/valterandersson/Documents/myon/adk_agent/canvas_orchestrator')

# Set up environment
os.environ['MYON_API_KEY'] = 'myon-agent-key-2024'
os.environ['MYON_FUNCTIONS_BASE_URL'] = 'https://us-central1-myon-53d85.cloudfunctions.net'
os.environ['X_USER_ID'] = 'xLRyVOI0XKSFsTXSFbGSvui8FJf2'

from app.libs.tools_canvas.client import CanvasFunctionsClient

async def test_user_data_fetching():
    """Test that user data functions are working."""
    print("\n=== Testing User Data Fetching ===")
    
    client = CanvasFunctionsClient(
        base_url=os.environ['MYON_FUNCTIONS_BASE_URL'],
        api_key=os.environ['MYON_API_KEY']
    )
    
    user_id = os.environ['X_USER_ID']
    
    # Test get_user
    print(f"\n1. Testing get_user for {user_id}...")
    try:
        result = client.get_user(user_id)
        if result.get("success"):
            print("✅ get_user working!")
            if result.get("data"):
                print(f"   Found user data: {list(result['data'].keys())[:5]}...")
        else:
            print(f"❌ get_user failed: {result.get('error')}")
    except Exception as e:
        print(f"❌ get_user error: {e}")
    
    # Test get_user_preferences
    print(f"\n2. Testing get_user_preferences...")
    try:
        result = client.get_user_preferences(user_id)
        if result.get("success"):
            print("✅ get_user_preferences working!")
            if result.get("data"):
                print(f"   Found preferences: {list(result['data'].keys())[:5]}...")
        else:
            print(f"❌ get_user_preferences failed: {result.get('error')}")
    except Exception as e:
        print(f"❌ get_user_preferences error: {e}")
    
    # Test get_user_workouts
    print(f"\n3. Testing get_user_workouts...")
    try:
        result = client.get_user_workouts(user_id, limit=5)
        if result.get("success"):
            print("✅ get_user_workouts working!")
            if result.get("data"):
                print(f"   Found {len(result.get('data', []))} workouts")
        else:
            print(f"❌ get_user_workouts failed: {result.get('error')}")
    except Exception as e:
        print(f"❌ get_user_workouts error: {e}")

async def test_canvas_lifecycle():
    """Test canvas lifecycle functions."""
    print("\n=== Testing Canvas Lifecycle ===")
    
    client = CanvasFunctionsClient(
        base_url=os.environ['MYON_FUNCTIONS_BASE_URL'],
        api_key=os.environ['MYON_API_KEY']
    )
    
    user_id = os.environ['X_USER_ID']
    
    # Test bootstrap_canvas
    print("\n1. Testing bootstrap_canvas...")
    try:
        result = client.bootstrap_canvas(user_id, "test")
        if result.get("success"):
            canvas_id = result.get("data", {}).get("canvasId")
            print(f"✅ bootstrap_canvas working! Created canvas: {canvas_id}")
            
            # Test check_pending_response
            print("\n2. Testing check_pending_response...")
            try:
                result = client.check_pending_response(user_id, canvas_id)
                if result.get("success"):
                    print("✅ check_pending_response working!")
                    has_response = result.get("data", {}).get("has_response", False)
                    print(f"   Has pending response: {has_response}")
                else:
                    print(f"❌ check_pending_response failed: {result.get('error')}")
            except Exception as e:
                print(f"❌ check_pending_response error: {e}")
                
        else:
            print(f"❌ bootstrap_canvas failed: {result.get('error')}")
    except Exception as e:
        print(f"❌ bootstrap_canvas error: {e}")

async def main():
    """Run all tests."""
    print("=" * 60)
    print("SALVAGED FEATURES TEST SUITE")
    print("=" * 60)
    
    await test_user_data_fetching()
    await test_canvas_lifecycle()
    
    print("\n" + "=" * 60)
    print("TEST SUITE COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
