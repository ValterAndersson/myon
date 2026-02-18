#!/usr/bin/env python3
"""
Training Analyst Eval Runner — tests recommendation quality end-to-end.

Calls the analyzer LLM directly with synthetic training data, simulates
the JS recommendation processing, then routes the final recommendation
document to the judge for scoring.

Usage:
    python3 tests/eval/runner.py                     # Full eval suite
    python3 tests/eval/runner.py --filter category=auto_pilot
    python3 tests/eval/runner.py --id ap_001
    python3 tests/eval/runner.py --no-judge           # Deterministic checks only

Environment:
    GOOGLE_APPLICATION_CREDENTIALS or GCP_SA_KEY must be set for Vertex AI.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure parent packages are importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from tests.eval.test_cases import (
    ALL_CASES, RecommendationTestCase, get_cases,
)
from tests.eval.judge import JudgeResult, score_recommendation

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

RESULTS_DIR = Path(__file__).resolve().parent / "results"


# ---------------------------------------------------------------------------
# Analyzer caller — calls LLM directly without Firestore
# ---------------------------------------------------------------------------

ANALYZER_MODEL = "gemini-2.5-pro"
ANALYZER_PROJECT = "myon-53d85"
ANALYZER_LOCATION = "us-central1"

# Token cache — gcloud tokens last 60 min, refresh at 50 min
_token_cache: Dict[str, Any] = {"token": None, "expires_at": 0}


def _get_gcloud_token() -> str:
    """Get GCP access token from gcloud CLI user credentials.

    Caches token for 50 minutes (gcloud tokens expire at 60 min).
    Uses gcloud CLI instead of SA key because the SA key lacks
    aiplatform.endpoints.predict permission.
    """
    import subprocess

    now = time.time()
    if _token_cache["token"] and now < _token_cache["expires_at"]:
        return _token_cache["token"]

    result = subprocess.run(
        ["gcloud", "auth", "print-access-token"],
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode == 0 and result.stdout.strip():
        _token_cache["token"] = result.stdout.strip()
        _token_cache["expires_at"] = now + 3000  # 50 min
        return _token_cache["token"]
    raise RuntimeError("Cannot obtain GCP access token. Run: gcloud auth login")


def _call_analyzer_llm(system_prompt: str, user_prompt: str) -> Dict[str, Any]:
    """Call analyzer LLM via Vertex AI REST API with gcloud user credentials.

    Retries once on timeout/5xx errors.
    """
    import re
    import requests as req

    url = (
        f"https://{ANALYZER_LOCATION}-aiplatform.googleapis.com/v1/"
        f"projects/{ANALYZER_PROJECT}/locations/{ANALYZER_LOCATION}/"
        f"publishers/google/models/{ANALYZER_MODEL}:generateContent"
    )

    payload = {
        "contents": [
            {"role": "user", "parts": [{"text": system_prompt.strip()}]},
            {"role": "user", "parts": [{"text": user_prompt.strip()}]},
        ],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
        },
    }

    last_err = None
    for attempt in range(2):
        try:
            token = _get_gcloud_token()
            resp = req.post(
                url, json=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                timeout=(10, 90),  # (connect, read) timeouts
            )
            resp.raise_for_status()
            data = resp.json()
            break
        except (req.exceptions.Timeout, req.exceptions.ConnectionError) as e:
            last_err = e
            if attempt == 0:
                # Retry once after brief pause
                time.sleep(3)
                _token_cache["token"] = None  # Force token refresh
                continue
            raise
        except req.exceptions.HTTPError as e:
            if resp.status_code >= 500 and attempt == 0:
                last_err = e
                time.sleep(3)
                continue
            raise
    else:
        raise last_err

    candidates = data.get("candidates", [])
    if not candidates:
        raise ValueError("Analyzer LLM returned no candidates")

    # Check for truncation
    finish_reason = candidates[0].get("finishReason", "")
    if finish_reason == "MAX_TOKENS":
        raise ValueError("Analyzer response truncated (MAX_TOKENS)")

    parts = candidates[0].get("content", {}).get("parts", [])
    text = ""
    for part in parts:
        if part.get("thought"):
            continue
        if "text" in part:
            text += part["text"]

    text = text.strip()
    if not text:
        raise ValueError("Analyzer LLM returned empty text")

    # Strip markdown fences if present
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```\s*$", "", text)

    return json.loads(text)


def call_analyzer(
    analyzer_type: str,
    training_data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Call the analyzer LLM directly with synthetic training data.

    Uses Vertex AI REST API with gcloud user credentials (the SA key
    lacks aiplatform.endpoints.predict permission). Extracts the system
    prompt from the analyzer class but bypasses Firestore entirely.

    Returns the parsed LLM response dict.
    """
    if analyzer_type == "post_workout":
        from app.analyzers.post_workout import PostWorkoutAnalyzer
        pw = PostWorkoutAnalyzer()
        system_prompt = pw._get_system_prompt()
    elif analyzer_type == "weekly_review":
        from app.analyzers.weekly_review import WeeklyReviewAnalyzer
        wr = WeeklyReviewAnalyzer()
        system_prompt = wr._get_system_prompt()
    else:
        raise ValueError(f"Unknown analyzer type: {analyzer_type}")

    user_prompt = json.dumps(training_data, indent=2, default=str)
    return _call_analyzer_llm(system_prompt, user_prompt)


