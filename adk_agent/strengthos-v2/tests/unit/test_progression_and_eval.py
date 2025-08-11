import json
from app.strengthos_agent import (
    compute_progression_suggestions,
    apply_progression_to_template,
    evaluate_template,
    evaluate_routine,
    enforce_brevity,
)


def test_progression_rir_anchored_increase_weight():
    history = [{
        "sets": [
            {"reps": 8, "rir": 1, "weight": 60.0},
            {"reps": 8, "rir": 1, "weight": 60.0},
            {"reps": 8, "rir": 1, "weight": 60.0},
        ]
    }]
    out = compute_progression_suggestions(history, policy="rir_anchored", min_increment_kg=2.5)
    assert out["policy"] == "rir_anchored"
    assert all(s["action"] == "increase_weight" and s["by_kg"] == 2.5 for s in out["suggestions"])  # type: ignore[index]


def test_apply_progression_to_template_weight_increment():
    template = {
        "name": "Push Day",
        "exercises": [
            {
                "name": "incline bench press",
                "exercise_id": "bench_incline",
                "sets": [
                    {"reps": 10, "weight": 40.0},
                    {"reps": 10, "weight": 40.0},
                ],
            }
        ],
    }
    suggestions = [
        {"action": "increase_weight", "by_kg": 2.5},
        {"action": "increase_weight", "by_kg": 2.5},
    ]
    new_t = apply_progression_to_template(template, "bench_incline", suggestions)
    weights = [s["weight"] for s in new_t["exercises"][0]["sets"]]
    assert weights == [42.5, 42.5]


def test_evaluate_template_detects_redundancy_and_order():
    tpl = {
        "exercises": [
            {"name": "curl", "sets": [{"reps": 12, "weight": 10}]},
            {"name": "barbell back squat", "sets": [{"reps": 8, "weight": 60}]},
            {"name": "curl", "sets": [{"reps": 12, "weight": 10}]},
        ]
    }
    ev = evaluate_template(tpl)
    assert ev["metrics"]["totalSets"] == 3
    # Redundancy present (curl twice)
    assert any("redundantExercises" in w for w in ev.get("warnings", []))
    # Compound late warning (squat after isolation)
    assert any("order" in w for w in ev.get("warnings", []))


def test_evaluate_routine_symmetry():
    templates = [
        {
            "exercises": [
                {"name": "bench press", "sets": [{"reps": 8, "weight": 80}]},
                {"name": "bench press", "sets": [{"reps": 8, "weight": 80}]},
            ]
        },
        {
            "exercises": [
                {"name": "romanian deadlift", "sets": [{"reps": 10, "weight": 100}]}
            ]
        },
    ]
    ev = evaluate_routine(templates)
    assert ev["metrics"]["totalSets"] == 3
    assert "setsPerGroup" in ev["metrics"]


def test_enforce_brevity_trims_bullets_and_sentences():
    txt = """
# Title
- a
- b
- c
- d
- e
- f
- g
"""
    out = enforce_brevity(txt, max_bullets=5)
    assert out["text"].count("\n-") <= 5

    txt2 = "This is one. This is two. This is three. This is four. This is five. This is six. This is seven."
    out2 = enforce_brevity(txt2, max_sentences=6)
    assert out2["text"].count(".") >= 1


