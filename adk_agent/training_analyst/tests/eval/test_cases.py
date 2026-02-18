"""
Training Analyst Eval Test Cases — 30 cases across 3 categories.

Each case defines training data input and expected recommendation quality
for automated scoring. Cases test the full pipeline: analyzer LLM output →
recommendation processing → final recommendation document.

Categories:
- AUTO_PILOT (10): Auto-applied recommendations (user has routine + auto_pilot ON)
- PENDING_REVIEW (10): Recommendations awaiting user approval (routine, no auto_pilot)
- EXERCISE_SCOPED (10): Recommendations without a routine context
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class RecommendationTestCase:
    """Single eval test case for recommendation quality."""
    id: str                          # e.g. "ap_001"
    category: str                    # "auto_pilot" | "pending_review" | "exercise_scoped"

    # Input scenario
    analyzer_type: str               # "post_workout" | "weekly_review"
    training_data: dict              # workout, rollups, exercise_series (passed to analyzer)
    user_state: dict                 # auto_pilot_enabled, activeRoutineId, routine/template names

    # Expected output
    expected_rec_type: str           # "progression" | "deload" | "volume_adjust"
    expected_signals: list           # Data points that MUST appear (e.g. "100kg x 8")

    # Gold standard
    gold_summary: str                # Example good summary
    gold_rationale: str              # Example good rationale
    quality_requirements: list       # Scenario-specific quality bars
    tags: list = field(default_factory=list)  # For filtering


# Import fixtures for building test data
from tests.eval.fixtures import (
    build_progression_ready,
    build_stall_detected,
    build_overreach,
    build_volume_imbalance,
    build_new_user,
    build_multi_exercise,
    build_bodyweight_exercise,
    build_sparse_history,
    build_high_weight_compound,
)


# =============================================================================
# AUTO_PILOT (10): Auto-applied recommendations
# =============================================================================

AUTO_PILOT_CASES = [
    RecommendationTestCase(
        id="ap_001",
        category="auto_pilot",
        analyzer_type="post_workout",
        training_data=build_progression_ready(
            exercise_name="Bench Press",
            exercise_id="bench-press-barbell",
            current_weight=100.0,
            weeks_stable=3,
            avg_rir=2.0,
            reps=8,
        ),
        user_state={
            "auto_pilot_enabled": True,
            "activeRoutineId": "routine-001",
            "routine_name": "Push Pull Legs",
            "template_id": "template-push-001",
            "template_name": "Push Day A",
            "template_exercises": [
                {"name": "Bench Press", "sets": [
                    {"weight_kg": 100, "reps": 8},
                    {"weight_kg": 100, "reps": 8},
                    {"weight_kg": 100, "reps": 8},
                ]},
            ],
        },
        expected_rec_type="progression",
        expected_signals=["100kg", "102.5kg", "8 reps", "3 weeks", "RIR 2"],
        gold_summary="Applied: Bench Press 100kg → 102.5kg",
        gold_rationale="e1RM stable at 113kg for 3 weeks with consistent RIR 2. Progressive overload applied. Updated in Push Day A.",
        quality_requirements=[
            "Past tense language (Applied, Updated, Increased)",
            "Specific kg values (from → to)",
            "Template name mentioned",
            "At least one supporting signal cited",
        ],
        tags=["progression", "compound", "bench"],
    ),
    RecommendationTestCase(
        id="ap_002",
        category="auto_pilot",
        analyzer_type="weekly_review",
        training_data=build_progression_ready(
            exercise_name="Barbell Squat",
            exercise_id="barbell-squat",
            current_weight=120.0,
            weeks_stable=4,
            avg_rir=2.5,
            reps=5,
        ),
        user_state={
            "auto_pilot_enabled": True,
            "activeRoutineId": "routine-001",
            "routine_name": "Push Pull Legs",
            "template_id": "template-legs-001",
            "template_name": "Leg Day",
            "template_exercises": [
                {"name": "Barbell Squat", "sets": [
                    {"weight_kg": 120, "reps": 5},
                    {"weight_kg": 120, "reps": 5},
                    {"weight_kg": 120, "reps": 5},
                    {"weight_kg": 120, "reps": 5},
                    {"weight_kg": 120, "reps": 5},
                ]},
            ],
        },
        expected_rec_type="progression",
        expected_signals=["120kg", "122.5kg", "5 reps", "4 weeks"],
        gold_summary="Applied: Barbell Squat 120kg → 122.5kg",
        gold_rationale="Consistent 5x5 at 120kg for 4 weeks with RIR 2-3. Strength progression applied. Updated in Leg Day.",
        quality_requirements=[
            "Past tense language",
            "Specific weight values",
            "Template name mentioned",
            "Weekly review context acknowledged",
        ],
        tags=["progression", "compound", "squat", "weekly"],
    ),
    RecommendationTestCase(
        id="ap_003",
        category="auto_pilot",
        analyzer_type="post_workout",
        training_data=build_overreach(
            exercise_name="Barbell Row",
            exercise_id="barbell-row",
            current_weight=80.0,
            reps=8,
        ),
        user_state={
            "auto_pilot_enabled": True,
            "activeRoutineId": "routine-001",
            "routine_name": "Push Pull Legs",
            "template_id": "template-pull-001",
            "template_name": "Pull Day",
            "template_exercises": [
                {"name": "Barbell Row", "sets": [
                    {"weight_kg": 80, "reps": 8},
                    {"weight_kg": 80, "reps": 8},
                    {"weight_kg": 80, "reps": 8},
                ]},
            ],
        },
        expected_rec_type="deload",
        expected_signals=["80kg", "72.5kg", "RIR", "fatigue"],
        gold_summary="Reduced Barbell Row to 72.5kg",
        gold_rationale="Avg RIR dropped below 1.0 with declining rep performance over 2 weeks. Deload applied to manage fatigue. Updated in Pull Day.",
        quality_requirements=[
            "Past tense (Reduced, Lowered)",
            "Deload-specific language",
            "Fatigue signals cited",
            "Template name mentioned",
        ],
        tags=["deload", "overreach", "compound"],
    ),
    RecommendationTestCase(
        id="ap_004",
        category="auto_pilot",
        analyzer_type="post_workout",
        training_data=build_progression_ready(
            exercise_name="Lateral Raise",
            exercise_id="lateral-raise-dumbbell",
            current_weight=10.0,
            weeks_stable=3,
            avg_rir=2.0,
            reps=15,
        ),
        user_state={
            "auto_pilot_enabled": True,
            "activeRoutineId": "routine-001",
            "routine_name": "PPL",
            "template_id": "template-push-001",
            "template_name": "Push Day A",
            "template_exercises": [
                {"name": "Lateral Raise", "sets": [
                    {"weight_kg": 10, "reps": 15},
                    {"weight_kg": 10, "reps": 15},
                    {"weight_kg": 10, "reps": 15},
                ]},
            ],
        },
        expected_rec_type="progression",
        expected_signals=["10kg", "11.25kg", "15 reps"],
        gold_summary="Applied: Lateral Raise 10kg → 11.25kg",
        gold_rationale="Consistent 3x15 at 10kg for 3 weeks with RIR 2. Small isolation increment applied. Updated in Push Day A.",
        quality_requirements=[
            "Correct isolation increment (+5% not +2.5%)",
            "Appropriate rounding (to 1.25kg)",
        ],
        tags=["progression", "isolation", "small_increment"],
    ),
    RecommendationTestCase(
        id="ap_005",
        category="auto_pilot",
        analyzer_type="post_workout",
        training_data=build_multi_exercise(
            exercises=[
                {"name": "Bench Press", "id": "bench-press", "weight": 100, "reps": 8, "rir": 2, "weeks_stable": 3},
                {"name": "Overhead Press", "id": "overhead-press", "weight": 50, "reps": 8, "rir": 2, "weeks_stable": 4},
            ],
        ),
        user_state={
            "auto_pilot_enabled": True,
            "activeRoutineId": "routine-001",
            "routine_name": "Upper Lower",
            "template_id": "template-upper-001",
            "template_name": "Upper Day A",
            "template_exercises": [
                {"name": "Bench Press", "sets": [
                    {"weight_kg": 100, "reps": 8},
                    {"weight_kg": 100, "reps": 8},
                    {"weight_kg": 100, "reps": 8},
                ]},
                {"name": "Overhead Press", "sets": [
                    {"weight_kg": 50, "reps": 8},
                    {"weight_kg": 50, "reps": 8},
                    {"weight_kg": 50, "reps": 8},
                ]},
            ],
        },
        expected_rec_type="progression",
        expected_signals=["100kg", "50kg", "Bench Press", "Overhead Press"],
        gold_summary="Applied: Bench Press 100kg → 102.5kg, Overhead Press 50kg → 52.5kg",
        gold_rationale="Both exercises showed stable e1RM with consistent RIR 2. Progressive overload applied to both. Updated in Upper Day A.",
        quality_requirements=[
            "Both exercises mentioned",
            "Separate weight changes for each",
            "Template name mentioned",
        ],
        tags=["progression", "multi_exercise", "compound"],
    ),
    RecommendationTestCase(
        id="ap_006",
        category="auto_pilot",
        analyzer_type="post_workout",
        training_data=build_new_user(
            exercise_name="Bench Press",
            exercise_id="bench-press",
            current_weight=60.0,
            weeks_data=4,
            reps=8,
        ),
        user_state={
            "auto_pilot_enabled": True,
            "activeRoutineId": "routine-001",
            "routine_name": "Beginner Full Body",
            "template_id": "template-fb-001",
            "template_name": "Full Body A",
            "template_exercises": [
                {"name": "Bench Press", "sets": [
                    {"weight_kg": 60, "reps": 8},
                    {"weight_kg": 60, "reps": 8},
                    {"weight_kg": 60, "reps": 8},
                ]},
            ],
        },
        expected_rec_type="progression",
        expected_signals=["60kg", "62.5kg", "4 weeks"],
        gold_summary="Applied: Bench Press 60kg → 62.5kg",
        gold_rationale="4 weeks of consistent performance at 60kg. Conservative progression applied given limited training history. Updated in Full Body A.",
        quality_requirements=[
            "Acknowledges limited history",
            "Conservative language",
        ],
        tags=["progression", "new_user", "conservative"],
    ),
    RecommendationTestCase(
        id="ap_007",
        category="auto_pilot",
        analyzer_type="weekly_review",
        training_data=build_volume_imbalance(
            underserved_group="hamstrings",
            weekly_sets=4,
            overserved_group="quadriceps",
            over_weekly_sets=22,
        ),
        user_state={
            "auto_pilot_enabled": True,
            "activeRoutineId": "routine-001",
            "routine_name": "PPL",
            "template_id": "template-legs-001",
            "template_name": "Leg Day",
            "template_exercises": [
                {"name": "Barbell Squat", "sets": [
                    {"weight_kg": 100, "reps": 8},
                    {"weight_kg": 100, "reps": 8},
                    {"weight_kg": 100, "reps": 8},
                ]},
            ],
        },
        expected_rec_type="volume_adjust",
        expected_signals=["hamstrings", "4 sets", "quadriceps", "22 sets"],
        gold_summary="Volume adjustment: hamstring work flagged as undertrained",
        gold_rationale="Hamstrings at 4 sets/week vs quadriceps at 22 sets/week. Volume imbalance detected. Consider adding dedicated hamstring work.",
        quality_requirements=[
            "Volume-specific language",
            "Both muscle groups mentioned with set counts",
        ],
        tags=["volume_adjust", "imbalance", "weekly"],
    ),
    RecommendationTestCase(
        id="ap_008",
        category="auto_pilot",
        analyzer_type="weekly_review",
        training_data=build_multi_exercise(
            exercises=[
                {"name": "Bench Press", "id": "bench-press", "weight": 100, "reps": 8, "rir": 2, "weeks_stable": 4},
                {"name": "Barbell Row", "id": "barbell-row", "weight": 80, "reps": 8, "rir": 1, "weeks_stable": 6},
            ],
        ),
        user_state={
            "auto_pilot_enabled": True,
            "activeRoutineId": "routine-001",
            "routine_name": "Upper Lower",
            "template_id": "template-upper-001",
            "template_name": "Upper Day",
            "template_exercises": [
                {"name": "Bench Press", "sets": [
                    {"weight_kg": 100, "reps": 8},
                    {"weight_kg": 100, "reps": 8},
                    {"weight_kg": 100, "reps": 8},
                ]},
                {"name": "Barbell Row", "sets": [
                    {"weight_kg": 80, "reps": 8},
                    {"weight_kg": 80, "reps": 8},
                    {"weight_kg": 80, "reps": 8},
                ]},
            ],
        },
        expected_rec_type="progression",
        expected_signals=["100kg", "Bench Press"],
        gold_summary="Applied: Bench Press 100kg → 102.5kg",
        gold_rationale="Bench Press stable at 100kg for 4 weeks with RIR 2 — progression applied. Barbell Row stalled (6 weeks) but not auto-progressed due to low confidence.",
        quality_requirements=[
            "Only progression auto-applied",
            "Stall acknowledged but not auto-applied",
        ],
        tags=["progression", "mixed_signals", "weekly"],
    ),
    RecommendationTestCase(
        id="ap_009",
        category="auto_pilot",
        analyzer_type="post_workout",
        training_data=build_progression_ready(
            exercise_name="Dumbbell Curl",
            exercise_id="dumbbell-curl",
            current_weight=14.0,
            weeks_stable=3,
            avg_rir=2.5,
            reps=10,
            confidence_override=0.71,
        ),
        user_state={
            "auto_pilot_enabled": True,
            "activeRoutineId": "routine-001",
            "routine_name": "PPL",
            "template_id": "template-pull-001",
            "template_name": "Pull Day",
            "template_exercises": [
                {"name": "Dumbbell Curl", "sets": [
                    {"weight_kg": 14, "reps": 10},
                    {"weight_kg": 14, "reps": 10},
                ]},
            ],
        },
        expected_rec_type="progression",
        expected_signals=["14kg", "0.7"],
        gold_summary="Applied: Dumbbell Curl 14kg → 15kg",
        gold_rationale="Borderline confidence (0.71) but consistent RIR 2-3. Small isolation progression applied cautiously. Updated in Pull Day.",
        quality_requirements=[
            "Cautious language given borderline confidence",
            "Still applied (threshold met)",
        ],
        tags=["progression", "isolation", "threshold"],
    ),
    RecommendationTestCase(
        id="ap_010",
        category="auto_pilot",
        analyzer_type="post_workout",
        training_data=build_high_weight_compound(
            exercise_name="Barbell Squat",
            exercise_id="barbell-squat-heavy",
            current_weight=200.0,
            weeks_stable=3,
            avg_rir=2.0,
            reps=3,
        ),
        user_state={
            "auto_pilot_enabled": True,
            "activeRoutineId": "routine-001",
            "routine_name": "Powerlifting",
            "template_id": "template-squat-001",
            "template_name": "Squat Day",
            "template_exercises": [
                {"name": "Barbell Squat", "sets": [
                    {"weight_kg": 200, "reps": 3},
                    {"weight_kg": 200, "reps": 3},
                    {"weight_kg": 200, "reps": 3},
                ]},
            ],
        },
        expected_rec_type="progression",
        expected_signals=["200kg", "205kg", "3 reps"],
        gold_summary="Applied: Barbell Squat 200kg → 205kg",
        gold_rationale="Stable at 200kg x 3 for 3 weeks with controlled effort. +2.5% increment applied. Updated in Squat Day.",
        quality_requirements=[
            "Correct increment for heavy weight (+2.5%, rounded to 2.5kg)",
            "High weight handled correctly",
        ],
        tags=["progression", "heavy", "compound"],
    ),
]


# =============================================================================
# PENDING_REVIEW (10): Awaiting user approval
# =============================================================================

PENDING_REVIEW_CASES = [
    RecommendationTestCase(
        id="pr_001",
        category="pending_review",
        analyzer_type="post_workout",
        training_data=build_progression_ready(
            exercise_name="Bench Press",
            exercise_id="bench-press-barbell",
            current_weight=100.0,
            weeks_stable=3,
            avg_rir=2.0,
            reps=8,
        ),
        user_state={
            "auto_pilot_enabled": False,
            "activeRoutineId": "routine-001",
            "routine_name": "Push Pull Legs",
            "template_id": "template-push-001",
            "template_name": "Push Day A",
            "template_exercises": [
                {"name": "Bench Press", "sets": [
                    {"weight_kg": 100, "reps": 8},
                    {"weight_kg": 100, "reps": 8},
                    {"weight_kg": 100, "reps": 8},
                ]},
            ],
        },
        expected_rec_type="progression",
        expected_signals=["100kg", "102.5kg", "8 reps", "3 weeks"],
        gold_summary="Try 102.5kg on Bench Press",
        gold_rationale="e1RM stable at 113kg for 3 weeks, avg RIR 2.0. Accepting updates Push Day A.",
        quality_requirements=[
            "Imperative language (Try, Consider)",
            "Specific target weight",
            "What happens on accept (template update)",
            "At-a-glance summary",
        ],
        tags=["progression", "compound", "bench"],
    ),
    RecommendationTestCase(
        id="pr_002",
        category="pending_review",
        analyzer_type="post_workout",
        training_data=build_overreach(
            exercise_name="Deadlift",
            exercise_id="deadlift-barbell",
            current_weight=140.0,
            reps=5,
        ),
        user_state={
            "auto_pilot_enabled": False,
            "activeRoutineId": "routine-001",
            "routine_name": "PPL",
            "template_id": "template-pull-001",
            "template_name": "Pull Day",
            "template_exercises": [
                {"name": "Deadlift", "sets": [
                    {"weight_kg": 140, "reps": 5},
                    {"weight_kg": 140, "reps": 5},
                    {"weight_kg": 140, "reps": 5},
                ]},
            ],
        },
        expected_rec_type="deload",
        expected_signals=["140kg", "126kg", "fatigue", "RIR"],
        gold_summary="Consider reducing Deadlift to 126kg",
        gold_rationale="Avg RIR below 1.0 for 2 consecutive weeks, rep quality declining. Accepting reduces Deadlift in Pull Day.",
        quality_requirements=[
            "Deload language (Consider reducing)",
            "Fatigue signals cited",
            "Accept outcome explained",
        ],
        tags=["deload", "compound", "overreach"],
    ),
    RecommendationTestCase(
        id="pr_003",
        category="pending_review",
        analyzer_type="weekly_review",
        training_data=build_progression_ready(
            exercise_name="Overhead Press",
            exercise_id="overhead-press",
            current_weight=50.0,
            weeks_stable=5,
            avg_rir=2.0,
            reps=8,
        ),
        user_state={
            "auto_pilot_enabled": False,
            "activeRoutineId": "routine-001",
            "routine_name": "PPL",
            "template_id": "template-push-001",
            "template_name": "Push Day B",
            "template_exercises": [
                {"name": "Overhead Press", "sets": [
                    {"weight_kg": 50, "reps": 8},
                    {"weight_kg": 50, "reps": 8},
                    {"weight_kg": 50, "reps": 8},
                ]},
            ],
        },
        expected_rec_type="progression",
        expected_signals=["50kg", "5 weeks", "Push Day B"],
        gold_summary="Try 52.5kg on Overhead Press",
        gold_rationale="e1RM stable for 5 weeks with consistent effort. Accepting updates Push Day B.",
        quality_requirements=[
            "Template name in rationale",
            "Weekly review context",
        ],
        tags=["progression", "compound", "weekly"],
    ),
    RecommendationTestCase(
        id="pr_004",
        category="pending_review",
        analyzer_type="weekly_review",
        training_data=build_volume_imbalance(
            underserved_group="rear delts",
            weekly_sets=3,
            overserved_group="front delts",
            over_weekly_sets=18,
        ),
        user_state={
            "auto_pilot_enabled": False,
            "activeRoutineId": "routine-001",
            "routine_name": "PPL",
            "template_id": "template-push-001",
            "template_name": "Push Day",
            "template_exercises": [
                {"name": "Face Pull", "sets": [
                    {"weight_kg": 15, "reps": 15},
                    {"weight_kg": 15, "reps": 15},
                ]},
            ],
        },
        expected_rec_type="volume_adjust",
        expected_signals=["rear delts", "3 sets", "front delts"],
        gold_summary="Consider adding rear delt volume",
        gold_rationale="Rear delts at 3 sets/week vs front delts at 18 sets/week. Accepting adds volume to Push Day.",
        quality_requirements=[
            "Volume context with numbers",
            "What template changes on accept",
        ],
        tags=["volume_adjust", "imbalance", "weekly"],
    ),
    RecommendationTestCase(
        id="pr_005",
        category="pending_review",
        analyzer_type="post_workout",
        training_data=build_multi_exercise(
            exercises=[
                {"name": "Bench Press", "id": "bench-press", "weight": 100, "reps": 8, "rir": 2, "weeks_stable": 3},
                {"name": "Incline Dumbbell Press", "id": "incline-db", "weight": 32, "reps": 10, "rir": 2, "weeks_stable": 3},
            ],
        ),
        user_state={
            "auto_pilot_enabled": False,
            "activeRoutineId": "routine-001",
            "routine_name": "PPL",
            "template_id": "template-push-001",
            "template_name": "Push Day",
            "template_exercises": [
                {"name": "Bench Press", "sets": [{"weight_kg": 100, "reps": 8}] * 3},
                {"name": "Incline Dumbbell Press", "sets": [{"weight_kg": 32, "reps": 10}] * 3},
            ],
        },
        expected_rec_type="progression",
        expected_signals=["100kg", "32kg", "Bench Press", "Incline"],
        gold_summary="Try 102.5kg on Bench Press and 33.5kg on Incline Dumbbell Press",
        gold_rationale="Both exercises showing stable performance. Accepting updates both in Push Day.",
        quality_requirements=[
            "Clear enumeration of multiple changes",
            "Both exercises with specific weights",
        ],
        tags=["progression", "multi_exercise"],
    ),
    RecommendationTestCase(
        id="pr_006",
        category="pending_review",
        analyzer_type="post_workout",
        training_data=build_progression_ready(
            exercise_name="Cable Fly",
            exercise_id="cable-fly",
            current_weight=15.0,
            weeks_stable=3,
            avg_rir=2.5,
            reps=12,
            confidence_override=0.72,
        ),
        user_state={
            "auto_pilot_enabled": False,
            "activeRoutineId": "routine-001",
            "routine_name": "PPL",
            "template_id": "template-push-001",
            "template_name": "Push Day",
            "template_exercises": [
                {"name": "Cable Fly", "sets": [
                    {"weight_kg": 15, "reps": 12},
                    {"weight_kg": 15, "reps": 12},
                    {"weight_kg": 15, "reps": 12},
                ]},
            ],
        },
        expected_rec_type="progression",
        expected_signals=["15kg", "0.72"],
        gold_summary="Try 16.25kg on Cable Fly",
        gold_rationale="Consistent performance but confidence is moderate (0.72). Consider trying a small increase. Accepting updates Push Day.",
        quality_requirements=[
            "Cautious language for low confidence",
            "Still a valid suggestion",
        ],
        tags=["progression", "isolation", "low_confidence"],
    ),
    RecommendationTestCase(
        id="pr_007",
        category="pending_review",
        analyzer_type="post_workout",
        training_data=build_progression_ready(
            exercise_name="Bench Press",
            exercise_id="bench-press",
            current_weight=105.0,
            weeks_stable=1,
            avg_rir=1.0,
            reps=8,
            pr_hit=True,
        ),
        user_state={
            "auto_pilot_enabled": False,
            "activeRoutineId": "routine-001",
            "routine_name": "PPL",
            "template_id": "template-push-001",
            "template_name": "Push Day",
            "template_exercises": [
                {"name": "Bench Press", "sets": [
                    {"weight_kg": 105, "reps": 8},
                    {"weight_kg": 105, "reps": 8},
                    {"weight_kg": 105, "reps": 8},
                ]},
            ],
        },
        expected_rec_type="progression",
        expected_signals=["105kg", "PR", "e1RM"],
        gold_summary="Try 107.5kg on Bench Press",
        gold_rationale="New e1RM PR hit today. Momentum suggests progression is warranted. Accepting updates Push Day.",
        quality_requirements=[
            "PR acknowledged",
            "Suggests next step based on PR",
        ],
        tags=["progression", "pr", "compound"],
    ),
    RecommendationTestCase(
        id="pr_008",
        category="pending_review",
        analyzer_type="post_workout",
        training_data=build_sparse_history(
            exercise_name="Romanian Deadlift",
            exercise_id="rdl",
            current_weight=60.0,
            weeks_data=3,
            reps=10,
        ),
        user_state={
            "auto_pilot_enabled": False,
            "activeRoutineId": "routine-001",
            "routine_name": "PPL",
            "template_id": "template-legs-001",
            "template_name": "Leg Day",
            "template_exercises": [
                {"name": "Romanian Deadlift", "sets": [
                    {"weight_kg": 60, "reps": 10},
                    {"weight_kg": 60, "reps": 10},
                    {"weight_kg": 60, "reps": 10},
                ]},
            ],
        },
        expected_rec_type="progression",
        expected_signals=["60kg", "3 weeks", "limited"],
        gold_summary="Try 62.5kg on Romanian Deadlift",
        gold_rationale="Only 3 weeks of data — limited history. Performance looks consistent so far. Accepting updates Leg Day.",
        quality_requirements=[
            "Acknowledges limited data",
            "Conservative suggestion",
        ],
        tags=["progression", "sparse_data", "compound"],
    ),
    RecommendationTestCase(
        id="pr_009",
        category="pending_review",
        analyzer_type="weekly_review",
        training_data=build_stall_detected(
            exercise_name="Lat Pulldown",
            exercise_id="lat-pulldown",
            current_weight=65.0,
            weeks_stalled=7,
            reps=10,
        ),
        user_state={
            "auto_pilot_enabled": False,
            "activeRoutineId": "routine-001",
            "routine_name": "PPL",
            "template_id": "template-pull-001",
            "template_name": "Pull Day",
            "template_exercises": [
                {"name": "Lat Pulldown", "sets": [
                    {"weight_kg": 65, "reps": 10},
                    {"weight_kg": 65, "reps": 10},
                    {"weight_kg": 65, "reps": 10},
                ]},
            ],
        },
        expected_rec_type="deload",
        expected_signals=["65kg", "7 weeks", "stalled"],
        gold_summary="Consider reducing Lat Pulldown to 57.5kg",
        gold_rationale="e1RM flat at 65kg for 7 consecutive weeks. A deload or variation may help break through the plateau. Accepting updates Pull Day.",
        quality_requirements=[
            "Stall duration mentioned",
            "Actionable suggestion (deload, swap, or variation)",
            "Template context included",
        ],
        tags=["stall", "deload", "extended_plateau"],
    ),
    RecommendationTestCase(
        id="pr_010",
        category="pending_review",
        analyzer_type="post_workout",
        training_data=build_multi_exercise(
            exercises=[
                {"name": "Bench Press", "id": "bench-press", "weight": 95, "reps": 8, "rir": 2, "weeks_stable": 3},
                {"name": "Incline DB Press", "id": "incline-db", "weight": 30, "reps": 10, "rir": 0.5, "weeks_stable": 4},
            ],
        ),
        user_state={
            "auto_pilot_enabled": False,
            "activeRoutineId": "routine-001",
            "routine_name": "PPL",
            "template_id": "template-push-001",
            "template_name": "Push Day",
            "template_exercises": [
                {"name": "Bench Press", "sets": [{"weight_kg": 95, "reps": 8}] * 3},
                {"name": "Incline DB Press", "sets": [{"weight_kg": 30, "reps": 10}] * 3},
            ],
        },
        expected_rec_type="progression",
        expected_signals=["95kg", "30kg", "volume up", "e1RM"],
        gold_summary="Try 97.5kg on Bench Press; consider reducing Incline DB Press volume",
        gold_rationale="Bench Press progressing well. Incline DB Press shows low RIR (0.5) suggesting near-failure consistently — volume may need reduction.",
        quality_requirements=[
            "Conflicting signals addressed",
            "Balanced recommendation",
            "Each exercise handled differently",
        ],
        tags=["progression", "conflicting_signals", "multi_exercise"],
    ),
]


# =============================================================================
# EXERCISE_SCOPED (10): No routine context
# =============================================================================

EXERCISE_SCOPED_CASES = [
    RecommendationTestCase(
        id="es_001",
        category="exercise_scoped",
        analyzer_type="post_workout",
        training_data=build_progression_ready(
            exercise_name="Bench Press",
            exercise_id="bench-press",
            current_weight=80.0,
            weeks_stable=3,
            avg_rir=2.0,
            reps=8,
        ),
        user_state={
            "auto_pilot_enabled": False,
            "activeRoutineId": None,
            "routine_name": None,
            "template_id": None,
            "template_name": None,
        },
        expected_rec_type="progression",
        expected_signals=["80kg", "82.5kg", "8 reps", "3 weeks"],
        gold_summary="Ready to progress Bench Press to 82.5kg",
        gold_rationale="e1RM stable at 80kg x 8 for 3 weeks with RIR 2. Use this in your next workout or add it to a template.",
        quality_requirements=[
            "No template jargon",
            "Observation-first language",
            "Includes where to apply (next workout or template)",
        ],
        tags=["progression", "compound", "no_routine"],
    ),
    RecommendationTestCase(
        id="es_002",
        category="exercise_scoped",
        analyzer_type="post_workout",
        training_data=build_overreach(
            exercise_name="Barbell Row",
            exercise_id="barbell-row",
            current_weight=70.0,
            reps=8,
        ),
        user_state={
            "auto_pilot_enabled": False,
            "activeRoutineId": None,
        },
        expected_rec_type="deload",
        expected_signals=["70kg", "fatigue", "RIR"],
        gold_summary="Barbell Row: consider a lighter session at 63kg",
        gold_rationale="Avg RIR dropping below 1.0 across sessions. Consider backing off to recover before pushing again.",
        quality_requirements=[
            "No template references",
            "Observation + suggestion format",
        ],
        tags=["deload", "no_routine"],
    ),
    RecommendationTestCase(
        id="es_003",
        category="exercise_scoped",
        analyzer_type="weekly_review",
        training_data=build_progression_ready(
            exercise_name="Dumbbell Bench Press",
            exercise_id="db-bench",
            current_weight=32.0,
            weeks_stable=4,
            avg_rir=2.0,
            reps=10,
        ),
        user_state={
            "auto_pilot_enabled": False,
            "activeRoutineId": None,
        },
        expected_rec_type="progression",
        expected_signals=["32kg", "4 weeks"],
        gold_summary="Ready to progress Dumbbell Bench Press to 33.5kg",
        gold_rationale="Consistent 3x10 at 32kg for 4 weeks. Ready for a small increase. Use this in your next workout or add it to a template.",
        quality_requirements=[
            "Contextual for no-template user",
            "Suggests where to apply",
        ],
        tags=["progression", "no_routine", "weekly"],
    ),
    RecommendationTestCase(
        id="es_004",
        category="exercise_scoped",
        analyzer_type="post_workout",
        training_data=build_new_user(
            exercise_name="Goblet Squat",
            exercise_id="goblet-squat",
            current_weight=20.0,
            weeks_data=2,
            reps=12,
        ),
        user_state={
            "auto_pilot_enabled": False,
            "activeRoutineId": None,
        },
        expected_rec_type="progression",
        expected_signals=["20kg"],
        gold_summary="Ready to progress Goblet Squat to 21.25kg",
        gold_rationale="Consistent performance at 20kg with room to spare. Small increment suggested. Use this in your next workout or add it to a template.",
        quality_requirements=[
            "Specific weight values mentioned",
            "Observation-first language",
        ],
        tags=["new_user", "no_routine"],
    ),
    RecommendationTestCase(
        id="es_005",
        category="exercise_scoped",
        analyzer_type="post_workout",
        training_data=build_multi_exercise(
            exercises=[
                {"name": "Bench Press", "id": "bench-press", "weight": 80, "reps": 8, "rir": 2, "weeks_stable": 3},
                {"name": "Lat Pulldown", "id": "lat-pulldown", "weight": 60, "reps": 10, "rir": 2, "weeks_stable": 4},
            ],
        ),
        user_state={
            "auto_pilot_enabled": False,
            "activeRoutineId": None,
        },
        expected_rec_type="progression",
        expected_signals=["80kg", "60kg", "Bench Press", "Lat Pulldown"],
        gold_summary="Ready to progress Bench Press to 82.5kg and Lat Pulldown to 62.5kg",
        gold_rationale="Both exercises show stable performance. Try these weights in your next workout.",
        quality_requirements=[
            "Each exercise gets context",
            "No template language",
        ],
        tags=["progression", "multi_exercise", "no_routine"],
    ),
    RecommendationTestCase(
        id="es_006",
        category="exercise_scoped",
        analyzer_type="weekly_review",
        training_data=build_volume_imbalance(
            underserved_group="calves",
            weekly_sets=2,
            overserved_group="quadriceps",
            over_weekly_sets=20,
        ),
        user_state={
            "auto_pilot_enabled": False,
            "activeRoutineId": None,
        },
        expected_rec_type="volume_adjust",
        expected_signals=["calves", "2 sets", "quadriceps"],
        gold_summary="Calves getting minimal volume at 2 sets/week",
        gold_rationale="Calves at 2 sets/week while quadriceps at 20 sets/week. Consider adding calf work to your sessions.",
        quality_requirements=[
            "Insight + suggestion format",
            "No template jargon",
        ],
        tags=["volume_adjust", "no_routine"],
    ),
    RecommendationTestCase(
        id="es_007",
        category="exercise_scoped",
        analyzer_type="post_workout",
        training_data=build_sparse_history(
            exercise_name="Barbell Squat",
            exercise_id="barbell-squat",
            current_weight=60.0,
            weeks_data=1,
            reps=8,
        ),
        user_state={
            "auto_pilot_enabled": False,
            "activeRoutineId": None,
        },
        expected_rec_type="progression",
        expected_signals=[],
        gold_summary="",
        gold_rationale="",
        quality_requirements=[
            "No recommendation expected (only 1 week of data)",
            "Should be skipped gracefully",
        ],
        tags=["sparse_data", "skip", "no_routine"],
    ),
    RecommendationTestCase(
        id="es_008",
        category="exercise_scoped",
        analyzer_type="post_workout",
        training_data=build_bodyweight_exercise(
            exercise_name="Pull Up",
            exercise_id="pull-up",
            current_reps=8,
            weeks_stable=3,
            avg_rir=2.0,
        ),
        user_state={
            "auto_pilot_enabled": False,
            "activeRoutineId": None,
        },
        expected_rec_type="progression",
        expected_signals=["8 reps", "bodyweight"],
        gold_summary="Ready to progress Pull Up: try 9-10 reps",
        gold_rationale="Consistent 3x8 bodyweight pull ups with RIR 2. Progress by adding reps before adding weight.",
        quality_requirements=[
            "No weight change (bodyweight exercise)",
            "Rep-based progression",
        ],
        tags=["bodyweight", "rep_progression", "no_routine"],
    ),
    RecommendationTestCase(
        id="es_009",
        category="exercise_scoped",
        analyzer_type="post_workout",
        training_data=build_stall_detected(
            exercise_name="Overhead Press",
            exercise_id="overhead-press",
            current_weight=45.0,
            weeks_stalled=5,
            reps=8,
        ),
        user_state={
            "auto_pilot_enabled": False,
            "activeRoutineId": None,
        },
        expected_rec_type="progression",
        expected_signals=["45kg", "5 weeks"],
        gold_summary="Ready to progress Overhead Press to 47.5kg",
        gold_rationale="e1RM stable at 45kg for 5 weeks. Trying a small increment may help break through the plateau. Use this in your next workout or add it to a template.",
        quality_requirements=[
            "Specific weight values mentioned",
            "Actionable suggestion",
            "No template references",
        ],
        tags=["stall", "progression", "no_routine"],
    ),
    RecommendationTestCase(
        id="es_010",
        category="exercise_scoped",
        analyzer_type="post_workout",
        training_data=build_progression_ready(
            exercise_name="Chest Fly Machine",
            exercise_id="chest-fly-machine",
            current_weight=0.0,  # No history
            weeks_stable=0,
            avg_rir=0,
            reps=0,
            no_history=True,
        ),
        user_state={
            "auto_pilot_enabled": False,
            "activeRoutineId": None,
        },
        expected_rec_type="progression",
        expected_signals=[],
        gold_summary="",
        gold_rationale="",
        quality_requirements=[
            "Should be skipped gracefully (no history)",
            "No recommendation generated",
        ],
        tags=["no_history", "skip", "no_routine"],
    ),
]


# =============================================================================
# ALL CASES — combined registry
# =============================================================================

ALL_CASES: list = AUTO_PILOT_CASES + PENDING_REVIEW_CASES + EXERCISE_SCOPED_CASES

CASES_BY_ID: dict = {c.id: c for c in ALL_CASES}

CASES_BY_CATEGORY: dict = {}
for _case in ALL_CASES:
    CASES_BY_CATEGORY.setdefault(_case.category, []).append(_case)

CATEGORIES = ["auto_pilot", "pending_review", "exercise_scoped"]


def get_cases(
    category: str = None,
    case_id: str = None,
    tags: list = None,
) -> list:
    """Filter test cases by category, ID, or tags."""
    cases = ALL_CASES

    if case_id:
        if case_id in CASES_BY_ID:
            return [CASES_BY_ID[case_id]]
        return []

    if category:
        cases = [c for c in cases if c.category == category]

    if tags:
        cases = [c for c in cases if any(t in c.tags for t in tags)]

    return cases
