"""
Coach Agent - Education and training principles.

This agent:
- Answers general questions about training, hypertrophy, form, etc.
- Provides explanations and education grounded in exercise science
- Understands user context (goals, current training) to personalize advice
- Does NOT create or modify artifacts (no plans, no active workout changes)

Permission boundary: Read-only. No artifact writes.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional

from google.adk import Agent
from google.adk.tools import FunctionTool

from app.libs.tools_canvas.client import CanvasFunctionsClient

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(levelname)s | %(name)s | %(message)s'))
    logger.addHandler(handler)

# Global context
_context: Dict[str, Any] = {
    "canvas_id": None,
    "user_id": None,
    "correlation_id": None,
}
_client: Optional[CanvasFunctionsClient] = None
_context_parsed_for_message: Optional[str] = None


def _auto_parse_context(message: str) -> None:
    """Auto-parse context from message prefix."""
    global _context_parsed_for_message
    
    if _context_parsed_for_message == message:
        return
    
    match = re.search(r'\(context:\s*canvas_id=(\S+)\s+user_id=(\S+)\s+corr=(\S+)\)', message)
    if match:
        _context["canvas_id"] = match.group(1).strip()
        _context["user_id"] = match.group(2).strip()
        corr = match.group(3).strip()
        _context["correlation_id"] = corr if corr != "none" else None
        _context_parsed_for_message = message
        logger.info("auto_parse_context canvas=%s user=%s corr=%s",
                    _context.get("canvas_id"), _context.get("user_id"), _context.get("correlation_id"))


def _canvas_client() -> CanvasFunctionsClient:
    global _client
    if _client is None:
        base_url = os.getenv("MYON_FUNCTIONS_BASE_URL", "https://us-central1-myon-53d85.cloudfunctions.net")
        api_key = os.getenv("MYON_API_KEY", "myon-agent-key-2024")
        _client = CanvasFunctionsClient(base_url=base_url, api_key=api_key)
    return _client


def _resolve(value: Optional[str], fallback_key: str) -> Optional[str]:
    if isinstance(value, str) and value.strip():
        return value.strip()
    stored = _context.get(fallback_key)
    return stored.strip() if isinstance(stored, str) and stored.strip() else None


# ============================================================================
# TOOLS: Read-Only Context and Education
# ============================================================================

def tool_get_user_profile(*, user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Get the user's fitness profile to personalize coaching advice.
    
    Call this ONCE per conversation to understand their context.
    
    Args:
        user_id: User ID (auto-resolved from context if not provided)
    
    Returns:
        {
            "user_id": str,
            "name": str | None,
            "fitness_goal": "hypertrophy" | "strength" | "general_fitness" | None,
            "fitness_level": "beginner" | "intermediate" | "advanced" | None,
            "equipment_preference": "full_gym" | "home_gym" | "bodyweight" | None,
            "workouts_per_week_goal": int | None,  # Target frequency (e.g., 3, 4, 5)
            "weight": float | None,  # Bodyweight in user's preferred unit
            "height": float | None,
            "weight_format": "kilograms" | "pounds"
        }
    
    Use cases:
        - Adjust advice complexity based on fitness_level
        - Recommend appropriate exercises for equipment_preference
        - Tailor volume recommendations to fitness_goal
    """
    uid = _resolve(user_id, "user_id")
    if not uid:
        return {"error": "No user_id available"}
    
    logger.info("get_user_profile uid=%s", uid)
    try:
        resp = _canvas_client().get_user(uid)
        data = resp.get("data") or resp.get("context") or {}
        
        # Extract key coaching-relevant fields
        return {
            "user_id": uid,
            "name": data.get("name"),
            "fitness_goal": data.get("fitness_goal") or data.get("fitnessGoal"),
            "fitness_level": data.get("fitness_level") or data.get("fitnessLevel"),
            "equipment_preference": data.get("equipment_preference") or data.get("equipmentPreference"),
            "workouts_per_week_goal": data.get("workouts_per_week_goal") or data.get("workoutsPerWeekGoal"),
            "weight": data.get("weight"),
            "height": data.get("height"),
            "weight_format": data.get("weight_format") or "kilograms",
            # Raw data for any additional context
            "_raw": data,
        }
    except Exception as e:
        logger.error("get_user_profile failed: %s", str(e))
        return {"error": f"Failed to fetch profile: {str(e)}"}


