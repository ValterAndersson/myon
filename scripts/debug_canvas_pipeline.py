#!/usr/bin/env python3

"""
Comprehensive debugging script for the Canvas pipeline
Checks Firebase Functions logs, ADK Agent logs, and Firestore data
"""

import sys
import json
import subprocess
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional
import firebase_admin
from firebase_admin import credentials, firestore

# Initialize Firebase Admin SDK
try:
    cred = credentials.Certificate('/Users/valterandersson/Documents/myon/firebase_functions/functions/service-account-key.json')
    firebase_admin.initialize_app(cred)
except:
    # Try without service account if already initialized or running in cloud
    try:
        firebase_admin.initialize_app()
    except:
        print("Warning: Could not initialize Firebase Admin SDK")
        pass

db = firestore.client() if 'firebase_admin' in sys.modules else None

def get_project_id() -> str:
    """Get the current GCP project ID"""
    try:
        result = subprocess.run(
            ["gcloud", "config", "get-value", "project"],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return "myon-53d85"  # Default project

def run_command(cmd: List[str]) -> Optional[str]:
    """Run a shell command and return output"""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"Command failed: {' '.join(cmd)}")
        print(f"Error: {e.stderr}")
        return None

def check_firebase_logs(correlation_id: Optional[str] = None, minutes: int = 10) -> Dict[str, Any]:
    """Check Firebase Functions logs"""
    print("\n🔥 Checking Firebase Functions Logs...")
    print("-" * 40)
    
    output = run_command(["firebase", "functions:log", "--limit", "500"])
    if not output:
        return {"error": "Could not read Firebase logs"}
    
    lines = output.split('\n')
    
    # Filter by time
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(minutes=minutes)
    
    results = {
        "proposeCards": [],
        "invokeCanvasOrchestrator": [],
        "streamAgentNormalized": [],
        "errors": [],
        "auth_issues": []
    }
    
    for line in lines:
        # Parse timestamp if present
        time_match = re.match(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})', line)
        if not time_match:
            continue
            
        # Check if correlation ID matches (if provided)
        if correlation_id and correlation_id not in line:
            continue
        
        # Categorize logs
        if "[proposeCards]" in line:
            results["proposeCards"].append(line)
            if "hasApiKey: false" in line:
                results["auth_issues"].append("Missing API key in proposeCards")
            if "hasUserHeader: false" in line:
                results["auth_issues"].append("Missing User-ID header in proposeCards")
                
        elif "[invokeCanvasOrchestrator]" in line:
            results["invokeCanvasOrchestrator"].append(line)
            
        elif "[streamAgentNormalized]" in line:
            results["streamAgentNormalized"].append(line)
            
        if any(word in line.lower() for word in ["error", "failed", "401", "403"]):
            results["errors"].append(line)
    
    # Display results
    if results["errors"]:
        print(f"❌ Errors found ({len(results['errors'])}):")
        for err in results["errors"][:3]:
            print(f"   {err[:150]}...")
    
    if results["auth_issues"]:
        print(f"🔐 Auth Issues:")
        for issue in results["auth_issues"]:
            print(f"   - {issue}")
    
    if results["proposeCards"]:
        print(f"📝 proposeCards calls: {len(results['proposeCards'])}")
        for log in results["proposeCards"][:3]:
            if "created_card_ids" in log:
                match = re.search(r"created_card_ids.*\[([^\]]*)\]", log)
                if match:
                    print(f"   ✅ Created cards: [{match[1]}]")
            elif "error" in log.lower():
                print(f"   ❌ {log[:100]}...")
    
    return results

