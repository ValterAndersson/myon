#!/usr/bin/env python3
"""
Shell Agent Eval Runner — full pipeline SSE testing with LLM-as-Judge.

Sends each test case to the deployed agent via streamAgentNormalized SSE,
collects the complete response (text, tools, timing), then passes it to
the LLM judge for automated scoring.

Usage:
    # Run full eval suite
    python3 tests/eval/runner.py

    # Filter by category
    python3 tests/eval/runner.py --filter category=edge

    # Run a single test case
    python3 tests/eval/runner.py --id easy_001

    # Run with parallel requests (default: 1)
    python3 tests/eval/runner.py --parallel 3

    # Skip LLM judge (deterministic checks only)
    python3 tests/eval/runner.py --no-judge

Environment:
    TEST_USER_ID: Firebase UID (default: Y4SJuNPOasaltF7TuKm1QCT7JIA3)
    MYON_FUNCTIONS_BASE_URL: Firebase Functions base URL
    MYON_API_KEY: API key
"""

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import requests

# Ensure parent packages are importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from tests.eval.test_cases import ALL_CASES, TestCase, get_cases
from tests.eval.judge import JudgeResult, score_response

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
USER_ID = os.getenv("TEST_USER_ID", "Y4SJuNPOasaltF7TuKm1QCT7JIA3")
BASE_URL = os.getenv(
    "MYON_FUNCTIONS_BASE_URL",
    "https://us-central1-myon-53d85.cloudfunctions.net",
)
API_KEY = os.getenv("MYON_API_KEY", "myon-agent-key-2024")
CANVAS_ID = os.getenv("TEST_CANVAS_ID", "eval-suite")

RESULTS_DIR = Path(__file__).resolve().parent / "results"


# ---------------------------------------------------------------------------
# SSE Client — sends query to streamAgentNormalized
# ---------------------------------------------------------------------------

