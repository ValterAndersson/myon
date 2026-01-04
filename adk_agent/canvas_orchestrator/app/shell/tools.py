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
    set_current_context,
)


def set_tool_context(ctx: SessionContext, message: str) -> None:
    """
    Set the context for tool execution.
    
    This is called by agent callbacks before tool/model calls.
    Alias for set_current_context for semantic clarity in agent.py.
    
    Args:
        ctx: SessionContext with user_id, canvas_id, etc.
        message: Raw message (for reference in tools)
    """
    set_current_context(ctx, message)

# =============================================================================
# IMPORTS FROM PURE SKILLS (NO LEGACY AGENTS)
# =============================================================================

# Read skills - no Safety Gate needed
from app.skills.coach_skills import (
    get_training_context,
    get_user_profile,
    search_exercises,
    get_exercise_details,
    # Token-safe v2 analytics (PREFERRED for progress questions)
    get_muscle_group_progress,
    get_muscle_progress,
    get_exercise_progress,
    get_coaching_context,
    query_training_sets,
)

# Write skills - direct execution (no Safety Gate - cards have accept/dismiss buttons)
from app.skills.planner_skills import (
    propose_workout as direct_propose_workout,
    propose_routine as direct_propose_routine,
    get_planning_context as _get_planning_context,
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


def tool_search_exercises(
    *,
    muscle_group: Optional[str] = None,
    movement_type: Optional[str] = None,
    category: Optional[str] = None,
    equipment: Optional[str] = None,
    query: Optional[str] = None,
    limit: int = 15,
    fields: str = "lean",
) -> Dict[str, Any]:
    """
    Search the exercise catalog.
    
    IMPORTANT: Use muscle_group for body-part searches.
    Use movement_type (not split) for push/pull/legs programming.
    
    Args:
        muscle_group: Body part category. Comma-separated OK.
            Values: "chest", "back", "legs", "shoulders", "arms", "core", "glutes",
                    "quadriceps", "hamstrings", "biceps", "triceps", "calves"
            Example: muscle_group="chest" or muscle_group="chest,shoulders,triceps"
        
        movement_type: Movement pattern. USE THIS for PPL splits.
            Values: "push", "pull", "hinge", "squat", "lunge", "carry", "core"
            Example: movement_type="push" gets chest press, shoulder press, tricep extensions
                     movement_type="pull" gets rows, pulldowns, curls
        
        category: Exercise complexity.
            Values: "compound", "isolation", "bodyweight"
        
        equipment: Equipment required. Comma-separated OK.
            Values: "barbell", "dumbbell", "cable", "machine", "bodyweight"
        
        query: Free text search for exercise names.
        
        limit: Max results (default 15)
        
        fields: Output format. Choose based on need:
            "minimal" - id + name only (smallest, for large searches)
            "lean" - id, name, category, equipment (default, good for planning)
            "full" - all fields (when you need muscles, instructions, etc.)
    
    Returns:
        List of exercises with fields based on 'fields' parameter
    
    Strategy:
        - PPL: movement_type="push" / "pull" / muscle_group="legs"
        - Upper/Lower: muscle_group="chest,back" / muscle_group="legs"
        - If sparse results, drop filters and proceed with best available
        - Use fields="minimal" for large result sets to save context
    """
    result = search_exercises(
        muscle_group=muscle_group,
        movement_type=movement_type,
        category=category,
        equipment=equipment,
        query=query,
        limit=limit,
        fields=fields,
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
    
    if not ctx.user_id:
        return {"error": "No user_id available in context"}
    
    result = _get_planning_context(user_id=ctx.user_id)
    return result.to_dict()


# =============================================================================
# TOKEN-SAFE TRAINING ANALYTICS v2 (PREFERRED)
# These tools use bounded, paginated endpoints that prevent agent timeouts.
# Use these INSTEAD OF tool_get_analytics_features for progress questions.
# =============================================================================

def tool_get_muscle_group_progress(
    *,
    muscle_group: str,
    window_weeks: int = 12,
) -> Dict[str, Any]:
    """
    Get comprehensive muscle group progress summary - TOKEN SAFE.
    
    PREFERRED for "How is my chest/back/etc developing?" questions.
    Returns bounded data (<15KB) with weekly series, top exercises,
    and flags (plateau, deload, overreach).
    
    Args:
        muscle_group: Target muscle group. REQUIRED.
            Valid values: chest, back, shoulders, arms, core, legs, glutes,
                         hip_flexors, calves, forearms, neck, cardio
        
        window_weeks: Analysis window in weeks (1-52, default 12)
    
    Returns:
        Weekly effective volume, hard sets, top exercises, flags.
        
    Example:
        tool_get_muscle_group_progress(muscle_group="chest", window_weeks=12)
        
    Error Recovery:
        If muscle_group is invalid, returns list of valid options.
    """
    ctx = get_current_context()
    
    if not ctx.user_id:
        return {"error": "No user_id available in context"}
    
    result = get_muscle_group_progress(
        user_id=ctx.user_id,
        muscle_group=muscle_group,
        window_weeks=window_weeks,
    )
    return result.to_dict()


def tool_get_muscle_progress(
    *,
    muscle: str,
    window_weeks: int = 12,
) -> Dict[str, Any]:
    """
    Get individual muscle progress summary - TOKEN SAFE.
    
    Use for specific muscle questions like "How are my rhomboids?" 
    or "How is my front delt developing?"
    
    Args:
        muscle: Target muscle. REQUIRED.
            Common values: 
              Back: latissimus_dorsi, rhomboids, trapezius_upper, trapezius_middle,
                    trapezius_lower, erector_spinae, teres_major
              Chest: pectoralis_major, pectoralis_minor
              Shoulders: deltoid_anterior, deltoid_lateral, deltoid_posterior, rotator_cuff
              Arms: biceps_brachii, triceps_brachii, brachialis, brachioradialis
              Core: rectus_abdominis, obliques, transverse_abdominis
              Legs: quadriceps, hamstrings, gluteus_maximus, gluteus_medius,
                    gastrocnemius, soleus, tibialis_anterior, adductors
        
        window_weeks: Analysis window in weeks (1-52, default 12)
    
    Returns:
        Weekly effective volume for the muscle, top exercises, flags.
        
    Example:
        tool_get_muscle_progress(muscle="rhomboids", window_weeks=12)
        
    Error Recovery:
        If muscle is invalid, returns list of common muscles.
    """
    ctx = get_current_context()
    
    if not ctx.user_id:
        return {"error": "No user_id available in context"}
    
    result = get_muscle_progress(
        user_id=ctx.user_id,
        muscle=muscle,
        window_weeks=window_weeks,
    )
    return result.to_dict()


def tool_get_exercise_progress(
    *,
    exercise_id: Optional[str] = None,
    exercise_name: Optional[str] = None,
    window_weeks: int = 12,
) -> Dict[str, Any]:
    """
    Get exercise progress summary with PR tracking - TOKEN SAFE.
    
    Use for "How is my bench press progressing?" questions.
    Returns weekly series, last session recap, PR markers.
    
    ACCEPTS EITHER exercise_id OR exercise_name:
    - exercise_id: Direct lookup by catalog ID
    - exercise_name: Fuzzy name search (e.g., "bench press", "squats", "deadlift")
    
    The fuzzy search matches against exercises in the user's training history.
    For example, "bench" will match "Bench Press", "Dumbbell Bench Press", etc.
    
    Args:
        exercise_id: Exercise ID from catalog (optional if exercise_name provided)
        
        exercise_name: Exercise name for fuzzy search (PREFERRED for user queries)
            Examples: "bench press", "squats", "deadlift", "lat pulldown"
        
        window_weeks: Analysis window in weeks (1-52, default 12)
    
    Returns:
        Weekly e1RM/volume series, last session sets, PR markers, plateau flag.
        If using exercise_name and no match found, returns matched=false with suggestions.
        
    Examples:
        # By name (preferred for user queries):
        tool_get_exercise_progress(exercise_name="bench press", window_weeks=12)
        tool_get_exercise_progress(exercise_name="squats")
        
        # By ID (when you have the ID from another query):
        tool_get_exercise_progress(exercise_id="barbell-bench-press", window_weeks=12)
    """
    ctx = get_current_context()
    
    if not ctx.user_id:
        return {"error": "No user_id available in context"}
    
    if not exercise_id and not exercise_name:
        return {"error": "exercise_id or exercise_name is required"}
    
    result = get_exercise_progress(
        user_id=ctx.user_id,
        exercise_id=exercise_id,
        exercise_name=exercise_name,
        window_weeks=window_weeks,
    )
    return result.to_dict()


def tool_get_coaching_context(
    *,
    window_weeks: int = 8,
) -> Dict[str, Any]:
    """
    Get compact coaching context in a single call - TOKEN SAFE.
    
    BEST STARTING POINT for coaching conversations.
    Response is GUARANTEED under 15KB.
    
    Returns:
        - Top muscle groups by training volume
        - Weekly trends for each group
        - Top exercises per group
        - Training adherence stats
        - Change flags (volume drops, high failure rate)
    
    Args:
        window_weeks: Analysis window (default 8, max 52)
    
    Example:
        tool_get_coaching_context(window_weeks=8)
    """
    ctx = get_current_context()
    
    if not ctx.user_id:
        return {"error": "No user_id available in context"}
    
    result = get_coaching_context(
        user_id=ctx.user_id,
        window_weeks=window_weeks,
    )
    return result.to_dict()


def tool_query_training_sets(
    *,
    muscle_group: Optional[str] = None,
    muscle: Optional[str] = None,
    exercise_ids: Optional[List[str]] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    """
    Query raw set facts for detailed evidence - DRILLDOWN ONLY.
    
    EXACTLY ONE filter required: muscle_group, muscle, or exercise_ids.
    Use only when you need raw set data. Prefer summary endpoints first.
    
    Args:
        muscle_group: Filter by muscle group (e.g., "chest")
            Mutually exclusive with muscle and exercise_ids.
        
        muscle: Filter by specific muscle (e.g., "rhomboids")  
            Mutually exclusive with muscle_group and exercise_ids.
        
        exercise_ids: Filter by exercise IDs (max 10)
            Mutually exclusive with muscle_group and muscle.
        
        start: Start date YYYY-MM-DD (optional)
        end: End date YYYY-MM-DD (optional)
        limit: Max results (default 50, max 200)
    
    Returns:
        Array of set facts: workout_date, exercise_name, reps, weight_kg, rir, e1rm.
        
    Example:
        tool_query_training_sets(muscle_group="chest", limit=20)
        tool_query_training_sets(exercise_ids=["barbell-bench-press"], limit=30)
        
    Error Recovery:
        Returns 400 if zero or multiple filters provided.
    """
    ctx = get_current_context()
    
    if not ctx.user_id:
        return {"error": "No user_id available in context"}
    
    result = query_training_sets(
        user_id=ctx.user_id,
        muscle_group=muscle_group,
        muscle=muscle,
        exercise_ids=exercise_ids,
        start=start,
        end=end,
        limit=limit,
    )
    return result.to_dict()


# =============================================================================
# WRITE TOOLS (Direct Execution - cards have accept/dismiss buttons)
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
    Create and publish a workout plan to the canvas.
    
    The card has accept/dismiss buttons - no confirmation needed.
    
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
    
    if not ctx.canvas_id or not ctx.user_id:
        return {"error": "Missing canvas_id or user_id in context"}
    
    result = direct_propose_workout(
        canvas_id=ctx.canvas_id,
        user_id=ctx.user_id,
        title=title,
        exercises=exercises,
        focus=focus,
        duration_minutes=duration_minutes,
        coach_notes=coach_notes,
        correlation_id=ctx.correlation_id,
        dry_run=False,  # Always publish - card has accept/dismiss buttons
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
    
    The card has save/dismiss buttons - no confirmation needed.
    
    Args:
        name: Routine name (e.g., "Push Pull Legs", "Upper Lower")
        frequency: Times per week (3, 4, 5, 6)
        workouts: List of workout days, each with:
            - title: Day name (e.g., "Push", "Pull", "Legs")
            - exercises: List of exercises (same format as propose_workout)
        description: Brief routine description
    """
    ctx = get_current_context()
    
    if not ctx.canvas_id or not ctx.user_id:
        return {"error": "Missing canvas_id or user_id in context"}
    
    result = direct_propose_routine(
        canvas_id=ctx.canvas_id,
        user_id=ctx.user_id,
        name=name,
        frequency=frequency,
        workouts=workouts,
        description=description,
        correlation_id=ctx.correlation_id,
        dry_run=False,  # Always publish - card has save/dismiss buttons
    )
    
    return result.to_dict()


# =============================================================================
# TOOL REGISTRY
# =============================================================================

# All tools available to ShellAgent
all_tools = [
    # Read tools (user context)
    FunctionTool(func=tool_get_training_context),
    FunctionTool(func=tool_get_user_profile),
    FunctionTool(func=tool_search_exercises),
    FunctionTool(func=tool_get_exercise_details),
    FunctionTool(func=tool_get_planning_context),
    
    # Token-safe Training Analytics v2 (PREFERRED for progress questions)
    FunctionTool(func=tool_get_muscle_group_progress),
    FunctionTool(func=tool_get_muscle_progress),
    FunctionTool(func=tool_get_exercise_progress),
    FunctionTool(func=tool_get_coaching_context),
    FunctionTool(func=tool_query_training_sets),
    
    # Write tools (cards have accept/dismiss buttons)
    FunctionTool(func=tool_propose_workout),
    FunctionTool(func=tool_propose_routine),
]


__all__ = [
    # Tool registry for ShellAgent
    "all_tools",
    # Context setter for agent callbacks
    "set_tool_context",
    # Read tools
    "tool_get_training_context",
    "tool_get_user_profile",
    "tool_search_exercises",
    "tool_get_exercise_details",
    "tool_get_planning_context",
    # Token-safe v2 analytics (PREFERRED)
    "tool_get_muscle_group_progress",
    "tool_get_muscle_progress",
    "tool_get_exercise_progress",
    "tool_get_coaching_context",
    "tool_query_training_sets",
    # Write tools
    "tool_propose_workout",
    "tool_propose_routine",
]
