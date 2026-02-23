#!/usr/bin/env python3
"""
End-to-end test: Shell Agent + training analysis pipeline.

Calls the real getAnalysisSummary endpoint, then feeds the data to Gemini
with the Shell Agent's instruction to verify response quality.

Usage:
    cd adk_agent/canvas_orchestrator
    GOOGLE_APPLICATION_CREDENTIALS=~/.config/povver/myon-53d85-80792c186dcb.json \
      python3 tests/test_agent_e2e.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import traceback

from google import genai
from google.genai.types import Content, GenerateContentConfig, Part

from app.shell.instruction import SHELL_INSTRUCTION

# Test config
USER_ID = "xLRyVOI0XKSFsTXSFbGSvui8FJf2"
MODEL = "gemini-2.5-flash"
BASE_URL = "https://us-central1-myon-53d85.cloudfunctions.net"
API_KEY = "myon-agent-key-2024"

# Baseline queries — the bread-and-butter that must never regress
QUERIES_BASELINE = [
    "How am I doing overall?",
    "Am I ready to train today?",
    "Did I hit any PRs recently?",
    "Where am I stalling and what should I change?",
    "How was my training volume this week compared to last?",
]

# Edge case queries — tests boundaries of pre-computed data
# Phase A: tool data IS provided, but the query asks for more than it contains
QUERIES_WITH_DATA = [
    "How many sets of chest did I do last Tuesday?",          # specific day — not in summaries
    "What's my squat 1RM?",                                   # exercise likely not in data
    "Should I do 4 or 5 sets of bench next session?",         # overly specific programming ask
    "My shoulder hurts when I do face pulls, what should I do?",  # pain/medical boundary
]

# Phase B: NO tool data injected — model only has system instruction + query
# Tests whether Flash hallucinates or correctly says it needs to look things up
QUERIES_NO_DATA = [
    "What's my deadlift max?",                                # no data, should not invent numbers
    "How many calories should I eat?",                        # off-topic for this tool
    "Create me a new push pull legs routine",                 # action request, not analysis
    "I just did 5x5 at 100kg on squat, was that good?",      # user provides data, agent has no context
]


def fetch_analysis_data(sections=None):
    """Read analysis data directly from Firestore (same data as getAnalysisSummary)."""
    from google.cloud import firestore

    db = firestore.Client(project="myon-53d85")
    user_ref = db.collection("users").document(USER_ID)

    def ts(v):
        if hasattr(v, "isoformat"):
            return v.isoformat()
        return v

    result = {}

    if not sections or "insights" in sections:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        # Simple query (no composite index needed) — filter expired in Python
        docs = (
            user_ref.collection("analysis_insights")
            .order_by("created_at", direction=firestore.Query.DESCENDING)
            .limit(10)
            .stream()
        )
        insights = []
        for doc in docs:
            d = doc.to_dict()
            expires = d.get("expires_at")
            if expires and hasattr(expires, "timestamp") and expires.timestamp() < now.timestamp():
                continue  # Skip expired
            insights.append({
                "id": doc.id,
                "type": d.get("type"),
                "workout_id": d.get("workout_id"),
                "workout_date": d.get("workout_date"),
                "summary": d.get("summary", ""),
                "highlights": d.get("highlights", []),
                "flags": d.get("flags", []),
                "recommendations": d.get("recommendations", []),
                "created_at": ts(d.get("created_at")),
                "expires_at": ts(d.get("expires_at")),
            })
            if len(insights) >= 5:
                break
        result["insights"] = insights

    if not sections or "weekly_review" in sections:
        docs = (
            user_ref.collection("weekly_reviews")
            .order_by("created_at", direction=firestore.Query.DESCENDING)
            .limit(1)
            .stream()
        )
        review = None
        for doc in docs:
            d = doc.to_dict()
            review = {
                "id": doc.id,
                "week_ending": d.get("week_ending"),
                "summary": d.get("summary", ""),
                "training_load": d.get("training_load", {}),
                "muscle_balance": d.get("muscle_balance", []),
                "exercise_trends": d.get("exercise_trends", []),
                "progression_candidates": d.get("progression_candidates", []),
                "stalled_exercises": d.get("stalled_exercises", []),
                "created_at": ts(d.get("created_at")),
            }
        result["weekly_review"] = review

    return result


def simulate_agent_turn(query: str, tool_result: dict = None) -> str:
    """Simulate a Shell Agent turn.

    If tool_result is provided, simulates: user query → tool call → tool result → response.
    If tool_result is None, simulates: user query → response (no tool data available).
    """
    client = genai.Client(
        vertexai=True,
        project="myon-53d85",
        location="us-central1",
    )

    if tool_result is not None:
        contents = [
            Content(role="user", parts=[Part(text=query)]),
            Content(role="model", parts=[Part(text="[Calling tool_get_training_analysis]")]),
            Content(
                role="user",
                parts=[Part(text=f"Tool result from tool_get_training_analysis:\n{json.dumps(tool_result, indent=2)}")],
            ),
        ]
    else:
        # No tool data — just user query. Tests if model hallucinates or handles gracefully.
        contents = [
            Content(role="user", parts=[Part(text=query)]),
        ]

    response = client.models.generate_content(
        model=MODEL,
        contents=contents,
        config=GenerateContentConfig(
            system_instruction=SHELL_INSTRUCTION,
            temperature=0.3,
        ),
    )

    # Model may emit text, function calls, or both — or be blocked
    try:
        candidates = response.candidates
    except Exception:
        candidates = None

    if not candidates:
        feedback = getattr(response, "prompt_feedback", None)
        # Try raw text as fallback
        try:
            if response.text:
                return response.text.strip()
        except Exception:
            pass
        return f"(no candidates — {feedback})"

    candidate = candidates[0]

    # Handle UNEXPECTED_TOOL_CALL — model tried to use a tool we didn't register
    finish_reason = getattr(candidate, "finish_reason", None)
    finish_msg = getattr(candidate, "finish_message", None)
    if finish_reason and "TOOL_CALL" in str(finish_reason):
        return f"[WOULD CALL TOOL: {finish_msg}]"

    content = getattr(candidate, "content", None)
    parts = content.parts if content and content.parts else []

    text_parts = []
    fc_parts = []
    for part in parts:
        if hasattr(part, "text") and part.text:
            text_parts.append(part.text.strip())
        if hasattr(part, "function_call") and part.function_call:
            fc = part.function_call
            args = dict(fc.args) if fc.args else {}
            fc_parts.append(f"[TOOL CALL: {fc.name}({json.dumps(args, indent=2)})]")

    output = "\n".join(fc_parts + text_parts)
    return output if output else f"(empty — finish_reason: {finish_reason})"


def check_quality(response, extra_checks=None):
    """Run quality checks on agent response. Returns list of issues."""
    issues = []
    if len(response) < 10:
        issues.append("Response too short (<10 chars)")
    if len(response.split("\n")) > 20:
        issues.append(f"Response too long ({len(response.split(chr(10)))} lines)")
    for bad_name in ["K21gndDYgWE25mFmPamH", "Onf5q14907l3BFrZlQUy"]:
        if bad_name in response:
            issues.append(f"Used raw exercise ID as name: {bad_name}")
    # Check for leaked tool names — but exclude responses where the model
    # attempted a tool call (shown as [Calling ...] or [WOULD CALL TOOL: ...]),
    # which is correct behavior that the test simulation can't execute.
    if "tool_get_" in response.lower():
        is_tool_attempt = response.startswith("[Calling ") or response.startswith("[WOULD CALL TOOL")
        if not is_tool_attempt:
            issues.append("Leaked tool name in response")
    if extra_checks:
        for label, check_fn in extra_checks:
            if check_fn(response):
                issues.append(label)
    return issues


def main():
    print("=" * 70)
    print("SHELL AGENT EDGE CASE TEST")
    print("=" * 70)

    # Fetch analysis data for Phase A
    print("\nFetching analysis data from Firestore...")
    try:
        data = fetch_analysis_data()
    except Exception as e:
        print(f"ERROR fetching data: {e}")
        return 1
    print(f"   insights: {len(data.get('insights', []))} items")
    print(f"   weekly_review: {'present' if data.get('weekly_review') else 'null'}")

    total_issues = 0

    # ── Phase 0: Baseline queries (regression check) ──
    print(f"\n{'=' * 70}")
    print("PHASE 0: Baseline queries — must not regress")
    print("=" * 70)

    for i, query in enumerate(QUERIES_BASELINE, 1):
        print(f"\n{'─' * 70}")
        print(f"Q{i}: \"{query}\"")
        print(f"{'─' * 70}")

        try:
            response = simulate_agent_turn(query, data)
            print(f"\n{response}")
            issues = check_quality(response)
            if issues:
                print(f"\n⚠️  ISSUES: {issues}")
                total_issues += len(issues)
            else:
                print(f"\n✅ OK")
        except Exception as e:
            print(f"\nERROR: {e}")
            total_issues += 1

    # ── Phase A: Tool data provided, but query goes beyond it ──
    print(f"\n{'=' * 70}")
    print("PHASE A: Data provided — queries that go BEYOND the summaries")
    print("=" * 70)

    for i, query in enumerate(QUERIES_WITH_DATA, 1):
        print(f"\n{'─' * 70}")
        print(f"A{i}: \"{query}\"")
        print(f"{'─' * 70}")

        try:
            response = simulate_agent_turn(query, data)
            print(f"\n{response}")
            issues = check_quality(response)
            if issues:
                print(f"\n⚠️  ISSUES: {issues}")
                total_issues += len(issues)
            else:
                print(f"\n✅ OK")
        except Exception as e:
            print(f"\nERROR: {e}")
            total_issues += 1

    # ── Phase B: NO tool data — tests hallucination boundaries ──
    print(f"\n{'=' * 70}")
    print("PHASE B: NO data provided — should NOT hallucinate numbers")
    print("=" * 70)

    for i, query in enumerate(QUERIES_NO_DATA, 1):
        print(f"\n{'─' * 70}")
        print(f"B{i}: \"{query}\"")
        print(f"{'─' * 70}")

        try:
            response = simulate_agent_turn(query, None)
            print(f"\n{response}")

            # Extra check: model should NOT produce specific kg/lb numbers
            # when it has no data — exclude numbers the user mentioned
            import re
            user_nums = set(re.findall(r'\d+', query))
            extra = [
                (
                    "Hallucinated specific weight with no data",
                    lambda r, _un=user_nums: any(
                        (f"{n}kg" in r.lower() or f"{n} kg" in r.lower())
                        and str(n) not in _un
                        for n in range(20, 300)
                    ),
                ),
            ]
            issues = check_quality(response, extra_checks=extra)
            if issues:
                print(f"\n⚠️  ISSUES: {issues}")
                total_issues += len(issues)
            else:
                print(f"\n✅ OK")
        except Exception as e:
            print(f"\nERROR: {e}")
            traceback.print_exc()
            total_issues += 1

    # ── Summary ──
    print(f"\n{'=' * 70}")
    total = len(QUERIES_BASELINE) + len(QUERIES_WITH_DATA) + len(QUERIES_NO_DATA)
    print(f"DONE: {total} queries, {total_issues} total issues")
    print("=" * 70)

    return 0 if total_issues == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