# ---------------------------------------------------------------------------
# Recommendation processing — Python port of process-recommendations.js
# ---------------------------------------------------------------------------

def round_to_nearest(value: float, step: float) -> float:
    """Round value to nearest step."""
    return round(value / step) * step


def compute_progression_weight(
    current_weight: float,
    rec_type: str,
    suggested_weight: Optional[float] = None,
) -> float:
    """
    Compute new weight. Python port of computeProgressionWeight from
    process-recommendations.js.
    """
    if suggested_weight is not None:
        return suggested_weight
    if rec_type in ("deload", "swap"):
        step = 2.5 if current_weight > 40 else 1.25
        return round_to_nearest(current_weight * 0.9, step)
    increment = 0.025 if current_weight > 40 else 0.05
    step = 2.5 if current_weight > 40 else 1.25
    new_weight = round_to_nearest(current_weight * (1 + increment), step)
    # If rounding killed the increment, bump by one step
    if new_weight <= current_weight:
        new_weight = current_weight + step
    new_weight = min(new_weight, current_weight + 5)
    return new_weight if new_weight > 0 else 0


def compute_changes_for_template(
    template_exercises: List[Dict],
    exercise_name: str,
    rec_type: str,
    suggested_weight: Optional[float] = None,
) -> tuple:
    """
    Compute changes for a template-scoped recommendation.
    Returns (exercise_index, changes_list).
    """
    ex_key = exercise_name.strip().lower()
    for idx, ex in enumerate(template_exercises):
        tmpl_name = ex.get("name", "").strip().lower()
        # Fuzzy match: exact or substring in either direction
        # (LLM may return "Bench Press" vs template's "Bench Press (Barbell)")
        if tmpl_name == ex_key or ex_key in tmpl_name or tmpl_name in ex_key:
            changes = []
            for set_idx, s in enumerate(ex.get("sets", [])):
                current = s.get("weight_kg", 0)
                new_weight = compute_progression_weight(
                    current, rec_type, suggested_weight
                )
                if new_weight != current and new_weight > 0:
                    changes.append({
                        "path": f"exercises[{idx}].sets[{set_idx}].weight_kg",
                        "from": current,
                        "to": new_weight,
                        "rationale": f"{rec_type}: {current}kg -> {new_weight}kg",
                    })
            return idx, changes
    return -1, []


