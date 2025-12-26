"""
Planner Agent - Workout and routine draft creation.

Part of the multi-agent architecture. This agent:
- Creates and edits workout drafts (session_plan cards)
- Creates and edits routine drafts (routine_summary + session_plan cards)
- Searches exercises and builds plans
- Does NOT manipulate active workouts (that's Copilot's job)

Permission boundary: Can write draft artifacts, cannot write activeWorkout.
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from typing import Any, Dict, List, Optional

from google.adk import Agent
from google.adk.tools import FunctionTool

from app.libs.tools_canvas.client import CanvasFunctionsClient

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Add a handler to ensure logs are visible
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(levelname)s | %(name)s | %(message)s'))
    logger.addHandler(handler)

# Global context for the current request
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
# TOOLS: User Context
# ============================================================================

def tool_get_user_profile(*, user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Get the user's fitness profile including experience level, goals, equipment, 
    and training preferences. Use this to personalize your recommendations.
    """
    uid = _resolve(user_id, "user_id")
    if not uid:
        return {"error": "No user_id available"}
    
    logger.info("get_user_profile uid=%s", uid)
    resp = _canvas_client().get_user(uid)
    return resp.get("data") or resp.get("context") or {}


def tool_get_recent_workouts(*, user_id: Optional[str] = None, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Get the user's recent workout sessions. Use this to understand their 
    training patterns, volume, and progress over time.
    """
    uid = _resolve(user_id, "user_id")
    if not uid:
        return []
    
    logger.info("get_recent_workouts uid=%s limit=%s", uid, limit)
    resp = _canvas_client().get_user_workouts(uid, limit=limit)
    return resp.get("data") or resp.get("workouts") or []


# ============================================================================
# TOOLS: Routine & Template Context
# ============================================================================

def tool_get_planning_context(*, user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Get complete planning context in one call: user profile, active routine,
    next workout, all templates, and recent workouts summary.
    
    Use this FIRST when planning a workout if the user has an active routine.
    Returns:
        - user: Profile with fitness level, goals, preferences
        - activeRoutine: Current routine with template_ids and frequency
        - nextWorkout: Template for the next workout in rotation
        - templates: List of all user templates (with exercises)
        - recentWorkoutsSummary: Recent training history
    """
    uid = _resolve(user_id, "user_id")
    if not uid:
        return {"error": "No user_id available"}
    
    logger.info("get_planning_context uid=%s", uid)
    return _canvas_client().get_planning_context(uid)


def tool_get_next_workout(*, user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Get the next workout template from the user's active routine.
    Uses deterministic rotation based on last completed workout.
    
    Returns:
        - template: Full template with exercises and sets
        - routine: Active routine info
        - index: Position in rotation (0-based)
        - selectionMethod: "cursor" (fast) or "history_scan" (fallback)
    
    Returns hasActiveRoutine=false if no routine is set.
    """
    uid = _resolve(user_id, "user_id")
    if not uid:
        return {"error": "No user_id available"}
    
    logger.info("get_next_workout uid=%s", uid)
    return _canvas_client().get_next_workout(uid)


def tool_get_template(*, user_id: Optional[str] = None, template_id: str) -> Dict[str, Any]:
    """
    Get a specific template with full exercise details.
    Use this to fetch a template when creating a plan based on it.
    """
    uid = _resolve(user_id, "user_id")
    if not uid:
        return {"error": "No user_id available"}
    
    logger.info("get_template uid=%s template_id=%s", uid, template_id)
    resp = _canvas_client().get_template(uid, template_id)
    return resp.get("data") or resp


def tool_save_workout_as_template(
    *,
    user_id: Optional[str] = None,
    mode: str,  # "create" or "update"
    plan: Dict[str, Any],
    name: Optional[str] = None,
    description: Optional[str] = None,
    target_template_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Save a workout plan as a template for future use.
    
    Args:
        mode: "create" for new template, "update" to patch existing template
        plan: The workout plan with title and blocks (same format as propose_workout)
        name: Template name (required for create, optional for update)
        description: Optional description
        target_template_id: Required when mode="update", the template to patch
    
    Returns:
        template_id of created/updated template
    """
    uid = _resolve(user_id, "user_id")
    if not uid:
        return {"error": "No user_id available"}
    
    if mode == "update" and not target_template_id:
        return {"error": "target_template_id required for update mode"}
    
    logger.info("save_workout_as_template uid=%s mode=%s", uid, mode)
    
    resp = _canvas_client().create_template_from_plan(
        uid,
        mode=mode,
        plan=plan,
        name=name,
        description=description,
        target_template_id=target_template_id,
    )
    return resp


def tool_create_routine(
    *,
    user_id: Optional[str] = None,
    name: str,
    template_ids: List[str],
    description: Optional[str] = None,
    frequency: int = 3,
    set_as_active: bool = True,
) -> Dict[str, Any]:
    """
    Create a new workout routine with templates.
    
    Args:
        name: Routine name (e.g., "Push Pull Legs", "Upper Lower")
        template_ids: Ordered list of template IDs for the routine
        description: Optional description
        frequency: Times per week (default 3)
        set_as_active: Automatically set as active routine (default true)
    
    Returns:
        routine_id and confirmation
    """
    uid = _resolve(user_id, "user_id")
    if not uid:
        return {"error": "No user_id available"}
    
    if not template_ids:
        return {"error": "template_ids cannot be empty"}
    
    logger.info("create_routine uid=%s name=%s templates=%d", uid, name, len(template_ids))
    
    resp = _canvas_client().create_routine(
        uid,
        name=name,
        template_ids=template_ids,
        description=description,
        frequency=frequency,
    )
    
    routine_id = resp.get("data", {}).get("id") or resp.get("routineId")
    
    if set_as_active and routine_id:
        _canvas_client().set_active_routine(uid, routine_id)
        resp["set_as_active"] = True
    
    return resp


def tool_manage_routine(
    *,
    user_id: Optional[str] = None,
    action: str,  # "add_template", "remove_template", "reorder", "update_info"
    routine_id: str,
    template_id: Optional[str] = None,
    template_ids: Optional[List[str]] = None,
    name: Optional[str] = None,
    description: Optional[str] = None,
    frequency: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Manage an existing routine (add/remove workouts, reorder, update info).
    
    Args:
        action: 
            - "add_template": Add a template to the routine
            - "remove_template": Remove a template from the routine
            - "reorder": Change the order of templates (provide full template_ids list)
            - "update_info": Change name, description, or frequency
        routine_id: The routine to modify
        template_id: Single template ID (for add/remove actions)
        template_ids: Full ordered list (for reorder action)
        name: New name (for update_info)
        description: New description (for update_info)
        frequency: New frequency (for update_info)
    
    Returns:
        Confirmation of the change
    """
    uid = _resolve(user_id, "user_id")
    if not uid:
        return {"error": "No user_id available"}
    
    logger.info("manage_routine uid=%s routine=%s action=%s", uid, routine_id, action)
    
    # Get current routine
    routine_resp = _canvas_client().get_routine(uid, routine_id)
    current = routine_resp.get("data") or routine_resp.get("routine") or {}
    current_templates = current.get("template_ids") or current.get("templateIds") or []
    
    if action == "add_template":
        if not template_id:
            return {"error": "template_id required for add_template"}
        new_templates = current_templates + [template_id]
        return _canvas_client().patch_routine(uid, routine_id, template_ids=new_templates)
    
    elif action == "remove_template":
        if not template_id:
            return {"error": "template_id required for remove_template"}
        new_templates = [t for t in current_templates if t != template_id]
        return _canvas_client().patch_routine(uid, routine_id, template_ids=new_templates)
    
    elif action == "reorder":
        if not template_ids:
            return {"error": "template_ids list required for reorder"}
        return _canvas_client().patch_routine(uid, routine_id, template_ids=template_ids)
    
    elif action == "update_info":
        return _canvas_client().patch_routine(
            uid, routine_id,
            name=name,
            description=description,
            frequency=frequency,
        )
    
    return {"error": f"Unknown action: {action}"}


# ============================================================================
# TOOLS: Exercise Catalog
# ============================================================================

def tool_search_exercises(
    *,
    muscle_group: Optional[str] = None,
    movement_type: Optional[str] = None,
    category: Optional[str] = None,
    equipment: Optional[str] = None,
    split: Optional[str] = None,
    difficulty: Optional[str] = None,
    query: Optional[str] = None,
    limit: int = 15,
) -> List[Dict[str, Any]]:
    """
    Search the exercise catalog. Returns exercises with IDs for use in workout plans.
    
    IMPORTANT: Use muscle_group (not primary_muscle) for body-part searches.
    Use movement_type (not split) for push/pull/legs programming.
    
    Args:
        muscle_group: Body part category. Case-insensitive. Most reliable filter.
            Values: "chest", "back", "legs", "shoulders", "arms", "core", "glutes", 
                    "quadriceps", "hamstrings", "biceps", "triceps", "calves", "forearms"
            Examples: muscle_group="chest" for chest exercises, muscle_group="back" for back exercises
        
        movement_type: Movement pattern. Use for push/pull/legs splits.
            Values: "push", "pull", "hinge", "squat", "lunge", "carry", "core", "rotation", "other"
            Examples: movement_type="push" for bench press, shoulder press, tricep extensions
                      movement_type="pull" for rows, pulldowns, curls
                      movement_type="hinge" for deadlifts, RDLs, hip thrusts
                      movement_type="squat" for squats, leg press
        
        category: Exercise complexity.
            Values: "compound" (multi-joint), "isolation" (single-joint), 
                    "bodyweight", "assistance", "olympic lift"
            Examples: category="compound" for big lifts, category="isolation" for accessories
        
        equipment: Equipment required. Can be comma-separated for multiple.
            Values: "barbell", "dumbbell", "cable", "machine", "bodyweight", 
                    "bench", "ez bar", "band", "pull-up bar", "trap bar"
            Examples: equipment="barbell" or equipment="barbell,dumbbell"
        
        split: Body region (NOT push/pull - use movement_type for that).
            Values: "upper", "lower", "core", "full"
            Examples: split="upper" for upper body, split="lower" for lower body
        
        difficulty: Experience level required.
            Values: "beginner", "intermediate", "advanced"
        
        query: Free text search. Searches exercise names and descriptions.
            Examples: query="bench press", query="deadlift", query="curl"
        
        limit: Max results to return (default 15, max 50)
    
    Returns:
        List of exercises with: id, name, category, primary_muscles, secondary_muscles, 
        equipment, level, split, movement_type
    
    Strategy Tips:
        - For PPL routines: Use movement_type="push" / "pull" + muscle_group="legs"
        - For Upper/Lower: Use split="upper" / split="lower"  
        - For specific muscles: Use muscle_group (e.g., muscle_group="chest")
        - Combine filters for precision: movement_type="push" + muscle_group="chest" + category="compound"
        - If results are sparse, try fewer filters or use query for name search
    """
    logger.info("🔍 SEARCH_EXERCISES: group=%s movement=%s category=%s equipment=%s split=%s query=%s limit=%d", 
                muscle_group, movement_type, category, equipment, split, query, limit)
    
    try:
        resp = _canvas_client().search_exercises(
            muscle_group=muscle_group,
            movement_type=movement_type,
            category=category,
            equipment=equipment,
            split=split,
            query=query,
            limit=limit,
        )
    except Exception as e:
        logger.error("❌ SEARCH_EXERCISES FAILED: %s", str(e))
        return []
    
    data = resp.get("data") or resp
    items = data.get("items") or []
    
    logger.info("✅ SEARCH_EXERCISES: found %d exercises", len(items))
    if len(items) == 0:
        logger.warning("⚠️ SEARCH_EXERCISES: 0 results! Params: group=%s movement=%s split=%s query=%s",
                       muscle_group, movement_type, split, query)
    
    result = [
        {
            "id": ex.get("id"),
            "name": ex.get("name"),
            "category": ex.get("category"),
            "primary_muscles": ex.get("muscles", {}).get("primary", []),
            "secondary_muscles": ex.get("muscles", {}).get("secondary", []),
            "muscle_groups": ex.get("muscles", {}).get("category", []),
            "equipment": ex.get("equipment", []),
            "level": ex.get("metadata", {}).get("level"),
            "movement_type": ex.get("movement", {}).get("type"),
            "split": ex.get("movement", {}).get("split"),
        }
        for ex in items
    ]
    
    # Log first few exercise names for debugging
    if result:
        names = [r.get("name", "?") for r in result[:5]]
        logger.info("📋 SEARCH_EXERCISES: first 5 = %s", names)
    
    return result


# ============================================================================
# TOOLS: Workout Creation & Publishing (Combined)
# ============================================================================

def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return slug[:48] or "exercise"


def _extract_reps(value: Any, default: int = 8) -> int:
    if isinstance(value, (int, float)):
        return max(int(value), 1)
    if isinstance(value, str):
        matches = re.findall(r"\d+", value)
        if matches:
            return int(matches[-1])
    return default


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
    
    Args:
        title: Name of the workout (e.g., "Push Day", "Leg Hypertrophy")
        exercises: List of exercises, each with:
            - name: Exercise name (from search results)
            - exercise_id: Catalog ID (from search results) 
            - sets: Number of working sets (int, typically 3-4)
            - reps: Target reps per set (typically 8-12 for hypertrophy)
            - rir: Target RIR for the final set (earlier sets have +1-2 RIR)
            - weight_kg: Target working weight
            - warmup_sets: Optional, auto-calculated for compounds if omitted
            - notes: Optional exercise-specific guidance
        focus: Brief description of the workout's goal
        duration_minutes: Estimated duration (default 45)
        coach_notes: 1-2 sentences explaining why this plan fits the user
    
    Returns:
        Confirmation that the workout was published to the canvas.
    """
    cid = _context.get("canvas_id")
    uid = _context.get("user_id")
    corr = _context.get("correlation_id")
    
    if not cid or not uid:
        return {"error": "Missing canvas_id or user_id - context not set"}
    
    # Build exercise blocks
    blocks: List[Dict[str, Any]] = []
    
    for idx, ex in enumerate(exercises):
        if not isinstance(ex, dict):
            continue
            
        name = ex.get("name") or ex.get("exercise_name") or "Exercise"
        exercise_id = ex.get("exercise_id") or ex.get("id") or _slugify(name)
        
        reps = _extract_reps(ex.get("reps"), 8)
        final_rir = _coerce_int(ex.get("rir"), 2)
        weight = ex.get("weight_kg") or ex.get("weight")
        if weight is not None:
            try:
                weight = float(weight)
            except (TypeError, ValueError):
                weight = None
        
        category = ex.get("category", "").lower()
        is_compound = category == "compound" or idx < 2  # First exercises typically compound
        
        # Build explicit sets array
        sets: List[Dict[str, Any]] = []
        num_working = _coerce_int(ex.get("sets", 3), 3)
        num_warmup = ex.get("warmup_sets")
        
        if num_warmup is None:
            num_warmup = 2 if is_compound and weight and weight >= 40 else 0
        else:
            num_warmup = _coerce_int(num_warmup, 0)
        
        # Add warmup sets with ramping weight
        if num_warmup > 0 and weight:
            warmup_weights = {
                1: [0.5],
                2: [0.4, 0.7],
                3: [0.3, 0.5, 0.7],
            }.get(num_warmup, [0.4, 0.7])
            
            for i, pct in enumerate(warmup_weights[:num_warmup]):
                sets.append({
                    "id": str(uuid.uuid4())[:8],
                    "type": "warmup",
                    "target": {
                        "reps": 10 if i == 0 else 6,
                        "rir": 5,  # Warmups are easy
                        "weight": round(weight * pct / 2.5) * 2.5,
                    },
                })
        
        # Add working sets with RIR progression
        for i in range(num_working):
            sets_remaining = num_working - i - 1
            set_rir = min(final_rir + sets_remaining, 5)
            
            target = {"reps": reps, "rir": set_rir}
            if weight is not None:
                target["weight"] = weight
            
            sets.append({
                "id": str(uuid.uuid4())[:8],
                "type": "working",
                "target": target,
            })
        
        blocks.append({
            "id": str(uuid.uuid4())[:8],
            "exercise_id": exercise_id,
            "name": name,
            "sets": sets,
            "primary_muscles": ex.get("primary_muscles") or [],
            "equipment": (ex.get("equipment") or [None])[0] if isinstance(ex.get("equipment"), list) else ex.get("equipment"),
            "coach_note": ex.get("notes") or ex.get("rationale"),
        })
    
    if not blocks:
        return {"error": "No valid exercises provided"}
    
    # Build the session_plan card
    card = {
        "type": "session_plan",
        "lane": "workout",
        "priority": 90,
        "actions": [
            {"kind": "accept_plan", "label": "Accept Plan", "style": "primary", "iconSystemName": "checkmark"},
            {"kind": "dismiss_plan", "label": "Dismiss", "style": "secondary", "iconSystemName": "xmark"},
            {"kind": "follow_up", "label": "Adjust", "style": "ghost", "iconSystemName": "bubble.left"},
        ],
        "content": {
            "title": title,
            "blocks": blocks,
            "estimated_duration_minutes": duration_minutes,
            "coach_notes": coach_notes,
        },
    }
    
    # Publish via proposeCards
    logger.info("🎯 PROPOSE_WORKOUT: canvas=%s title='%s' exercises=%d",
                cid, title, len(blocks))
    
    try:
        resp = _canvas_client().propose_cards(
            canvas_id=cid,
            cards=[card],
            user_id=uid,
            correlation_id=corr,
        )
        logger.info("✅ PROPOSE_WORKOUT SUCCESS: response=%s", resp.get("success", resp.get("status", "unknown")))
    except Exception as e:
        logger.error("❌ PROPOSE_WORKOUT FAILED: %s", str(e))
        return {"error": f"Failed to publish workout: {str(e)}"}
    
    # Emit telemetry
    try:
        _canvas_client().emit_event(
            user_id=uid,
            canvas_id=cid,
            event_type="plan_workout",
            payload={
                "task": "plan_workout",
                "status": "published",
                "title": title,
                "exercise_count": len(blocks),
            },
            correlation_id=corr,
        )
    except Exception as e:
        logger.warning("⚠️ PROPOSE_WORKOUT telemetry failed: %s", str(e))
    
    return {
        "status": "published",
        "message": f"'{title}' published to canvas",
        "exercises": len(blocks),
        "total_sets": sum(len(b.get("sets", [])) for b in blocks),
    }


# ============================================================================
# TOOLS: Communication
# ============================================================================

def tool_ask_user(*, question: str) -> Dict[str, Any]:
    """
    Ask the user a clarifying question. Use this only when the request is 
    genuinely ambiguous and clarification would significantly change your output.
    
    The conversation pauses until they respond.
    """
    cid = _context.get("canvas_id")
    uid = _context.get("user_id")
    corr = _context.get("correlation_id")
    
    qid = f"clarify_{uuid.uuid4().hex[:8]}"
    
    if cid and uid:
        _canvas_client().emit_event(
            user_id=uid,
            canvas_id=cid,
            event_type="clarification.request",
            payload={"id": qid, "question": question},
            correlation_id=corr,
        )
    
    logger.info("ask_user question=%s", question[:50])
    
    return {
        "status": "question_sent",
        "question_id": qid,
        "instruction": "Wait for the user's response before continuing."
    }


def tool_send_message(*, message: str) -> Dict[str, Any]:
    """
    Send a text message to the user. Use this for explanations, 
    confirmations, or when no workout card is needed.
    """
    cid = _context.get("canvas_id")
    uid = _context.get("user_id")
    corr = _context.get("correlation_id")
    
    if cid and uid:
        _canvas_client().emit_event(
            user_id=uid,
            canvas_id=cid,
            event_type="agent_message",
            payload={"text": message},
            correlation_id=corr,
        )
    
    logger.info("send_message length=%d", len(message))
    
    return {"status": "sent", "message": message}


# ============================================================================
# TOOLS: Routine Creation (Multi-Workout Draft)
# ============================================================================

def tool_propose_routine(
    *,
    name: str,
    frequency: int,
    workouts: List[Dict[str, Any]],
    description: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Propose a complete routine with multiple workouts as a single draft.
    Creates a routine_summary card + session_plan cards for each day.
    
    Use this when the user asks for a "routine", "program", "split", "PPL", etc.
    
    Args:
        name: Routine name (e.g., "Push Pull Legs", "Upper Lower", "Full Body 3x")
        frequency: Times per week (e.g., 3, 4, 5, 6)
        description: Brief description of the routine's purpose
        workouts: List of workout days, each with:
            - title: Day name (e.g., "Push", "Pull", "Legs", "Upper A")
            - exercises: List of exercises, each with:
                - name: Exercise name (from search)
                - exercise_id: Catalog ID (from search)
                - sets: Number of working sets
                - reps: Target reps
                - rir: Target RIR for final set
                - weight_kg: Target weight (optional)
    
    Returns:
        Confirmation that routine was published to canvas with draft_id.
        The user can then review, edit, and save the routine.
    
    Example:
        tool_propose_routine(
            name="Push Pull Legs",
            frequency=6,
            workouts=[
                {"title": "Push", "exercises": [...]},
                {"title": "Pull", "exercises": [...]},
                {"title": "Legs", "exercises": [...]},
            ]
        )
    """
    cid = _context.get("canvas_id")
    uid = _context.get("user_id")
    corr = _context.get("correlation_id")
    
    if not cid or not uid:
        return {"error": "Missing canvas_id or user_id - context not set"}
    
    if not workouts:
        return {"error": "At least one workout is required"}
    
    cards: List[Dict[str, Any]] = []
    
    # Build session_plan cards for each workout day
    workout_summaries = []
    for idx, workout in enumerate(workouts):
        title = workout.get("title") or f"Day {idx + 1}"
        exercises = workout.get("exercises") or []
        
        # Build exercise blocks (same logic as tool_propose_workout)
        blocks: List[Dict[str, Any]] = []
        for ex_idx, ex in enumerate(exercises):
            if not isinstance(ex, dict):
                continue
            
            ex_name = ex.get("name") or ex.get("exercise_name") or "Exercise"
            exercise_id = ex.get("exercise_id") or ex.get("id") or _slugify(ex_name)
            
            reps = _extract_reps(ex.get("reps"), 8)
            final_rir = _coerce_int(ex.get("rir"), 2)
            weight = ex.get("weight_kg") or ex.get("weight")
            if weight is not None:
                try:
                    weight = float(weight)
                except (TypeError, ValueError):
                    weight = None
            
            num_working = _coerce_int(ex.get("sets", 3), 3)
            
            # Build sets array
            sets: List[Dict[str, Any]] = []
            for i in range(num_working):
                sets_remaining = num_working - i - 1
                set_rir = min(final_rir + sets_remaining, 5)
                
                target = {"reps": reps, "rir": set_rir}
                if weight is not None:
                    target["weight"] = weight
                
                sets.append({
                    "id": str(uuid.uuid4())[:8],
                    "type": "working",
                    "target": target,
                })
            
            blocks.append({
                "id": str(uuid.uuid4())[:8],
                "exercise_id": exercise_id,
                "name": ex_name,
                "sets": sets,
                "primary_muscles": ex.get("primary_muscles") or [],
                "equipment": (ex.get("equipment") or [None])[0] if isinstance(ex.get("equipment"), list) else ex.get("equipment"),
            })
        
        # Estimate duration (5 min per exercise average)
        estimated_duration = len(blocks) * 5 + 10  # +10 for warmup/cooldown
        
        # Create session_plan card for this day
        day_card = {
            "type": "session_plan",
            "lane": "workout",
            "content": {
                "title": title,
                "blocks": blocks,
                "estimated_duration_minutes": estimated_duration,
            },
            "actions": [
                {"kind": "expand", "label": "View Details", "style": "ghost"},
            ],
        }
        cards.append(day_card)
        
        # Build summary for this day (card_id will be set by backend)
        workout_summaries.append({
            "day": idx + 1,
            "title": title,
            "card_id": None,  # Backend will set this
            "estimated_duration": estimated_duration,
            "exercise_count": len(blocks),
        })
    
    # Create routine_summary anchor card (FIRST in array so backend knows to link)
    summary_card = {
        "type": "routine_summary",
        "lane": "workout",
        "priority": 95,  # Higher than session_plans so it appears first
        "content": {
            "name": name,
            "description": description,
            "frequency": frequency,
            "workouts": workout_summaries,
        },
        "actions": [
            {"kind": "save_routine", "label": "Save Routine", "style": "primary", "iconSystemName": "checkmark"},
            {"kind": "dismiss_draft", "label": "Dismiss", "style": "secondary", "iconSystemName": "xmark"},
        ],
    }
    
    # Put summary first, then day cards
    all_cards = [summary_card] + cards
    
    logger.info("🎯 PROPOSE_ROUTINE: canvas=%s name='%s' workouts=%d total_exercises=%d",
                cid, name, len(workouts), sum(len(w.get("exercises", [])) for w in workouts))
    
    # Publish all cards at once (backend will assign group_id, draft_id, link card_ids)
    try:
        resp = _canvas_client().propose_cards(
            canvas_id=cid,
            cards=all_cards,
            user_id=uid,
            correlation_id=corr,
        )
        # Verify the response indicates success
        is_success = resp.get("success", False)
        created_ids = resp.get("data", {}).get("created_card_ids") or resp.get("created_card_ids") or []
        
        if not is_success:
            error_msg = resp.get("error", {}).get("message") if isinstance(resp.get("error"), dict) else str(resp.get("error", "Unknown error"))
            logger.error("❌ PROPOSE_ROUTINE REJECTED: %s", error_msg)
            return {"error": f"Backend rejected routine: {error_msg}"}
        
        logger.info("✅ PROPOSE_ROUTINE SUCCESS: cards=%d created_ids=%s", 
                    len(all_cards), created_ids)
    except Exception as e:
        logger.error("❌ PROPOSE_ROUTINE FAILED: %s", str(e))
        return {"error": f"Failed to publish routine: {str(e)}"}
    
    # Emit telemetry
    try:
        _canvas_client().emit_event(
            user_id=uid,
            canvas_id=cid,
            event_type="plan_routine",
            payload={
                "task": "plan_routine",
                "status": "published",
                "name": name,
                "workout_count": len(workouts),
                "frequency": frequency,
            },
            correlation_id=corr,
        )
    except Exception as e:
        logger.warning("⚠️ PROPOSE_ROUTINE telemetry failed: %s", str(e))
    
    return {
        "status": "published",
        "message": f"'{name}' routine published to canvas ({len(workouts)} workouts)",
        "workout_count": len(workouts),
        "total_exercises": sum(len(w.get("exercises", [])) for w in workouts),
    }


# ============================================================================
# ALL TOOLS
# ============================================================================

all_tools = [
    # User context
    FunctionTool(func=tool_get_user_profile),
    FunctionTool(func=tool_get_recent_workouts),
    # Routine & template context
    FunctionTool(func=tool_get_planning_context),
    FunctionTool(func=tool_get_next_workout),
    FunctionTool(func=tool_get_template),
    FunctionTool(func=tool_save_workout_as_template),
    FunctionTool(func=tool_create_routine),
    FunctionTool(func=tool_manage_routine),
    # Exercise catalog
    FunctionTool(func=tool_search_exercises),
    # Workout creation
    FunctionTool(func=tool_propose_workout),
    FunctionTool(func=tool_propose_routine),  # Multi-day routine draft
    # Communication
    FunctionTool(func=tool_ask_user),
    FunctionTool(func=tool_send_message),
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
# UNIFIED AGENT INSTRUCTION
# ============================================================================

UNIFIED_INSTRUCTION = """
## ROLE
You are the Planner Agent. You plan and edit workouts and routines as canvas artifacts.
You behave like a two-way editor, not a chatty assistant.

## CANVAS PRINCIPLE
- The card is the output. Chat text is only a control surface.
- When the user asks “how should we modify”, you must propose an updated draft AND attach rationale inside the artifact (not as long chat prose).

## CRITICAL OUTPUT RULES
1. Start by understanding the user's request, look over the tools you have available to you, and plan what steps to take to fulfil the request. 
2. Once you understand what the user has asked you to do, and you know what you need to do in order to satisfy the request, give the user a one-time 1 (max 2) sentence summary before you begin the work.
3. Never narrate searches or tool usage.
4. Never apologize for sparse results. Adapt parameters and continue. Use exercises from whatever results you got.
5. ALWAYS COMPLETE THE TASK: If the user asks for a workout or routine, you MUST call tool_propose_workout or tool_propose_routine. Never end the conversation without publishing an artifact.
6. Never output full workout/routine details as chat prose. Publish via tool_propose_workout or tool_propose_routine.
7. After a successful propose call, output at most 1 short control sentence.
8. Never ask for template IDs or card IDs.
9. Do not auto save.

## TOOLS
- tool_get_planning_context: constraints + defaults
- tool_search_exercises: exercise candidates
- tool_propose_workout: publish single workout draft
- tool_propose_routine: publish full routine draft in one call
- tool_get_next_workout: next planned session from active routine
- tool_ask_user: only under ASK POLICY
(If history/progression tools exist in the environment, use them. If not available, fall back to conservative defaults.)

## ASK POLICY (1 QUESTION MAX, ONLY IF BLOCKING)
Ask only if you cannot generate a safe/correct draft:
- Missing routine frequency/days when user clearly wants a routine
- Equipment constraints block all reasonable options
- Injury/pain constraint is needed to avoid risky choices
Otherwise propose a draft using defaults.

## INTENT PARSING (EVERY TURN)
Classify as:
A) Create single workout
B) Create routine (multi-day)
C) Edit existing workout/routine

Routine intent requires explicit multi-day structure or explicit frequency.
Negative triggers: split squat, Bulgarian split squat, split stance.

Default to single workout when ambiguous.

## CORE WORKFLOW (MANDATORY)
1) Fetch planning context (tool_get_planning_context) unless already fetched this turn.
2) If request is an EDIT or OPTIMIZATION, start from the existing artifact and apply minimal deltas.
3) Use data (history/progression) if available to decide what to change.
4) Propose updated draft using the correct tool.
5) Output one short control sentence.

