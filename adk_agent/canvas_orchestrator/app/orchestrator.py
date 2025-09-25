import os
import copy
import logging
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from google.adk.agents import Agent, SequentialAgent, BaseAgent
from google.adk.tools import FunctionTool


logger = logging.getLogger("canvas_orchestrator")
logger.setLevel(logging.INFO)


_context_state: Dict[str, Optional[str]] = {"canvas_id": None, "user_id": None}


def _set_context(canvas_id: Optional[str], user_id: Optional[str]) -> None:
    global _context_state
    _context_state = {"canvas_id": canvas_id or None, "user_id": user_id or None}


def _context() -> Dict[str, Optional[str]]:
    return dict(_context_state)


def _update_context(canvas_id: Optional[str] = None, user_id: Optional[str] = None) -> None:
    current = _context()
    resolved_canvas = canvas_id if canvas_id is not None else current.get("canvas_id")
    resolved_user = user_id if user_id is not None else current.get("user_id")
    _set_context(resolved_canvas, resolved_user)


def _parse_context_from_text(text: str) -> Tuple[Optional[str], Optional[str]]:
    canvas_id: Optional[str] = None
    user_id: Optional[str] = None
    if not text:
        return canvas_id, user_id

    # Prefer explicit (context: ...) blocks but fall back to looser matching.
    match = re.search(r"\(context:([^)]*)\)", text, flags=re.IGNORECASE)
    candidates: List[str] = []
    if match:
        candidates.append(match.group(1))
    else:
        # Handle JSON-ish context= {...} by capturing the braces contents.
        jsonish = re.search(r"context\s*[=:]\s*\{([^}]*)\}", text, flags=re.IGNORECASE | re.DOTALL)
        if jsonish:
            candidates.append(jsonish.group(1))

    if not candidates:
        candidates.append(text)

    for payload in candidates:
        # Accept separators: space, semicolon, comma, newline.
        tokens = re.split(r"[;,\s]+", payload)
        for token in tokens:
            if "=" not in token and ":" not in token:
                continue
            sep = "=" if "=" in token else ":"
            key, value = token.split(sep, 1)
            key = key.strip().lower().strip('"')
            value = value.strip().strip('"')
            if key in {"canvas_id", "canvasid"} and value:
                canvas_id = value
            elif key in {"user_id", "uid", "userid"} and value:
                user_id = value

    return canvas_id, user_id


def _make_stage_group_id(user_id: str, canvas_id: str) -> str:
    base = f"{user_id}_{canvas_id}".lower()
    safe = re.sub(r"[^a-z0-9_-]+", "-", base).strip("-")
    if not safe:
        safe = "default"
    # Clamp to avoid oversized group keys
    if len(safe) > 48:
        safe = safe[:48]
    return f"stage1_{safe}"


