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
# ANALYTICS
# ============================================================================

def get_analytics_features(
    user_id: str,
    weeks: int = 8,
    exercise_ids: Optional[List[str]] = None,
    muscles: Optional[List[str]] = None,
    client: Optional[CanvasFunctionsClient] = None,
) -> SkillResult:
    """
    Fetch analytics features for progress analysis.
    
    Args:
        user_id: User ID (required)
        weeks: Number of weeks to analyze (1-52, default 8)
        exercise_ids: Optional exercise IDs for per-exercise e1RM series
        muscles: Optional muscle names for per-muscle series
        client: Optional client instance (for Worker injection)
        
    Returns:
        SkillResult with volume, intensity, and progression data
    """
    if not user_id:
        return SkillResult(success=False, error="user_id is required")
    
    weeks = max(1, min(52, weeks))
    logger.info("get_analytics_features uid=%s weeks=%d", user_id, weeks)
    
    try:
        api_client = client or _get_client()
        resp = api_client.get_analytics_features(
            user_id,
            mode="weekly",
            weeks=weeks,
            exercise_ids=exercise_ids,
            muscles=muscles,
        )
        
        success, data, error_details = parse_api_response(resp)
        if not success:
            logger.error("get_analytics_features failed: %s", error_details)
            return SkillResult(success=False, error=str(error_details))
            
    except Exception as e:
        logger.error("get_analytics_features exception: %s", e)
        return SkillResult(success=False, error=str(e))
    
    rollups = data.get("rollups") or []
    series_muscle = data.get("series_muscle") or {}
    series_exercise = data.get("series_exercise") or {}
    
    # Compute summary stats
    weeks_with_data = len([r for r in rollups if (r.get("workouts") or r.get("cadence", {}).get("sessions") or 0) > 0])
    total_workouts = sum(r.get("workouts") or r.get("cadence", {}).get("sessions") or 0 for r in rollups)
    total_sets = sum(r.get("total_sets") or 0 for r in rollups)
    total_weight = sum(r.get("total_weight") or 0 for r in rollups)
    
    # Aggregate intensity metrics
    muscle_sets: Dict[str, float] = {}
    muscle_low_rir: Dict[str, float] = {}
    total_hard_sets = 0
    total_low_rir_sets = 0
    
    for rollup in rollups:
        intensity = rollup.get("intensity") or {}
        total_hard_sets += intensity.get("hard_sets_total") or 0
        total_low_rir_sets += intensity.get("low_rir_sets_total") or 0
        
        for muscle, sets in (intensity.get("hard_sets_per_muscle") or {}).items():
            muscle_sets[muscle] = muscle_sets.get(muscle, 0) + (sets or 0)
        for muscle, sets in (intensity.get("low_rir_sets_per_muscle") or {}).items():
            muscle_low_rir[muscle] = muscle_low_rir.get(muscle, 0) + (sets or 0)
    
    sorted_muscles = sorted(muscle_sets.items(), key=lambda x: -x[1])
    muscle_avg = {m: round(s / max(weeks_with_data, 1), 1) for m, s in muscle_sets.items()}
    
    # Calculate intensity ratios
    muscle_intensity_ratio = {}
    for muscle, hard in muscle_sets.items():
        low = muscle_low_rir.get(muscle, 0)
        if hard > 0:
            muscle_intensity_ratio[muscle] = round(low / hard, 2)
    
    overall_intensity_ratio = round(total_low_rir_sets / max(total_hard_sets, 1), 2)
    
    return SkillResult(
        success=True,
        data={
            "weeks_requested": weeks,
            "weeks_with_data": weeks_with_data,
            "total_workouts": total_workouts,
            "total_sets": total_sets,
            "total_volume_kg": round(total_weight, 0),
            "avg_workouts_per_week": round(total_workouts / max(weeks_with_data, 1), 1),
            "avg_sets_per_week": round(total_sets / max(weeks_with_data, 1), 1),
            "intensity_summary": {
                "total_hard_sets": total_hard_sets,
                "total_low_rir_sets": total_low_rir_sets,
                "intensity_ratio": overall_intensity_ratio,
                "interpretation": "high intensity" if overall_intensity_ratio > 0.3 else "moderate intensity",
            },
            "muscle_sets_ranking": [
                {
                    "muscle": m, 
                    "total_sets": round(s, 1), 
                    "avg_sets_per_week": muscle_avg.get(m, 0),
                    "low_rir_sets": round(muscle_low_rir.get(m, 0), 1),
                    "intensity_ratio": muscle_intensity_ratio.get(m, 0),
                } 
                for m, s in sorted_muscles[:10]
            ],
            "rollups": rollups,
            "series_muscle": series_muscle,
            "series_exercise": series_exercise,
        }
    )


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
# RECENT WORKOUTS
# ============================================================================

def get_recent_workouts(
    user_id: str,
    limit: int = 10,
    client: Optional[CanvasFunctionsClient] = None,
) -> SkillResult:
    """
    Get user's recent completed workouts.
    
    Args:
        user_id: User ID (required)
        limit: Max workouts to return (5-30)
        client: Optional client instance (for Worker injection)
        
    Returns:
        SkillResult with list of workouts
    """
    if not user_id:
        return SkillResult(success=False, error="user_id is required")
    
    limit = max(5, min(30, limit))
    logger.info("get_recent_workouts uid=%s limit=%d", user_id, limit)
    
    try:
        api_client = client or _get_client()
        resp = api_client.get_user_workouts(user_id, limit=limit)
        success, data, error_details = parse_api_response(resp)
        
        if not success:
            return SkillResult(success=False, error=str(error_details))
        
        workouts = data.get("items") if isinstance(data, dict) else data
        if not isinstance(workouts, list):
            workouts = []
            
        return SkillResult(
            success=True,
            data={"count": len(workouts), "workouts": workouts}
        )
    except Exception as e:
        logger.error("get_recent_workouts exception: %s", e)
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
) -> SkillResult:
    """
    Search exercise catalog.
    
    Args:
        muscle_group: Target muscle group
        movement_type: push, pull, hinge, squat, etc.
        category: compound, isolation, bodyweight
        equipment: barbell, dumbbell, cable, machine
        query: Free text search
        limit: Max results (default 10)
        
    Returns:
        SkillResult with list of exercises
    """
    logger.info("search_exercises query=%s muscle=%s", query, muscle_group)
    
    try:
        resp = _get_client().search_exercises(
            muscle_group=muscle_group,
            movement_type=movement_type,
            category=category,
            equipment=equipment,
            query=query,
            limit=limit,
        )
        
        success, data, error_details = parse_api_response(resp)
        if not success:
            return SkillResult(success=False, error=str(error_details))
            
    except Exception as e:
        logger.error("search_exercises exception: %s", e)
        return SkillResult(success=False, error=str(e))
    
    items = data.get("items") or []
    
    # LEAN response format to minimize context window usage.
    # Only include fields the agent needs for selection + tool calls.
    # Full metadata was causing context bloat and output truncation.
    exercises = [
        {
            "id": ex.get("id"),
            "name": ex.get("name"),
            "category": ex.get("category"),  # compound/isolation - needed for selection
            "equipment": (ex.get("equipment") or [])[:1],  # Just first equipment, not all
        }
        for ex in items
    ]
    
    return SkillResult(
        success=True,
        data={"items": exercises, "count": len(exercises)}
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


__all__ = [
    "SkillResult",
    "get_training_context",
    "get_analytics_features", 
    "get_user_profile",
    "get_recent_workouts",
    "search_exercises",
    "get_exercise_details",
]
