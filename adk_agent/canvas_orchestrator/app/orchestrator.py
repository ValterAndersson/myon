import os
import json
import logging
from typing import Any, Dict, List, Optional

from google.adk.agents import Agent, SequentialAgent, BaseAgent
from google.adk.tools import FunctionTool


logger = logging.getLogger("canvas_orchestrator")
logger.setLevel(logging.INFO)


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
# --- Context helpers ---
def tool_set_user_context(user_id: str) -> Dict[str, Any]:
    """Set per-request user context for downstream HTTP tools.

    The HTTP client reads `X_USER_ID` env var when constructing headers.
    """
    os.environ["X_USER_ID"] = user_id
    # no return payload needed
    return {"ok": True, "user_id": user_id}



# --- Tools ---
def tool_propose_cards(canvas_id: str, cards: List[Dict[str, Any]], correlation_id: Optional[str] = None, user_id: Optional[str] = None) -> Dict[str, Any]:
    """Publish one or more cards to the user's canvas.

    Args:
        canvas_id: Target canvas id (users/{uid}/canvases/{canvas_id}).
        cards: Array of card inputs. Server will fill defaults and validate via Ajv.
        correlation_id: Optional correlation id for tracing.
        user_id: Optional explicit user id to route to correct user scope.
    Returns: Server response JSON.
    """
    client = _canvas_client()
    # Light shaping: leave defaults to server; ensure minimal required fields
    shaped: List[Dict[str, Any]] = []
    for c in cards or []:
        if not isinstance(c, dict):
            continue
        item = {k: v for k, v in c.items() if v is not None}
        shaped.append(item)
    logger.info(f"tool_propose_cards: canvas_id={canvas_id} user_id={user_id} count={len(shaped)}")
    return client.propose_cards(canvas_id, shaped, correlation_id=correlation_id, user_id_override=user_id)


def tool_build_clarify_card(question_texts: List[str], group_id: Optional[str] = None) -> Dict[str, Any]:
    """Build a clarify-questions proposal with simple text questions."""
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
    """Build Ajv-compliant Stage-1 bundle: session_plan + first set_target."""
    # Emits session_plan + first set_target
    cards: List[Dict[str, Any]] = []
    # Ensure Ajv-compliant session_plan: blocks[*].exercise_id + sets[] with target
    sp_blocks: List[Dict[str, Any]] = []
    for b in plan.get("blocks", []):
        ex_id = b.get("exercise_id") or b.get("id") or b.get("exerciseId")
        # Minimal one-set target if none present
        sets = b.get("sets")
        if not isinstance(sets, list):
            sets = [{"target": {"reps": 8, "rir": 1}}]
        sp_blocks.append({
            "exercise_id": ex_id or "ex_barbell_bench_press",
            "sets": sets,
        })
    sp_content = {"blocks": sp_blocks} if sp_blocks else {
        "blocks": [
            {"exercise_id": "ex_barbell_bench_press", "sets": [{"target": {"reps": 8, "rir": 1}}]},
            {"exercise_id": "ex_lat_pulldown", "sets": [{"target": {"reps": 10, "rir": 2}}]},
        ]
    }
    cards.append({
        "type": "session_plan",
        "lane": "workout",
        "content": sp_content,
        "meta": {"groupId": group_id} if group_id else {},
        "priority": 90,
    })
    # set_target must include content.target and refs.exercise_id/set_index
    st_ex = first_target.get("exercise_id") or "ex_barbell_bench_press"
    st_idx = int(first_target.get("set_index", 0))
    st_target = first_target.get("target") or {"reps": 8, "rir": 1}
    cards.append({
        "type": "set_target",
        "lane": "workout",
        "content": {"target": st_target},
        "refs": {"exercise_id": st_ex, "set_index": st_idx},
        "meta": {"groupId": group_id} if group_id else {},
        "priority": 95,
    })
    return cards


# --- Agents ---
def _router_instruction() -> str:
    return (
        "You are the General Router. Read the latest user instruction and decide the route: 'workout'|'analysis'|'progress'. "
        "If intent is ambiguous, produce a short list of clarify questions. Output JSON: {route, entities, confidence, clarify_questions?}."
    )


def tool_route_intent(instruction_text: str) -> Dict[str, Any]:
    # Very small heuristic + LLM room later (kept tool-shaped for ADK FunctionTool)
    t = (instruction_text or "").strip().lower()
    route = "unknown"
    if any(w in t for w in ["train", "workout", "plan"]):
        route = "workout"
    elif any(w in t for w in ["analy", "visual", "chart", "show"]):
        route = "analysis"
    elif any(w in t for w in ["progress", "trend", "weekly", "monthly"]):
        route = "progress"
    confidence = 0.8 if route != "unknown" else 0.3
    entities: Dict[str, Any] = {}
    return {"route": route, "entities": entities, "confidence": confidence}