### Inputs you should use when available
- Past workouts and exercise history
- Exercise-level progression (load, reps, RIR, volume)
- Muscle-group progression deltas and volume distribution
- Pain/injury flags + tolerated movement patterns
- Time per session + weekly frequency

### Optimization levers (choose the smallest set that solves the problem)
1) Volume: add/remove sets, reallocate weekly sets across muscles
2) Frequency: redistribute target muscle across days without increasing total session time (if possible)
3) Exercise selection: swap to better ROM/stability/angle/equipment fit
4) Intensity/rep ranges: adjust ranges and target RIR
5) Order/rest: reduce performance drop-offs on the target muscle

## SEARCH STRATEGY (POOL-FIRST, BUDGETED)

Goal: Fetch one broad candidate pool, then select locally from that pool.

Budget:
- Single workout: 1 search call. Optional 1 retry only if usable candidates < 12.
- Routine: 1 search call per day type (Push/Pull/Legs or Upper/Lower). Optional 1 retry per day type only if usable candidates < 12.
After budget is used, stop searching and build with what you have.

Primary broad fetch (choose one):
- Push day: movement_type="push", limit=50
- Pull day: movement_type="pull", limit=50
- Legs day: split="lower", limit=50

Selection happens locally:
- From the broad results, rank by: user goal → injury safety → equipment preference → movement pattern fit → variety.
- Do not perform extra searches to “validate” each exercise slot. Fill the workout from the pool.

