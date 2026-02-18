"""
Training data fixtures — realistic builders for eval test cases.

Each builder produces training data in the exact format that analyzers expect:
- workout: trimmed workout (exercise names + set summaries)
- rollups: weekly analytics rollups
- exercise_series: weekly points for exercises

All data is synthetic and deterministic (no randomness, no Firestore).
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional


def _week_id(weeks_ago: int) -> str:
    """Generate a week start date string N weeks ago from a fixed reference."""
    ref = datetime(2026, 2, 16)  # Fixed reference Monday
    d = ref - timedelta(weeks=weeks_ago)
    # Snap to Monday
    d = d - timedelta(days=d.weekday())
    return d.strftime("%Y-%m-%d")


def _build_exercise_series(
    exercise_name: str,
    exercise_id: str,
    weeks: int,
    base_weight: float,
    base_reps: int,
    avg_rir: float,
    e1rm_trend: str = "stable",  # "stable" | "improving" | "declining"
    e1rm_slope: float = 0.0,
) -> Dict[str, Any]:
    """Build a single exercise series with weekly data points."""
    weekly_points = []
    base_e1rm = base_weight * (1 + base_reps / 30)  # Epley

    for i in range(weeks):
        weeks_ago = weeks - 1 - i
        if e1rm_trend == "improving":
            e1rm = base_e1rm + (e1rm_slope * i)
        elif e1rm_trend == "declining":
            e1rm = base_e1rm - (abs(e1rm_slope) * i)
        else:
            e1rm = base_e1rm + (e1rm_slope * 0.1 * (i % 2))  # tiny noise

        weekly_points.append({
            "week_start": _week_id(weeks_ago),
            "sets": 3,
            "volume": round(base_weight * base_reps * 3),
            "e1rm_max": round(e1rm, 1),
            "hard_sets": 3,
            "load_max": base_weight,
            "avg_rir": avg_rir,
        })

    return {
        "exercise_id": exercise_id,
        "exercise_name": exercise_name,
        "weeks": weekly_points,
    }


def _build_rollups(
    weeks: int,
    base_sets: int = 60,
    base_volume: int = 40000,
    trend: str = "stable",
) -> List[Dict[str, Any]]:
    """Build weekly analytics rollups."""
    rollups = []
    for i in range(weeks):
        weeks_ago = weeks - 1 - i
        factor = 1.0
        if trend == "increasing":
            factor = 1.0 + (0.05 * i)
        elif trend == "decreasing":
            factor = 1.0 - (0.03 * i)

        rollups.append({
            "week_id": _week_id(weeks_ago),
            "workouts": 4,
            "total_sets": round(base_sets * factor),
            "total_weight": round(base_volume * factor),
            "hard_sets_total": round(base_sets * factor * 0.7),
            "low_rir_sets_total": round(base_sets * factor * 0.3),
        })
    return rollups


def _build_workout(
    exercises: List[Dict[str, Any]],
    date: str = None,
    duration_minutes: int = 60,
) -> Dict[str, Any]:
    """Build a trimmed workout document."""
    if date is None:
        date = _week_id(0)

    workout_exercises = []
    for ex in exercises:
        sets = ex.get("sets", 3)
        weight = ex.get("weight", 0)
        reps = ex.get("reps", 8)
        rir = ex.get("rir", 2.0)

        # e1RM from best set (Epley, reps <= 12)
        e1rm = None
        if 0 < reps <= 12 and weight > 0:
            e1rm = round(weight * (1 + reps / 30), 1)

        workout_exercises.append({
            "name": ex["name"],
            "exercise_id": ex.get("id", ex["name"].lower().replace(" ", "-")),
            "working_sets": sets,
            "top_weight_kg": weight if weight > 0 else None,
            "rep_range": str(reps),
            "avg_rir": rir if rir > 0 else None,
            "volume": round(weight * reps * sets),
            "e1rm": e1rm,
        })

    return {
        "workout_date": date,
        "duration_minutes": duration_minutes,
        "exercises": workout_exercises,
    }


# =============================================================================
# Public builders (used by test_cases.py)
# =============================================================================

def build_progression_ready(
    exercise_name: str,
    exercise_id: str,
    current_weight: float,
    weeks_stable: int,
    avg_rir: float,
    reps: int,
    confidence_override: float = None,
    pr_hit: bool = False,
    no_history: bool = False,
) -> Dict[str, Any]:
    """Build training data for a progression-ready exercise.

    3+ weeks at same weight, consistent RIR 2-3, stable e1RM.
    """
    if no_history:
        return {
            "workout": _build_workout([]),
            "recent_rollups": [],
            "exercise_series": [],
        }

    weeks = max(weeks_stable, 4)

    workout = _build_workout([
        {"name": exercise_name, "id": exercise_id, "weight": current_weight,
         "reps": reps, "rir": avg_rir, "sets": 3},
    ])

    rollups = _build_rollups(weeks=weeks)

    series = [_build_exercise_series(
        exercise_name=exercise_name,
        exercise_id=exercise_id,
        weeks=weeks,
        base_weight=current_weight,
        base_reps=reps,
        avg_rir=avg_rir,
        e1rm_trend="stable",
    )]

    data = {
        "workout": workout,
        "recent_rollups": rollups,
        "exercise_series": series,
    }
    if confidence_override is not None:
        data["_confidence_hint"] = confidence_override
    if pr_hit:
        data["_pr_hit"] = True
        # Rebuild series with improving e1RM to actually show a PR
        data["exercise_series"] = [_build_exercise_series(
            exercise_name=exercise_name,
            exercise_id=exercise_id,
            weeks=weeks,
            base_weight=current_weight,
            base_reps=reps,
            avg_rir=avg_rir,
            e1rm_trend="improving",
            e1rm_slope=2.0,  # Strong upward trend for PR
        )]
    return data


def build_stall_detected(
    exercise_name: str,
    exercise_id: str,
    current_weight: float,
    weeks_stalled: int,
    reps: int,
) -> Dict[str, Any]:
    """Build training data for a stalled exercise.

    4+ weeks flat e1RM (±2%), volume maintained.
    """
    workout = _build_workout([
        {"name": exercise_name, "id": exercise_id, "weight": current_weight,
         "reps": reps, "rir": 1.5, "sets": 3},
    ])

    rollups = _build_rollups(weeks=weeks_stalled)

    series = [_build_exercise_series(
        exercise_name=exercise_name,
        exercise_id=exercise_id,
        weeks=weeks_stalled,
        base_weight=current_weight,
        base_reps=reps,
        avg_rir=1.5,
        e1rm_trend="stable",
        e1rm_slope=0.0,
    )]

    return {
        "workout": workout,
        "recent_rollups": rollups,
        "exercise_series": series,
    }


def build_overreach(
    exercise_name: str,
    exercise_id: str,
    current_weight: float,
    reps: int,
) -> Dict[str, Any]:
    """Build training data showing overreach signals.

    Low RIR across multiple exercises, declining rep quality.
    """
    workout = _build_workout([
        {"name": exercise_name, "id": exercise_id, "weight": current_weight,
         "reps": reps - 1, "rir": 0.5, "sets": 3},  # reps declining, very low RIR
    ])

    rollups = _build_rollups(weeks=6, trend="increasing")  # volume ramped up

    series = [_build_exercise_series(
        exercise_name=exercise_name,
        exercise_id=exercise_id,
        weeks=6,
        base_weight=current_weight,
        base_reps=reps,
        avg_rir=0.8,
        e1rm_trend="declining",
        e1rm_slope=0.5,
    )]

    return {
        "workout": workout,
        "recent_rollups": rollups,
        "exercise_series": series,
    }


def build_volume_imbalance(
    underserved_group: str,
    weekly_sets: int,
    overserved_group: str,
    over_weekly_sets: int,
) -> Dict[str, Any]:
    """Build training data showing volume imbalance between muscle groups.

    One group <10 sets/week, another >20.
    Used primarily for weekly_review cases (no single workout needed).
    """
    rollups = _build_rollups(weeks=6)
    # Add per-muscle-group data to rollups
    for rollup in rollups:
        rollup["hard_sets_per_muscle_group"] = {
            underserved_group: weekly_sets,
            overserved_group: over_weekly_sets,
            "chest": 14,
            "back": 16,
        }

    return {
        "workout": _build_workout([]),  # empty (weekly review)
        "recent_rollups": rollups,
        "exercise_series": [],
        "_volume_context": {
            "underserved": underserved_group,
            "underserved_sets": weekly_sets,
            "overserved": overserved_group,
            "overserved_sets": over_weekly_sets,
        },
    }


def build_new_user(
    exercise_name: str,
    exercise_id: str,
    current_weight: float,
    weeks_data: int,
    reps: int,
) -> Dict[str, Any]:
    """Build training data for a new user with limited history.

    <4 weeks of data, sparse.
    """
    workout = _build_workout([
        {"name": exercise_name, "id": exercise_id, "weight": current_weight,
         "reps": reps, "rir": 3.0, "sets": 3},
    ])

    rollups = _build_rollups(weeks=weeks_data, base_sets=30, base_volume=15000)

    series = [_build_exercise_series(
        exercise_name=exercise_name,
        exercise_id=exercise_id,
        weeks=weeks_data,
        base_weight=current_weight,
        base_reps=reps,
        avg_rir=3.0,
        e1rm_trend="improving",
        e1rm_slope=1.0,
    )]

    return {
        "workout": workout,
        "recent_rollups": rollups,
        "exercise_series": series,
    }


def build_multi_exercise(
    exercises: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build training data with multiple exercises.

    Each entry: {"name", "id", "weight", "reps", "rir", "weeks_stable"}
    """
    workout_exercises = [
        {"name": ex["name"], "id": ex["id"], "weight": ex["weight"],
         "reps": ex["reps"], "rir": ex.get("rir", 2.0), "sets": 3}
        for ex in exercises
    ]
    workout = _build_workout(workout_exercises)

    max_weeks = max(ex.get("weeks_stable", 4) for ex in exercises)
    rollups = _build_rollups(weeks=max_weeks)

    series = [
        _build_exercise_series(
            exercise_name=ex["name"],
            exercise_id=ex["id"],
            weeks=ex.get("weeks_stable", 4),
            base_weight=ex["weight"],
            base_reps=ex["reps"],
            avg_rir=ex.get("rir", 2.0),
            e1rm_trend="stable",
        )
        for ex in exercises
    ]

    return {
        "workout": workout,
        "recent_rollups": rollups,
        "exercise_series": series,
    }


