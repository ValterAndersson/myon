"""
Coach Skills - Pure functions for analytics and coaching data access.

These are extracted from coach_agent.py and refactored to:
- Take explicit parameters (no global _context dict)
- Return structured results
- Be usable by both Shell Agent tools and direct calls

All functions take user_id explicitly rather than reading from global state.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.libs.tools_canvas.client import CanvasFunctionsClient
from app.libs.tools_common.response_helpers import (
    parse_api_response,
    format_validation_error_for_agent,
)

logger = logging.getLogger(__name__)

# Singleton client (stateless, just holds config)
_client: Optional[CanvasFunctionsClient] = None


def _get_client() -> CanvasFunctionsClient:
    """Get or create the canvas client."""
    global _client
    if _client is None:
        base_url = os.getenv("MYON_FUNCTIONS_BASE_URL", "https://us-central1-myon-53d85.cloudfunctions.net")
        api_key = os.getenv("MYON_API_KEY", "myon-agent-key-2024")
        _client = CanvasFunctionsClient(base_url=base_url, api_key=api_key)
    return _client


@dataclass
class SkillResult:
    """Standardized result from a skill."""
    success: bool
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        if not self.success:
            return {"error": self.error or "Unknown error"}
        return self.data


# ============================================================================
# TRAINING CONTEXT
# ============================================================================

def get_training_context(
    user_id: str,
    client: Optional[CanvasFunctionsClient] = None,
) -> SkillResult:
    """
    Get user's training structure: active routine, split type, patterns.
    
    Args:
        user_id: User ID (required, no fallback)
        client: Optional client instance (for Worker injection)
        
    Returns:
        SkillResult with activeRoutine, templates, recentWorkoutsSummary
    """
    if not user_id:
        return SkillResult(success=False, error="user_id is required")
    
    logger.info("get_training_context uid=%s", user_id)
    
    try:
        api_client = client or _get_client()
        resp = api_client.get_planning_context(user_id)
        success, data, error_details = parse_api_response(resp)
        
        if not success:
            logger.error("get_training_context failed: %s", error_details)
            return SkillResult(success=False, error=str(error_details))
        
        return SkillResult(
            success=True,
            data={
                "activeRoutine": data.get("activeRoutine"),
                "templates": data.get("templates"),
                "recentWorkoutsSummary": data.get("recentWorkoutsSummary"),
            }
        )
    except Exception as e:
        logger.error("get_training_context exception: %s", e)
        return SkillResult(success=False, error=str(e))




# ============================================================================
# USER PROFILE
# ============================================================================

def get_user_profile(user_id: str) -> SkillResult:
    """
    Get user's fitness profile: goals, experience, preferences.
    
    Args:
        user_id: User ID (required)
        
    Returns:
        SkillResult with user profile data
    """
    if not user_id:
        return SkillResult(success=False, error="user_id is required")
    
    logger.info("get_user_profile uid=%s", user_id)
    
    try:
        resp = _get_client().get_user(user_id)
        success, data, error_details = parse_api_response(resp)
        
        if not success:
            return SkillResult(success=False, error=str(error_details))
        
        return SkillResult(success=True, data=data)
    except Exception as e:
        logger.error("get_user_profile exception: %s", e)
        return SkillResult(success=False, error=str(e))


# ============================================================================
# EXERCISE LOOKUP
# ============================================================================

def search_exercises(
    muscle_group: Optional[str] = None,
    movement_type: Optional[str] = None,
    category: Optional[str] = None,
    equipment: Optional[str] = None,
    query: Optional[str] = None,
    limit: int = 10,
    fields: str = "full",
) -> SkillResult:
    """
    Search exercise catalog.
    
    Args:
        muscle_group: Target muscle group (comma-separated OK)
        movement_type: push, pull, hinge, squat, etc.
        category: compound, isolation, bodyweight
        equipment: barbell, dumbbell, cable, machine
        query: Free text search
        limit: Max results (default 10)
        fields: Output format - "minimal" (id+name), "lean" (id+name+category+equipment), "full" (all)
        
    Returns:
        SkillResult with list of exercises
    """
    logger.info("search_exercises query=%s muscle=%s fields=%s", query, muscle_group, fields)
    
    try:
        resp = _get_client().search_exercises(
            muscle_group=muscle_group,
            movement_type=movement_type,
            category=category,
            equipment=equipment,
            query=query,
            limit=limit,
            fields=fields,
        )
        
        success, data, error_details = parse_api_response(resp)
        if not success:
            return SkillResult(success=False, error=str(error_details))
            
    except Exception as e:
        logger.error("search_exercises exception: %s", e)
        return SkillResult(success=False, error=str(e))
    
    # Return items directly from API (projection is handled server-side via fields param)
    items = data.get("items") or []
    
    return SkillResult(
        success=True,
        data={"items": items, "count": len(items), "fields": fields}
    )


def get_exercise_details(exercise_id: str) -> SkillResult:
    """
    Get detailed info for a specific exercise.
    
    Args:
        exercise_id: Exercise ID
        
    Returns:
        SkillResult with exercise details
    """
    logger.info("get_exercise_details id=%s", exercise_id)
    
    try:
        resp = _get_client().search_exercises(query=exercise_id, limit=1)
        data = resp.get("data") or resp
        items = data.get("items") or []
        
        if items:
            ex = items[0]
            return SkillResult(
                success=True,
                data={
                    "id": ex.get("id"),
                    "name": ex.get("name"),
                    "category": ex.get("category"),
                    "primary_muscles": ex.get("muscles", {}).get("primary", []),
                    "secondary_muscles": ex.get("muscles", {}).get("secondary", []),
                    "equipment": ex.get("equipment", []),
                    "instructions": ex.get("instructions", []),
                    "tips": ex.get("tips", []),
                    "common_mistakes": ex.get("commonMistakes", []),
                }
            )
        return SkillResult(success=False, error="Exercise not found")
    except Exception as e:
        logger.error("get_exercise_details exception: %s", e)
        return SkillResult(success=False, error=str(e))


# ============================================================================
# TOKEN-SAFE TRAINING ANALYTICS v2
# These skills use the new bounded, paginated endpoints that prevent timeouts.
# See: docs/TRAINING_ANALYTICS_API_V2_SPEC.md
# ============================================================================

def get_muscle_group_progress(
    user_id: str,
    muscle_group: str,
    window_weeks: int = 12,
    include_distribution: bool = False,
    client: Optional[CanvasFunctionsClient] = None,
) -> SkillResult:
    """
    Get comprehensive muscle group progress summary - TOKEN SAFE.
    
    PREFERRED for answering "How is my X developing?" questions.
    Response is bounded (<15KB) with weekly series, top exercises,
    and deterministic flags (plateau, deload, overreach).
    
    Valid muscle_groups:
        chest, back, shoulders, arms, core, legs, glutes,
        hip_flexors, calves, forearms, neck, cardio
    
    Args:
        user_id: User ID (required)
        muscle_group: Canonical muscle group ID (e.g., "chest", "back")
        window_weeks: Analysis window 1-52 (default 12)
        include_distribution: Include rep range distribution
        client: Optional client for dependency injection
        
    Returns:
        SkillResult with weekly_points, top_exercises, summary, flags
        
    Recovery:
        - Returns valid muscle groups on 400 error
        - Returns empty data if no training history
    """
    if not user_id:
        return SkillResult(success=False, error="user_id is required")
    
    window_weeks = max(1, min(52, window_weeks))
    logger.info("get_muscle_group_progress uid=%s group=%s weeks=%d", user_id, muscle_group, window_weeks)
    
    try:
        api_client = client or _get_client()
        resp = api_client.get_muscle_group_summary(
            user_id,
            muscle_group,
            window_weeks=window_weeks,
            include_distribution=include_distribution,
        )
        success, data, error_details = parse_api_response(resp)
        
        if not success:
            error_msg = str(error_details)
            # Include valid options for recovery
            if "invalid" in error_msg.lower() or "not found" in error_msg.lower():
                error_msg += "\n\nValid muscle_groups: chest, back, shoulders, arms, core, legs, glutes, hip_flexors, calves, forearms, neck, cardio"
            return SkillResult(success=False, error=error_msg)
        
        return SkillResult(success=True, data=data)
    except Exception as e:
        logger.error("get_muscle_group_progress exception: %s", e)
        return SkillResult(success=False, error=str(e))


def get_muscle_progress(
    user_id: str,
    muscle: str,
    window_weeks: int = 12,
    client: Optional[CanvasFunctionsClient] = None,
) -> SkillResult:
    """
    Get individual muscle progress summary - TOKEN SAFE.
    
    Use for specific muscle questions like "How are my rhomboids?"
    or "How is my front delt developing?"
    
    Valid muscles (examples):
        pectoralis_major, pectoralis_minor, latissimus_dorsi, rhomboids,
        trapezius_upper, trapezius_middle, trapezius_lower, erector_spinae,
        deltoid_anterior, deltoid_lateral, deltoid_posterior, rotator_cuff,
        biceps_brachii, triceps_brachii, brachialis, brachioradialis,
        rectus_abdominis, obliques, transverse_abdominis,
        quadriceps, hamstrings, gluteus_maximus, gluteus_medius,
        gastrocnemius, soleus, tibialis_anterior
        
    Args:
        user_id: User ID (required)
        muscle: Canonical muscle ID (e.g., "rhomboids", "deltoid_anterior")
        window_weeks: Analysis window 1-52 (default 12)
        client: Optional client for dependency injection
        
    Returns:
        SkillResult with weekly_points, top_exercises, summary, flags
    """
    if not user_id:
        return SkillResult(success=False, error="user_id is required")
    
    window_weeks = max(1, min(52, window_weeks))
    logger.info("get_muscle_progress uid=%s muscle=%s weeks=%d", user_id, muscle, window_weeks)
    
    try:
        api_client = client or _get_client()
        resp = api_client.get_muscle_summary(
            user_id,
            muscle,
            window_weeks=window_weeks,
        )
        success, data, error_details = parse_api_response(resp)
        
        if not success:
            error_msg = str(error_details)
            # Include valid options for recovery
            if "invalid" in error_msg.lower() or "not found" in error_msg.lower():
                error_msg += "\n\nCommon muscles: pectoralis_major, latissimus_dorsi, rhomboids, deltoid_anterior, deltoid_lateral, deltoid_posterior, biceps_brachii, triceps_brachii, quadriceps, hamstrings, gluteus_maximus"
            return SkillResult(success=False, error=error_msg)
        
        return SkillResult(success=True, data=data)
    except Exception as e:
        logger.error("get_muscle_progress exception: %s", e)
        return SkillResult(success=False, error=str(e))


def get_exercise_progress(
    user_id: str,
    exercise_id: Optional[str] = None,
    exercise_name: Optional[str] = None,
    window_weeks: int = 12,
    client: Optional[CanvasFunctionsClient] = None,
) -> SkillResult:
    """
    Get exercise progress summary with PR tracking - TOKEN SAFE.
    
    Use for questions like "How is my bench press progressing?"
    Includes weekly series, last session recap, and PR markers.
    
    ACCEPTS EITHER exercise_id OR exercise_name:
    - exercise_id: Direct lookup by catalog ID
    - exercise_name: Fuzzy name search (e.g., "bench press", "squats", "deadlift")
    
    Args:
        user_id: User ID (required)
        exercise_id: Exercise ID from catalog (optional if exercise_name provided)
        exercise_name: Exercise name for fuzzy search (e.g., "bench press")
        window_weeks: Analysis window 1-52 (default 12)
        client: Optional client for dependency injection
        
    Returns:
        SkillResult with weekly_points, last_session, pr_markers, flags
        
    Example:
        get_exercise_progress(user_id, exercise_name="bench press")
        get_exercise_progress(user_id, exercise_id="barbell-bench-press")
    """
    if not user_id:
        return SkillResult(success=False, error="user_id is required")
    
    if not exercise_id and not exercise_name:
        return SkillResult(success=False, error="exercise_id or exercise_name is required")
    
    window_weeks = max(1, min(52, window_weeks))
    logger.info("get_exercise_progress uid=%s exercise_id=%s exercise_name=%s weeks=%d", 
                user_id, exercise_id, exercise_name, window_weeks)
    
    try:
        api_client = client or _get_client()
        resp = api_client.get_exercise_summary(
            user_id,
            exercise_id=exercise_id,
            exercise_name=exercise_name,
            window_weeks=window_weeks,
        )
        success, data, error_details = parse_api_response(resp)
        
        if not success:
            return SkillResult(success=False, error=str(error_details))
        
        return SkillResult(success=True, data=data)
    except Exception as e:
        logger.error("get_exercise_progress exception: %s", e)
        return SkillResult(success=False, error=str(e))


def query_training_sets(
    user_id: str,
    muscle_group: Optional[str] = None,
    muscle: Optional[str] = None,
    exercise_ids: Optional[List[str]] = None,
    exercise_name: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    include_warmups: bool = False,
    limit: int = 50,
    client: Optional[CanvasFunctionsClient] = None,
) -> SkillResult:
    """
    Query individual set facts with filters - FOR DRILLDOWN ONLY.
    
    EXACTLY ONE target filter is required: muscle_group, muscle, exercise_ids, or exercise_name.
    Use this only when you need raw set data for evidence.
    Prefer summary endpoints for general questions.
    
    Args:
        user_id: User ID (required)
        muscle_group: Filter by muscle group (mutually exclusive)
        muscle: Filter by specific muscle (mutually exclusive)
        exercise_ids: Filter by exercise IDs, max 10 (mutually exclusive)
        exercise_name: Filter by exercise name (fuzzy search, e.g., "bench press")
        start: Start date YYYY-MM-DD
        end: End date YYYY-MM-DD
        include_warmups: Include warmup sets (default false)
        limit: Max results per page (default 50, max 200)
        client: Optional client for dependency injection
        
    Returns:
        SkillResult with array of set facts
        
    Error Recovery:
        - Returns 400 if zero or multiple targets provided
        - Validates muscle_group/muscle against taxonomy
    """
    if not user_id:
        return SkillResult(success=False, error="user_id is required")
    
    # Validate exactly one target
    targets_provided = sum([
        muscle_group is not None,
        muscle is not None,
        exercise_ids is not None and len(exercise_ids) > 0,
        exercise_name is not None,
    ])
    
    if targets_provided == 0:
        return SkillResult(
            success=False, 
            error="Exactly one target required: muscle_group, muscle, exercise_ids, or exercise_name"
        )
    if targets_provided > 1:
        return SkillResult(
            success=False,
            error="Only one target allowed. Specify muscle_group OR muscle OR exercise_ids OR exercise_name, not multiple."
        )
    
    limit = max(1, min(200, limit))
    logger.info("query_training_sets uid=%s group=%s muscle=%s exIds=%s exName=%s", 
                user_id, muscle_group, muscle, exercise_ids, exercise_name)
    
    try:
        api_client = client or _get_client()
        resp = api_client.query_sets(
            user_id,
            muscle_group=muscle_group,
            muscle=muscle,
            exercise_ids=exercise_ids,
            exercise_name=exercise_name,
            start=start,
            end=end,
            include_warmups=include_warmups,
            limit=limit,
        )
        success, data, error_details = parse_api_response(resp)
        
        if not success:
            error_msg = str(error_details)
            if "invalid" in error_msg.lower():
                error_msg += "\n\nValid muscle_groups: chest, back, shoulders, arms, core, legs, glutes"
            return SkillResult(success=False, error=error_msg)
        
        # Wrap in consistent structure
        if isinstance(data, list):
            return SkillResult(success=True, data={"sets": data, "count": len(data)})
        return SkillResult(success=True, data=data)
    except Exception as e:
        logger.error("query_training_sets exception: %s", e)
        return SkillResult(success=False, error=str(e))


# ============================================================================
# PRE-COMPUTED ANALYSIS SUMMARIES
# ============================================================================

def get_training_analysis(
    user_id: str,
    sections: Optional[List[str]] = None,
    limit: int = 5,
    client: Optional[CanvasFunctionsClient] = None,
) -> SkillResult:
    """
    Get pre-computed AI training analysis — single call for all sections.

    Returns up to 2 sections of pre-computed analysis. Default: all sections.

    Args:
        user_id: User ID (required)
        sections: Optional filter. Valid: "insights", "weekly_review"
            Default (None): returns all available sections.
        limit: Max insights to return (default 5)
        client: Optional client instance (for Worker injection)

    Returns:
        SkillResult with requested sections:

        insights: [{
            id, type: "post_workout",
            workout_id, workout_date,
            summary,
            highlights: [{ type, message, exercise_id? }],
            flags: [{ type, severity, message }],
            recommendations: [{ type, target, action, confidence }],
            created_at, expires_at
        }]

        weekly_review: {
            id (YYYY-WNN), week_ending,
            summary,
            training_load: { sessions, total_sets, total_volume, vs_last_week },
            muscle_balance: [{ muscle_group, weekly_sets, trend, status }],
            exercise_trends: [{ exercise_name, trend, e1rm_slope, note }],
            progression_candidates: [{ exercise_name, current_weight, suggested_weight, rationale, confidence }],
            stalled_exercises: [{ exercise_name, weeks_stalled, suggested_action, rationale }],
            periodization: {
                current_phase: "hypertrophy | strength | endurance | mixed",
                weeks_in_phase: number,
                suggestion: "phase change recommendation if applicable",
                reasoning: "evidence from data"
            },
            routine_recommendations: [
                {
                    type: "add_exercise | remove_exercise | frequency_change | volume_adjust | restructure",
                    target: "muscle group or template name",
                    suggestion: "specific recommendation",
                    reasoning: "evidence from data"
                }
            ],
            fatigue_status: {
                overall_acwr: number,
                interpretation: "optimal | underloading | overreaching | high_overreach",
                flags: [{ muscle, acwr, concern }],
                recommendation: "text"
            }
        }
    """
    if not user_id:
        return SkillResult(success=False, error="user_id is required")

    logger.info(
        "get_training_analysis uid=%s sections=%s limit=%d",
        user_id, sections, limit,
    )

    try:
        api_client = client or _get_client()
        resp = api_client.get_analysis_summary(
            user_id,
            sections=sections,
            limit=limit,
        )
        success, data, error_details = parse_api_response(resp)

        if not success:
            logger.error("get_training_analysis failed: %s", error_details)
            return SkillResult(success=False, error=str(error_details))

        return SkillResult(success=True, data=data)
    except Exception as e:
        logger.error("get_training_analysis exception: %s", e)
        return SkillResult(success=False, error=str(e))


__all__ = [
    "SkillResult",
    "get_training_context",
    "get_user_profile",
    "search_exercises",
    "get_exercise_details",
    # Token-safe v2 analytics
    "get_muscle_group_progress",
    "get_muscle_progress",
    "get_exercise_progress",
    "query_training_sets",
    # Pre-computed analysis (single consolidated call)
    "get_training_analysis",
]