def check_agent_logs(correlation_id: Optional[str] = None, minutes: int = 10) -> Dict[str, Any]:
    """Check ADK Agent logs"""
    print("\n🤖 Checking ADK Agent Logs...")
    print("-" * 40)
    
    project_id = get_project_id()
    
    # Build log filter
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(minutes=minutes)
    
    log_filter = f'''
        resource.type="aiplatform.googleapis.com/ReasoningEngine"
        resource.labels.resource_id="8723635205937561600"
        timestamp >= "{start_time.strftime('%Y-%m-%dT%H:%M:%SZ')}"
        timestamp <= "{end_time.strftime('%Y-%m-%dT%H:%M:%SZ')}"
    '''
    
    if correlation_id:
        log_filter += f' AND jsonPayload.message=~"{correlation_id}"'
    
    output = run_command([
        "gcloud", "logging", "read",
        log_filter.strip(),
        "--limit=500",
        "--format=json",
        "--project", project_id
    ])
    
    if not output:
        return {"error": "Could not read agent logs"}
    
    try:
        logs = json.loads(output)
    except json.JSONDecodeError:
        return {"error": "Could not parse agent logs"}
    
    results = {
        "tool_calls": [],
        "canvas_publishes": [],
        "errors": [],
        "context_issues": []
    }
    
    for log in reversed(logs):  # Chronological order
        payload = log.get("jsonPayload", {})
        message = payload.get("message", "")
        
        # Categorize
        if "tool_canvas_publish" in message or "tool_propose_cards" in message:
            results["canvas_publishes"].append(message)
            
        if "tool_" in message:
            results["tool_calls"].append(message)
            
        if any(word in message.lower() for word in ["error", "failed", "exception"]):
            results["errors"].append(message)
            
        if "user_id is required" in message or "canvas_id is required" in message:
            results["context_issues"].append(message)
    
    # Display results
    if results["errors"]:
        print(f"❌ Errors found ({len(results['errors'])}):")
        for err in results["errors"][:3]:
            print(f"   {err[:150]}...")
    
    if results["context_issues"]:
        print(f"⚠️  Context Issues:")
        for issue in results["context_issues"][:3]:
            print(f"   {issue[:100]}...")
    
    if results["canvas_publishes"]:
        print(f"📝 Canvas publish attempts: {len(results['canvas_publishes'])}")
        for pub in results["canvas_publishes"][:3]:
            if "ok" in pub:
                print(f"   ✅ Success: {pub[:100]}...")
            elif "failed" in pub:
                print(f"   ❌ Failed: {pub[:100]}...")
    
    return results

def check_firestore_data(user_id: str, canvas_id: str) -> Dict[str, Any]:
    """Check Firestore data for a canvas"""
    if not db:
        print("\n⚠️  Firestore not available (missing credentials)")
        return {}
    
    print(f"\n🗄️  Checking Firestore Data...")
    print("-" * 40)
    print(f"User: {user_id}")
    print(f"Canvas: {canvas_id}")
    
    try:
        # Check canvas document
        canvas_ref = db.collection('users').document(user_id).collection('canvases').document(canvas_id)
        canvas_doc = canvas_ref.get()
        
        if not canvas_doc.exists:
            print("❌ Canvas document not found!")
            return {"error": "Canvas not found"}
        
        # Check cards
        cards = list(canvas_ref.collection('cards').stream())
        print(f"\n📇 Cards: {len(cards)} total")
        
        # Check up_next
        up_next = list(canvas_ref.collection('up_next').stream())
        print(f"⏭️  Up Next: {len(up_next)} items")
        
        # Check recent events
        events = list(canvas_ref.collection('events').order_by('created_at', direction=firestore.Query.DESCENDING).limit(10).stream())
        print(f"📊 Recent Events: {len(events)} (last 10)")
        
        for event in events:
            event_data = event.to_dict()
            event_type = event_data.get('type', 'unknown')
            created_at = event_data.get('created_at', '')
            
            if event_type == 'agent_propose':
                card_ids = event_data.get('payload', {}).get('created_card_ids', [])
                print(f"   ✅ {event_type}: created {len(card_ids)} cards")
            elif event_type == 'agent_publish_failed':
                error = event_data.get('payload', {}).get('error', 'unknown')
                print(f"   ❌ {event_type}: {error}")
            else:
                print(f"   📌 {event_type}")
        
        # Check for specific card types
        card_types = {}
        for card in cards:
            card_data = card.to_dict()
            card_type = card_data.get('type', 'unknown')
            card_types[card_type] = card_types.get(card_type, 0) + 1
        
        print(f"\n📋 Card Types:")
        for card_type, count in card_types.items():
            print(f"   - {card_type}: {count}")
        
        return {
            "canvas_exists": True,
            "cards": len(cards),
            "up_next": len(up_next),
            "events": len(events),
            "card_types": card_types
        }
        
    except Exception as e:
        print(f"❌ Error checking Firestore: {e}")
        return {"error": str(e)}