def tool_canvas_publish(cards: List[Dict[str, Any]], canvas_id: Optional[str] = None, correlation_id: Optional[str] = None, user_id: Optional[str] = None) -> Dict[str, Any]:
    cid = canvas_id or os.getenv("TEST_CANVAS_ID") or ""
    if not cid:
        raise ValueError("canvas_id is required (or set TEST_CANVAS_ID env var)")
    return tool_propose_cards(cid, cards, correlation_id=correlation_id, user_id=user_id)


def tool_stage1_plan(entities: Dict[str, Any]) -> Dict[str, Any]:
    """Synthesize a minimal workout plan and the first target to prime the UI."""
    # Minimal plan skeleton and first target with safe bounds (reps 6–12, RIR 0–2)
    plan = {
        "blocks": [
            {"exercise_id": "ex_barbell_bench_press", "sets": [{"target": {"reps": 8, "rir": 1}}]},
            {"exercise_id": "ex_lat_pulldown", "sets": [{"target": {"reps": 10, "rir": 2}}]},
        ],
    }
    first_target = {
        "exercise_id": "ex_barbell_bench_press",
        "set_index": 0,
        "target": {"reps": 8, "rir": 1},
    }
    return {"plan": plan, "first_target": first_target}


class RouterAdapter(BaseAgent):
    async def _run_async_impl(self, ctx):
        # Placeholder adapter (no-op)
        if False:
            yield None


router_tools = [
    FunctionTool(func=tool_set_user_context),
    FunctionTool(func=tool_route_intent),
    FunctionTool(func=tool_build_clarify_card),
    FunctionTool(func=tool_canvas_publish),
]

workout_tools = [
    FunctionTool(func=tool_stage1_plan),
    FunctionTool(func=tool_build_stage1_workout_cards),
    FunctionTool(func=tool_canvas_publish),
]


# --- MVP fast-path wrapper to make Router able to complete Stage-1 end-to-end ---
def tool_workout_stage1_publish(entities: Optional[Dict[str, Any]] = None, canvas_id: Optional[str] = None, user_id: Optional[str] = None) -> Dict[str, Any]:
    data = tool_stage1_plan(entities or {})
    plan = data.get("plan") or {}
    first_target = data.get("first_target") or {}
    group_id = f"stage1_{os.getenv('PIPELINE_USER_ID', 'canvas_orchestrator_engine')}"
    cards = tool_build_stage1_workout_cards(plan, first_target, group_id)
    logger.info(f"tool_workout_stage1_publish: canvas_id={canvas_id} user_id={user_id} cards={len(cards)}")
    res = tool_canvas_publish(cards, canvas_id=canvas_id, correlation_id=None, user_id=user_id)
    try:
        count = len(cards)
    except Exception:
        count = 2
    return {"ok": True, "published_cards": count, "group_id": group_id, "response": res}

# Expose wrapper on Router so it can complete the MVP path without agent transfer race
router_tools.append(FunctionTool(func=tool_workout_stage1_publish))


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
        " After publishing, reply with a short line like 'published stage1 cards=2'."
    ),
    tools=workout_tools,
)


def _root_instruction() -> str:
    return (
        "You are the Canvas Root Agent. Step 1: use RouterAgent (transfer) to decide route. "
        "If 'workout', transfer to WorkoutOrchestrator. After sub-agent completes, emit a one-line summary (e.g., 'done route=workout status=published')."
    )


root_agent = Agent(
    name="CanvasRoot",
    model=os.getenv("CANVAS_ROOT_MODEL", "gemini-2.5-pro"),
    instruction=_root_instruction() + " Always start by calling tool_set_user_context(user_id=?). If the user intent is about training or is ambiguous, you MUST call tool_workout_stage1_publish(canvas_id=?, user_id=?). Prefer concise outputs.",
    sub_agents=[RouterAgent, WorkoutOrchestrator],
    tools=[
        FunctionTool(func=tool_set_user_context),
        FunctionTool(func=tool_workout_stage1_publish),
        FunctionTool(func=tool_canvas_publish),
        FunctionTool(func=tool_build_stage1_workout_cards),
        FunctionTool(func=tool_stage1_plan),
        FunctionTool(func=tool_build_clarify_card),
    ],
)



