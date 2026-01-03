"""
Shell Tools - Tool definitions for ShellAgent using pure skills.

CRITICAL: This module imports ONLY from app/skills/.
NO imports from app/agents/ (coach_agent.py, planner_agent.py).

Tool categories:
- Read tools: From coach_skills.py (analytics, user data)
- Write tools: From gated_planner.py (Safety Gate enforced)

Security:
- Tool signatures do NOT include user_id (prevents LLM hallucination)
- user_id is retrieved from contextvars (set in agent_engine_app.py)
- Thread-safe for concurrent requests in Agent Engine

The tools defined here wrap skill functions with ADK-compatible signatures.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from google.adk.tools import FunctionTool

# Import context from contextvars-based context module
from app.shell.context import (
    SessionContext,
    get_current_context,
    get_current_message,
)

# =============================================================================
# IMPORTS FROM PURE SKILLS (NO LEGACY AGENTS)
# =============================================================================

# Read skills - no Safety Gate needed
from app.skills.coach_skills import (
    get_analytics_features,
    get_training_context,
    get_user_profile,
    get_recent_workouts,
    search_exercises,
    get_exercise_details,
)

# Write skills - with Safety Gate enforcement
from app.skills.gated_planner import (
    propose_workout as gated_propose_workout,
    propose_routine as gated_propose_routine,
    get_planning_context,
)

logger = logging.getLogger(__name__)


# =============================================================================
# READ TOOLS (Analytics & User Data)
# Note: user_id is NOT exposed to LLM - retrieved from context vars.
# =============================================================================

def tool_get_training_context() -> Dict[str, Any]:
    """
    Get the user's training context: active routine, templates, schedule.
    
    Use this to understand the user's current training structure.
    """
    ctx = get_current_context()
    
    if not ctx.user_id:
        return {"error": "No user_id available in context"}
    
    result = get_training_context(ctx.user_id)
    return result.to_dict()


def tool_get_analytics_features(
    *,
    weeks: int = 8,
    muscle_group: Optional[str] = None,
    exercise_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Get analytics features for progress analysis.
    
    Returns volume trends, intensity ratios, e1RM progressions.
    Use this when analyzing training progress or stalls.
    
    Args:
        weeks: Number of weeks to analyze (default 8)
        muscle_group: Filter by muscle group (e.g., "chest", "back")
        exercise_ids: Filter by specific exercises
    """
    ctx = get_current_context()
    
    if not ctx.user_id:
        return {"error": "No user_id available in context"}
    
    result = get_analytics_features(
        user_id=ctx.user_id,
        weeks=weeks,
        muscle_group=muscle_group,
        exercise_ids=exercise_ids,
    )
    return result.to_dict()


def tool_get_user_profile() -> Dict[str, Any]:
    """
    Get user's fitness profile: goals, experience level, equipment.
    
    Use this to personalize recommendations.
    """
    ctx = get_current_context()
    
    if not ctx.user_id:
        return {"error": "No user_id available in context"}
    
    result = get_user_profile(ctx.user_id)
    return result.to_dict()


def tool_get_recent_workouts(*, limit: int = 5) -> Dict[str, Any]:
    """
    Get user's recent workout sessions.
    
    Returns list of completed workouts with exercises and sets.
    
    Args:
        limit: Maximum number of workouts to return (default 5)
    """
    ctx = get_current_context()
    
    if not ctx.user_id:
        return {"error": "No user_id available in context"}
    
    result = get_recent_workouts(ctx.user_id, limit=limit)
    return result.to_dict()


def tool_search_exercises(
    *,
    muscle_group: Optional[str] = None,
    movement_type: Optional[str] = None,
    category: Optional[str] = None,
    equipment: Optional[str] = None,
    query: Optional[str] = None,
    limit: int = 15,
) -> Dict[str, Any]:
    """
    Search the exercise catalog.
    
    Args:
        muscle_group: Body part (chest, back, legs, etc.)
        movement_type: Push, pull, hinge, squat, etc.
        category: Compound, isolation, bodyweight
        equipment: Barbell, dumbbell, machine, cable
        query: Free text search
        limit: Max results (default 15)
    
    Returns:
        List of exercises with id, name, category, equipment
    """
    result = search_exercises(
        muscle_group=muscle_group,
        movement_type=movement_type,
        category=category,
        equipment=equipment,
        query=query,
        limit=limit,
    )
    return result.to_dict()


