"""
Unified Canvas Agent v2.0 - Evidence-based strength coaching with autonomous reasoning.

Design principles:
- Knowledge over procedures: Agent understands WHY, not just WHAT
- Minimal tools: Each tool has a clear purpose
- Adaptive behavior: Uses context intelligently
- Efficient output: Brief, actionable communication
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
# TOOLS: Exercise Catalog
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
    Search the exercise catalog for real exercises with their IDs.
    
    Args:
        primary_muscle: Target muscle (e.g., "quadriceps", "chest", "lats")
        muscle_group: Broad category (e.g., "legs", "back", "arms")
        split: Training split (e.g., "push", "pull", "legs", "upper", "lower")
        category: Movement type - "compound" (multi-joint) or "isolation" (single-joint)
        equipment: Equipment filter (e.g., "barbell", "dumbbell", "cable", "machine")
        query: Free text search for specific exercise names
        limit: Max results (default 10, use 15-20 for more variety)
    
    Returns:
        List of exercises with id, name, muscles, equipment, etc.
        If results are limited, try broader filters or different parameters.
    """
    logger.info("search_exercises muscle=%s group=%s split=%s category=%s query=%s", 
                primary_muscle, muscle_group, split, category, query)
    
    resp = _canvas_client().search_exercises(
        primary_muscle=primary_muscle,
        muscle_group=muscle_group,
        split=split,
        category=category,
        equipment=equipment,
        query=query,
        limit=limit,
    )
    
    data = resp.get("data") or resp
    items = data.get("items") or []
    
    return [
        {
            "id": ex.get("id"),
            "name": ex.get("name"),
            "category": ex.get("category"),
            "primary_muscles": ex.get("muscles", {}).get("primary", []),
            "secondary_muscles": ex.get("muscles", {}).get("secondary", []),
            "equipment": ex.get("equipment", []),
            "level": ex.get("metadata", {}).get("level"),
            "split": ex.get("movement", {}).get("split"),
        }
        for ex in items
    ]


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
    logger.info("propose_workout canvas=%s title=%s exercises=%d",
                cid, title, len(blocks))
    
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
            "title": title,
            "exercise_count": len(blocks),
        },
        correlation_id=corr,
    )
    
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
# ALL TOOLS
# ============================================================================

all_tools = [
    FunctionTool(func=tool_get_user_profile),
    FunctionTool(func=tool_get_recent_workouts),
    FunctionTool(func=tool_search_exercises),
    FunctionTool(func=tool_propose_workout),
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
You are a strength coach. Create workout plans quickly and silently.

## CRITICAL RULES
1. DO NOT output text while working. Execute tools silently.
2. DO NOT apologize or explain failed searches. Just try again.
3. DO NOT narrate your process. Just do it.
4. ONE search is usually enough. Use limit=20 for variety.
5. You MUST call tool_propose_workout to publish workout. Text alone does nothing.
6. Output ONE brief message ONLY after tool_propose_workout returns {"status": "published"}.
7. If you say "here's your workout" you MUST have just called tool_propose_workout.

## SEARCH STRATEGY
Use ONE search with the right parameter:
- Leg workout: muscle_group="legs" limit=20
- Push workout: split="push" limit=15
- Pull workout: split="pull" limit=15
- Full body: category="compound" limit=20
- Specific muscle: primary_muscle="quadriceps" etc.

If search returns <5 results, try query="squat" or query="bench" etc.

## ESSENTIAL LEG EXERCISES
For any leg workout, ALWAYS include:
- A squat variation (search query="squat" if needed)
- A hip hinge (deadlift, RDL)
- Quad isolation (leg extension)
- Hamstring isolation (leg curl)

## WORKOUT STRUCTURE
- 4-5 exercises per workout
- Compounds first, isolation last
- 3-4 sets per exercise
- 8-12 reps for hypertrophy
- RIR 2-3 for compounds, RIR 1-2 for isolation

## FLOW
1. tool_search_exercises (ONE search, limit=20)
2. Pick 4-5 good exercises from results
3. tool_propose_workout with selected exercises
4. Brief confirmation: "Here's your leg workout."
5. DONE - stop responding

## WEIGHTS (if not specified)
Beginner: Squat 40kg, Deadlift 50kg, Leg Press 80kg
Intermediate: Squat 80kg, Deadlift 100kg, Leg Press 140kg
Isolation: 15-30kg

## NEVER DO
- Output text between tool calls
- Apologize for search issues
- Explain what you're doing
- Make multiple searches for the same muscle group
"""

# ============================================================================
# AGENT DEFINITION
# ============================================================================

UnifiedAgent = Agent(
    name="MYONCoach",
    model=os.getenv("CANVAS_AGENT_MODEL", "gemini-2.5-flash"),
    instruction=UNIFIED_INSTRUCTION,
    tools=all_tools,
    before_tool_callback=_before_tool_callback,
    before_model_callback=_before_model_callback,
)

root_agent = UnifiedAgent

__all__ = ["root_agent", "UnifiedAgent"]