def tool_get_training_context(*, user_id: Optional[str] = None, workout_limit: int = 5) -> Dict[str, Any]:
    """
    Get a LIGHT summary of the user's current training setup.
    
    Use this to understand WHAT they're doing, NOT for data analysis.
    For detailed progress analysis, direct questions to the Analysis agent.
    
    Args:
        user_id: User ID (auto-resolved from context if not provided)
        workout_limit: Recent workouts to scan (3-10, default 5)
    
    Returns:
        {
            "user_id": str,
            
            # Their active program (if any)
            "active_routine": {
                "id": str,
                "name": str,  # e.g., "PPL Program"
                "frequency": int,  # Workouts per week (e.g., 3, 4, 6)
                "template_count": int  # Number of workout templates
            } | None,
            
            "recent_workouts_count": int,
            
            # Brief preview of last sessions (not full exercise details)
            "recent_workout_summary": [
                {
                    "date": timestamp,
                    "exercise_count": int,
                    "exercises_preview": [str]  # First 5 exercise names, truncated
                }, ...
            ],
            
            # Inferred training pattern
            "training_pattern": "Full Body or PPL" | "Upper-focused" | "Lower-focused" | "Mixed" | "unknown"
        }
    
    Use cases:
        - Know if they have an active routine before discussing programming
        - Understand their general training style to contextualize advice
        - Refer to their current approach when answering questions
    """
    uid = _resolve(user_id, "user_id")
    if not uid:
        return {"error": "No user_id available"}
    
    workout_limit = max(3, min(10, workout_limit))
    
    logger.info("get_training_context uid=%s limit=%d", uid, workout_limit)
    
    result: Dict[str, Any] = {
        "user_id": uid,
        "active_routine": None,
        "recent_workouts_count": 0,
        "recent_workout_summary": [],
        "training_pattern": "unknown",
    }
    
    # Get active routine (if any)
    try:
        routine_resp = _canvas_client().get_active_routine(uid)
        routine = routine_resp.get("data") or routine_resp.get("routine")
        if routine:
            result["active_routine"] = {
                "id": routine.get("id"),
                "name": routine.get("name"),
                "frequency": routine.get("frequency"),
                "template_count": len(routine.get("template_ids") or routine.get("templateIds") or []),
            }
    except Exception as e:
        logger.warning("get_active_routine failed: %s", str(e))
    
    # Get recent workouts summary
    try:
        workouts_resp = _canvas_client().get_user_workouts(uid, limit=workout_limit)
        workouts = workouts_resp.get("data") or workouts_resp.get("workouts") or []
        result["recent_workouts_count"] = len(workouts)
        
        # Build light summary (not full details)
        summaries = []
        muscle_groups_seen: Dict[str, int] = {}
        
        for w in workouts:
            exercises = w.get("exercises") or []
            exercise_names = [e.get("name", "Unknown")[:30] for e in exercises[:5]]
            
            # Track muscle groups for pattern detection
            for ex in exercises:
                group = (ex.get("muscleGroup") or ex.get("muscle_group") or "").lower()
                if group:
                    muscle_groups_seen[group] = muscle_groups_seen.get(group, 0) + 1
            
            summaries.append({
                "date": w.get("end_time") or w.get("endTime") or w.get("created_at"),
                "exercise_count": len(exercises),
                "exercises_preview": exercise_names,
            })
        
        result["recent_workout_summary"] = summaries
        
        # Infer training pattern from muscle group distribution
        if muscle_groups_seen:
            sorted_groups = sorted(muscle_groups_seen.items(), key=lambda x: -x[1])
            top_groups = [g for g, _ in sorted_groups[:4]]
            
            has_legs = any("leg" in g or "quad" in g or "hamstring" in g or "glute" in g for g in top_groups)
            has_push = any("chest" in g or "shoulder" in g or "tricep" in g for g in top_groups)
            has_pull = any("back" in g or "bicep" in g for g in top_groups)
            
            if has_legs and has_push and has_pull:
                result["training_pattern"] = "Full Body or PPL"
            elif has_push and has_pull and not has_legs:
                result["training_pattern"] = "Upper-focused"
            elif has_legs and not (has_push and has_pull):
                result["training_pattern"] = "Lower-focused"
            else:
                result["training_pattern"] = "Mixed"
                
    except Exception as e:
        logger.warning("get_user_workouts failed: %s", str(e))
    
    return result


