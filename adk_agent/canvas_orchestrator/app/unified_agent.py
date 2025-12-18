"""
Unified Canvas Agent - Single agent architecture with explicit state management.

This replaces the multi-agent transfer pattern which causes issues with:
1. Session state not persisting across clarification requests
2. Agent transfers getting stuck in loops
3. CardAgent not receiving proper context

Design principles:
- ONE agent that handles the full flow
- Explicit state tracking via canvas context
- All tools available to the agent
- No transfers - agent decides what to do based on conversation history
"""

from __future__ import annotations

import logging
import os
import re
import time
import uuid
from typing import Any, Dict, List, Optional

from google.adk import Agent
from google.adk.tools import FunctionTool

from app.libs.tools_canvas.client import CanvasFunctionsClient

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Global context for the current request
_context: Dict[str, Any] = {
    "canvas_id": None,
    "user_id": None,
    "correlation_id": None,
    "conversation_state": "initial",  # initial, clarifying, planning, publishing
    "pending_clarification_id": None,
    "gathered_info": {},  # Store info gathered from clarifications
}
_client: Optional[CanvasFunctionsClient] = None


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
# CONTEXT TOOLS
# ============================================================================

def tool_set_context(
    *,
    canvas_id: Optional[str] = None,
    user_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Set the canvas/user context for this request.
    ALWAYS call this first with values from the context prefix.
    """
    if canvas_id:
        _context["canvas_id"] = canvas_id.strip()
    if user_id:
        _context["user_id"] = user_id.strip()
    if correlation_id:
        _context["correlation_id"] = correlation_id.strip()
    
    logger.info("set_context canvas=%s user=%s corr=%s",
                _context.get("canvas_id"), _context.get("user_id"), _context.get("correlation_id"))
    
    return {"status": "ok", "context": dict(_context)}


def tool_get_user_profile(*, user_id: Optional[str] = None) -> Dict[str, Any]:
    """Get the user's profile including goals, experience level, equipment, etc."""
    uid = _resolve(user_id, "user_id")
    if not uid:
        return {"error": "No user_id available"}
    
    logger.info("get_user_profile uid=%s", uid)
    resp = _canvas_client().get_user(uid)
    return resp.get("data") or resp.get("context") or {}


def tool_get_recent_workouts(*, user_id: Optional[str] = None, limit: int = 5) -> List[Dict[str, Any]]:
    """Get the user's recent workout sessions for context."""
    uid = _resolve(user_id, "user_id")
    if not uid:
        return []
    
    logger.info("get_recent_workouts uid=%s limit=%s", uid, limit)
    resp = _canvas_client().get_user_workouts(uid, limit=limit)
    return resp.get("data") or resp.get("workouts") or []


# ============================================================================
# EXERCISE CATALOG TOOLS
# ============================================================================

def tool_search_exercises(
    *,
    primary_muscle: Optional[str] = None,
    muscle_group: Optional[str] = None,
    split: Optional[str] = None,
    category: Optional[str] = None,
    equipment: Optional[str] = None,
    query: Optional[str] = None,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """
    Search the exercise catalog from Firestore to get REAL exercises with their IDs.
    ALWAYS use this to find exercises before creating workout plans.
    
    Args:
        primary_muscle: Filter by primary muscle (e.g., "quadriceps", "chest", "lats")
        muscle_group: Filter by muscle category (e.g., "legs", "chest", "back")
        split: Filter by workout split (e.g., "push", "pull", "legs", "upper", "lower")
        category: Filter by movement category (e.g., "compound", "isolation")
        equipment: Filter by equipment (e.g., "barbell", "dumbbell", "cable", "bodyweight")
        query: Text search (matches name, muscles, etc.)
        limit: Max results (default 10)
    
    Returns:
        List of exercises with id, name, muscles, equipment, etc.
    """
    logger.info("search_exercises muscle=%s group=%s split=%s query=%s", 
                primary_muscle, muscle_group, split, query)
    
    resp = _canvas_client().search_exercises(
        primary_muscle=primary_muscle,
        muscle_group=muscle_group,
        split=split,
        category=category,
        equipment=equipment,
        query=query,
        limit=limit,
    )
    
    items = resp.get("items") or []
    
    # Return simplified exercise data for the agent
    return [
        {
            "id": ex.get("id"),
            "name": ex.get("name"),
            "category": ex.get("category"),
            "primary_muscles": ex.get("muscles", {}).get("primary", []),
            "secondary_muscles": ex.get("muscles", {}).get("secondary", []),
            "equipment": ex.get("equipment", []),
            "level": ex.get("metadata", {}).get("level"),
            "movement_type": ex.get("movement", {}).get("type"),
            "split": ex.get("movement", {}).get("split"),
        }
        for ex in items
    ]


# ============================================================================
# CLARIFICATION TOOLS
# ============================================================================

def tool_ask_user(
    *,
    question: str,
    question_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Ask the user a clarifying question. The conversation will pause until they respond.
    Use this when you need more information to proceed.
    
    Args:
        question: The question to ask the user
        question_id: Optional ID to track this question (auto-generated if not provided)
    
    Returns:
        Confirmation that the question was sent. The user's answer will come in the next message.
    """
    cid = _context.get("canvas_id")
    uid = _context.get("user_id")
    corr = _context.get("correlation_id")
    
    qid = question_id or f"clarify_{uuid.uuid4().hex[:8]}"
    
    _context["conversation_state"] = "clarifying"
    _context["pending_clarification_id"] = qid
    
    payload = {"id": qid, "question": question}
    
    if cid and uid:
        _canvas_client().emit_event(
            user_id=uid,
            canvas_id=cid,
            event_type="clarification.request",
            payload=payload,
            correlation_id=corr,
        )
    
    logger.info("ask_user question_id=%s question=%s", qid, question[:50])
    
    return {
        "status": "question_sent",
        "question_id": qid,
        "message": f"Question sent to user: {question}",
        "instruction": "STOP HERE. Wait for the user's response in the next message. Do not continue planning until they answer."
    }


def tool_record_user_info(
    *,
    key: str,
    value: str,
) -> Dict[str, Any]:
    """
    Record information gathered from the user (from their clarification response).
    Use this to track what you've learned.
    
    Args:
        key: What type of info this is (e.g., "workout_type", "focus_area", "equipment")
        value: The user's answer
    """
    _context.setdefault("gathered_info", {})[key] = value
    _context["conversation_state"] = "planning"
    _context["pending_clarification_id"] = None
    
    logger.info("record_user_info key=%s value=%s", key, value[:50] if value else None)
    
    return {
        "status": "recorded",
        "gathered_info": dict(_context.get("gathered_info", {})),
        "message": f"Recorded {key}: {value}"
    }


# ============================================================================
# WORKOUT PLANNING TOOLS
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


def tool_create_workout_plan(
    *,
    title: str,
    exercises: List[Dict[str, Any]],
    focus: Optional[str] = None,
    duration_minutes: int = 45,
    coach_notes: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a workout plan with specific exercises.
    
    Args:
        title: Name of the workout (e.g., "Leg Day", "Upper Body Strength")
        exercises: List of exercises, each with:
            - name: Exercise name
            - exercise_id: Optional catalog ID
            - sets: Number of sets (int) OR list of set targets
            - reps: Target reps per set
            - rir: Reps in reserve (default 2)
            - weight_kg: Optional suggested weight
            - notes: Optional exercise-specific notes
        focus: Short description of the workout focus
        duration_minutes: Estimated duration
        coach_notes: Explanation of why this plan fits the user
    
    Returns:
        Formatted workout plan ready for publishing
    """
    blocks: List[Dict[str, Any]] = []
    
    for ex in exercises:
        if not isinstance(ex, dict):
            continue
            
        name = ex.get("name") or ex.get("exercise_name") or "Exercise"
        exercise_id = ex.get("exercise_id") or ex.get("id") or _slugify(name)
        
        # Handle sets
        raw_sets = ex.get("sets", 3)
        if isinstance(raw_sets, int):
            reps = _extract_reps(ex.get("reps"), 8)
            rir = _coerce_int(ex.get("rir"), 2)
            weight = ex.get("weight_kg") or ex.get("weight")
            sets = []
            for _ in range(raw_sets):
                target: Dict[str, Any] = {"reps": reps, "rir": rir}
                if weight and isinstance(weight, (int, float)):
                    target["weight"] = float(weight)
                sets.append({"target": target})
        elif isinstance(raw_sets, list):
            sets = []
            for s in raw_sets:
                if isinstance(s, dict):
                    target = s.get("target") or s
                    sets.append({"target": target})
                else:
                    sets.append({"target": {"reps": 8, "rir": 2}})
        else:
            sets = [{"target": {"reps": 8, "rir": 2}} for _ in range(3)]
        
        blocks.append({
            "exercise_id": exercise_id,
            "name": name,
            "exercise_name": name,
            "sets": sets,
            "set_count": len(sets),
            "notes": ex.get("notes") or ex.get("rationale"),
        })
    
    if not blocks:
        return {
            "error": "No valid exercises provided",
            "instruction": "Please specify exercises with at least a name and number of sets"
        }
    
    plan = {
        "title": title,
        "focus": focus or "Custom workout",
        "duration_minutes": duration_minutes,
        "blocks": blocks,
        "coach_notes": coach_notes,
    }
    
    # Store in context for publishing
    _context["pending_plan"] = plan
    _context["conversation_state"] = "ready_to_publish"
    
    logger.info("create_workout_plan title=%s exercises=%d", title, len(blocks))
    
    return {
        "status": "plan_created",
        "plan": plan,
        "instruction": "Plan created. Now call tool_publish_workout_plan to show it to the user."
    }


def tool_publish_workout_plan(
    *,
    plan: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Publish the workout plan to the canvas so the user can see it.
    
    Args:
        plan: The workout plan (if not provided, uses the pending plan from tool_create_workout_plan)
    """
    cid = _context.get("canvas_id")
    uid = _context.get("user_id")
    corr = _context.get("correlation_id")
    
    if not cid or not uid:
        return {"error": "Missing canvas_id or user_id"}
    
    plan_data = plan or _context.get("pending_plan")
    if not plan_data:
        return {"error": "No plan to publish. Call tool_create_workout_plan first."}
    
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
            "title": plan_data.get("title", "Workout"),
            "blocks": plan_data.get("blocks", []),
            "estimated_duration_minutes": plan_data.get("duration_minutes", 45),
            "coach_notes": plan_data.get("coach_notes"),
        },
    }
    
    # Publish via proposeCards
    logger.info("publish_workout_plan canvas=%s corr=%s blocks=%d",
                cid, corr, len(plan_data.get("blocks", [])))
    
    resp = _canvas_client().propose_cards(
        canvas_id=cid,
        cards=[card],
        user_id=uid,
        correlation_id=corr,
    )
    
    # Emit telemetry
    _canvas_client().emit_event(
        user_id=uid,
        canvas_id=cid,
        event_type="plan_workout",
        payload={
            "task": "plan_workout",
            "status": "published",
            "title": plan_data.get("title"),
            "exercise_count": len(plan_data.get("blocks", [])),
        },
        correlation_id=corr,
    )
    
    _context["pending_plan"] = None
    _context["conversation_state"] = "complete"
    
    return {
        "status": "published",
        "message": f"Workout '{plan_data.get('title')}' published to canvas",
        "card_count": 1
    }


# ============================================================================
# RESPONSE TOOLS
# ============================================================================

def tool_send_message(
    *,
    message: str,
) -> Dict[str, Any]:
    """
    Send a text message to the user (appears in the chat timeline).
    Use this for explanations, confirmations, or when no card output is needed.
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


def tool_emit_status(
    *,
    event_type: str,
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Emit a status/telemetry event for debugging or tracking.
    """
    cid = _context.get("canvas_id")
    uid = _context.get("user_id")
    corr = _context.get("correlation_id")
    
    if cid and uid:
        _canvas_client().emit_event(
            user_id=uid,
            canvas_id=cid,
            event_type=event_type,
            payload=payload or {},
            correlation_id=corr,
        )
    
    return {"status": "emitted", "event_type": event_type}


# ============================================================================
# ALL TOOLS
# ============================================================================

all_tools = [
    FunctionTool(func=tool_set_context),
    FunctionTool(func=tool_get_user_profile),
    FunctionTool(func=tool_get_recent_workouts),
    FunctionTool(func=tool_search_exercises),
    FunctionTool(func=tool_ask_user),
    FunctionTool(func=tool_record_user_info),
    FunctionTool(func=tool_create_workout_plan),
    FunctionTool(func=tool_publish_workout_plan),
    FunctionTool(func=tool_send_message),
    FunctionTool(func=tool_emit_status),
]


# ============================================================================
# UNIFIED AGENT
# ============================================================================

UNIFIED_INSTRUCTION = """
You are the Myon Fitness Coach Agent. Your job is to CREATE WORKOUT PLANS FAST using REAL exercises from the catalog.

## STEP 1: Set Context (REQUIRED)
Parse `(context: canvas_id=XYZ user_id=ABC corr=...)` and call `tool_set_context(...)`.

## STEP 2: Search Exercises from Catalog (REQUIRED)
ALWAYS use `tool_search_exercises(...)` to find real exercises from our database.
This is CRITICAL - exercises must have valid IDs from the catalog.

Search parameters:
- `split`: "push", "pull", "legs", "upper", "lower", "full"
- `muscle_group`: "chest", "back", "legs", "shoulders", "arms"
- `primary_muscle`: "quadriceps", "chest", "lats", "hamstrings", etc.
- `category`: "compound", "isolation"
- `equipment`: "barbell", "dumbbell", "cable", "machine", "bodyweight"

Example searches:
- Leg day: `tool_search_exercises(split="legs", limit=8)`
- Push day: `tool_search_exercises(split="push", limit=8)`
- Back exercises: `tool_search_exercises(muscle_group="back", limit=6)`

## STEP 3: Create and Publish Plan
Use the EXACT `id` and `name` from search results in `tool_create_workout_plan`.

## FLOW:
1. `tool_set_context(...)`
2. `tool_search_exercises(split="...", limit=8)` - get real exercises
3. Pick 5 exercises from results, use their `id` as `exercise_id`
4. `tool_create_workout_plan(title="...", exercises=[{exercise_id: "...", name: "...", sets: 3, reps: 8}])`
5. `tool_publish_workout_plan()`

## REQUEST MAPPINGS:
- "Plan a workout" / "I want to train" → search split="full", pick 5
- "Leg day" / "leg workout" → search split="legs", pick 5
- "Upper body" → search split="upper", pick 5
- "Push day" → search split="push", pick 5
- "Pull day" / "back workout" → search split="pull", pick 5
- "Chest and triceps" → search muscle_group="chest", then muscle_group="triceps"

## DEFAULTS:
- Sets: 3
- Reps: 8
- RIR: 2
- Duration: 45 minutes
- Exercises: 5

## CRITICAL RULES:
- ALWAYS search exercises first - never invent exercise names
- Use the `id` field from search results as `exercise_id` in the plan
- Use the exact `name` from search results
- If search returns no results, try a broader search (remove filters)

DO NOT:
- Make up exercise names - they won't exist in database
- Skip the search step
- Use hardcoded exercise lists
- Ask clarifying questions unless user says only "Hello" or "Hi"
"""

UnifiedAgent = Agent(
    name="MYONCoach",
    model=os.getenv("CANVAS_AGENT_MODEL", "gemini-2.5-pro"),
    instruction=UNIFIED_INSTRUCTION,
    tools=all_tools,
)

# Export as root agent
root_agent = UnifiedAgent

__all__ = ["root_agent", "UnifiedAgent"]
