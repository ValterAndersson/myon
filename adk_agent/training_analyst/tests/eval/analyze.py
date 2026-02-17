#!/usr/bin/env python3
"""
Results analysis + A/B comparison for recommendation eval runs.

Usage:
    # Analyze latest results
    python3 tests/eval/analyze.py

    # Compare two runs
    python3 tests/eval/analyze.py --compare --baseline eval_20260217_120000 --new eval_20260217_130000
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

RESULTS_DIR = Path(__file__).resolve().parent / "results"


def find_latest_summary() -> Optional[Path]:
    """Find the most recent summary JSON file."""
    summaries = sorted(RESULTS_DIR.glob("eval_*_summary.json"), reverse=True)
    return summaries[0] if summaries else None


def load_summary(name_or_path: str) -> Dict:
    """Load a summary JSON by filename prefix or full path."""
    path = Path(name_or_path)
    if not path.exists():
        path = RESULTS_DIR / f"{name_or_path}_summary.json"
    if not path.exists():
        matches = sorted(RESULTS_DIR.glob(f"*{name_or_path}*_summary.json"))
        if matches:
            path = matches[0]
    if not path.exists():
        print(f"Error: Cannot find summary for '{name_or_path}'")
        sys.exit(1)
    with open(path) as f:
        return json.load(f)


def load_jsonl(name_or_path: str) -> List[Dict]:
    """Load per-case JSONL results."""
    path = Path(name_or_path)
    if not path.exists():
        path = RESULTS_DIR / f"{name_or_path}.jsonl"
    if not path.exists():
        matches = sorted(RESULTS_DIR.glob(f"*{name_or_path}*.jsonl"))
        if matches:
            path = matches[0]
    if not path.exists():
        return []
    results = []
    with open(path) as f:
        for line in f:
            if line.strip():
                results.append(json.loads(line))
    return results


def analyze_latest():
    """Analyze the most recent eval run."""
    summary_path = find_latest_summary()
    if not summary_path:
        print("No eval results found in results/")
        sys.exit(1)

    summary = json.loads(summary_path.read_text())
    timestamp = summary.get("timestamp", "unknown")

    print(f"Analysis of eval run: {timestamp}")
    print(f"Total cases: {summary.get('total_cases', 0)}")
    print("=" * 72)

    overall = summary.get("overall", {})
    print(f"\nOverall Score: {overall.get('avg_score', 0)}/100")
    print(f"Pass Rate: {overall.get('pass_rate', 0)}%")
    print(f"Failures: {overall.get('failures', 0)}")

    print("\n--- Category Breakdown ---")
    for cat, data in summary.get("categories", {}).items():
        status = "OK" if data["failures"] == 0 else "NEEDS WORK"
        print(
            f"  {cat:20s}: avg={data['avg_score']:5.1f} "
            f"min={data['min_score']:5.1f} "
            f"max={data['max_score']:5.1f} "
            f"[{status}]"
        )

    print("\n--- Dimension Analysis ---")
    for dim, data in summary.get("dimensions", {}).items():
        flag = " << LOW" if data["avg_score"] < 60 else ""
        print(f"  {dim:20s}: avg={data['avg_score']:5.1f} min={data['min_score']:5.1f}{flag}")

    print("\n--- Top Failure Patterns ---")
    for issue in summary.get("top_issues", [])[:8]:
        print(f"  [{issue['count']}x] {issue['issue']}")

    print("\n--- Worst Cases ---")
    for case in summary.get("failing_tests", [])[:5]:
        print(f"  {case['test_id']:20s}: {case['score']:.0f}/100")
        for issue in case.get("issues", [])[:2]:
            print(f"    -> {issue}")

    # Diagnosis
    print("\n--- Diagnosis ---")
    dims = summary.get("dimensions", {})
    if dims.get("clarity", {}).get("avg_score", 100) < 60:
        print("  [!] Clarity low: summaries/rationales are unclear or too terse")
    if dims.get("data_grounding", {}).get("avg_score", 100) < 60:
        print("  [!] Data grounding low: numbers/signals not being cited")
        print("      -> Likely fix: evolve analyzer prompts (add reasoning/signals fields)")
    if dims.get("actionability", {}).get("avg_score", 100) < 60:
        print("  [!] Actionability low: users don't know what action to take")
        print("      -> Likely fix: evolve process-recommendations.js (contextual summaries)")
    if dims.get("contextual_fit", {}).get("avg_score", 100) < 60:
        print("  [!] Contextual fit low: language doesn't match scenario")
        print("      -> Likely fix: add scenario-aware text generation in JS processing")


def compare_runs(baseline_name: str, new_name: str):
    """Compare two eval runs and show deltas."""
    baseline = load_summary(baseline_name)
    new = load_summary(new_name)

    print(f"Comparison: {baseline_name} (baseline) vs {new_name} (new)")
    print("=" * 72)

    # Overall
    b_overall = baseline.get("overall", {})
    n_overall = new.get("overall", {})

    b_avg = b_overall.get("avg_score", 0)
    n_avg = n_overall.get("avg_score", 0)
    delta = n_avg - b_avg
    direction = "+" if delta > 0 else ""

    print(f"\nOverall Score: {b_avg:.1f} -> {n_avg:.1f} ({direction}{delta:.1f})")
    print(
        f"Pass Rate: {b_overall.get('pass_rate', 0):.1f}% -> "
        f"{n_overall.get('pass_rate', 0):.1f}%"
    )
    print(
        f"Failures: {b_overall.get('failures', 0)} -> "
        f"{n_overall.get('failures', 0)}"
    )

    # Category comparison
    print("\n--- Category Deltas ---")
    all_cats = set(
        list(baseline.get("categories", {}).keys())
        + list(new.get("categories", {}).keys())
    )
    for cat in sorted(all_cats):
        b_cat = baseline.get("categories", {}).get(cat, {})
        n_cat = new.get("categories", {}).get(cat, {})
        b_score = b_cat.get("avg_score", 0)
        n_score = n_cat.get("avg_score", 0)
        d = n_score - b_score
        sign = "+" if d > 0 else ""
        emoji = "^" if d > 5 else ("v" if d < -5 else "=")
        print(f"  {cat:20s}: {b_score:5.1f} -> {n_score:5.1f} ({sign}{d:.1f}) [{emoji}]")

    # Dimension comparison
    print("\n--- Dimension Deltas ---")
    all_dims = set(
        list(baseline.get("dimensions", {}).keys())
        + list(new.get("dimensions", {}).keys())
    )
    for dim in sorted(all_dims):
        b_dim = baseline.get("dimensions", {}).get(dim, {})
        n_dim = new.get("dimensions", {}).get(dim, {})
        b_score = b_dim.get("avg_score", 0)
        n_score = n_dim.get("avg_score", 0)
        d = n_score - b_score
        sign = "+" if d > 0 else ""
        print(f"  {dim:20s}: {b_score:5.1f} -> {n_score:5.1f} ({sign}{d:.1f})")

    # New failures / fixed
    b_fails = {f["test_id"] for f in baseline.get("failing_tests", [])}
    n_fails = {f["test_id"] for f in new.get("failing_tests", [])}

    fixed = b_fails - n_fails
    regressed = n_fails - b_fails

    if fixed:
        print(f"\nFixed ({len(fixed)}):")
        for tid in sorted(fixed):
            print(f"  + {tid}")
    if regressed:
        print(f"\nRegressed ({len(regressed)}):")
        for tid in sorted(regressed):
            print(f"  - {tid}")


def main():
    parser = argparse.ArgumentParser(description="Eval Results Analyzer")
    parser.add_argument(
        "--compare", action="store_true",
        help="Compare two eval runs",
    )
    parser.add_argument("--baseline", "-B", help="Baseline run name/path")
    parser.add_argument("--new", "-N", help="New run name/path")
    args = parser.parse_args()

    if args.compare:
        if not args.baseline or not args.new:
            print("Error: --compare requires --baseline (-B) and --new (-N)")
            sys.exit(1)
        compare_runs(args.baseline, args.new)
    else:
        analyze_latest()


if __name__ == "__main__":
    main()