def tool_search_exercises(
    *,
    query: Optional[str] = None,
    muscle_group: Optional[str] = None,
    movement_type: Optional[str] = None,
    equipment: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 10,
) -> Dict[str, Any]:
    """
    Search the exercise catalog for education and recommendations.
    
    Use this when users ask about exercises:
    - "What muscles does the Romanian deadlift work?"
    - "What's a good chest exercise I can do at home?"
    - "Show me some pull exercises"
    
    Args:
        query: Free text search (exercise name, description). E.g., "bench press", "Romanian"
        muscle_group: Filter by target muscle. Values:
            "chest", "back", "legs", "shoulders", "arms", "core",
            "glutes", "quadriceps", "hamstrings", "biceps", "triceps", "calves", "forearms"
        movement_type: Filter by movement pattern. Values:
            "push", "pull", "hinge", "squat", "lunge", "carry", "core", "rotation"
        equipment: Filter by required equipment. Values:
            "barbell", "dumbbell", "cable", "machine", "bodyweight",
            "bench", "ez bar", "band", "pull-up bar", "trap bar"
        category: Filter by exercise type. Values:
            "compound", "isolation", "bodyweight", "assistance", "olympic lift"
        limit: Max results (1-20, default 10)
    
    Returns:
        {
            "count": int,
            "exercises": [
                {
                    "id": str,  # Exercise catalog ID
                    "name": str,  # e.g., "Bench Press (Barbell)"
                    "category": str,  # "compound" | "isolation" | etc.
                    "equipment": [str],  # e.g., ["barbell", "bench"]
                    "primary_muscles": [str],  # e.g., ["chest"]
                    "secondary_muscles": [str],  # e.g., ["triceps", "shoulders"]
                    "muscle_category": [str],  # e.g., ["chest"]
                    "movement_type": str,  # e.g., "push"
                    "description": str | None,
                    "difficulty": "beginner" | "intermediate" | "advanced" | None,
                    
                    # Coaching content (use for education)
                    "coaching_cues": [str],  # e.g., ["Drive through heels", "Keep chest up"]
                    "execution_notes": [str],  # Technique details
                    "common_mistakes": [str]  # e.g., ["Flaring elbows too wide"]
                }, ...
            ]
        }
    
    Tip: Use specific filters for best results. E.g., for home chest exercises:
        tool_search_exercises(muscle_group="chest", equipment="bodyweight")
    """
    limit = max(1, min(20, limit))
    
    logger.info("search_exercises query=%s muscle=%s movement=%s equipment=%s",
                query, muscle_group, movement_type, equipment)
    
    try:
        resp = _canvas_client().search_exercises(
            query=query,
            muscle_group=muscle_group,
            movement_type=movement_type,
            equipment=equipment,
            category=category,
            limit=limit,
        )
        
        exercises = resp.get("data") or resp.get("exercises") or []
        
        # Format for coaching (include educational fields)
        formatted = []
        for ex in exercises:
            muscles = ex.get("muscles") or {}
            formatted.append({
                "id": ex.get("id"),
                "name": ex.get("name"),
                "category": ex.get("category"),
                "equipment": ex.get("equipment") or [],
                "primary_muscles": muscles.get("primary") or [],
                "secondary_muscles": muscles.get("secondary") or [],
                "muscle_category": muscles.get("category") or [],
                "movement_type": (ex.get("movement") or {}).get("type"),
                "description": ex.get("description"),
                "coaching_cues": ex.get("coaching_cues") or [],
                "execution_notes": ex.get("execution_notes") or [],
                "common_mistakes": ex.get("common_mistakes") or [],
                "difficulty": (ex.get("metadata") or {}).get("level"),
            })
        
        return {
            "count": len(formatted),
            "exercises": formatted,
        }
        
    except Exception as e:
        logger.error("search_exercises failed: %s", str(e))
        return {"error": f"Failed to search exercises: {str(e)}"}


