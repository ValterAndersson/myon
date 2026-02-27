#!/usr/bin/env python3
"""
Integration tests for Shell Agent tool connectivity.

Tests every Firebase Function endpoint that the agent calls, using the same
HTTP client (CanvasFunctionsClient) the agent uses. This isolates whether
issues are in the data pipeline vs. LLM behavior.

Usage:
    # Run all tests against production Firebase Functions
    python3 -m pytest tests/test_tool_connectivity.py -v

    # Run a specific test
    python3 -m pytest tests/test_tool_connectivity.py -v -k test_search_exercises

    # Run with a different user
    TEST_USER_ID=abc123 python3 -m pytest tests/test_tool_connectivity.py -v

Environment:
    TEST_USER_ID: Firebase UID to test with (default: Y4SJuNPOasaltF7TuKm1QCT7JIA3)
    MYON_FUNCTIONS_BASE_URL: Firebase Functions base URL (default: production)
    MYON_API_KEY: API key (required — set in env)
"""

import os
import sys
import pytest
import requests

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.libs.tools_canvas.client import CanvasFunctionsClient
from app.libs.tools_common.response_helpers import parse_api_response

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
TEST_USER_ID = os.getenv("TEST_USER_ID", "Y4SJuNPOasaltF7TuKm1QCT7JIA3")
BASE_URL = os.getenv(
    "MYON_FUNCTIONS_BASE_URL",
    "https://us-central1-myon-53d85.cloudfunctions.net",
)
API_KEY = os.environ["MYON_API_KEY"]  # Required — set in env, never hardcode


def safe_call(fn, *args, **kwargs):
    """Call a client method, returning (resp, error_msg) tuple.

    Catches HTTPError so tests can assert on connectivity failures
    with clear messages instead of raw tracebacks.
    """
    try:
        return fn(*args, **kwargs), None
    except requests.HTTPError as e:
        status = e.response.status_code if e.response is not None else "?"
        return None, f"HTTP {status}: {e}"


@pytest.fixture(scope="module")
def client():
    """Shared HTTP client — same as the agent uses."""
    return CanvasFunctionsClient(
        base_url=BASE_URL,
        api_key=API_KEY,
        timeout_seconds=30,
    )


# ============================================================================
# 1. EXERCISE SEARCH (global catalog, no user required)
# ============================================================================


class TestSearchExercises:
    """Verify the exercise catalog is reachable and returns results."""

    def test_search_by_muscle_group(self, client):
        """Search by muscle_group should return exercises."""
        resp = client.search_exercises(muscle_group="chest", limit=5)
        success, data, err = parse_api_response(resp)
        assert success, f"search_exercises(muscle_group=chest) failed: {err}"
        items = data.get("items", [])
        assert len(items) > 0, "No chest exercises found in catalog"
        # Verify items have IDs and names
        for item in items:
            assert item.get("id"), f"Exercise missing id: {item}"
            assert item.get("name"), f"Exercise missing name: {item}"

    def test_search_by_query_text(self, client):
        """Free-text search should find exercises by name."""
        resp = client.search_exercises(query="bench press", limit=5)
        success, data, err = parse_api_response(resp)
        assert success, f"search_exercises(query=bench press) failed: {err}"
        items = data.get("items", [])
        assert len(items) > 0, "No exercises found for 'bench press'"
        # At least one result should contain "bench" in the name
        names = [i.get("name", "").lower() for i in items]
        assert any("bench" in n for n in names), f"No 'bench' in results: {names}"

    def test_search_by_movement_type(self, client):
        """Search by movement_type (push/pull) should work."""
        resp = client.search_exercises(movement_type="push", limit=5)
        success, data, err = parse_api_response(resp)
        assert success, f"search_exercises(movement_type=push) failed: {err}"
        items = data.get("items", [])
        assert len(items) > 0, "No push exercises found"

    def test_search_fields_lean(self, client):
        """Lean field projection should return minimal fields."""
        resp = client.search_exercises(muscle_group="back", limit=3, fields="lean")
        success, data, err = parse_api_response(resp)
        assert success, f"search_exercises(fields=lean) failed: {err}"
        items = data.get("items", [])
        assert len(items) > 0, "No back exercises found (lean)"
        for item in items:
            assert "id" in item
            assert "name" in item

    def test_search_fields_minimal(self, client):
        """Minimal field projection should return only id and name."""
        resp = client.search_exercises(muscle_group="legs", limit=3, fields="minimal")
        success, data, err = parse_api_response(resp)
        assert success, f"search_exercises(fields=minimal) failed: {err}"
        items = data.get("items", [])
        assert len(items) > 0, "No legs exercises found (minimal)"

    def test_search_empty_query_returns_results(self, client):
        """Search with no filters should still return exercises."""
        resp = client.search_exercises(limit=5)
        success, data, err = parse_api_response(resp)
        assert success, f"search_exercises(no filters) failed: {err}"
        items = data.get("items", [])
        assert len(items) > 0, "Empty search returned no exercises"


