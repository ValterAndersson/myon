#!/usr/bin/env python3
"""
Eval Results Analyzer — reads JSONL eval results and produces actionable insights.

Features:
- Weakest dimensions (ranked by avg score)
- Most common issues (counted across all tests)
- Category breakdown (avg score per category)
- Failing tests (score < 75) with identified root cause
- Compare mode: --compare file1.jsonl file2.jsonl shows delta per dimension/category

Usage:
    # Analyze latest eval run
    python3 tests/eval/analyze.py

    # Analyze specific run
    python3 tests/eval/analyze.py --file tests/eval/results/eval_20240101_120000.jsonl

    # Compare two runs
    python3 tests/eval/analyze.py --compare tests/eval/results/eval_001.jsonl tests/eval/results/eval_002.jsonl
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional


RESULTS_DIR = Path(__file__).resolve().parent / "results"


def load_results(filepath: Path) -> List[Dict]:
    """Load results from JSONL file."""
    results = []
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if line:
                results.append(json.loads(line))
    return results


def find_latest_results() -> Optional[Path]:
    """Find the most recent eval results JSONL file."""
    jsonl_files = sorted(RESULTS_DIR.glob("eval_*.jsonl"), reverse=True)
    # Exclude summary files
    jsonl_files = [f for f in jsonl_files if "_summary" not in f.name]
    return jsonl_files[0] if jsonl_files else None


def analyze(results: List[Dict]) -> Dict:
    """Analyze eval results and return structured analysis."""

    # --- Overall scores ---
    scores = [r["overall_score"] for r in results if r.get("overall_score") is not None]
    overall = {
        "avg": sum(scores) / len(scores) if scores else 0,
        "median": sorted(scores)[len(scores) // 2] if scores else 0,
        "min": min(scores) if scores else 0,
        "max": max(scores) if scores else 0,
        "pass_rate": len([s for s in scores if s >= 75]) / len(scores) * 100 if scores else 0,
        "total": len(results),
        "scored": len(scores),
    }

    # --- Dimension analysis ---
    dim_scores = {}  # dim_name -> [scores]
    dim_sub_scores = {}  # dim_name -> sub_name -> [scores]
    for r in results:
        judge = r.get("judge")
        if not judge:
            continue
        for dim_name, dim_data in judge.get("dimensions", {}).items():
            dim_scores.setdefault(dim_name, []).append(dim_data.get("score", 0))
            for sub_name, sub_val in dim_data.get("sub_scores", {}).items():
                key = f"{dim_name}.{sub_name}"
                dim_sub_scores.setdefault(key, []).append(sub_val)

    dimensions = []
    for dim_name, scores_list in dim_scores.items():
        avg = sum(scores_list) / len(scores_list) if scores_list else 0
        dimensions.append({
            "name": dim_name,
            "avg_score": round(avg, 1),
            "min_score": round(min(scores_list), 1) if scores_list else 0,
            "count": len(scores_list),
        })
    # Sort by avg_score ascending (weakest first)
    dimensions.sort(key=lambda d: d["avg_score"])

    # Sub-score breakdown
    sub_dimensions = []
    for key, scores_list in dim_sub_scores.items():
        avg = sum(scores_list) / len(scores_list) if scores_list else 0
        dim, sub = key.split(".", 1)
        sub_dimensions.append({
            "dimension": dim,
            "sub_score": sub,
            "avg": round(avg, 1),
            "count": len(scores_list),
        })
    sub_dimensions.sort(key=lambda d: d["avg"])

    # --- Category breakdown ---
    cat_data = {}
    for r in results:
        cat = r.get("category", "unknown")
        cat_data.setdefault(cat, {"scores": [], "count": 0})
        cat_data[cat]["count"] += 1
        if r.get("overall_score") is not None:
            cat_data[cat]["scores"].append(r["overall_score"])

    categories = []
    for cat, data in cat_data.items():
        cat_scores = data["scores"]
        categories.append({
            "category": cat,
            "avg_score": round(sum(cat_scores) / len(cat_scores), 1) if cat_scores else 0,
            "min_score": round(min(cat_scores), 1) if cat_scores else 0,
            "count": data["count"],
            "failures": len([s for s in cat_scores if s < 75]),
        })
    categories.sort(key=lambda c: c["avg_score"])

    # --- Most common issues ---
    all_issues = []
    for r in results:
        judge = r.get("judge")
        if judge:
            all_issues.extend(judge.get("deterministic_issues", []))
            all_issues.extend(judge.get("llm_issues", []))

    issue_counts = {}
    for issue in all_issues:
        # Normalize: strip details after first colon for grouping
        key = issue.split(":")[0].strip() if ":" in issue else issue
        # Further normalize dimension prefixes
        if key.startswith("[") and "]" in key:
            key = key[key.index("]") + 1:].strip()
        issue_counts[key] = issue_counts.get(key, 0) + 1

    common_issues = sorted(issue_counts.items(), key=lambda x: -x[1])

    # --- Failing tests (score < 75) ---
    failing = []
    for r in results:
        if r.get("overall_score") is not None and r["overall_score"] < 75:
            judge = r.get("judge", {}) or {}
            issues = (
                judge.get("deterministic_issues", [])
                + judge.get("llm_issues", [])
            )

            # Classify root cause
            root_cause = _classify_failure(r, issues)

            failing.append({
                "test_id": r["test_id"],
                "score": round(r["overall_score"], 1),
                "category": r.get("category", "unknown"),
                "query": r.get("query", ""),
                "root_cause": root_cause,
                "issues": issues[:5],
                "tools_expected": r.get("expected_tools", []),
                "tools_used": r.get("tools_used", []),
            })
    failing.sort(key=lambda f: f["score"])

    # --- Timing ---
    durations = [r.get("duration_s", 0) for r in results if r.get("duration_s")]
    timing = {
        "avg_s": round(sum(durations) / len(durations), 1) if durations else 0,
        "max_s": round(max(durations), 1) if durations else 0,
        "total_s": round(sum(durations), 1),
    }

    return {
        "overall": overall,
        "dimensions_weakest_first": dimensions,
        "sub_dimensions_weakest_first": sub_dimensions[:10],
        "categories_weakest_first": categories,
        "common_issues": [{"issue": k, "count": v} for k, v in common_issues[:15]],
        "failing_tests": failing,
        "timing": timing,
    }


def _classify_failure(result: Dict, issues: List[str]) -> str:
    """Classify the root cause of a test failure."""
    tools_expected = set(result.get("expected_tools", []))
    tools_used = set(result.get("tools_used", []))
    issue_text = " ".join(issues).lower()

    # Check for tool selection issues
    if tools_expected and not tools_used:
        return "instruction: agent used no tools when tools were expected"
    if tools_expected and tools_used and not tools_expected & tools_used:
        return "instruction: wrong tools selected"
    if tools_expected - tools_used:
        missing = tools_expected - tools_used
        return f"instruction: missing tools {missing}"

    # Check for safety issues
    if "hallucinated" in issue_text or "invented" in issue_text:
        return "instruction: hallucinated data"
    if "leaked" in issue_text or "id" in issue_text:
        return "safety: information leakage"

    # Check for quality issues
    if "too long" in issue_text or "line" in issue_text:
        return "instruction: response too verbose"
    if "actionab" in issue_text:
        return "instruction: missing actionable recommendation"

    # Check for persona issues
    if "over-coaching" in issue_text or "lecture" in issue_text:
        return "instruction: over-coaching"
    if "motivational" in issue_text or "hype" in issue_text:
        return "instruction: wrong tone"

    # Check for errors
    if result.get("errors"):
        return "system: runtime error"

    return "unknown"


# ---------------------------------------------------------------------------
# Compare Mode
# ---------------------------------------------------------------------------

def compare(results_a: List[Dict], results_b: List[Dict], label_a: str, label_b: str) -> Dict:
    """Compare two eval runs and compute deltas."""
    analysis_a = analyze(results_a)
    analysis_b = analyze(results_b)

    # Overall delta
    overall_delta = {
        "avg_score": round(
            analysis_b["overall"]["avg"] - analysis_a["overall"]["avg"], 1
        ),
        "pass_rate": round(
            analysis_b["overall"]["pass_rate"] - analysis_a["overall"]["pass_rate"], 1
        ),
        label_a: {
            "avg": analysis_a["overall"]["avg"],
            "pass_rate": analysis_a["overall"]["pass_rate"],
        },
        label_b: {
            "avg": analysis_b["overall"]["avg"],
            "pass_rate": analysis_b["overall"]["pass_rate"],
        },
    }

    # Dimension deltas
    dims_a = {d["name"]: d["avg_score"] for d in analysis_a["dimensions_weakest_first"]}
    dims_b = {d["name"]: d["avg_score"] for d in analysis_b["dimensions_weakest_first"]}
    dimension_deltas = {}
    for dim in set(list(dims_a.keys()) + list(dims_b.keys())):
        a_val = dims_a.get(dim, 0)
        b_val = dims_b.get(dim, 0)
        dimension_deltas[dim] = {
            label_a: a_val,
            label_b: b_val,
            "delta": round(b_val - a_val, 1),
        }

    # Category deltas
    cats_a = {c["category"]: c["avg_score"] for c in analysis_a["categories_weakest_first"]}
    cats_b = {c["category"]: c["avg_score"] for c in analysis_b["categories_weakest_first"]}
    category_deltas = {}
    for cat in set(list(cats_a.keys()) + list(cats_b.keys())):
        a_val = cats_a.get(cat, 0)
        b_val = cats_b.get(cat, 0)
        category_deltas[cat] = {
            label_a: a_val,
            label_b: b_val,
            "delta": round(b_val - a_val, 1),
        }

    # Per-test deltas (for tests present in both)
    scores_a = {r["test_id"]: r.get("overall_score") or 0 for r in results_a}
    scores_b = {r["test_id"]: r.get("overall_score") or 0 for r in results_b}
    common_tests = set(scores_a.keys()) & set(scores_b.keys())

    test_deltas = []
    for test_id in sorted(common_tests):
        delta = (scores_b.get(test_id, 0) or 0) - (scores_a.get(test_id, 0) or 0)
        if abs(delta) >= 5:  # Only show meaningful changes
            test_deltas.append({
                "test_id": test_id,
                label_a: scores_a.get(test_id, 0),
                label_b: scores_b.get(test_id, 0),
                "delta": round(delta, 1),
            })
    test_deltas.sort(key=lambda t: t["delta"])

    # Regressions and improvements
    regressions = [t for t in test_deltas if t["delta"] < -5]
    improvements = [t for t in test_deltas if t["delta"] > 5]

    return {
        "overall": overall_delta,
        "dimensions": dimension_deltas,
        "categories": category_deltas,
        "regressions": regressions,
        "improvements": improvements,
        "test_deltas": test_deltas,
    }


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def print_analysis(analysis: Dict, filepath: str = None):
    """Print analysis to console."""
    print("=" * 72)
    print("EVAL ANALYSIS")
    if filepath:
        print(f"File: {filepath}")
    print("=" * 72)

    ov = analysis["overall"]
    print(f"\nOverall: {ov['avg']:.1f}/100 avg | "
          f"Pass rate: {ov['pass_rate']:.1f}% | "
          f"Range: {ov['min']:.1f}-{ov['max']:.1f} | "
          f"{ov['scored']}/{ov['total']} scored")

    print(f"\n{'─' * 72}")
    print("WEAKEST DIMENSIONS (ranked)")
    print(f"{'─' * 72}")
    for d in analysis["dimensions_weakest_first"]:
        bar = "█" * int(d["avg_score"] / 5) + "░" * (20 - int(d["avg_score"] / 5))
        print(f"  {d['name']:18s} {bar} {d['avg_score']:5.1f} "
              f"(min: {d['min_score']:.1f})")

    if analysis.get("sub_dimensions_weakest_first"):
        print(f"\n  Weakest Sub-Scores:")
        for sd in analysis["sub_dimensions_weakest_first"][:8]:
            print(f"    {sd['dimension']}.{sd['sub_score']:30s} {sd['avg']:5.1f}")

    print(f"\n{'─' * 72}")
    print("CATEGORY BREAKDOWN (weakest first)")
    print(f"{'─' * 72}")
    for c in analysis["categories_weakest_first"]:
        bar = "█" * int(c["avg_score"] / 5) + "░" * (20 - int(c["avg_score"] / 5))
        print(f"  {c['category']:18s} {bar} {c['avg_score']:5.1f} "
              f"({c['count']} cases, {c['failures']} failures)")

    if analysis["common_issues"]:
        print(f"\n{'─' * 72}")
        print("MOST COMMON ISSUES")
        print(f"{'─' * 72}")
        for issue in analysis["common_issues"][:10]:
            print(f"  [{issue['count']:2d}x] {issue['issue']}")

    if analysis["failing_tests"]:
        print(f"\n{'─' * 72}")
        print(f"FAILING TESTS ({len(analysis['failing_tests'])} total)")
        print(f"{'─' * 72}")
        for f in analysis["failing_tests"]:
            print(f"\n  {f['test_id']} ({f['category']}) — score: {f['score']:.1f}")
            print(f"    Query: {f['query'][:60]}")
            print(f"    Root cause: {f['root_cause']}")
            if f.get("tools_expected") or f.get("tools_used"):
                print(f"    Tools expected: {f.get('tools_expected', [])}")
                print(f"    Tools used: {f.get('tools_used', [])}")
            for issue in f["issues"][:3]:
                print(f"    → {issue}")

    timing = analysis["timing"]
    print(f"\nTiming: {timing['avg_s']}s avg, {timing['max_s']}s max, "
          f"{timing['total_s']}s total")


def print_comparison(comparison: Dict, label_a: str, label_b: str):
    """Print comparison results to console."""
    print("=" * 72)
    print(f"EVAL COMPARISON: {label_a} → {label_b}")
    print("=" * 72)

    ov = comparison["overall"]
    delta_sign = "+" if ov["avg_score"] >= 0 else ""
    print(f"\nOverall: {delta_sign}{ov['avg_score']:.1f} "
          f"({ov[label_a]['avg']:.1f} → {ov[label_b]['avg']:.1f})")
    pr_sign = "+" if ov["pass_rate"] >= 0 else ""
    print(f"Pass rate: {pr_sign}{ov['pass_rate']:.1f}% "
          f"({ov[label_a]['pass_rate']:.1f}% → {ov[label_b]['pass_rate']:.1f}%)")

    print(f"\n{'─' * 72}")
    print("DIMENSION DELTAS")
    print(f"{'─' * 72}")
    for dim, data in comparison["dimensions"].items():
        sign = "+" if data["delta"] >= 0 else ""
        indicator = "▲" if data["delta"] > 0 else ("▼" if data["delta"] < 0 else "─")
        print(f"  {dim:18s} {data[label_a]:5.1f} → {data[label_b]:5.1f} "
              f"({sign}{data['delta']:.1f}) {indicator}")

    print(f"\n{'─' * 72}")
    print("CATEGORY DELTAS")
    print(f"{'─' * 72}")
    for cat, data in comparison["categories"].items():
        sign = "+" if data["delta"] >= 0 else ""
        indicator = "▲" if data["delta"] > 0 else ("▼" if data["delta"] < 0 else "─")
        print(f"  {cat:18s} {data[label_a]:5.1f} → {data[label_b]:5.1f} "
              f"({sign}{data['delta']:.1f}) {indicator}")

    if comparison["regressions"]:
        print(f"\n{'─' * 72}")
        print(f"REGRESSIONS ({len(comparison['regressions'])})")
        print(f"{'─' * 72}")
        for t in comparison["regressions"]:
            print(f"  {t['test_id']:18s} {t[label_a]:5.1f} → {t[label_b]:5.1f} "
                  f"({t['delta']:.1f}) ▼")

    if comparison["improvements"]:
        print(f"\n{'─' * 72}")
        print(f"IMPROVEMENTS ({len(comparison['improvements'])})")
        print(f"{'─' * 72}")
        for t in sorted(comparison["improvements"], key=lambda x: -x["delta"]):
            print(f"  {t['test_id']:18s} {t[label_a]:5.1f} → {t[label_b]:5.1f} "
                  f"(+{t['delta']:.1f}) ▲")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Eval Results Analyzer")
    parser.add_argument(
        "--file",
        help="Path to eval JSONL file (default: latest)",
    )
    parser.add_argument(
        "--compare",
        nargs=2,
        metavar=("BASELINE", "NEW"),
        help="Compare two eval runs (BASELINE NEW)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON instead of formatted text",
    )
    args = parser.parse_args()

    if args.compare:
        # Compare mode
        path_a, path_b = Path(args.compare[0]), Path(args.compare[1])
        if not path_a.exists():
            print(f"Error: File not found: {path_a}")
            sys.exit(1)
        if not path_b.exists():
            print(f"Error: File not found: {path_b}")
            sys.exit(1)

        results_a = load_results(path_a)
        results_b = load_results(path_b)
        label_a = path_a.stem.replace("eval_", "")
        label_b = path_b.stem.replace("eval_", "")

        comparison = compare(results_a, results_b, label_a, label_b)

        if args.json:
            print(json.dumps(comparison, indent=2))
        else:
            print_comparison(comparison, label_a, label_b)

    else:
        # Analyze mode
        if args.file:
            filepath = Path(args.file)
        else:
            filepath = find_latest_results()
            if not filepath:
                print("Error: No eval results found. Run `make eval` first.")
                sys.exit(1)

        if not filepath.exists():
            print(f"Error: File not found: {filepath}")
            sys.exit(1)

        results = load_results(filepath)
        analysis = analyze(results)

        if args.json:
            print(json.dumps(analysis, indent=2))
        else:
            print_analysis(analysis, str(filepath))


if __name__ == "__main__":
    main()