def _coerce_str(value: Any) -> Optional[str]:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _iter_entity_candidates(entities: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    yield entities
    for key in ("context", "canvas", "user"):
        maybe = entities.get(key)
        if isinstance(maybe, dict):
            yield maybe
        elif isinstance(maybe, list):
            for item in maybe:
                if isinstance(item, dict):
                    yield item


def _update_context_from_entities(entities: Optional[Dict[str, Any]]) -> None:
    if not isinstance(entities, dict):
        return

    canvas_val: Optional[str] = None
    user_val: Optional[str] = None

    for candidate in _iter_entity_candidates(entities):
        if canvas_val is None:
            for key in ("canvas_id", "canvasId", "canvasID"):
                canvas_val = _coerce_str(candidate.get(key)) or canvas_val
                if canvas_val:
                    break
            if canvas_val is None and isinstance(candidate.get("canvas"), dict):
                inner = candidate["canvas"]
                for key in ("id", "canvas_id", "canvasId"):
                    canvas_val = _coerce_str(inner.get(key)) or canvas_val
                    if canvas_val:
                        break
        if user_val is None:
            for key in ("user_id", "uid", "userId"):
                user_val = _coerce_str(candidate.get(key)) or user_val
                if user_val:
                    break
            if user_val is None and isinstance(candidate.get("user"), dict):
                inner_user = candidate["user"]
                for key in ("id", "uid", "user_id", "userId"):
                    user_val = _coerce_str(inner_user.get(key)) or user_val
                    if user_val:
                        break

        if canvas_val and user_val:
            break

    if canvas_val or user_val:
        _update_context(canvas_id=canvas_val, user_id=user_val)


# --- Clients ---
try:
    from app.libs.tools_canvas.client import CanvasFunctionsClient  # type: ignore
except Exception:
    # Local dev fallback import path
    from libs.tools_canvas.client import CanvasFunctionsClient  # type: ignore


def _canvas_client() -> "CanvasFunctionsClient":  # type: ignore
    base_url = os.getenv("MYON_FUNCTIONS_BASE_URL", "https://us-central1-myon-53d85.cloudfunctions.net")
    api_key = os.getenv("FIREBASE_API_KEY")
    bearer = os.getenv("FIREBASE_ID_TOKEN")
    user_id = os.getenv("PIPELINE_USER_ID") or os.getenv("X_USER_ID") or "canvas_orchestrator_engine"
    return CanvasFunctionsClient(base_url=base_url, api_key=api_key, bearer_token=bearer, user_id=user_id)


# --- Tools ---
def tool_propose_cards(
    canvas_id: str,
    cards: List[Dict[str, Any]],
    *,
    user_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> Dict[str, Any]:
    client = _canvas_client()
    # Light shaping: leave defaults to server; ensure minimal required fields
    shaped: List[Dict[str, Any]] = []
    for c in cards or []:
        if not isinstance(c, dict):
            continue
        item = {k: v for k, v in c.items() if v is not None}
        shaped.append(item)
    return client.propose_cards(canvas_id, shaped, user_id=user_id, correlation_id=correlation_id)


def tool_build_clarify_card(question_texts: List[str], group_id: Optional[str] = None) -> Dict[str, Any]:
    # Minimal clarify-questions card compatible with iOS draft schema
    qs = []
    for idx, q in enumerate(question_texts):
        qs.append({"id": f"q_{idx}", "label": str(q), "type": "text"})
    card = {
        "type": "clarify-questions",
        "lane": "analysis",
        "content": {
            "title": "A few questions",
            "questions": qs,
        },
        "meta": {"groupId": group_id} if group_id else {},
        "priority": 50,
        "ttl": {"minutes": 10},
    }
    return card


def tool_build_stage1_workout_cards(plan: Dict[str, Any], first_target: Dict[str, Any], group_id: Optional[str] = None) -> List[Dict[str, Any]]:
    # Emits session_plan + first set_target
    cards: List[Dict[str, Any]] = []
    meta = {"groupId": group_id} if group_id else None
    cards.append({
        "type": "session_plan",
        "lane": "workout",
        "content": plan,
        "meta": meta,
        "priority": 90,
    })
    refs: Dict[str, Any] = {}
    exercise_id = first_target.get("exercise_id") if isinstance(first_target, dict) else None
    set_index = first_target.get("set_index") if isinstance(first_target, dict) else None
    if exercise_id is not None and set_index is not None:
        refs = {"exercise_id": exercise_id, "set_index": set_index}
    content: Dict[str, Any] = {}
    target: Optional[Dict[str, Any]] = None
    if isinstance(first_target, dict):
        maybe_target = first_target.get("target")
        if isinstance(maybe_target, dict):
            target = maybe_target
    if target is None and exercise_id is not None:
        try:
            blocks = plan.get("blocks") if isinstance(plan, dict) else []
            for block in blocks or []:
                if not isinstance(block, dict):
                    continue
                if block.get("exercise_id") != exercise_id:
                    continue
                sets = block.get("sets")
                if isinstance(sets, list) and set_index is not None and 0 <= int(set_index) < len(sets):
                    candidate = sets[int(set_index)]
                    if isinstance(candidate, dict) and isinstance(candidate.get("target"), dict):
                        target = candidate.get("target")
                        break
        except Exception:
            pass
    if not isinstance(target, dict):
        raise ValueError("first_target requires a target payload")
    content = {"target": target}
    cards.append({
        "type": "set_target",
        "lane": "workout",
        "content": content,
        "refs": refs or None,
        "meta": meta,
        "priority": 95,
    })
    return cards


# --- Agents ---
def _router_instruction() -> str:
    return (
        "You are the General Router. Read the latest user instruction and decide the route: 'workout'|'analysis'|'progress'. "
        "If intent is ambiguous, produce a short list of clarify questions. Output JSON: {route, entities, confidence, clarify_questions?}."
        " When context like (context: canvas_id=... user_id=...) is present, surface it in entities and ensure downstream tools receive it."
    )


def tool_route_intent(instruction_text: str) -> Dict[str, Any]:
    # Very small heuristic + LLM room later (kept tool-shaped for ADK FunctionTool)
    raw = instruction_text or ""
    canvas_id, user_id = _parse_context_from_text(raw)
    _set_context(canvas_id, user_id)
    t = raw.strip().lower()
    route = "unknown"
    if any(w in t for w in ["train", "workout", "plan"]):
        route = "workout"
    elif any(w in t for w in ["analy", "visual", "chart", "show"]):
        route = "analysis"
    elif any(w in t for w in ["progress", "trend", "weekly", "monthly"]):
        route = "progress"
    confidence = 0.8 if route != "unknown" else 0.3
    entities: Dict[str, Any] = {}
    if canvas_id:
        entities["canvas_id"] = canvas_id
        entities.setdefault("canvasId", canvas_id)
    if user_id:
        entities["user_id"] = user_id
        entities.setdefault("uid", user_id)
    return {"route": route, "entities": entities, "confidence": confidence}


def tool_canvas_publish(
    cards: List[Dict[str, Any]],
    canvas_id: Optional[str] = None,
    user_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> Dict[str, Any]:
    if canvas_id is not None or user_id is not None:
        _update_context(canvas_id, user_id)
    ctx = _context()
    cid = canvas_id or ctx.get("canvas_id") or os.getenv("TEST_CANVAS_ID") or ""
    uid = user_id or ctx.get("user_id") or os.getenv("X_USER_ID") or os.getenv("PIPELINE_USER_ID")
    if not cid:
        raise ValueError("canvas_id is required (or set TEST_CANVAS_ID env var)")
    if not uid:
        raise ValueError("user_id is required (include in context or pass explicitly)")
    return tool_propose_cards(cid, cards, user_id=uid, correlation_id=correlation_id)


def tool_stage1_plan(entities: Dict[str, Any]) -> Dict[str, Any]:
    # Minimal plan skeleton and first target with safe bounds (reps 6–12, RIR 0–2)
    _update_context_from_entities(entities)
    default_sets = [
        {"target": {"reps": 8, "rir": 1}},
        {"target": {"reps": 8, "rir": 1}},
        {"target": {"reps": 8, "rir": 1}},
    ]
    bench_sets = copy.deepcopy(default_sets)
    pulldown_sets = copy.deepcopy(default_sets)
    plan = {
        "title": "Session Plan",
        "blocks": [
            {
                "exercise_id": "ex_barbell_bench_press",
                "name": "Barbell Bench Press",
                "sets": bench_sets,
            },
            {
                "exercise_id": "ex_lat_pulldown",
                "name": "Lat Pulldown",
                "sets": pulldown_sets,
            },
        ],
    }
    first_target = {
        "exercise_id": plan["blocks"][0]["exercise_id"],
        "set_index": 0,
        "target": plan["blocks"][0]["sets"][0]["target"],
    }
    return {"plan": plan, "first_target": first_target}


class RouterAdapter(BaseAgent):
    async def _run_async_impl(self, ctx):
        # Placeholder adapter (no-op)
        if False:
            yield None


router_tools = [
    FunctionTool(func=tool_route_intent),
    FunctionTool(func=tool_build_clarify_card),
    FunctionTool(func=tool_canvas_publish),
]

workout_tools = [
    FunctionTool(func=tool_stage1_plan),
    FunctionTool(func=tool_build_stage1_workout_cards),
    FunctionTool(func=tool_canvas_publish),
]


RouterAgent = Agent(
    name="RouterAgent",
    model=os.getenv("CANVAS_ROUTER_MODEL", "gemini-2.5-flash"),
    instruction=_router_instruction() + " Always reply with a one-line status summarizing your action (e.g., 'route=workout action=transfer|clarify').",
    tools=router_tools,
)

WorkoutOrchestrator = Agent(
    name="WorkoutOrchestrator",
    model=os.getenv("CANVAS_WORKOUT_MODEL", "gemini-2.5-flash"),
    instruction=(
        "You orchestrate Stage-1 workout planning. Call tool_stage1_plan to get a minimal plan and first target,"
        " then build cards via tool_build_stage1_workout_cards and publish with tool_canvas_publish."
        " Always pass canvas_id and user_id (from context/entities) when calling publishing tools."
        " After publishing, reply with a short line like 'published stage1 cards=2'."
    ),
    tools=workout_tools,
)


def _root_instruction() -> str:
    return (
        "You are the Canvas Root Agent. Step 1: use RouterAgent (transfer) to decide route. "
        "If 'workout', transfer to WorkoutOrchestrator. Ensure canvas_id and user_id from context/entities are preserved. After sub-agent completes, emit a one-line summary (e.g., 'done route=workout status=published')."
    )


root_agent = Agent(
    name="CanvasRoot",
    model=os.getenv("CANVAS_ROOT_MODEL", "gemini-2.5-pro"),
    instruction=_root_instruction(),
    sub_agents=[RouterAgent, WorkoutOrchestrator],
)

# --- MVP fast-path wrapper to make Router able to complete Stage-1 end-to-end ---
def tool_workout_stage1_publish(
    entities: Optional[Dict[str, Any]] = None,
    canvas_id: Optional[str] = None,
    user_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> Dict[str, Any]:
    _update_context_from_entities(entities or {})
    if canvas_id is not None or user_id is not None:
        _update_context(canvas_id, user_id)
    ctx = _context()
    cid = canvas_id or ctx.get("canvas_id") or os.getenv("TEST_CANVAS_ID")
    uid = user_id or ctx.get("user_id") or os.getenv("X_USER_ID") or os.getenv("PIPELINE_USER_ID")
    if not cid:
        raise ValueError("canvas_id is required for stage1 publish")
    if not uid:
        raise ValueError("user_id is required for stage1 publish")
    data = tool_stage1_plan(entities or {})
    plan = data.get("plan") or {}
    first_target = data.get("first_target") or {}
    group_id = _make_stage_group_id(uid, cid)
    cards = tool_build_stage1_workout_cards(plan, first_target, group_id)
    res = tool_canvas_publish(cards, canvas_id=cid, user_id=uid, correlation_id=correlation_id)
    try:
        count = len(cards)
    except Exception:
        count = 2
    return {"ok": True, "published_cards": count, "group_id": group_id, "response": res}

# Expose wrapper on Router so it can complete the MVP path without agent transfer race
router_tools.append(FunctionTool(func=tool_workout_stage1_publish))