def build_summary(
    rec: Dict, scope: str, state: str,
    change: Optional[Dict], template_name: Optional[str],
) -> str:
    """
    Build contextual summary. Python port of the evolved buildSummary
    from process-recommendations.js.
    """
    name = rec.get("target", "")
    from_val = change.get("from") if change else None
    to_val = change.get("to") if change else None
    rec_type = rec.get("type", "")
    is_rep_change = change and change.get("path") == "reps"
    unit = "reps" if is_rep_change else "kg"

    if scope == "template" and state == "applied":
        if rec_type == "progression" and from_val is not None:
            return f"Applied: {name} {from_val}{unit} -> {to_val}{unit}"
        if rec_type == "deload" and to_val is not None:
            return f"Reduced {name} to {to_val}{unit}"
        if rec_type == "volume_adjust":
            return f"Volume adjustment applied for {name}"
        return f"Applied {rec_type} for {name}"

    if scope == "template" and state == "pending_review":
        if rec_type == "progression" and to_val is not None:
            return f"Try {to_val} {unit} on {name}" if is_rep_change else f"Try {to_val}kg on {name}"
        if rec_type == "deload" and to_val is not None:
            return f"Consider reducing {name} to {to_val}{unit}"
        if rec_type == "volume_adjust":
            return f"Consider adjusting {name} volume"
        return f"{rec_type} for {name}"

    if scope == "exercise":
        if rec_type == "progression" and to_val is not None:
            if is_rep_change:
                return f"Ready to progress {name}: try {to_val} reps"
            return f"Ready to progress {name} to {to_val}kg"
        if rec_type == "deload" and to_val is not None:
            return f"{name}: consider a lighter session at {to_val}{unit}"
        if rec_type == "volume_adjust":
            return f"{name}: volume may need attention"
        return f"{rec_type} for {name}"

    return f"{rec_type} for {name}"


def build_rationale(
    rec: Dict, scope: str, state: str,
    template_name: Optional[str],
) -> str:
    """
    Build contextual rationale. Python port of the evolved buildRationale
    from process-recommendations.js.
    """
    reasoning = rec.get("reasoning") or rec.get("rationale", "")
    signals = rec.get("signals", [])
    signals_text = ". ".join(signals) if signals else ""

    if scope == "template" and state == "applied":
        suffix = f" Updated in {template_name}." if template_name else ""
        return f"{reasoning}{suffix}"

    if scope == "template" and state == "pending_review":
        prefix = f"{signals_text}. " if signals_text else ""
        suffix = f" Accepting updates {template_name}." if template_name else ""
        return f"{prefix}{reasoning}{suffix}"

    if scope == "exercise":
        prefix = f"{signals_text}. " if signals_text else ""
        return (
            f"{prefix}{reasoning} "
            f"Use this in your next workout or add it to a template."
        )

    return reasoning