# ============================================================================
# 2. PLANNING CONTEXT (user-specific: routine, templates, recent workouts)
# ============================================================================


class TestPlanningContext:
    """Verify planning context returns user data correctly."""

    def test_get_planning_context_basic(self, client):
        """Planning context should return user, templates, workouts."""
        resp = client.get_planning_context(TEST_USER_ID)
        success, data, err = parse_api_response(resp)
        assert success, f"get_planning_context failed: {err}"
        assert "user" in data, "Missing 'user' in planning context"
        assert data["user"] is not None, "User is null"
        assert data["user"].get("id") == TEST_USER_ID, "User ID mismatch"

    def test_planning_context_has_workouts(self, client):
        """Planning context should include recent workouts summary."""
        resp = client.get_planning_context(TEST_USER_ID, workout_limit=5)
        success, data, err = parse_api_response(resp)
        assert success, f"get_planning_context failed: {err}"
        workouts = data.get("recentWorkoutsSummary")
        assert workouts is not None, "recentWorkoutsSummary is None"
        assert len(workouts) > 0, "No recent workouts found for user"
        # Verify workout structure
        w = workouts[0]
        assert "id" in w, "Workout missing id"
        assert "exercises" in w, "Workout missing exercises"
        assert len(w["exercises"]) > 0, "Workout has no exercises"
        # Verify exercise structure (should have name + set count)
        ex = w["exercises"][0]
        assert "name" in ex, f"Exercise in workout missing name: {ex}"

    def test_planning_context_with_template_exercises(self, client):
        """When includeTemplateExercises=True, templates should have exercises."""
        resp = client.get_planning_context(
            TEST_USER_ID,
            include_template_exercises=True,
        )
        success, data, err = parse_api_response(resp)
        assert success, f"get_planning_context(includeTemplateExercises) failed: {err}"
        templates = data.get("templates", [])
        if templates:
            # At least one template should have exercises array
            has_exercises = any(
                isinstance(t.get("exercises"), list) and len(t["exercises"]) > 0
                for t in templates
            )
            assert has_exercises, "No template has exercises despite includeTemplateExercises=True"


# ============================================================================
# 3. WORKOUT-TO-TEMPLATE FLOW (the failing scenario)
# ============================================================================


class TestWorkoutToTemplateFlow:
    """
    Reproduce the reported issue: agent gets workout exercises but can't
    find them in the catalog. This test simulates the exact flow.
    """

    def test_workout_exercises_findable_in_catalog(self, client):
        """
        Get last workout exercises, then search each one in the catalog.
        This is the exact flow the agent should use for 'make a template
        from my last workout'.
        """
        # Step 1: Get planning context with recent workouts
        resp = client.get_planning_context(TEST_USER_ID, workout_limit=1)
        success, data, err = parse_api_response(resp)
        assert success, f"get_planning_context failed: {err}"

        workouts = data.get("recentWorkoutsSummary", [])
        assert len(workouts) > 0, "No workouts to test with"

        last_workout = workouts[0]
        exercises = last_workout.get("exercises", [])
        assert len(exercises) > 0, "Last workout has no exercises"

        # Step 2: Try to find each exercise in the catalog
        not_found = []
        found = []
        for ex in exercises:
            name = ex.get("name", "")
            if not name:
                continue
            search_resp = client.search_exercises(query=name, limit=3)
            s, d, e = parse_api_response(search_resp)
            items = d.get("items", []) if s else []
            if items:
                found.append({"name": name, "catalog_id": items[0].get("id")})
            else:
                not_found.append(name)

        print(f"\n  Found in catalog ({len(found)}):")
        for f in found:
            print(f"    + {f['name']} -> {f['catalog_id']}")
        if not_found:
            print(f"  NOT found in catalog ({len(not_found)}):")
            for n in not_found:
                print(f"    x {n}")

        assert len(not_found) == 0, (
            f"These exercises from the last workout were NOT found in the catalog: {not_found}"
        )


# ============================================================================
# 4. TRAINING ANALYTICS v2 (set_facts / series)
# ============================================================================