Equipment handling:
- Treat equipment as a preference unless the user explicitly says “only machines” (or equivalent).
- Default: do NOT filter by equipment in the search. Prefer matching equipment during ranking.
- If “only machines”: apply equipment="machine" in the broad fetch.
- If the pool cannot satisfy a complete workout under the preference, relax in this order:
  machine → cable → dumbbell → barbell → bodyweight

Name searches:
- Use query/name search only when the user asks for a specific exercise by name.

## ROUTINE RULES (CRITICAL)
If creating or editing a routine (user asks for "routine", "program", "split", "PPL", etc.):
- NEVER call tool_propose_workout when building a routine. Use tool_propose_routine ONLY.
- Build ALL days locally (in memory), then call tool_propose_routine EXACTLY ONCE with all workouts.
- NEVER propose days one at a time via tool_propose_workout. One tool_propose_routine call = complete routine.
- If user already has a workout card on canvas and wants to expand it into a routine:
  1) Extract the exercises from the existing card conceptually (read them from context)
  2) Build the missing days by searching for new exercises
  3) Call tool_propose_routine ONCE with all days (existing + new)
  The routine proposal will include the original day AND the new days together.

## DEFAULT TRAINING PARAMETERS (IF NO HISTORY)
Hypertrophy default:
- Exercises: Aim for 4-5 exercises per workout, (1-2 compounds, 2-3 isolations)
- Compounds: 3–4 sets, 6–10 reps, RIR 1–2
- Isolations: 2–4 sets, 10–15 reps, RIR 0–2
- Rest: 2–3 min compounds, 60–90 sec isolations
Progression: double progression (top of range across sets at target RIR → smallest load increase).
If the user has a workout history, you should try to adapt to their structure (assuming it follows hypertrophy principles, otherwise challenge it), and aim to optimize. 

