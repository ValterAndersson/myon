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
_context_parsed_for_message: Optional[str] = None  # Track if we've parsed context for this message


def _auto_parse_context(message: str) -> None:
    """Auto-parse context from message prefix to avoid needing tool_set_context calls."""
    global _context_parsed_for_message
    
    # Only parse once per unique message
    if _context_parsed_for_message == message:
        return
    
    # Parse: (context: canvas_id=XYZ user_id=ABC corr=DEF)
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
    
    # Response is wrapped in data.items
    data = resp.get("data") or resp
    items = data.get("items") or []
    
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
    Create a workout plan with specific exercises and explicit per-set arrays.
    
    Args:
        title: Name of the workout (e.g., "Leg Day", "Upper Body Strength")
        exercises: List of exercises, each with:
            - name: Exercise name
            - exercise_id: Optional catalog ID
            - sets: Number of working sets (int) OR list of explicit set objects
            - reps: Target reps per set
            - rir: Target RIR for the LAST set (earlier sets have higher RIR)
            - weight_kg: Target weight for working sets
            - warmup_sets: Number of warmup sets (0-3, default based on category)
            - notes: Optional exercise-specific notes
        focus: Short description of the workout focus
        duration_minutes: Estimated duration
        coach_notes: Explanation of why this plan fits the user
    
    Returns:
        Formatted workout plan with explicit per-set arrays
    """
    blocks: List[Dict[str, Any]] = []
    
    for idx, ex in enumerate(exercises):
        if not isinstance(ex, dict):
            continue
            
        name = ex.get("name") or ex.get("exercise_name") or "Exercise"
        exercise_id = ex.get("exercise_id") or ex.get("id") or _slugify(name)
        
        # Get base prescription
        reps = _extract_reps(ex.get("reps"), 8)
        final_rir = _coerce_int(ex.get("rir"), 2)  # RIR for the LAST working set
        weight = ex.get("weight_kg") or ex.get("weight")
        if weight is not None:
            try:
                weight = float(weight)
            except (TypeError, ValueError):
                weight = None
        
        # Get category to determine warmup needs
        category = ex.get("category", "").lower()
        is_compound = category == "compound" or idx == 0  # First exercise often compound
        
        # Build explicit sets array
        sets: List[Dict[str, Any]] = []
        raw_sets = ex.get("sets", 3)
        
        if isinstance(raw_sets, list):
            # Already explicit list - use as-is
            for s in raw_sets:
                if isinstance(s, dict):
                    sets.append({
                        "id": str(uuid.uuid4())[:8],
                        "type": s.get("type", "working"),
                        "reps": s.get("reps", reps),
                        "weight": s.get("weight") or s.get("weight_kg") or weight,
                        "rir": s.get("rir"),
                    })
        else:
            # Expand from count to explicit array
            num_working = _coerce_int(raw_sets, 3)
            num_warmup = ex.get("warmup_sets")
            
            if num_warmup is None:
                # Auto-determine warmup sets
                num_warmup = 2 if is_compound and weight and weight >= 40 else 0
            else:
                num_warmup = _coerce_int(num_warmup, 0)
            
            # Add warmup sets (ramping weight)
            if num_warmup > 0 and weight:
                warmup_weights = []
                if num_warmup == 1:
                    warmup_weights = [weight * 0.5]
                elif num_warmup == 2:
                    warmup_weights = [weight * 0.4, weight * 0.7]
                elif num_warmup >= 3:
                    warmup_weights = [weight * 0.3, weight * 0.5, weight * 0.7]
                
                for i, wu_weight in enumerate(warmup_weights[:num_warmup]):
                    sets.append({
                        "id": str(uuid.uuid4())[:8],
                        "type": "warmup",
                        "reps": 10 if i == 0 else 6,  # More reps on lighter warmups
                        "weight": round(wu_weight / 2.5) * 2.5,  # Round to 2.5kg
                        "rir": None,  # No RIR for warmups
                    })
            
            # Add working sets with RIR progression
            # RIR decreases towards the final set
            for i in range(num_working):
                # Calculate RIR for this set (higher for earlier sets)
                sets_remaining = num_working - i - 1
                set_rir = min(final_rir + sets_remaining, 5)  # Cap at 5
                
                sets.append({
                    "id": str(uuid.uuid4())[:8],
                    "type": "working",
                    "reps": reps,
                    "weight": weight,
                    "rir": set_rir,
                })
        
        # Include muscle data for swap functionality
        primary_muscles = ex.get("primary_muscles") or ex.get("primaryMuscles") or []
        equipment_list = ex.get("equipment") or []
        equipment_str = equipment_list[0] if isinstance(equipment_list, list) and equipment_list else None
        
        blocks.append({
            "id": str(uuid.uuid4())[:8],
            "exercise_id": exercise_id,
            "name": name,
            "sets": sets,  # Now explicit per-set array
            "primary_muscles": primary_muscles,
            "equipment": equipment_str,
            "coach_note": ex.get("notes") or ex.get("rationale"),
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
    
    logger.info("create_workout_plan title=%s exercises=%d total_sets=%d", 
                title, len(blocks), sum(len(b.get("sets", [])) for b in blocks))
    
    return {
        "status": "plan_created",
        "plan": plan,
        "instruction": "Plan created. Now call tool_publish_workout_plan to show it to the user."
    }


def tool_publish_workout_plan(
    *,
    plan: Optional[Dict[str, Any]] = None,
    canvas_id: Optional[str] = None,
    user_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Publish the workout plan to the canvas so the user can see it.
    
    Args:
        plan: The workout plan (if not provided, uses the pending plan from tool_create_workout_plan)
        canvas_id: Canvas ID from the context prefix (required if not set via tool_set_context)
        user_id: User ID from the context prefix (required if not set via tool_set_context)
        correlation_id: Correlation ID from the context prefix
    """
    # Accept context from parameters (avoids need for separate tool_set_context call)
    if canvas_id:
        _context["canvas_id"] = canvas_id.strip()
    if user_id:
        _context["user_id"] = user_id.strip()
    if correlation_id:
        _context["correlation_id"] = correlation_id.strip() if correlation_id != "none" else None
        
    cid = _context.get("canvas_id")
    uid = _context.get("user_id")
    corr = _context.get("correlation_id")
    
    if not cid or not uid:
        return {"error": "Missing canvas_id or user_id"}
    
    plan_data = plan or _context.get("pending_plan")
    if not plan_data:
        return {"error": "No plan to publish. Call tool_create_workout_plan first."}
    
    # Transform blocks to match iOS schema
    # Sets use flat structure: type, reps, weight, rir, is_linked_to_base
    blocks = plan_data.get("blocks", [])
    transformed_blocks = []
    for block in blocks:
        # Ensure exercise_id exists
        exercise_id = block.get("exercise_id") or _slugify(block.get("name", "exercise"))
        
        # Transform sets to flat structure matching iOS PlanSet model
        raw_sets = block.get("sets", [])
        transformed_sets = []
        for s in raw_sets:
            set_type = s.get("type", "working")
            reps = s.get("reps", 8)
            # rir is REQUIRED by schema (0-5). Default: warmup=5, working=2
            rir = s.get("rir")
            if rir is None:
                rir = 5 if set_type == "warmup" else 2
            # Ensure rir is clamped to valid range
            rir = max(0, min(5, int(rir)))
            
            # Flat structure matching iOS PlanSet
            transformed_set = {
                "id": s.get("id", str(uuid.uuid4())[:8]),
                "type": set_type,
                "reps": int(reps) if reps else 8,
                "rir": rir if set_type != "warmup" else None,
                "is_linked_to_base": set_type != "warmup",  # Working sets linked by default
            }
            if s.get("weight") is not None:
                transformed_set["weight"] = s.get("weight")
            transformed_sets.append(transformed_set)
        
        transformed_blocks.append({
            "id": block.get("id", str(uuid.uuid4())[:8]),
            "exercise_id": exercise_id,
            "name": block.get("name", "Exercise"),
            "sets": transformed_sets,
            "primary_muscles": block.get("primary_muscles", []),
            "equipment": block.get("equipment"),
            "coach_note": block.get("coach_note"),
        })
    
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
            "blocks": transformed_blocks,
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
You are a strength coach. Create workout plans quickly.