def send_prompt(
    message: str,
    session_id: str = None,
    workout_id: str = None,
) -> Dict:
    """
    Send a prompt to streamAgentNormalized and collect the full response.

    Returns dict with:
        text: str - full agent text response
        tools: list[str] - tool names called
        tool_details: list[dict] - tool calls with labels
        errors: list - any errors
        duration_s: float - wall clock time
        session_id: str - session ID
        events: list - all raw SSE events
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
    if workout_id:
        body["workoutId"] = workout_id

    t0 = time.time()
    try:
        resp = requests.post(url, json=body, headers=headers, stream=True, timeout=180)
        resp.raise_for_status()
    except requests.RequestException as e:
        return {
            "text": "",
            "tools": [],
            "tool_details": [],
            "errors": [str(e)],
            "duration_s": round(time.time() - t0, 1),
            "session_id": session_id,
            "events": [],
        }

    text_parts = []
    tools_used = []
    tool_details = []
    errors = []
    sess_id = session_id
    all_events = []

    for line in resp.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data: "):
            continue
        payload = line[len("data: "):]
        try:
            evt = json.loads(payload)
        except json.JSONDecodeError:
            continue

        all_events.append(evt)
        evt_type = evt.get("type", "")

        if evt_type == "status":
            sid = evt.get("content", {}).get("session_id")
            if sid:
                sess_id = sid

        elif evt_type == "toolRunning":
            tool_name = evt.get("content", {}).get("tool_name", "?")
            tool_text = evt.get("content", {}).get("text", "")
            tools_used.append(tool_name)
            tool_details.append({"tool": tool_name, "label": tool_text})

        elif evt_type == "message":
            text_parts.append(evt.get("content", {}).get("text", ""))

        elif evt_type == "error":
            err = evt.get("content", {})
            if isinstance(err, dict):
                errors.append(err.get("error", str(err)))
            else:
                errors.append(str(err))

        elif evt_type == "done":
            break

    elapsed = time.time() - t0
    full_text = "".join(text_parts).strip()

    return {
        "text": full_text,
        "tools": tools_used,
        "tool_details": tool_details,
        "errors": errors,
        "duration_s": round(elapsed, 1),
        "session_id": sess_id,
        "events": all_events,
    }


# ---------------------------------------------------------------------------
# Eval Runner
# ---------------------------------------------------------------------------

def run_single_case(
    case: TestCase,
    skip_judge: bool = False,
) -> Dict:
    """
    Run a single test case through the full pipeline.

    Returns a result dict with response data and judge scores.
    """
    # For active workout cases, prepend the workout brief to the message.
    # Do NOT send a fake workoutId — that triggers workout state lookup in the
    # Firebase function. The brief is injected directly into the message text.
    message = case.query
    if case.workout_brief:
        message = f"{case.workout_brief}\n{case.query}"

    # Send to agent (retry on transient errors with backoff)
    max_retries = 2
    response = None
    for attempt in range(max_retries + 1):
        response = send_prompt(message)
        # Retry if no text and errors (transient Vertex AI 400/401s)
        if response["text"] or not response["errors"] or attempt == max_retries:
            break
        time.sleep(3 * (attempt + 1))  # Backoff: 3s, 6s

    # Score with judge
    judge_result = None
    if not skip_judge and response["text"]:
        try:
            judge_result = score_response(
                test_case=case,
                response_text=response["text"],
                tools_used=response["tools"],
            )
        except Exception as e:
            judge_result = JudgeResult(
                test_id=case.id,
                overall_score=0,
                deterministic_issues=[f"Judge error: {e}"],
            )

    return {
        "test_id": case.id,
        "query": case.query,
        "category": case.category,
        "expected_tools": case.expected_tools,
        "response_text": response["text"],
        "tools_used": response["tools"],
        "tool_details": response["tool_details"],
        "errors": response["errors"],
        "duration_s": response["duration_s"],
        "session_id": response["session_id"],
        "judge": judge_result.to_dict() if judge_result else None,
        "overall_score": judge_result.overall_score if judge_result else None,
        "timestamp": datetime.utcnow().isoformat(),
    }


def run_eval(
    cases: List[TestCase],
    parallel: int = 1,
    skip_judge: bool = False,
) -> List[Dict]:
    """
    Run eval across all test cases.

    Args:
        cases: Test cases to evaluate
        parallel: Number of parallel requests (default 1 = sequential)
        skip_judge: Skip LLM judge, run deterministic checks only

    Returns:
        List of result dicts
    """
    results = []
    total = len(cases)

    if parallel <= 1:
        # Sequential execution with small delay to avoid Vertex AI rate limits
        for i, case in enumerate(cases):
            print(f"\n[{i+1}/{total}] {case.id}: {case.query[:60]}...")
            result = run_single_case(case, skip_judge=skip_judge)
            _print_result_summary(result)
            results.append(result)
            if i < total - 1:
                time.sleep(0.5)  # Brief pause between requests
    else:
        # Parallel execution
        print(f"Running {total} cases with {parallel} parallel workers...")
        with ThreadPoolExecutor(max_workers=parallel) as executor:
            future_to_case = {
                executor.submit(run_single_case, case, skip_judge): case
                for case in cases
            }
            completed = 0
            for future in as_completed(future_to_case):
                completed += 1
                case = future_to_case[future]
                try:
                    result = future.result()
                    print(f"\n[{completed}/{total}] {case.id}: ", end="")
                    _print_result_summary(result)
                    results.append(result)
                except Exception as e:
                    print(f"\n[{completed}/{total}] {case.id}: ERROR - {e}")
                    results.append({
                        "test_id": case.id,
                        "query": case.query,
                        "category": case.category,
                        "errors": [str(e)],
                        "overall_score": 0,
                        "timestamp": datetime.utcnow().isoformat(),
                    })

    # Sort by test ID for consistent output
    results.sort(key=lambda r: r["test_id"])
    return results


def _print_result_summary(result: Dict):
    """Print a one-line summary of a result."""
    score = result.get("overall_score")
    score_str = f"{score:.0f}" if score is not None else "N/A"
    duration = result.get("duration_s", 0)
    tools = result.get("tools_used", [])
    errors = result.get("errors", [])
    text_preview = (result.get("response_text", "") or "")[:80]

    status = "PASS" if score and score >= 75 else ("FAIL" if score is not None else "ERR")
    if errors:
        status = "ERR"

    print(f"[{status}] score={score_str} time={duration}s tools={len(tools)} ", end="")
    if errors:
        print(f"errors={errors[:1]}")
    else:
        print(f"| {text_preview}...")


# ---------------------------------------------------------------------------
# Output — write results to files
# ---------------------------------------------------------------------------

def save_results(results: List[Dict], timestamp: str) -> tuple:
    """Save results as JSONL (per-case) and summary JSON."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # Per-case JSONL
    jsonl_path = RESULTS_DIR / f"eval_{timestamp}.jsonl"
    with open(jsonl_path, "w") as f:
        for result in results:
            # Remove raw events to keep file manageable
            output = {k: v for k, v in result.items() if k != "events"}
            f.write(json.dumps(output) + "\n")

    # Summary JSON
    summary = _compute_summary(results)
    summary["timestamp"] = timestamp
    summary["total_cases"] = len(results)
    summary["user_id"] = USER_ID

    summary_path = RESULTS_DIR / f"eval_{timestamp}_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    return jsonl_path, summary_path