class TestTrainingAnalytics:
    """Verify the token-safe analytics endpoints work."""

    def test_muscle_group_progress(self, client):
        """Muscle group progress should return weekly data."""
        resp = client.get_muscle_group_summary(
            TEST_USER_ID, "chest", window_weeks=8
        )
        success, data, err = parse_api_response(resp)
        assert success, f"get_muscle_group_summary(chest) failed: {err}"
        assert "weekly_points" in data or "weeks" in data, (
            f"Missing weekly data. Keys: {list(data.keys())}"
        )

    def test_exercise_progress_by_name(self, client):
        """Exercise progress via fuzzy name search should work."""
        resp, http_err = safe_call(
            client.get_exercise_summary,
            TEST_USER_ID, exercise_name="bench press", window_weeks=8,
        )
        assert http_err is None, f"get_exercise_summary(bench press) HTTP error: {http_err}"
        success, data, err = parse_api_response(resp)
        assert success, f"get_exercise_summary(bench press) failed: {err}"
        # Should have resolved an exercise_id via name search
        assert "exercise_id" in data or "exercise_name" in data or "weekly_points" in data, (
            f"Unexpected response shape. Keys: {list(data.keys())}"
        )

    def test_query_training_sets(self, client):
        """Raw set query should return set facts."""
        resp, http_err = safe_call(
            client.query_sets,
            TEST_USER_ID, muscle_group="chest", limit=10,
        )
        assert http_err is None, f"query_sets(chest) HTTP error: {http_err}"
        success, data, err = parse_api_response(resp)
        assert success, f"query_sets(chest) failed: {err}"
        # Data should be a list or have a 'data' key with a list
        if isinstance(data, list):
            sets = data
        else:
            sets = data.get("sets", data.get("data", []))
        # User may or may not have chest data; just verify no error
        assert isinstance(sets, list), f"Sets is not a list: {type(sets)}"

    def test_query_training_sets_by_exercise_name(self, client):
        """Raw set query by exercise name should work."""
        resp, http_err = safe_call(
            client.query_sets,
            TEST_USER_ID, exercise_name="squat", limit=5,
        )
        assert http_err is None, f"query_sets(exercise_name=squat) HTTP error: {http_err}"
        success, data, err = parse_api_response(resp)
        assert success, f"query_sets(exercise_name=squat) failed: {err}"


# ============================================================================
# 5. PRE-COMPUTED ANALYSIS
# ============================================================================


class TestTrainingAnalysis:
    """Verify the pre-computed analysis endpoint works."""

    def test_get_all_sections(self, client):
        """Get all analysis sections in one call."""
        resp, http_err = safe_call(
            client.get_analysis_summary, TEST_USER_ID,
        )
        assert http_err is None, f"get_analysis_summary HTTP error: {http_err}"
        success, data, err = parse_api_response(resp)
        assert success, f"get_analysis_summary failed: {err}"
        # At least one section should be present
        sections_found = [
            k for k in ["insights", "weekly_review"]
            if k in data
        ]
        assert len(sections_found) > 0, (
            f"No analysis sections returned. Keys: {list(data.keys())}"
        )

    def test_get_insights_only(self, client):
        """Get just the insights section."""
        resp, http_err = safe_call(
            client.get_analysis_summary,
            TEST_USER_ID, sections=["insights"],
        )
        assert http_err is None, f"get_analysis_summary(insights) HTTP error: {http_err}"
        success, data, err = parse_api_response(resp)
        assert success, f"get_analysis_summary(insights) failed: {err}"

    def test_get_weekly_review(self, client):
        """Get the weekly review."""
        resp, http_err = safe_call(
            client.get_analysis_summary,
            TEST_USER_ID, sections=["weekly_review"],
        )
        assert http_err is None, f"get_analysis_summary(weekly_review) HTTP error: {http_err}"
        success, data, err = parse_api_response(resp)
        assert success, f"get_analysis_summary(weekly_review) failed: {err}"


# ============================================================================
# 6. USER PROFILE
# ============================================================================


class TestUserProfile:
    """Verify user profile endpoints work."""

    def test_get_user(self, client):
        """Get user profile should return data."""
        resp = client.get_user(TEST_USER_ID)
        success, data, err = parse_api_response(resp)
        assert success, f"get_user failed: {err}"
        assert data is not None, "User data is None"


# ============================================================================
# 7. TRAINING CONTEXT (routine structure)
# ============================================================================


class TestTrainingContext:
    """Verify training context (routine/template structure)."""

    def test_get_planning_context_routine(self, client):
        """If user has an active routine, it should be returned."""
        resp = client.get_planning_context(TEST_USER_ID)
        success, data, err = parse_api_response(resp)
        assert success, f"get_planning_context failed: {err}"
        # Log what we got for debugging
        has_routine = data.get("activeRoutine") is not None
        has_templates = len(data.get("templates", [])) > 0
        has_next = data.get("nextWorkout") is not None
        print(f"\n  activeRoutine: {'yes' if has_routine else 'no'}")
        print(f"  templates: {len(data.get('templates', []))}")
        print(f"  nextWorkout: {'yes' if has_next else 'no'}")
        print(f"  recentWorkouts: {len(data.get('recentWorkoutsSummary', []))}")