def diagnose_pipeline(user_id: str, canvas_id: str, correlation_id: Optional[str] = None):
    """Run comprehensive diagnosis of the pipeline"""
    print("\n" + "=" * 60)
    print("🔍 CANVAS PIPELINE DIAGNOSIS")
    print("=" * 60)
    
    # 1. Check Firebase Functions logs
    firebase_results = check_firebase_logs(correlation_id, minutes=15)
    
    # 2. Check Agent logs
    agent_results = check_agent_logs(correlation_id, minutes=15)
    
    # 3. Check Firestore data
    firestore_results = check_firestore_data(user_id, canvas_id)
    
    # 4. Diagnosis
    print("\n" + "=" * 60)
    print("🩺 DIAGNOSIS SUMMARY")
    print("=" * 60)
    
    issues = []
    
    # Check for auth issues
    if firebase_results.get("auth_issues"):
        issues.append("🔐 Authentication problem: API key or User-ID header missing")
    
    # Check for agent errors
    if agent_results.get("errors"):
        issues.append("🤖 Agent execution errors detected")
    
    # Check for context propagation
    if agent_results.get("context_issues"):
        issues.append("📍 Context not propagating correctly (user_id/canvas_id)")
    
    # Check for Firestore write issues
    if firestore_results.get("cards", 0) == 0:
        issues.append("📝 No cards written to Firestore")
    
    # Check for publish failures
    if not firebase_results.get("proposeCards"):
        issues.append("🚫 No proposeCards function calls detected")
    
    if issues:
        print("\n⚠️  Issues Found:")
        for issue in issues:
            print(f"   {issue}")
    else:
        print("\n✅ No obvious issues detected")
    
    # Recommendations
    print("\n💡 Recommendations:")
    
    if "Authentication problem" in str(issues):
        print("   1. Check MYON_API_KEY environment variable in agent deployment")
        print("   2. Verify VALID_API_KEYS in Firebase Functions includes the agent's key")
        print("   3. Ensure X-User-Id header is being set by the agent")
    
    if "Context not propagating" in str(issues):
        print("   1. Check tool_set_user_context is being called first")
        print("   2. Verify canvas_id is being passed to publish tools")
        print("   3. Check _canvas_client() is reading context correctly")
    
    if "No cards written" in str(issues):
        print("   1. Check proposeCards function logs for write errors")
        print("   2. Verify Firestore permissions for the canvas path")
        print("   3. Check card validation in proposeCards")
    
    print()

def main():
    if len(sys.argv) < 3:
        print("Usage: python debug_canvas_pipeline.py <user_id> <canvas_id> [correlation_id]")
        print("Example: python debug_canvas_pipeline.py xLRyVOI0XKSFsTXSFbGSvui8FJf2 nF61JxsIgA2HOmDD1QsB")
        sys.exit(1)
    
    user_id = sys.argv[1]
    canvas_id = sys.argv[2]
    correlation_id = sys.argv[3] if len(sys.argv) > 3 else None
    
    diagnose_pipeline(user_id, canvas_id, correlation_id)

if __name__ == "__main__":
    main()
