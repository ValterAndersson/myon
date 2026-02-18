#!/usr/bin/env python3
"""
Enrichment Eval Runner — tests exercise content quality end-to-end.

Calls enrich_exercise_holistic() with synthetic exercise documents, then
routes the enriched output to the judge for scoring.

Usage:
    python3 tests/eval/runner.py                       # Full eval suite
    python3 tests/eval/runner.py --filter category=fix
    python3 tests/eval/runner.py --id gen_001
    python3 tests/eval/runner.py --no-judge             # Deterministic only

Environment:
    GOOGLE_APPLICATION_CREDENTIALS or GCP_SA_KEY must be set for Vertex AI.
"""

import argparse
import copy
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

# Ensure parent packages are importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from tests.eval.test_cases import (
    ALL_CASES, EnrichmentTestCase, get_cases,
)
from tests.eval.judge import JudgeResult, score_enrichment

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

RESULTS_DIR = Path(__file__).resolve().parent / "results"


# ---------------------------------------------------------------------------
# Enrichment caller — calls enrich_exercise_holistic directly
# ---------------------------------------------------------------------------

def call_enrichment(exercise: Dict[str, Any]) -> Dict[str, Any]:
    """
    Call the holistic enrichment function with a synthetic exercise.
    Returns the enrichment result dict.
    """
    from app.enrichment.engine import enrich_exercise_holistic

    result = enrich_exercise_holistic(
        exercise=exercise,
        reviewer_hint="",  # No reviewer hint — test raw enrichment
        use_pro_model=False,  # Use Flash for cost efficiency
    )
    return result