## NEW WORKOUT FLOW
1. `tool_search_exercises(muscle_group="...")`
2. `tool_create_workout_plan(title="...", exercises=[...])`
3. Brief intro: "Here's your workout:"
4. `tool_publish_workout_plan(canvas_id="...", user_id="...")`
5. STOP - done

## SWAP EXERCISE FLOW (when user asks to swap)
If user says "swap X for another exercise":
1. `tool_search_exercises` for target muscle/equipment
2. Pick ONE good replacement from results
3. Rebuild the ENTIRE plan with the swap applied
4. `tool_create_workout_plan` with updated exercises
5. Brief: "Swapped X for Y:"
6. `tool_publish_workout_plan`
7. STOP - done

## ADJUST FLOW (shorter/harder/etc)
Same as swap: rebuild entire plan with adjustment, publish, stop.

## CRITICAL
- After `tool_publish_workout_plan` → output NOTHING
- Do NOT list exercises in text
- Do NOT explain after publishing

## PROGRAMMING
- 4-5 exercises, compounds first
- 3-4 sets × 8-12 reps
- RIR 2 compounds, RIR 1 isolation
- Include weight_kg for every exercise

## WEIGHTS
Beginner: Bench 30kg, Squat 40kg, Row 30kg
Intermediate: Bench 60kg, Squat 80kg, Row 60kg
Isolation: 10-25kg

## FORMAT
Each exercise: exercise_id, name, sets, reps, weight_kg, rir, primary_muscles

## SEARCH
- "chest"/"push" → muscle_group="chest"
- "back"/"pull" → muscle_group="back"
- "legs" → muscle_group="legs"

## COACH_NOTES
1-2 sentences: focus, total sets, intensity.

## RULES
- Search first, never invent exercises
- After publish: STOP. Done.
"""

UnifiedAgent = Agent(
    name="MYONCoach",
    model=os.getenv("CANVAS_AGENT_MODEL", "gemini-2.5-flash"),
    instruction=UNIFIED_INSTRUCTION,
    tools=all_tools,
)

# Export as root agent
root_agent = UnifiedAgent

__all__ = ["root_agent", "UnifiedAgent"]