def tool_get_exercise_details(*, exercise_id: str) -> Dict[str, Any]:
    """
    Get detailed information about a specific exercise.
    
    Returns full exercise data including muscles, instructions, tips.
    """
    result = get_exercise_details(exercise_id)
    return result.to_dict()


def tool_get_planning_context() -> Dict[str, Any]:
    """
    Get complete planning context in one call.
    
    Returns user profile, active routine, templates, recent workouts.
    Use this FIRST when planning a workout or routine.
    """
    ctx = get_current_context()
    result = get_planning_context(ctx)
    return result.to_dict()


# =============================================================================
# WRITE TOOLS (Safety Gate Enforced)
# Note: user_id and canvas_id are retrieved from context vars.
# =============================================================================

def tool_propose_workout(
    *,
    title: str,
    exercises: List[Dict[str, Any]],
    focus: Optional[str] = None,
    duration_minutes: int = 45,
    coach_notes: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create and publish a workout plan.
    
    SAFETY: First call returns preview. User must confirm to publish.
    
    Args:
        title: Workout name (e.g., "Push Day", "Leg Hypertrophy")
        exercises: List of exercises, each with:
            - name: Exercise name
            - exercise_id: Catalog ID
            - sets: Number of working sets (3-4)
            - reps: Target reps (8-12 for hypertrophy)
            - rir: Target RIR for final set
            - weight_kg: Target weight (optional)
        focus: Brief goal description
        duration_minutes: Estimated duration
        coach_notes: Rationale for the plan
    """
    ctx = get_current_context()
    message = get_current_message()
    
    if not ctx.canvas_id or not ctx.user_id:
        return {"error": "Missing canvas_id or user_id in context"}
    
    result = gated_propose_workout(
        ctx=ctx,
        message=message,
        title=title,
        exercises=exercises,
        focus=focus,
        duration_minutes=duration_minutes,
        coach_notes=coach_notes,
    )
    
    return result.to_dict()


def tool_propose_routine(
    *,
    name: str,
    frequency: int,
    workouts: List[Dict[str, Any]],
    description: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a complete routine with multiple workout days.
    
    SAFETY: First call returns preview. User must confirm to publish.
    
    Args:
        name: Routine name (e.g., "Push Pull Legs", "Upper Lower")
        frequency: Times per week (3, 4, 5, 6)
        workouts: List of workout days, each with:
            - title: Day name (e.g., "Push", "Pull", "Legs")
            - exercises: List of exercises (same format as propose_workout)
        description: Brief routine description
    """
    ctx = get_current_context()
    message = get_current_message()
    
    if not ctx.canvas_id or not ctx.user_id:
        return {"error": "Missing canvas_id or user_id in context"}
    
    result = gated_propose_routine(
        ctx=ctx,
        message=message,
        name=name,
        frequency=frequency,
        workouts=workouts,
        description=description,
    )
    
    return result.to_dict()


# =============================================================================
# TOOL REGISTRY
# =============================================================================

# All tools available to ShellAgent
all_tools = [
    # Read tools (analytics, user data)
    FunctionTool(func=tool_get_training_context),
    FunctionTool(func=tool_get_analytics_features),
    FunctionTool(func=tool_get_user_profile),
    FunctionTool(func=tool_get_recent_workouts),
    FunctionTool(func=tool_search_exercises),
    FunctionTool(func=tool_get_exercise_details),
    FunctionTool(func=tool_get_planning_context),
    
    # Write tools (Safety Gate enforced)
    FunctionTool(func=tool_propose_workout),
    FunctionTool(func=tool_propose_routine),
]


__all__ = [
    # Tool registry for ShellAgent
    "all_tools",
    # Individual tools for testing
    "tool_get_training_context",
    "tool_get_analytics_features",
    "tool_get_user_profile",
    "tool_get_recent_workouts",
    "tool_search_exercises",
    "tool_get_exercise_details",
    "tool_get_planning_context",
    "tool_propose_workout",
    "tool_propose_routine",
]
