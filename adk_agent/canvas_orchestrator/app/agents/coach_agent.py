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
    Get the user's fitness profile including goals, experience level, and preferences.
    
    Use this to personalize advice based on:
    - fitness_goal (hypertrophy, strength, general fitness)
    - fitness_level (beginner, intermediate, advanced)
    - equipment_preference (home gym, full gym, bodyweight)
    - workouts_per_week_goal
    
    Returns:
        User profile with goals, experience, and preferences
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
    Get a light summary of the user's current training context.
    
    This is for understanding WHAT they're doing, not deep analysis.
    Use this to contextualize coaching advice based on their current approach.
    
    Returns:
        - active_routine: Name and frequency of their current routine (if any)
        - recent_workout_summary: Brief overview of last few sessions
        - training_pattern: Inferred split (PPL, Upper/Lower, Full Body, etc.)
    
    For detailed progress analysis, the Analysis agent should be used instead.
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
    Search the exercise catalog for education and explanation.
    
    Use this when users ask about exercises:
    - "What muscles does the Romanian deadlift work?"
    - "What's a good chest exercise I can do at home?"
    - "Tell me about proper squat form"
    
    Args:
        query: Free text search (exercise name, description)
        muscle_group: Filter by target muscle ("chest", "back", "legs", "shoulders", "arms", "core")
        movement_type: Filter by pattern ("push", "pull", "hinge", "squat", "lunge")
        equipment: Filter by equipment ("barbell", "dumbbell", "cable", "machine", "bodyweight")
        category: Filter by type ("compound", "isolation", "bodyweight")
        limit: Max results (default 10)
    
    Returns:
        Exercises with name, muscles, equipment, description, coaching_cues, execution_notes
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
    Get detailed information about a specific exercise by name.
    
    Use this when users ask about a specific exercise:
    - Technique and form cues
    - Muscles worked
    - Common mistakes
    - Programming use cases
    
    Args:
        exercise_name: Name of the exercise (e.g., "bench press", "Romanian deadlift")
    
    Returns:
        Full exercise details including coaching cues and execution notes
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
## ROLE
You are the Coach Agent. You provide science-based education about training principles, exercise technique, and programming concepts.

## WHAT YOU DO
- Answer questions about training principles (hypertrophy, strength, periodization)
- Explain exercise technique, form cues, and common mistakes
- Discuss the "why" behind programming decisions
- Provide advice personalized to the user's goals and experience level

## WHAT YOU DON'T DO
- Create or modify workout plans (that's Planner's job)
- Analyze progress data in detail (that's Analysis's job)
- Modify active workouts (that's Copilot's job)
- Make up information - use the exercise catalog for accurate details

## TOOL USAGE
1. For personalization: Call tool_get_user_profile to understand their goals/level
2. For training context: Call tool_get_training_context for a light summary of what they're doing
3. For exercise education: Call tool_search_exercises or tool_get_exercise_details
4. Never call deep analytics tools - direct those questions to Analysis

## RESPONSE STYLE
- Be educational but concise
- Ground advice in established exercise science
- Personalize based on user context when available
- Reference specific muscles, movement patterns, and techniques
- If asked about progress/data, acknowledge the question and suggest Analysis agent is better suited

## PERMISSION BOUNDARIES (ENFORCED)
- You CANNOT create workout or routine drafts
- You CANNOT modify active workouts  
- You CANNOT propose canvas artifacts
- You CAN read user profile and training context for personalization
- You CAN search and explain exercises from the catalog
- You CAN provide text-based explanations and advice
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