def tool_get_exercise_details(*, exercise_name: str) -> Dict[str, Any]:
    """
    Get comprehensive details about a specific exercise for education.
    
    Use this for in-depth questions about ONE exercise:
    - "How do I do a Romanian deadlift properly?"
    - "What muscles does the bench press work?"
    - "What are common mistakes on squats?"
    
    Args:
        exercise_name: Name of the exercise (e.g., "bench press", "Romanian deadlift", "lat pulldown")
    
    Returns:
        {
            "id": str,  # Exercise catalog ID
            "name": str,  # Full canonical name
            "description": str | None,  # Overview
            "category": "compound" | "isolation" | "bodyweight" | etc.,
            "difficulty": "beginner" | "intermediate" | "advanced" | None,
            
            # Muscle information
            "primary_muscles": [str],  # e.g., ["hamstrings", "glutes"]
            "secondary_muscles": [str],  # e.g., ["lower back", "core"]
            "muscle_category": [str],  # Body region categories
            "muscle_contribution": {str: float},  # e.g., {"hamstrings": 0.6, "glutes": 0.3}
            
            # Movement pattern
            "movement_type": "push" | "pull" | "hinge" | "squat" | etc.,
            "movement_split": "upper" | "lower" | "core" | "full",
            "plane_of_motion": str | None,  # e.g., "sagittal"
            "unilateral": bool,  # True if single-limb exercise
            
            # Equipment
            "equipment": [str],  # e.g., ["barbell"]
            
            # Coaching content (USE THESE FOR EDUCATION)
            "coaching_cues": [str],  # e.g., ["Hip hinge first, not squat", "Keep bar close to legs"]
            "execution_notes": [str],  # Detailed technique points
            "common_mistakes": [str],  # e.g., ["Rounding lower back", "Bending knees too early"]
            "programming_use_cases": [str],  # When to use this exercise
            "suitability_notes": [str]  # Who this exercise suits/doesn't suit
        }
    
    Tip: For general exercise discovery, use tool_search_exercises instead.
    """
    logger.info("get_exercise_details name=%s", exercise_name)
    
    try:
        resp = _canvas_client().search_exercises(query=exercise_name, limit=3)
        exercises = resp.get("data") or resp.get("exercises") or []
        
        if not exercises:
            return {"error": f"Exercise '{exercise_name}' not found in catalog"}
        
        # Take the best match (first result from search)
        ex = exercises[0]
        muscles = ex.get("muscles") or {}
        metadata = ex.get("metadata") or {}
        movement = ex.get("movement") or {}
        
        return {
            "id": ex.get("id"),
            "name": ex.get("name"),
            "description": ex.get("description"),
            "category": ex.get("category"),
            "difficulty": metadata.get("level"),
            # Muscle information
            "primary_muscles": muscles.get("primary") or [],
            "secondary_muscles": muscles.get("secondary") or [],
            "muscle_category": muscles.get("category") or [],
            "muscle_contribution": muscles.get("contribution") or {},
            # Movement pattern
            "movement_type": movement.get("type"),
            "movement_split": movement.get("split"),
            "plane_of_motion": metadata.get("plane_of_motion"),
            "unilateral": metadata.get("unilateral", False),
            # Equipment
            "equipment": ex.get("equipment") or [],
            # Coaching content
            "coaching_cues": ex.get("coaching_cues") or [],
            "execution_notes": ex.get("execution_notes") or [],
            "common_mistakes": ex.get("common_mistakes") or [],
            "programming_use_cases": ex.get("programming_use_cases") or [],
            "suitability_notes": ex.get("suitability_notes") or [],
        }
        
    except Exception as e:
        logger.error("get_exercise_details failed: %s", str(e))
        return {"error": f"Failed to get exercise details: {str(e)}"}


# ============================================================================
# ALL TOOLS
# ============================================================================

all_tools = [
    FunctionTool(func=tool_get_user_profile),
    FunctionTool(func=tool_get_training_context),
    FunctionTool(func=tool_search_exercises),
    FunctionTool(func=tool_get_exercise_details),
]


# ============================================================================
# AGENT CALLBACKS
# ============================================================================

def _before_tool_callback(tool, args, tool_context):
    """Auto-parse context from message before tool execution."""
    try:
        ctx = tool_context.invocation_context
        if ctx and hasattr(ctx, 'user_content'):
            user_msg = str(ctx.user_content.parts[0].text) if ctx.user_content and ctx.user_content.parts else ""
            _auto_parse_context(user_msg)
    except Exception as e:
        logger.debug("before_tool_callback parse error: %s", e)
    return None


def _before_model_callback(callback_context, llm_request):
    """Auto-parse context from message before LLM inference."""
    try:
        contents = llm_request.contents or []
        for content in contents:
            if hasattr(content, 'role') and content.role == 'user':
                for part in (content.parts or []):
                    if hasattr(part, 'text') and part.text:
                        _auto_parse_context(part.text)
                        break
    except Exception as e:
        logger.debug("before_model_callback parse error: %s", e)
    return None


# ============================================================================
# AGENT INSTRUCTION
# ============================================================================

# TODO: Replace with user-provided instruction block
COACH_INSTRUCTION = """
"""

# ============================================================================
# AGENT DEFINITION
# ============================================================================

CoachAgent = Agent(
    name="CoachAgent",
    model=os.getenv("CANVAS_COACH_MODEL", "gemini-2.5-flash"),
    instruction=COACH_INSTRUCTION,
    tools=all_tools,
    before_tool_callback=_before_tool_callback,
    before_model_callback=_before_model_callback,
)

root_agent = CoachAgent

__all__ = ["root_agent", "CoachAgent"]