def apply_changes(
    original: Dict[str, Any],
    changes: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Apply enrichment changes to the original exercise document.
    Handles dotted paths (e.g., "muscles.primary" -> muscles.primary).
    Returns a new dict with changes applied.
    """
    result = copy.deepcopy(original)

    for path, value in changes.items():
        parts = path.split(".")
        target = result
        for part in parts[:-1]:
            if part not in target:
                target[part] = {}
            target = target[part]
        target[parts[-1]] = value

    return result


# ---------------------------------------------------------------------------
# Eval Runner
# ---------------------------------------------------------------------------

def run_single_case(
    case: EnrichmentTestCase,
    skip_judge: bool = False,
) -> Dict:
    """Run a single test case through the enrichment + judge pipeline."""
    t0 = time.time()
    errors = []

    # 1. Call enrichment
    try:
        enrichment_result = call_enrichment(case.exercise)
    except Exception as e:
        elapsed = time.time() - t0
        return {
            "test_id": case.id,
            "category": case.category,
            "exercise_name": case.exercise.get("name", "unknown"),
            "errors": [f"Enrichment error: {e}"],
            "overall_score": 0,
            "duration_s": round(elapsed, 1),
            "timestamp": datetime.utcnow().isoformat(),
        }

    if not enrichment_result.get("success"):
        elapsed = time.time() - t0
        return {
            "test_id": case.id,
            "category": case.category,
            "exercise_name": case.exercise.get("name", "unknown"),
            "errors": [f"Enrichment failed: {enrichment_result.get('error', 'unknown')}"],
            "enrichment_result": enrichment_result,
            "overall_score": 0,
            "duration_s": round(elapsed, 1),
            "timestamp": datetime.utcnow().isoformat(),
        }

    # 2. Apply changes to get enriched exercise
    changes = enrichment_result.get("changes", {})
    enriched_exercise = apply_changes(case.exercise, changes)

    # 3. Score with judge
    judge_result = None
    try:
        judge_result = score_enrichment(
            test_case=case,
            original_exercise=case.exercise,
            enriched_exercise=enriched_exercise,
            skip_llm=skip_judge,
        )
    except Exception as e:
        judge_result = JudgeResult(
            test_id=case.id,
            overall_score=0,
            deterministic_issues=[f"Judge error: {e}"],
        )

    elapsed = time.time() - t0

    return {
        "test_id": case.id,
        "category": case.category,
        "exercise_name": case.exercise.get("name", "unknown"),
        "changes_count": len(changes),
        "changes_fields": list(changes.keys()),
        "enrichment_reasoning": enrichment_result.get("reasoning", "")[:200],
        "enrichment_confidence": enrichment_result.get("confidence", ""),
        "enriched_content": _extract_content_fields(enriched_exercise),
        "errors": errors,
        "duration_s": round(elapsed, 1),
        "judge": judge_result.to_dict() if judge_result else None,
        "overall_score": judge_result.overall_score if judge_result else None,
        "timestamp": datetime.utcnow().isoformat(),
    }


def _extract_content_fields(exercise: Dict[str, Any]) -> Dict:
    """Extract just the content fields for result storage."""
    return {
        k: exercise.get(k)
        for k in [
            "description", "execution_notes", "common_mistakes",
            "suitability_notes", "programming_use_cases", "stimulus_tags",
        ]
        if exercise.get(k)
    }


def run_eval(
    cases: List[EnrichmentTestCase],
    skip_judge: bool = False,
) -> List[Dict]:
    """Run eval across all test cases sequentially."""
    results = []
    total = len(cases)

    for i, case in enumerate(cases):
        print(
            f"\n[{i+1}/{total}] {case.id}: "
            f"{case.category} / {case.exercise.get('name', '?')}..."
        )
        result = run_single_case(case, skip_judge=skip_judge)
        _print_result_summary(result)
        results.append(result)
        if i < total - 1:
            time.sleep(1)  # Brief pause between LLM calls

    results.sort(key=lambda r: r["test_id"])
    return results


def _print_result_summary(result: Dict):
    """Print a one-line summary."""
    score = result.get("overall_score")
    score_str = f"{score:.0f}" if score is not None else "N/A"
    duration = result.get("duration_s", 0)
    errors = result.get("errors", [])
    changes = result.get("changes_count", 0)
    confidence = result.get("enrichment_confidence", "")

    status = "PASS" if score and score >= 75 else ("FAIL" if score is not None else "ERR")
    if errors:
        status = "ERR"

    print(f"  [{status}] score={score_str} time={duration}s changes={changes} conf={confidence}")

    if errors:
        print(f"    errors={errors[:1]}")

    # Show deterministic issues if any
    judge = result.get("judge")
    if judge and judge.get("deterministic_issues"):
        for issue in judge["deterministic_issues"][:3]:
            print(f"    det: {issue}")


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def save_results(results: List[Dict], timestamp: str) -> tuple:
    """Save results as JSONL (per-case) and summary JSON."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    jsonl_path = RESULTS_DIR / f"eval_{timestamp}.jsonl"
    with open(jsonl_path, "w") as f:
        for result in results:
            f.write(json.dumps(result, default=str) + "\n")

    summary = _compute_summary(results)
    summary["timestamp"] = timestamp
    summary["total_cases"] = len(results)

    summary_path = RESULTS_DIR / f"eval_{timestamp}_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    return jsonl_path, summary_path


def _compute_summary(results: List[Dict]) -> Dict:
    """Compute aggregate scores from results."""
    scores = [
        r["overall_score"] for r in results
        if r.get("overall_score") is not None
    ]

    # Per-category breakdown
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

    # Per-dimension averages
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
            "exercise": r.get("exercise_name", ""),
            "score": r.get("overall_score", 0),
            "issues": (
                (r.get("judge", {}) or {}).get("deterministic_issues", [])
                + (r.get("judge", {}) or {}).get("llm_issues", [])
            )[:5],
        }
        for r in results
        if r.get("overall_score") is not None and r["overall_score"] < 75
    ]
    failing.sort(key=lambda x: x["score"])

    # Top issues
    all_issues = []
    for r in results:
        judge = r.get("judge")
        if judge:
            all_issues.extend(judge.get("deterministic_issues", []))
            all_issues.extend(judge.get("llm_issues", []))

    issue_counts = {}
    for issue in all_issues:
        # Normalize issue key (strip specific values after colon)
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
    parser = argparse.ArgumentParser(description="Enrichment Content Quality Eval Runner")
    parser.add_argument(
        "--filter",
        help="Filter cases (e.g., category=fix, tags=compound)",
    )
    parser.add_argument("--id", help="Run a single test case by ID")
    parser.add_argument(
        "--no-judge", action="store_true",
        help="Skip LLM judge (deterministic checks only)",
    )
    args = parser.parse_args()

    # Resolve GCP credentials
    if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        gcp_key = os.environ.get("GCP_SA_KEY")
        if gcp_key and os.path.isfile(gcp_key):
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = gcp_key
        else:
            fallback = os.path.expanduser(
                "~/.config/povver/myon-53d85-80792c186dcb.json"
            )
            if os.path.isfile(fallback):
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = fallback

    # Select cases
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

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    print(f"Enrichment Content Quality Eval - {len(cases)} cases")
    print(f"Timestamp: {timestamp}")
    if args.no_judge:
        print("LLM Judge: DISABLED (deterministic only)")
    print("=" * 72)

    results = run_eval(cases, skip_judge=args.no_judge)

    jsonl_path, summary_path = save_results(results, timestamp)

    # Print summary
    print("\n" + "=" * 72)
    print("EVAL SUMMARY")
    print("=" * 72)

    summary = _compute_summary(results)
    overall = summary["overall"]
    print(
        f"\nOverall: {overall['avg_score']}/100 avg "
        f"(pass rate: {overall['pass_rate']}%, "
        f"failures: {overall['failures']})"
    )

    print("\nCategory Breakdown:")
    for cat, data in summary["categories"].items():
        print(
            f"  {cat:12s}: {data['avg_score']:5.1f} avg "
            f"({data['count']} cases, {data['failures']} failures)"
        )

    print("\nDimension Averages:")
    for dim, data in summary.get("dimensions", {}).items():
        print(f"  {dim:22s}: {data['avg_score']:5.1f} avg (min: {data['min_score']:.1f})")

    if summary["failing_tests"]:
        print("\nFailing Tests (score < 75):")
        for f in summary["failing_tests"][:10]:
            print(f"  {f['test_id']:12s} ({f['exercise']:30s}): {f['score']:5.1f}")
            for issue in f["issues"][:2]:
                print(f"    -> {issue}")

    if summary["top_issues"]:
        print("\nMost Common Issues:")
        for issue in summary["top_issues"][:5]:
            print(f"  [{issue['count']}x] {issue['issue']}")

    timing = summary["timing"]
    print(
        f"\nTiming: {timing['avg_duration_s']}s avg, "
        f"{timing['max_duration_s']}s max, "
        f"{timing['total_duration_s']}s total"
    )

    print(f"\nResults saved:")
    print(f"  JSONL: {jsonl_path}")
    print(f"  Summary: {summary_path}")

    if overall["pass_rate"] < 50:
        sys.exit(2)
    elif overall["failures"] > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
