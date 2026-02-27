#!/usr/bin/env python3
"""
End-to-end agent response tests.

Sends natural language prompts to the deployed agent via streamAgentNormalized
and captures the full text response. Useful for evaluating agent behavior
from the user's perspective.

Usage:
    # Run all test prompts
    python3 tests/test_agent_responses.py

    # Run a single prompt
    python3 tests/test_agent_responses.py "How did my last workout go?"

    # With a specific user
    TEST_USER_ID=abc123 python3 tests/test_agent_responses.py

Environment:
    TEST_USER_ID: Firebase UID (default: Y4SJuNPOasaltF7TuKm1QCT7JIA3)
    MYON_FUNCTIONS_BASE_URL: Firebase Functions base URL
    MYON_API_KEY: API key (required — set in env)
"""

import json
import os
import sys
import time

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
USER_ID = os.getenv("TEST_USER_ID", "Y4SJuNPOasaltF7TuKm1QCT7JIA3")
BASE_URL = os.getenv(
    "MYON_FUNCTIONS_BASE_URL",
    "https://us-central1-myon-53d85.cloudfunctions.net",
)
API_KEY = os.environ["MYON_API_KEY"]  # Required — set in env, never hardcode
CANVAS_ID = os.getenv("TEST_CANVAS_ID", "test-agent-responses")

# ---------------------------------------------------------------------------
# SSE Client
# ---------------------------------------------------------------------------

def send_prompt(message: str, session_id: str = None) -> dict:
    """
    Send a prompt to streamAgentNormalized and collect the response.

    Returns dict with:
        text: str - full agent text response
        tools: list - tool calls made
        errors: list - any errors
        duration_s: float - wall clock time
        session_id: str - session ID (for follow-ups)
    """
    url = f"{BASE_URL}/streamAgentNormalized"
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY,
        "X-User-Id": USER_ID,
    }
    body = {
        "message": message,
        "canvasId": CANVAS_ID,
        "userId": USER_ID,
    }
    if session_id:
        body["sessionId"] = session_id

    t0 = time.time()
    resp = requests.post(url, json=body, headers=headers, stream=True, timeout=120)
    resp.raise_for_status()

    text_parts = []
    tools_used = []
    errors = []
    sess_id = session_id

    for line in resp.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data: "):
            continue
        payload = line[len("data: "):]
        try:
            evt = json.loads(payload)
        except json.JSONDecodeError:
            continue

        evt_type = evt.get("type", "")

        if evt_type == "status":
            sid = evt.get("content", {}).get("session_id")
            if sid:
                sess_id = sid

        elif evt_type == "toolRunning":
            tool_name = evt.get("content", {}).get("tool_name", "?")
            tool_text = evt.get("content", {}).get("text", "")
            tools_used.append({"tool": tool_name, "label": tool_text})

        elif evt_type == "message":
            # Collect streaming text deltas only (not text_commit/agentResponse
            # which would duplicate the same text)
            text_parts.append(evt.get("content", {}).get("text", ""))

        elif evt_type == "error":
            errors.append(evt.get("content", {}).get("error", "unknown"))

    elapsed = time.time() - t0
    full_text = "".join(text_parts).strip()

    return {
        "text": full_text,
        "tools": tools_used,
        "errors": errors,
        "duration_s": round(elapsed, 1),
        "session_id": sess_id,
    }


# ---------------------------------------------------------------------------
# Test prompts — natural language, what a real user would ask
# ---------------------------------------------------------------------------

TEST_PROMPTS = [
    # ===========================================
    # EASY — straightforward, single-tool answers
    # ===========================================

    # Recent workout (planning context or analysis)
    "How did my last workout go?",
    # Exercise-specific (exercise drilldown)
    "Is my bench press progressing?",
    # Readiness (daily brief)
    "Am I ready to train today?",
    # General knowledge (no tools needed)
    "How many sets per week do I need for chest growth?",
    # Missing data (exercise with no history)
    "What's my estimated squat max?",

    # ===========================================
    # MODERATE — requires date reasoning or
    #   multi-step tool selection
    # ===========================================

    # Date-relative: "yesterday" — must compute from today
    "What did I do yesterday?",
    # Muscle group trend — needs the right drilldown tool
    "How's my chest development going?",
    # Emotional framing — needs data check before empathy
    "I feel kinda tired, should I still train?",
    # Volume question — may need planning context
    "Am I training enough back?",
    # Vague but answerable
    "What should I focus on improving?",

    # ===========================================
    # COMPLEX — multi-tool, date math, or ambiguity
    # ===========================================

    # Current week volume — pre-computed may be stale
    "How many sets did I do this week?",
    # Comparison across time — needs to reason about trends
    "Am I training more or less than last month?",
    # Specific day + muscle — date math + filter
    "Did I hit chest on Monday?",
    # Open-ended advice requiring context
    "What should my next workout look like?",
    # Follow-up style question (but no session context)
    "Which of my exercises are stalling?",
]


def print_separator():
    print("=" * 72)


def run_prompt(prompt: str, idx: int = 0, total: int = 1):
    print_separator()
    print(f"  [{idx+1}/{total}] PROMPT: {prompt}")
    print_separator()

    result = send_prompt(prompt)

    if result["tools"]:
        print(f"  Tools: {', '.join(t['tool'] for t in result['tools'])}")

    if result["errors"]:
        print(f"  ERRORS: {result['errors']}")

    print(f"  Time: {result['duration_s']}s")
    print()
    print(result["text"] if result["text"] else "  (no text response)")
    print()

    return result


def main():
    if len(sys.argv) > 1:
        # Single prompt mode
        prompt = " ".join(sys.argv[1:])
        run_prompt(prompt)
        return

    print(f"\nAgent Response Test — {len(TEST_PROMPTS)} prompts")
    print(f"User: {USER_ID}")
    print(f"Base URL: {BASE_URL}")
    print()

    results = []
    for i, prompt in enumerate(TEST_PROMPTS):
        result = run_prompt(prompt, i, len(TEST_PROMPTS))
        result["prompt"] = prompt
        results.append(result)

    # Summary
    print_separator()
    print("  SUMMARY")
    print_separator()
    for r in results:
        status = "PASS" if r["text"] and not r["errors"] else "FAIL"
        has_data = "data" if r["tools"] else "knowledge"
        truncated = r["text"][:60] + "..." if len(r["text"]) > 60 else r["text"]
        print(f"  [{status}] ({r['duration_s']}s, {has_data}) {r['prompt']}")
        print(f"         → {truncated}")
    print()

    failed = [r for r in results if not r["text"] or r["errors"]]
    if failed:
        print(f"  {len(failed)} FAILED out of {len(results)}")
    else:
        print(f"  All {len(results)} passed.")


if __name__ == "__main__":
    main()