## LOAD TARGETS + WARM-UPS
- Every non-bodyweight exercise must include a target load (even if estimated).
- If exercise history exists: use the most recent working load as the target and apply simple progression rules.
- If no exact match: infer from closest pattern (press↔press, row↔row, pulldown↔pulldown, squat/hinge).
- If no usable history at all: choose conservative starter loads based on fitness level and equipment (undershoot).

Warm-ups:
- Compounds: include 2 warm-up sets (3 if heavy or low-rep).
- Isolations: warm-up sets optional, default 0.

## TEXT RESPONSE
After proposing, output exactly one short sentence describing the update (eg “Updated your routine to focus more on your quads.”). If and when relevant to the context, you can attach a short rationale (eg "This should materially help you reach your goal of growing chunky legs."). Keep it short - Do not dump long explanations in chat.
"""

# ============================================================================
# AGENT DEFINITION
# ============================================================================

PlannerAgent = Agent(
    name="PlannerAgent",
    model=os.getenv("CANVAS_PLANNER_MODEL", "gemini-2.5-flash"),
    instruction=UNIFIED_INSTRUCTION,
    tools=all_tools,
    before_tool_callback=_before_tool_callback,
    before_model_callback=_before_model_callback,
)

# For backwards compatibility
UnifiedAgent = PlannerAgent
root_agent = PlannerAgent

__all__ = ["root_agent", "PlannerAgent", "UnifiedAgent"]
