"""Agent Engine multi-agent definitions for the canvas router, specialists, and card agent."""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional, Set

from google.adk import Agent
from google.adk.tools import FunctionTool

from app.libs.tools_canvas.client import CanvasFunctionsClient

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_context: Dict[str, Optional[str]] = {"canvas_id": None, "user_id": None, "correlation_id": None}
_client: Optional[CanvasFunctionsClient] = None
_auto_publish_guard: Set[str] = set()


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


def tool_set_canvas_context(
    *,
    canvas_id: Optional[str] = None,
    user_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> Dict[str, Optional[str]]:
    """Persist the current canvas/user routing context for downstream tools."""
    if canvas_id and canvas_id.strip():
        _context["canvas_id"] = canvas_id.strip()
    if user_id and user_id.strip():
        _context["user_id"] = user_id.strip()
    if correlation_id and correlation_id.strip():
        _context["correlation_id"] = correlation_id.strip()
    logger.info(
        "set_canvas_context canvas=%s user=%s correlation=%s",
        _context.get("canvas_id"),
        _context.get("user_id"),
        _context.get("correlation_id"),
    )
    return dict(_context)


def tool_fetch_profile(*, user_id: Optional[str] = None) -> Dict[str, Any]:
    """Return the profile for the active user."""
    uid = _resolve(user_id, "user_id")
    if not uid:
        raise ValueError("tool_fetch_profile requires user_id or prior context")
    logger.info("fetch_profile uid=%s", uid)
    resp = _canvas_client().get_user(uid)
    return resp.get("data") or resp.get("context") or {}


def tool_fetch_recent_sessions(*, user_id: Optional[str] = None, limit: int = 5) -> List[Dict[str, Any]]:
    """Return recent sessions/workouts for grounding."""
    uid = _resolve(user_id, "user_id")
    if not uid:
        raise ValueError("tool_fetch_recent_sessions requires user_id or prior context")
    logger.info("fetch_recent_sessions uid=%s limit=%s", uid, limit)
    resp = _canvas_client().get_user_workouts(uid, limit=limit)
    return resp.get("data") or resp.get("workouts") or []


def tool_emit_agent_event(
    *,
    event_type: str,
    payload: Optional[Dict[str, Any]] = None,
    canvas_id: Optional[str] = None,
    user_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Emit a structured debug event that the client can subscribe to."""
    uid = _resolve(user_id, "user_id")
    cid = _resolve(canvas_id, "canvas_id")
    corr = _resolve(correlation_id, "correlation_id")
    if not uid or not cid:
        raise ValueError("emit_agent_event requires canvas_id and user_id")
    logger.info("emit_event type=%s canvas=%s corr=%s", event_type, cid, corr)
    _canvas_client().emit_event(
        user_id=uid,
        canvas_id=cid,
        event_type=event_type,
        payload=payload or {},
        correlation_id=corr,
    )
    _maybe_auto_publish_cards(
        event_type=event_type,
        payload=payload or {},
        canvas_id=cid,
        user_id=uid,
        correlation_id=corr,
    )
    return {"ok": True}


def tool_publish_cards(
    *,
    cards: List[Dict[str, Any]],
    canvas_id: Optional[str] = None,
    user_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Publish fully-formed cards via proposeCards."""
    if not isinstance(cards, list) or not cards:
        raise ValueError("tool_publish_cards requires a non-empty cards list")
    uid = _resolve(user_id, "user_id")
    cid = _resolve(canvas_id, "canvas_id")
    corr = _resolve(correlation_id, "correlation_id")
    if not uid or not cid:
        raise ValueError("publish_cards requires canvas_id and user_id")
    logger.info(
        "publish_cards canvas=%s corr=%s count=%s types=%s",
        cid,
        corr,
        len(cards),
        [card.get("type") for card in cards],
    )
    resp = _canvas_client().propose_cards(
        canvas_id=cid,
        cards=cards,
        user_id=uid,
        correlation_id=corr,
    )
    return resp.get("data") or {"ok": True}

def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default

def _coerce_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default

def _extract_reps(value: Any, default: int = 8) -> int:
    if isinstance(value, (int, float)):
        return max(int(value), 1)
    if isinstance(value, str):
        matches = re.findall(r"\d+", value)
        if matches:
            return int(matches[-1])
    return default


def _build_sets_from_count(block: Dict[str, Any], count: int) -> List[Dict[str, Any]]:
    reps_hint = _extract_reps(block.get("reps") or block.get("rep_range") or block.get("rep_target"))
    rir_hint = _coerce_int(block.get("rir"), 2)
    weight_hint = block.get("weight") or block.get("weight_kg")
    sets: List[Dict[str, Any]] = []
    for _ in range(max(count, 1)):
        target: Dict[str, Any] = {"reps": reps_hint, "rir": rir_hint}
        if isinstance(weight_hint, (int, float)):
            target["weight"] = float(weight_hint)
        sets.append({"target": target})
    return sets


def _normalize_sets(block: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw_sets = (
        block.get("sets")
        or block.get("targets")
        or block.get("set_targets")
        or block.get("prescribed_sets")
    )
    if isinstance(raw_sets, int):
        return _build_sets_from_count(block, raw_sets)
    if isinstance(raw_sets, dict):
        items = raw_sets.get("items")
        if isinstance(items, list):
            raw_sets = items
        else:
            return _build_sets_from_count(block, _coerce_int(raw_sets.get("count"), 3))
    if not raw_sets:
        return []
    sets: List[Dict[str, Any]] = []
    for raw_set in raw_sets:
        if isinstance(raw_set, dict):
            target = raw_set.get("target") or raw_set
            if not isinstance(target, dict):
                target = {}
            reps = _extract_reps(target.get("reps"), _extract_reps(block.get("reps")))
            rir = _coerce_int(target.get("rir"), _coerce_int(block.get("rir"), 2))
            entry: Dict[str, Any] = {"target": {"reps": reps, "rir": rir}}
            weight = target.get("weight") or target.get("weight_kg")
            if isinstance(weight, (int, float)):
                entry["target"]["weight"] = float(weight)
            sets.append(entry)
        elif isinstance(raw_set, (int, float)):
            sets.append({"target": {"reps": int(raw_set), "rir": 2}})
    return sets


def tool_format_workout_plan_cards(
    *,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    """Deterministically convert a workout planning payload into session_plan + narration cards."""
    logger.info("format_workout_plan payload keys: %s", list(payload.keys()))
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    session = (
        payload.get("session")
        or payload.get("plan")
        or payload.get("workout")
        or payload.get("session_plan")
        or data.get("session")
        or data.get("session_plan")
        or {}
    )
    if not isinstance(session, dict):
        session = {}
    blocks_in = (
        session.get("blocks")
        or session.get("exercises")
        or payload.get("blocks")
        or payload.get("exercises")
        or data.get("blocks")
        or data.get("exercises")
        or []
    )
    if not isinstance(blocks_in, list):
        blocks_in = [blocks_in] if blocks_in else []
    blocks: List[Dict[str, Any]] = []
    for block in blocks_in:
        if not isinstance(block, dict):
            continue
        exercise_id = block.get("exercise_id") or block.get("id") or ""
        if not exercise_id:
            exercise = block.get("exercise") or {}
            if isinstance(exercise, dict):
                exercise_id = exercise.get("id", "") or exercise.get("exercise_id", "")
        name = block.get("name") or block.get("title") or block.get("display_name")
        if not name and isinstance(block.get("exercise"), dict):
            name = block["exercise"].get("name")
        name = name or "Exercise"
        sets = _normalize_sets(block)
        if not sets:
            sets = _build_sets_from_count(block, 3)
        blocks.append(
            {
                "exercise_id": exercise_id or f"exercise_{len(blocks)+1}",
                "name": name,
                "sets": sets,
                "notes": (
                    block.get("notes")
                    or block.get("instruction")
                    or block.get("rationale")
                    or block.get("rest")
                ),
            }
        )

    if not blocks:
        logger.warning("format_workout_plan produced no blocks for payload")
        blocks.append({"exercise_id": "exercise_1", "name": "Exercise", "sets": [{"target": {"reps": 8, "rir": 2}}]})

    cards: List[Dict[str, Any]] = []
    duration_minutes = (
        session.get("duration_minutes")
        or payload.get("duration_minutes")
        or data.get("duration_minutes")
    )
    cards.append(
        {
            "type": "session_plan",
            "lane": "workout",
            "priority": 90,
            "content": {
                "title": session.get("title") or session.get("name") or payload.get("title") or data.get("title") or "Proposed Workout",
                "blocks": blocks,
                "estimated_duration_minutes": _coerce_int(duration_minutes, 45),
            },
        }
    )

    narration = (
        payload.get("narration")
        or data.get("narration")
        or session.get("summary")
        or session.get("description")
        or payload.get("summary")
    )
    if narration:
        cards.append(
            {
                "type": "inline-info",
                "lane": "analysis",
                "priority": 40,
                "content": {
                    "title": "Coach Notes",
                    "body": narration,
                },
            }
        )
    return {"cards": cards}

def tool_format_analysis_cards(
    *,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    """Convert analysis results into inline-info/list cards."""
    cards: List[Dict[str, Any]] = []
    insights = payload.get("insights") or []
    if insights:
        body = "\n".join(f"• {ins.get('title')}: {ins.get('detail')}" for ins in insights if isinstance(ins, dict))
        cards.append(
            {
                "type": "inline-info",
                "lane": "analysis",
                "priority": 50,
                "content": {
                    "title": payload.get("title") or "Key Findings",
                    "body": body or "See recommendations below.",
                },
            }
        )
    recommendations = payload.get("recommendations") or []
    if recommendations:
        items = []
        for rec in recommendations:
            if not isinstance(rec, dict):
                continue
            items.append(
                {
                    "title": rec.get("title") or "Recommendation",
                    "subtitle": rec.get("action") or rec.get("detail") or "",
                }
            )
        if items:
            cards.append(
                {
                    "type": "list",
                    "lane": "analysis",
                    "priority": 45,
                    "content": {
                        "title": "Recommendations",
                        "items": items,
                    },
                }
            )
    if not cards:
        cards.append(
            {
                "type": "inline-info",
                "lane": "analysis",
                "priority": 40,
                "content": {
                    "title": "Analysis",
                    "body": payload.get("summary") or "No significant findings.",
                },
            }
        )
    return {"cards": cards}

def tool_request_clarification(
    *,
    question: str,
    canvas_id: Optional[str] = None,
    user_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Publish a clarify-questions card for additional user input."""
    card = {
        "type": "clarify-questions",
        "lane": "analysis",
        "priority": 95,
        "content": {
            "title": "Quick clarification",
            "questions": [
                {
                    "id": "clarify_1",
                    "text": question,
                    "type": "text",
                    "options": None,
                }
            ],
        },
        "actions": [
            {"kind": "submit", "label": "Send", "style": "primary"},
            {"kind": "skip", "label": "Skip", "style": "secondary"},
        ],
    }
    return tool_publish_cards(
        cards=[card],
        canvas_id=canvas_id,
        user_id=user_id,
        correlation_id=correlation_id,
    )


router_tools = [
    FunctionTool(func=tool_set_canvas_context),
    FunctionTool(func=tool_fetch_profile),
    FunctionTool(func=tool_fetch_recent_sessions),
    FunctionTool(func=tool_emit_agent_event),
    FunctionTool(func=tool_request_clarification),
]

analysis_tools = [
    FunctionTool(func=tool_fetch_profile),
    FunctionTool(func=tool_fetch_recent_sessions),
    FunctionTool(func=tool_emit_agent_event),
]

planner_tools = [
    FunctionTool(func=tool_fetch_profile),
    FunctionTool(func=tool_fetch_recent_sessions),
    FunctionTool(func=tool_emit_agent_event),
]

runner_tools = [
    FunctionTool(func=tool_fetch_profile),
    FunctionTool(func=tool_fetch_recent_sessions),
    FunctionTool(func=tool_emit_agent_event),
]

card_tools = [
    FunctionTool(func=tool_set_canvas_context),
    FunctionTool(func=tool_format_workout_plan_cards),
    FunctionTool(func=tool_format_analysis_cards),
    FunctionTool(func=tool_publish_cards),
    FunctionTool(func=tool_emit_agent_event),
]


def _maybe_auto_publish_cards(
    *,
    event_type: str,
    payload: Dict[str, Any],
    canvas_id: Optional[str],
    user_id: Optional[str],
    correlation_id: Optional[str],
) -> None:
    """Deterministic fallback so critical tasks still render even if CardAgent stalls."""
    if not isinstance(payload, dict):
        logger.info("auto_publish skipped: payload is %s", type(payload).__name__)
        return
    task = payload.get("task") if isinstance(payload, dict) else None
    if event_type != "plan_workout" and task != "plan_workout":
        return
    if payload.get("_skip_auto_publish"):
        logger.info("auto_publish skip requested explicitly")
        return
    if not canvas_id or not user_id:
        logger.warning("auto_publish skipped (no canvas/user)")
        return
    key = f"{event_type}:{correlation_id or 'none'}"
    if key in _auto_publish_guard:
        logger.info("auto_publish already completed for %s", key)
        return
    plan_sources = [
        payload.get("session"),
        payload.get("plan"),
        payload.get("workout"),
        payload.get("session_plan"),
        payload.get("data"),
    ]
    if not any(isinstance(src, (dict, list)) for src in plan_sources):
        logger.info("auto_publish skipped: no plan data in payload keys=%s", list(payload.keys()))
        return

    logger.info("auto_publish start event=%s corr=%s", event_type, correlation_id)
    try:
        formatted = tool_format_workout_plan_cards(payload=payload or {})
        cards = formatted.get("cards") if isinstance(formatted, dict) else None
        if not cards:
            raise ValueError("formatter returned no cards")
        tool_publish_cards(
            cards=cards,
            canvas_id=canvas_id,
            user_id=user_id,
            correlation_id=correlation_id,
        )
        _auto_publish_guard.add(key)
        _canvas_client().emit_event(
            user_id=user_id,
            canvas_id=canvas_id,
            event_type="card.auto.plan_workout",
            payload={"status": "published", "cards": len(cards)},
            correlation_id=correlation_id,
        )
        logger.info("auto_publish success key=%s cards=%s", key, len(cards))
    except Exception as exc:
        extra = ""
        status = None
        try:
            import requests  # type: ignore

            if isinstance(exc, requests.HTTPError) and exc.response is not None:
                status = exc.response.status_code
                try:
                    extra = exc.response.text or ""
                except Exception:
                    extra = ""
        except Exception:
            extra = extra or ""
        logger.exception("auto_publish failed status=%s body=%s", status, extra, exc_info=exc)
        _canvas_client().emit_event(
            user_id=user_id,
            canvas_id=canvas_id,
            event_type="card.auto.plan_workout.error",
            payload={"error": str(exc), "status": status, "body": extra},
            correlation_id=correlation_id,
        )


ANALYSIS_INSTRUCTION = """
You are the Analysis Agent. Interpret the user's instruction, reference their profile + recent sessions,
derive 1-3 key insights, and package them into a structured payload.

Workflow:
1. Call tool_fetch_profile / tool_fetch_recent_sessions to gather context.
2. Reason about trends, issues, or opportunities. Keep explanations concise, actionable, and science-backed.
3. When you're ready to present, TRANSFER to CardAgentAnalysis and include JSON payload:
   {
     "task": "analysis",
     "insights": [...],
     "visuals": [...],
     "recommendations": [...]
   }
4. Emit events via tool_emit_agent_event as needed.
Never publish cards yourself; CardAgent handles formatting.
"""

PLANNER_INSTRUCTION = """
You are the Workout Planner Agent. Design a single workout proposal tailored to the user's constraints.

Workflow:
1. Fetch the profile and recent sessions.
2. Define 3-6 exercises with set/rep targets, rest guidance, and rationale.
3. Prepare JSON:
   {
     "task": "plan_workout",
     "session": { "title": "...", "blocks": [ ... ] },
     "narration": "short summary"
   }
4. Before transferring, call tool_emit_agent_event(type="plan_workout", payload=<the same JSON>) so telemetry + fallbacks stay in sync.
5. TRANSFER to CardAgentPlanner with that JSON so it can produce UI cards.
Do not call tool_publish_cards directly.
"""

RUNNER_INSTRUCTION = """
You are the Workout Runner Agent. Help when a workout is in progress (adjust loads, suggest swaps, summarize progress).
Use recent sessions to stay consistent.
Output JSON:
{
  "task": "run_workout",
  "adjustments": [...],
  "next_actions": [...],
  "notes": "..."
}
Transfer to CardAgentRunner with this payload.
"""

CARD_INSTRUCTION = """
You are the Card Agent. You only receive structured payloads from other agents.
Steps:
1. Read payload.task and payload data.
2. For workout plans, call tool_format_workout_plan_cards(payload=payload) to build a valid session_plan card.
3. For analysis tasks, call tool_format_analysis_cards(payload=payload) to build inline-info/list cards.
4. Only after formatting is complete, call tool_publish_cards with the returned cards list. Emit a summary event via tool_emit_agent_event.
5. If payload.task is unknown, emit an inline-info card describing the issue.
"""

CARD_MODEL = os.getenv("CANVAS_CARD_MODEL", "gemini-2.5-pro")


def _make_card_agent(suffix: str) -> Agent:
    return Agent(
        name=f"CardAgent{suffix}",
        model=CARD_MODEL,
        instruction=CARD_INSTRUCTION,
        tools=card_tools,
        disallow_transfer_to_parent=True,
    )


CardAgentAnalysis = _make_card_agent("Analysis")
CardAgentPlanner = _make_card_agent("Planner")
CardAgentRunner = _make_card_agent("Runner")
CardAgentGeneral = _make_card_agent("General")

ROUTER_INSTRUCTION = """
You are the Router Agent for the Canvas orchestrator.

Process:
1. Every user message begins with a prefix like `(context: canvas_id=XYZ user_id=ABC corr=...)`. Parse those literal values and IMMEDIATELY call tool_set_canvas_context(user_id=<parsed user_id>, canvas_id=<parsed canvas_id>, correlation_id=<parsed corr>). Never skip this step.
2. After context is set, call tool_fetch_profile / tool_fetch_recent_sessions as needed to understand the user.
3. Decide whether the request is an analysis, workout planning, workout running, or general conversation.
4. Emit tool_emit_agent_event(type="route.<task>", payload={ "summary": "..." }).
5. Transfer to the appropriate specialist agent (AnalysisAgent, WorkoutPlannerAgent, WorkoutRunnerAgent, GeneralistAgent).
6. Specialists must transfer to their dedicated CardAgent child to produce UI cards.
If you cannot determine the user or canvas from the context prefix, call tool_request_clarification.
"""

AnalysisAgent = Agent(
    name="AnalysisAgent",
    model=os.getenv("CANVAS_ANALYSIS_MODEL", "gemini-2.5-pro"),
    instruction=ANALYSIS_INSTRUCTION,
    tools=analysis_tools,
    sub_agents=[CardAgentAnalysis],
)

WorkoutPlannerAgent = Agent(
    name="WorkoutPlannerAgent",
    model=os.getenv("CANVAS_PLANNER_MODEL", "gemini-2.5-pro"),
    instruction=PLANNER_INSTRUCTION,
    tools=planner_tools,
    sub_agents=[CardAgentPlanner],
)

WorkoutRunnerAgent = Agent(
    name="WorkoutRunnerAgent",
    model=os.getenv("CANVAS_RUNNER_MODEL", "gemini-2.5-flash"),
    instruction=RUNNER_INSTRUCTION,
    tools=runner_tools,
    sub_agents=[CardAgentRunner],
)

GeneralistAgent = Agent(
    name="GeneralistAgent",
    model=os.getenv("CANVAS_GENERALIST_MODEL", "gemini-2.5-flash"),
    instruction="""
You are the general fallback agent. Provide reassuring narration, ask clarifying questions,
or hand back control when the user intent is outside analysis/workouts. Use tool_request_clarification if needed.
Always transfer to CardAgentGeneral if you produce content for the canvas.
""",
    tools=[FunctionTool(func=tool_emit_agent_event), FunctionTool(func=tool_request_clarification)],
    sub_agents=[CardAgentGeneral],
)

RouterAgent = Agent(
    name="RouterAgent",
    model=os.getenv("CANVAS_ROUTER_MODEL", "gemini-2.5-flash"),
    instruction=ROUTER_INSTRUCTION,
    tools=router_tools,
    sub_agents=[AnalysisAgent, WorkoutPlannerAgent, WorkoutRunnerAgent, GeneralistAgent],
)

# Root agent exported to the Agent Engine app.
root_agent = RouterAgent

__all__ = [
    "root_agent",
    "RouterAgent",
    "AnalysisAgent",
    "WorkoutPlannerAgent",
    "WorkoutRunnerAgent",
    "CardAgentAnalysis",
    "CardAgentPlanner",
    "CardAgentRunner",
    "CardAgentGeneral",
    "GeneralistAgent",
]