def simulate_recommendation_processing(
    analyzer_output: Dict[str, Any],
    user_state: Dict[str, Any],
    analyzer_type: str,
    training_data: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Simulate the full recommendation processing pipeline.
    Python port of processActionableRecommendations from process-recommendations.js.

    Args:
        training_data: Original test case training_data (needed for exercise-scoped
            cases where we look up current weight from workout exercises).

    Returns list of final recommendation documents (the `agent_recommendations` shape).
    """
    auto_pilot = user_state.get("auto_pilot_enabled", False)
    has_routine = user_state.get("activeRoutineId") is not None
    template_name = user_state.get("template_name")
    template_exercises = user_state.get("template_exercises", [])

    # Extract actionable recommendations based on analyzer type
    actionable = []

    if analyzer_type == "post_workout":
        recs = analyzer_output.get("recommendations", [])
        for rec in recs:
            conf = rec.get("confidence", 0)
            rtype = rec.get("type", "")
            if conf >= 0.7 and rtype in ("progression", "deload", "swap", "volume_adjust"):
                actionable.append({
                    "type": rtype,
                    "target": rec.get("target", ""),
                    "suggestedWeight": rec.get("suggested_weight"),
                    "rationale": rec.get("action", ""),
                    "reasoning": rec.get("reasoning", ""),
                    "signals": rec.get("signals", []),
                    "confidence": conf,
                })
    elif analyzer_type == "weekly_review":
        for pc in analyzer_output.get("progression_candidates", []):
            actionable.append({
                "type": "progression",
                "target": pc.get("exercise_name", ""),
                "suggestedWeight": pc.get("suggested_weight"),
                "rationale": pc.get("rationale", ""),
                "reasoning": pc.get("reasoning", ""),
                "signals": pc.get("signals", []),
                "confidence": pc.get("confidence", 0.8),
            })
        for se in analyzer_output.get("stalled_exercises", []):
            action = se.get("suggested_action", "deload").lower()
            # Map stall actions to recommendation types
            if action in ("deload", "swap"):
                rtype = "deload"
            elif action in ("increase_weight", "progress", "progression",
                            "increase weight", "increase_load"):
                rtype = "progression"
            else:
                rtype = "volume_adjust"
            actionable.append({
                "type": rtype,
                "target": se.get("exercise_name", ""),
                "suggestedWeight": None,
                "rationale": se.get("rationale", ""),
                "reasoning": se.get("reasoning", ""),
                "signals": se.get("signals", []),
                "confidence": 0.7,
            })
        # Extract volume recommendations from muscle_balance
        for mb in analyzer_output.get("muscle_balance", []):
            status = mb.get("status", "")
            if status in ("undertrained", "overtrained"):
                group = mb.get("muscle_group", "")
                sets = mb.get("weekly_sets", 0)
                trend = mb.get("trend", "stable")
                actionable.append({
                    "type": "volume_adjust",
                    "target": group,
                    "suggestedWeight": None,
                    "rationale": f"{group} at {sets} sets/week ({status})",
                    "reasoning": (
                        f"{group} is {status} at {sets} sets/week. "
                        f"{'Consider adding more direct work.' if status == 'undertrained' else 'Consider reducing volume to allow recovery.'}"
                    ),
                    "signals": [
                        f"{group}: {sets} sets/week",
                        f"status: {status}",
                        f"trend: {trend}",
                    ],
                    "confidence": 0.75,
                })

    if not actionable:
        return []

    # Process each recommendation
    results = []
    scope = "template" if has_routine else "exercise"
    state = "applied" if (has_routine and auto_pilot) else "pending_review"

    for rec in actionable:
        exercise_name = rec["target"]

        # Volume adjustments don't need weight changes — they're observational
        if rec["type"] == "volume_adjust":
            changes = [{
                "path": "volume",
                "from": None,
                "to": None,
                "rationale": rec.get("rationale", ""),
            }]
            first_change = changes[0]
            summary = build_summary(rec, scope, state, first_change, template_name)
            rationale = build_rationale(rec, scope, state, template_name)

            rec_doc = {
                "scope": scope,
                "state": state,
                "target": {
                    "template_id": user_state.get("template_id"),
                    "template_name": template_name,
                    "routine_id": user_state.get("activeRoutineId"),
                    "exercise_name": exercise_name if scope == "exercise" else None,
                },
                "recommendation": {
                    "type": rec["type"],
                    "changes": changes,
                    "summary": summary,
                    "rationale": rationale,
                    "confidence": rec["confidence"],
                    "signals": rec.get("signals", []),
                },
            }
            results.append(rec_doc)
            continue

        # Compute changes
        if has_routine and template_exercises:
            ex_idx, changes = compute_changes_for_template(
                template_exercises, exercise_name,
                rec["type"], rec.get("suggestedWeight"),
            )
            if not changes:
                continue
        else:
            # Exercise-scoped: derive from original training data workout
            td = training_data or {}
            workout_exercises = (
                td.get("workout", {}).get("exercises", [])
            )
            current_weight = 0
            ex_key = exercise_name.strip().lower()
            for wex in workout_exercises:
                wex_name = wex.get("name", "").strip().lower()
                # Fuzzy match: exact or substring in either direction
                if wex_name == ex_key or ex_key in wex_name or wex_name in ex_key:
                    current_weight = wex.get("top_weight_kg", 0) or 0
                    break

            if current_weight <= 0:
                # Bodyweight exercise: produce rep-based change instead
                matched_ex = None
                for wex in workout_exercises:
                    wex_name = wex.get("name", "").strip().lower()
                    if wex_name == ex_key or ex_key in wex_name or wex_name in ex_key:
                        matched_ex = wex
                        break
                if matched_ex:
                    current_reps = int(matched_ex.get("rep_range", "0") or "0")
                    if current_reps > 0:
                        new_reps = current_reps + 2
                        changes = [{
                            "path": "reps",
                            "from": current_reps,
                            "to": new_reps,
                            "rationale": f"{rec['type']}: {current_reps} -> {new_reps} reps",
                        }]
                    else:
                        continue
                else:
                    continue
            else:
                new_weight = compute_progression_weight(
                    current_weight, rec["type"], rec.get("suggestedWeight"),
                )
                if new_weight == current_weight or new_weight <= 0:
                    continue

                changes = [{
                    "path": "weight_kg",
                    "from": current_weight,
                    "to": new_weight,
                    "rationale": f"{rec['type']}: {current_weight}kg -> {new_weight}kg",
                }]

        first_change = changes[0] if changes else None
        summary = build_summary(rec, scope, state, first_change, template_name)
        rationale = build_rationale(rec, scope, state, template_name)

        rec_doc = {
            "scope": scope,
            "state": state,
            "target": {
                "template_id": user_state.get("template_id"),
                "template_name": template_name,
                "routine_id": user_state.get("activeRoutineId"),
                "exercise_name": exercise_name if scope == "exercise" else None,
            },
            "recommendation": {
                "type": rec["type"],
                "changes": changes,
                "summary": summary,
                "rationale": rationale,
                "confidence": rec["confidence"],
                "signals": rec.get("signals", []),
            },
        }
        results.append(rec_doc)

    return results


# ---------------------------------------------------------------------------
# Eval Runner
# ---------------------------------------------------------------------------

def run_single_case(
    case: RecommendationTestCase,
    skip_judge: bool = False,
) -> Dict:
    """Run a single test case through the full pipeline."""
    t0 = time.time()
    errors = []

    # 1. Call analyzer
    try:
        analyzer_output = call_analyzer(case.analyzer_type, case.training_data)
    except Exception as e:
        elapsed = time.time() - t0
        return {
            "test_id": case.id,
            "category": case.category,
            "errors": [f"Analyzer error: {e}"],
            "overall_score": 0,
            "duration_s": round(elapsed, 1),
            "timestamp": datetime.utcnow().isoformat(),
        }

    # 2. Simulate recommendation processing
    try:
        rec_docs = simulate_recommendation_processing(
            analyzer_output, case.user_state, case.analyzer_type,
            training_data=case.training_data,
        )
    except Exception as e:
        elapsed = time.time() - t0
        return {
            "test_id": case.id,
            "category": case.category,
            "analyzer_output": analyzer_output,
            "errors": [f"Processing error: {e}"],
            "overall_score": 0,
            "duration_s": round(elapsed, 1),
            "timestamp": datetime.utcnow().isoformat(),
        }

    # 3. Score with judge
    judge_result = None
    if rec_docs and not skip_judge:
        try:
            judge_result = score_recommendation(
                test_case=case,
                rec_docs=rec_docs,
                analyzer_output=analyzer_output,
            )
        except Exception as e:
            judge_result = JudgeResult(
                test_id=case.id,
                overall_score=0,
                deterministic_issues=[f"Judge error: {e}"],
            )
    elif rec_docs and skip_judge:
        # Deterministic checks only (no LLM judge)
        from tests.eval.judge import run_deterministic_checks
        det_issues, det_penalty = run_deterministic_checks(rec_docs, case)
        judge_result = JudgeResult(
            test_id=case.id,
            overall_score=max(0, 80 - det_penalty),
            deterministic_issues=det_issues,
        )
    elif not rec_docs and (not case.tags or "skip" not in case.tags):
        # No recommendations produced (might be expected for some cases)
        if case.expected_signals:
            judge_result = JudgeResult(
                test_id=case.id,
                overall_score=20,
                deterministic_issues=["No recommendations produced"],
            )

    elapsed = time.time() - t0

    return {
        "test_id": case.id,
        "category": case.category,
        "expected_rec_type": case.expected_rec_type,
        "rec_docs": rec_docs,
        "analyzer_output": _summarize_analyzer_output(analyzer_output),
        "errors": errors,
        "duration_s": round(elapsed, 1),
        "judge": judge_result.to_dict() if judge_result else None,
        "overall_score": judge_result.overall_score if judge_result else None,
        "timestamp": datetime.utcnow().isoformat(),
    }


def _summarize_analyzer_output(output: Dict) -> Dict:
    """Trim analyzer output for result storage (remove large fields)."""
    return {
        "summary": output.get("summary", ""),
        "recommendation_count": len(output.get("recommendations", [])),
        "progression_candidates": len(output.get("progression_candidates", [])),
        "stalled_exercises": len(output.get("stalled_exercises", [])),
        "has_recommendations": bool(
            output.get("recommendations")
            or output.get("progression_candidates")
        ),
    }


def run_eval(
    cases: List[RecommendationTestCase],
    skip_judge: bool = False,
) -> List[Dict]:
    """Run eval across all test cases sequentially."""
    results = []
    total = len(cases)

    for i, case in enumerate(cases):
        print(f"\n[{i+1}/{total}] {case.id}: {case.category}/{case.expected_rec_type}...")
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
    rec_count = len(result.get("rec_docs", []))

    status = "PASS" if score and score >= 75 else ("FAIL" if score is not None else "ERR")
    if errors:
        status = "ERR"

    print(f"  [{status}] score={score_str} time={duration}s recs={rec_count} ", end="")
    if errors:
        print(f"errors={errors[:1]}")
    else:
        # Show summary from first rec
        recs = result.get("rec_docs", [])
        if recs:
            summary = recs[0].get("recommendation", {}).get("summary", "")
            print(f"| {summary[:70]}")
        else:
            print("| (no recs)")


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

    failing = [
        {
            "test_id": r["test_id"],
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

    all_issues = []
    for r in results:
        judge = r.get("judge")
        if judge:
            all_issues.extend(judge.get("deterministic_issues", []))
            all_issues.extend(judge.get("llm_issues", []))

    issue_counts = {}
    for issue in all_issues:
        key = issue.split(":")[0].strip() if ":" in issue else issue
        issue_counts[key] = issue_counts.get(key, 0) + 1
    top_issues = sorted(issue_counts.items(), key=lambda x: -x[1])[:10]

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
    parser = argparse.ArgumentParser(description="Training Analyst Eval Runner")
    parser.add_argument(
        "--filter",
        help="Filter cases (e.g., category=auto_pilot, tags=progression)",
    )
    parser.add_argument("--id", help="Run a single test case by ID")
    parser.add_argument(
        "--no-judge", action="store_true",
        help="Skip LLM judge (deterministic checks only)",
    )
    args = parser.parse_args()

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
    print(f"Training Analyst Eval - {len(cases)} cases")
    print(f"Timestamp: {timestamp}")
    if args.no_judge:
        print("LLM Judge: DISABLED (deterministic only)")
    print("=" * 72)

    results = run_eval(cases, skip_judge=args.no_judge)

    jsonl_path, summary_path = save_results(results, timestamp)

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
            f"  {cat:20s}: {data['avg_score']:5.1f} avg "
            f"({data['count']} cases, {data['failures']} failures)"
        )

    print("\nDimension Averages:")
    for dim, data in summary.get("dimensions", {}).items():
        print(f"  {dim:20s}: {data['avg_score']:5.1f} avg (min: {data['min_score']:.1f})")

    if summary["failing_tests"]:
        print("\nFailing Tests (score < 75):")
        for f in summary["failing_tests"][:10]:
            print(f"  {f['test_id']:20s}: {f['score']:5.1f}")
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