def _compute_summary(results: List[Dict]) -> Dict:
    """Compute aggregate scores from results."""
    scores = [r["overall_score"] for r in results if r.get("overall_score") is not None]

    # Category breakdown
    categories = {}
    for r in results:
        cat = r.get("category", "unknown")
        if cat not in categories:
            categories[cat] = {"scores": [], "count": 0, "failures": 0}
        categories[cat]["count"] += 1
        if r.get("overall_score") is not None:
            categories[cat]["scores"].append(r["overall_score"])
            if r["overall_score"] < 75:
                categories[cat]["failures"] += 1

    category_summary = {}
    for cat, data in categories.items():
        cat_scores = data["scores"]
        category_summary[cat] = {
            "count": data["count"],
            "avg_score": round(sum(cat_scores) / len(cat_scores), 1) if cat_scores else 0,
            "min_score": round(min(cat_scores), 1) if cat_scores else 0,
            "max_score": round(max(cat_scores), 1) if cat_scores else 0,
            "failures": data["failures"],
        }

    # Dimension averages
    dimension_avgs = {}
    for r in results:
        judge = r.get("judge")
        if not judge:
            continue
        for dim_name, dim_data in judge.get("dimensions", {}).items():
            if dim_name not in dimension_avgs:
                dimension_avgs[dim_name] = []
            dimension_avgs[dim_name].append(dim_data.get("score", 0))

    dimensions = {}
    for dim_name, dim_scores in dimension_avgs.items():
        dimensions[dim_name] = {
            "avg_score": round(sum(dim_scores) / len(dim_scores), 1) if dim_scores else 0,
            "min_score": round(min(dim_scores), 1) if dim_scores else 0,
        }

    # Failing tests
    failing = [
        {
            "test_id": r["test_id"],
            "score": r.get("overall_score", 0),
            "query": r.get("query", ""),
            "issues": (
                (r.get("judge", {}) or {}).get("deterministic_issues", [])
                + (r.get("judge", {}) or {}).get("llm_issues", [])
            )[:5],
        }
        for r in results
        if r.get("overall_score") is not None and r["overall_score"] < 75
    ]
    failing.sort(key=lambda x: x["score"])

    # Most common issues
    all_issues = []
    for r in results:
        judge = r.get("judge")
        if judge:
            all_issues.extend(judge.get("deterministic_issues", []))
            all_issues.extend(judge.get("llm_issues", []))

    issue_counts = {}
    for issue in all_issues:
        # Normalize issue text for grouping
        key = issue.split(":")[0].strip() if ":" in issue else issue
        issue_counts[key] = issue_counts.get(key, 0) + 1

    top_issues = sorted(issue_counts.items(), key=lambda x: -x[1])[:10]

    # Timing
    durations = [r.get("duration_s", 0) for r in results if r.get("duration_s")]

    return {
        "overall": {
            "avg_score": round(sum(scores) / len(scores), 1) if scores else 0,
            "min_score": round(min(scores), 1) if scores else 0,
            "max_score": round(max(scores), 1) if scores else 0,
            "pass_rate": round(
                len([s for s in scores if s >= 75]) / len(scores) * 100, 1
            ) if scores else 0,
            "failures": len([s for s in scores if s < 75]),
        },
        "categories": category_summary,
        "dimensions": dimensions,
        "failing_tests": failing[:15],
        "top_issues": [{"issue": k, "count": v} for k, v in top_issues],
        "timing": {
            "avg_duration_s": round(sum(durations) / len(durations), 1) if durations else 0,
            "max_duration_s": round(max(durations), 1) if durations else 0,
            "total_duration_s": round(sum(durations), 1),
        },
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Shell Agent Eval Runner")
    parser.add_argument(
        "--filter",
        help="Filter cases (e.g., category=edge, tags=safety)",
    )
    parser.add_argument(
        "--id",
        help="Run a single test case by ID",
    )
    parser.add_argument(
        "--parallel",
        type=int,
        default=1,
        help="Number of parallel requests (default: 1)",
    )
    parser.add_argument(
        "--no-judge",
        action="store_true",
        help="Skip LLM judge (deterministic checks only)",
    )
    args = parser.parse_args()

    # Select test cases
    if args.id:
        cases = get_cases(case_id=args.id)
        if not cases:
            print(f"Error: No test case with ID '{args.id}'")
            sys.exit(1)
    elif args.filter:
        key, _, value = args.filter.partition("=")
        if key == "category":
            cases = get_cases(category=value)
        elif key == "tags":
            cases = get_cases(tags=value.split(","))
        else:
            print(f"Error: Unknown filter key '{key}'. Use category= or tags=")
            sys.exit(1)
        if not cases:
            print(f"Error: No cases matching filter '{args.filter}'")
            sys.exit(1)
    else:
        cases = ALL_CASES

    # Run
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    print(f"Shell Agent Eval — {len(cases)} cases")
    print(f"User: {USER_ID}")
    print(f"Base URL: {BASE_URL}")
    print(f"Timestamp: {timestamp}")
    if args.no_judge:
        print("LLM Judge: DISABLED (deterministic only)")
    print("=" * 72)

    results = run_eval(
        cases,
        parallel=args.parallel,
        skip_judge=args.no_judge,
    )

    # Save results
    jsonl_path, summary_path = save_results(results, timestamp)

    # Print summary
    print("\n" + "=" * 72)
    print("EVAL SUMMARY")
    print("=" * 72)

    summary = _compute_summary(results)

    overall = summary["overall"]
    print(f"\nOverall: {overall['avg_score']}/100 avg "
          f"(pass rate: {overall['pass_rate']}%, "
          f"failures: {overall['failures']})")

    print(f"\nCategory Breakdown:")
    for cat, data in summary["categories"].items():
        print(f"  {cat:18s}: {data['avg_score']:5.1f} avg "
              f"({data['count']} cases, {data['failures']} failures)")

    print(f"\nDimension Averages:")
    for dim, data in summary.get("dimensions", {}).items():
        print(f"  {dim:18s}: {data['avg_score']:5.1f} avg "
              f"(min: {data['min_score']:.1f})")

    if summary["failing_tests"]:
        print(f"\nFailing Tests (score < 75):")
        for f in summary["failing_tests"][:10]:
            print(f"  {f['test_id']:18s}: {f['score']:5.1f} — {f['query'][:50]}")
            for issue in f["issues"][:2]:
                print(f"    → {issue}")

    if summary["top_issues"]:
        print(f"\nMost Common Issues:")
        for issue in summary["top_issues"][:5]:
            print(f"  [{issue['count']}x] {issue['issue']}")

    timing = summary["timing"]
    print(f"\nTiming: {timing['avg_duration_s']}s avg, "
          f"{timing['max_duration_s']}s max, "
          f"{timing['total_duration_s']}s total")

    print(f"\nResults saved:")
    print(f"  JSONL: {jsonl_path}")
    print(f"  Summary: {summary_path}")

    # Exit code based on pass rate
    if overall["pass_rate"] < 50:
        sys.exit(2)
    elif overall["failures"] > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