def build_bodyweight_exercise(
    exercise_name: str,
    exercise_id: str,
    current_reps: int,
    weeks_stable: int,
    avg_rir: float,
) -> Dict[str, Any]:
    """Build training data for a bodyweight exercise (no weight_kg)."""
    workout = _build_workout([
        {"name": exercise_name, "id": exercise_id, "weight": 0,
         "reps": current_reps, "rir": avg_rir, "sets": 3},
    ])

    rollups = _build_rollups(weeks=weeks_stable)

    # Series with 0 weight, track reps only
    series_data = {
        "exercise_id": exercise_id,
        "exercise_name": exercise_name,
        "weeks": [],
    }
    for i in range(weeks_stable):
        weeks_ago = weeks_stable - 1 - i
        series_data["weeks"].append({
            "week_start": _week_id(weeks_ago),
            "sets": 3,
            "volume": 0,
            "e1rm_max": None,
            "hard_sets": 3,
            "load_max": 0,
            "avg_rir": avg_rir,
        })

    return {
        "workout": workout,
        "recent_rollups": rollups,
        "exercise_series": [series_data],
    }


def build_sparse_history(
    exercise_name: str,
    exercise_id: str,
    current_weight: float,
    weeks_data: int,
    reps: int,
) -> Dict[str, Any]:
    """Build training data with very sparse history (1-3 weeks)."""
    return build_new_user(exercise_name, exercise_id, current_weight, weeks_data, reps)


def build_high_weight_compound(
    exercise_name: str,
    exercise_id: str,
    current_weight: float,
    weeks_stable: int,
    avg_rir: float,
    reps: int,
) -> Dict[str, Any]:
    """Build training data for a very heavy compound lift (>150kg)."""
    return build_progression_ready(
        exercise_name=exercise_name,
        exercise_id=exercise_id,
        current_weight=current_weight,
        weeks_stable=weeks_stable,
        avg_rir=avg_rir,
        reps=reps,
    )
