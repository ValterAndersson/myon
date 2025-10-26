#!/usr/bin/env python3

"""
Script to read ADK Agent logs from Google Cloud Logging
Usage: python read_agent_logs.py [minutes] [filter]
Example: python read_agent_logs.py 5 "tool_canvas_publish"
"""

import sys
import json
from datetime import datetime, timedelta, timezone
import subprocess
import re
from typing import List, Dict, Any, Optional

def get_project_id() -> str:
    """Get the current GCP project ID"""
    try:
        result = subprocess.run(
            ["gcloud", "config", "get-value", "project"],
            capture_output=True,
            text=True,
            check=True
        )
        project = result.stdout.strip()
        # If it's a project number, use the known project ID
        if project.isdigit():
            return "myon-53d85"
        return project
    except subprocess.CalledProcessError:
        return "myon-53d85"  # Default to known project ID

def read_agent_logs(minutes_ago: int = 10, filter_text: Optional[str] = None) -> List[Dict[str, Any]]:
    """Read logs from the ADK agent"""
    project_id = get_project_id()
    
    # Calculate time range
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(minutes=minutes_ago)
    
    # Format timestamps for gcloud
    start_str = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_str = end_time.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    print(f"\n📋 Reading ADK Agent logs from {minutes_ago} minutes ago...")
    print(f"Project: {project_id}")
    print(f"Time range: {start_str} to {end_str}\n")
    print("=" * 80)
    
    # Build the log filter
    log_filter = f'''
        resource.type="aiplatform.googleapis.com/ReasoningEngine"
        resource.labels.resource_id="8723635205937561600"
        timestamp >= "{start_str}"
        timestamp <= "{end_str}"
    '''
    
    if filter_text:
        log_filter += f' AND jsonPayload.message=~"{filter_text}"'
    
    # Read logs using gcloud
    cmd = [
        "gcloud", "logging", "read",
        log_filter.strip(),
        "--limit=500",
        "--format=json",
        "--project", project_id
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        logs = json.loads(result.stdout) if result.stdout else []
        return logs
    except subprocess.CalledProcessError as e:
        print(f"Error reading logs: {e}")
        print(f"Stderr: {e.stderr}")
        return []
    except json.JSONDecodeError as e:
        print(f"Error parsing logs: {e}")
        return []

def analyze_logs(logs: List[Dict[str, Any]]) -> None:
    """Analyze and display logs in a structured way"""
    
    if not logs:
        print("\n⚠️  No logs found for the specified time range")
        return
    
    print(f"\n📊 Found {len(logs)} log entries\n")
    
    # Group logs by patterns
    tool_calls = []
    errors = []
    canvas_publishes = []
    auth_issues = []
    correlations = set()
    
    for log in reversed(logs):  # Reverse to show chronological order
        payload = log.get("jsonPayload", {})
        message = payload.get("message", "")
        timestamp = log.get("timestamp", "")
        
        # Extract correlation IDs
        corr_match = re.search(r"correlation_id[=:]([A-F0-9-]+)", message, re.IGNORECASE)
        if corr_match:
            correlations.add(corr_match.group(1))
        
        # Categorize logs
        if "tool_" in message:
            tool_calls.append((timestamp, message))
        
        if any(word in message.lower() for word in ["error", "failed", "exception"]):
            errors.append((timestamp, message))
        
        if "tool_canvas_publish" in message or "tool_propose_cards" in message:
            canvas_publishes.append((timestamp, message))
        
        if any(word in message.lower() for word in ["401", "403", "api_key", "auth"]):
            auth_issues.append((timestamp, message))
    
    # Display analysis
    print("🔍 Log Analysis:\n")
    
    if correlations:
        print(f"📌 Correlation IDs found: {', '.join(sorted(correlations))}\n")
    
    if errors:
        print(f"❌ Errors ({len(errors)}):")
        for ts, msg in errors[:5]:  # Show first 5
            print(f"   [{ts[:19]}] {msg[:150]}...")
        if len(errors) > 5:
            print(f"   ... and {len(errors) - 5} more")
        print()
    
    if auth_issues:
        print(f"🔐 Auth Issues ({len(auth_issues)}):")
        for ts, msg in auth_issues[:3]:
            print(f"   [{ts[:19]}] {msg[:150]}...")
        print()
    
    if canvas_publishes:
        print(f"📝 Canvas Publish Attempts ({len(canvas_publishes)}):")
        for ts, msg in canvas_publishes:
            # Extract key info
            if "begin" in msg:
                match = re.search(r"canvas_id=(\w+).*user_id=(\w+).*count=(\d+)", msg)
                if match:
                    print(f"   [{ts[:19]}] BEGIN: canvas={match.group(1)[:8]}... user={match.group(2)[:8]}... cards={match.group(3)}")
            elif "ok" in msg:
                match = re.search(r"created=(\[.*?\])", msg)
                if match:
                    print(f"   [{ts[:19]}] ✅ SUCCESS: created {match.group(1)}")
            elif "failed" in msg:
                match = re.search(r"error=([^,}]+)", msg)
                if match:
                    print(f"   [{ts[:19]}] ❌ FAILED: {match.group(1)}")
        print()
    
    if tool_calls:
        print(f"🔧 Tool Calls ({len(tool_calls)}):")
        # Group consecutive tool calls
        for ts, msg in tool_calls[:10]:  # Show first 10
            tool_match = re.search(r"(tool_\w+):", msg)
            if tool_match:
                tool_name = tool_match.group(1)
                status = "✅" if "ok" in msg else "❌" if "failed" in msg else "🔄"
                print(f"   [{ts[:19]}] {status} {tool_name}")
        if len(tool_calls) > 10:
            print(f"   ... and {len(tool_calls) - 10} more")
        print()
    
    # Show recent logs in detail
    print("📜 Recent Log Details (last 10):\n")
    for log in logs[:10]:  # Already reversed, so these are the most recent
        payload = log.get("jsonPayload", {})
        message = payload.get("message", "")
        timestamp = log.get("timestamp", "")
        severity = log.get("severity", "INFO")
        
        # Color code by severity
        severity_icon = {
            "ERROR": "❌",
            "WARNING": "⚠️",
            "INFO": "ℹ️",
            "DEBUG": "🔍"
        }.get(severity, "")
        
        print(f"{severity_icon} [{timestamp[:19]}] {severity}")
        print(f"   {message[:200]}")
        if len(message) > 200:
            print(f"   ...")
        print()

def check_specific_issues(logs: List[Dict[str, Any]]) -> None:
    """Check for specific known issues"""
    print("\n🔎 Checking for Known Issues:\n")
    
    issues_found = []
    
    # Check for API key issues
    api_key_errors = [log for log in logs if "api_key" in str(log).lower() or "401" in str(log)]
    if api_key_errors:
        issues_found.append("⚠️  API Key authentication issues detected")
    
    # Check for user_id propagation
    user_id_missing = [log for log in logs if "user_id is required" in str(log).lower()]
    if user_id_missing:
        issues_found.append("⚠️  User ID not being propagated correctly")
    
    # Check for canvas_id issues
    canvas_id_missing = [log for log in logs if "canvas_id is required" in str(log).lower()]
    if canvas_id_missing:
        issues_found.append("⚠️  Canvas ID not being set correctly")
    
    # Check for tool execution failures
    tool_failures = [log for log in logs if "tool_result" in str(log) and '"ok":false' in str(log)]
    if tool_failures:
        issues_found.append(f"⚠️  {len(tool_failures)} tool execution failures detected")
    
    # Check for HTTP errors
    http_errors = [log for log in logs if re.search(r"status[=:]\s*[4-5]\d\d", str(log))]
    if http_errors:
        issues_found.append(f"⚠️  {len(http_errors)} HTTP errors detected")
    
    if issues_found:
        for issue in issues_found:
            print(f"   {issue}")
    else:
        print("   ✅ No known issues detected")
    
    print()

def main():
    # Parse command line arguments
    minutes = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    filter_text = sys.argv[2] if len(sys.argv) > 2 else None
    
    # Read logs
    logs = read_agent_logs(minutes, filter_text)
    
    # Analyze logs
    analyze_logs(logs)
    
    # Check for specific issues
    check_specific_issues(logs)
    
    print("=" * 80)
    print("\n💡 Tips:")
    print("  - Use a filter to search for specific text: python read_agent_logs.py 10 'tool_canvas_publish'")
    print("  - Check Firebase Function logs too: node read_firebase_logs.js proposeCards 10")
    print("  - Look for correlation IDs to trace requests end-to-end")
    print()

if __name__ == "__main__":
    main()
