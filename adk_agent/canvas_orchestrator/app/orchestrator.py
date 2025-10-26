import os
import copy
import logging
import re
import json
import hashlib
from typing import Any, Dict, Iterable, List, Optional, Tuple

from google.adk.agents import Agent, SequentialAgent, BaseAgent
from google.adk.tools import FunctionTool


logger = logging.getLogger("canvas_orchestrator")
logger.setLevel(logging.INFO)


_context_state: Dict[str, Optional[str]] = {"canvas_id": None, "user_id": None}
# In-process idempotency stores (per-stream/session scope)
_published_canvases: set[str] = set()
_canvas_card_fingerprints: Dict[str, set[str]] = {}


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
    # Prefer dedicated agent API key; avoid using Firebase web key in production
    api_key = os.getenv("MYON_API_KEY") or None
    if not api_key:
        alt = os.getenv("FIREBASE_API_KEY")
        if alt:
            logger.warning("Using FIREBASE_API_KEY for proposeCards; set MYON_API_KEY for production")
            api_key = alt
    bearer = os.getenv("FIREBASE_ID_TOKEN")
    # IMPORTANT: prefer per-request user context header over pipeline id
    user_id = os.getenv("X_USER_ID") or os.getenv("PIPELINE_USER_ID") or None
    return CanvasFunctionsClient(base_url=base_url, api_key=api_key, bearer_token=bearer, user_id=user_id)
# --- Context helpers ---

def tool_set_user_context(
    user_id: Optional[str] = None,
    uid: Optional[str] = None,
    userId: Optional[str] = None,
    usera_id: Optional[str] = None,
    canvas_id: Optional[str] = None,
    canvasa_id: Optional[str] = None,
    canvasId: Optional[str] = None,
) -> Dict[str, Any]:
    """Set per-request user and canvas context for downstream HTTP tools.

    Accepts multiple parameter names to be robust to model typos.
    """
    chosen_user = user_id or uid or userId or usera_id
    chosen_canvas = canvas_id or canvasa_id or canvasId
    
    if not isinstance(chosen_user, str) or not chosen_user.strip():
        return {"ok": False, "error": "missing_user_id"}
    
    user_val = chosen_user.strip()
    prev = os.getenv("X_USER_ID")
    os.environ["X_USER_ID"] = user_val
    
    # Also update in-process context for agent-side defaults
    try:
        _update_context(user_id=user_val, canvas_id=chosen_canvas)
    except Exception:
        pass
    return {"ok": True, "user_id": user_val, "canvas_id": chosen_canvas, "already_set": prev == user_val}



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
    try:
        logger.info(
            "tool_propose_cards: begin", extra={
                "canvas_id": canvas_id, "user_id": user_id, "count": len(shaped), "correlation_id": correlation_id,
            }
        )
    except Exception:
        pass
    try:
        result = client.propose_cards(canvas_id, shaped, user_id=user_id, correlation_id=correlation_id)
        try:
            logger.info("tool_propose_cards: ok", extra={"created": result.get("created_card_ids"), "canvas_id": canvas_id, "correlation_id": correlation_id})
        except Exception:
            pass
        return {"ok": True, **result}
    except Exception as e:
        try:
            status = getattr(getattr(e, "response", None), "status_code", None)
            logger.error("tool_propose_cards: failed", extra={"error": str(e), "status": status, "canvas_id": canvas_id, "correlation_id": correlation_id})
        except Exception:
            pass
        return {"ok": False, "error": str(e), "status": getattr(getattr(e, "response", None), "status_code", None)}


def tool_check_user_response(
    canvas_id: Optional[str] = None,
    canvasa_id: Optional[str] = None,
    user_id: Optional[str] = None,
    usera_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Check for pending user responses to clarify questions."""
    cid = canvas_id or canvasa_id
    uid = user_id or usera_id
    
    ctx = _context()
    cid = cid or ctx.get("canvas_id")
    uid = uid or ctx.get("user_id") or os.getenv("X_USER_ID")
    
    # In production, this would query Firestore pending_responses
    # For now, return mock response
    return {
        "ok": True,
        "has_response": False,
        "response": None
    }

def tool_get_user_preferences(
    user_id: Optional[str] = None,
    usera_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Get user preferences and profile data from Firestore."""
    uid = user_id or usera_id
    ctx = _context()
    uid = uid or ctx.get("user_id") or os.getenv("X_USER_ID") or os.getenv("PIPELINE_USER_ID")
    
    if not uid:
        return {"ok": False, "error": "user_id required", "preferences": {}}
    
    # Mock response showing MISSING data to trigger questions
    # In production this would query Firestore
    return {
        "ok": True,
        "preferences": {
            # Empty/missing data to trigger clarifying questions
            "training_experience": None,
            "goals": None,
            "available_days": None,
            "equipment": None,
            "injuries": None
        }
    }

def tool_publish_agent_message(
    message: str,
    canvas_id: Optional[str] = None,
    canvasa_id: Optional[str] = None,  # Handle typo
    user_id: Optional[str] = None,
    usera_id: Optional[str] = None,  # Handle typo
    status: str = "working",
    tool_calls: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Publish an agent message/narration card to explain what the agent is doing."""
    # Handle typos
    cid = canvas_id or canvasa_id
    uid = user_id or usera_id
    
    ctx = _context()
    cid = cid or ctx.get("canvas_id") or os.getenv("TEST_CANVAS_ID") or ""
    uid = uid or ctx.get("user_id") or os.getenv("X_USER_ID") or os.getenv("PIPELINE_USER_ID")
    
    if not cid or not uid:
        logger.warning(f"tool_publish_agent_message: missing canvas_id={cid} or user_id={uid}")
        return {"ok": False, "error": "canvas_id and user_id required"}
    
    card = {
        "type": "agent-message",
        "lane": "system",
        "priority": 100,
        "content": {
            "text": message,
            "status": status,
            "tool_calls": tool_calls or []
        },
        "actions": [],  # No actions for agent messages
        "ttl": {"minutes": 5}
    }
    
    logger.info(f"tool_publish_agent_message: publishing to canvas_id={cid} user_id={uid}")
    return tool_canvas_publish([card], canvas_id=cid, user_id=uid)

def tool_build_clarify_card(questions: List[Dict[str, Any]], title: str = "Quick question", group_id: Optional[str] = None) -> Dict[str, Any]:
    """Build a clarify-questions card with choice or text questions.
    
    Args:
        questions: List of dicts with 'text' (question), 'type' ('choice' or 'text'), and optional 'options' (for choice)
        title: Card title
        group_id: Optional group ID
    """
    # Build questions with proper structure
    qs = []
    for idx, q in enumerate(questions):
        question_item = {
            "id": f"q_{idx}",
            "text": q.get("text", ""),  # The question text
        }
        
        # Add type and options if it's a choice question
        if q.get("type") == "choice" and q.get("options"):
            question_item["type"] = "choice"
            question_item["options"] = q["options"]
        else:
            question_item["type"] = "text"
            
        qs.append(question_item)
    
    card = {
        "type": "clarify-questions",
        "lane": "analysis",
        "content": {
            "title": title,
            "questions": qs,
        },
        "actions": [
            {
                "label": "Submit",
                "kind": "submit",
                "style": "primary",
                "iconSystemName": "paperplane"
            },
            {
                "label": "Skip",
                "kind": "dismiss",
                "style": "secondary",
                "iconSystemName": "xmark"
            }
        ],
        "meta": {"groupId": group_id} if group_id else {},
        "priority": 50,
        "ttl": {"minutes": 10},
    }
    return card


def tool_build_stage1_workout_cards(plan: Dict[str, Any], _: Dict[str, Any], group_id: Optional[str] = None) -> List[Dict[str, Any]]:
    cards: List[Dict[str, Any]] = []
    meta = {"groupId": group_id} if group_id else None
    if group_id:
        cards.append({
            "type": "proposal-group",
            "lane": "workout",
            "content": {"title": plan.get("title") or "Session Plan"},
            "meta": meta,
            "priority": 100,
            "menuItems": [
                {"kind": "accept_all", "label": "Accept all", "style": "primary", "iconSystemName": "checkmark.circle"},
                {"kind": "reject_all", "label": "Dismiss all", "style": "destructive", "iconSystemName": "xmark.circle"},
            ],
        })
    cards.append({
        "type": "session_plan",
        "lane": "workout",
        "content": plan,
        "meta": meta,
        "priority": 90,
        "actions": [
            {"kind": "apply", "label": "Apply", "style": "primary", "iconSystemName": "checkmark"},
            {"kind": "dismiss", "label": "Dismiss", "style": "destructive", "iconSystemName": "xmark"},
        ],
    })
    return cards


def tool_publish_clarify_questions(
    question_texts: Optional[List[str]] = None,
    questions: Optional[List[str]] = None,
    questiona_texts: Optional[List[str]] = None,
    question: Optional[str] = None,  # Allow single question
    *,
    canvas_id: Optional[str] = None,
    user_id: Optional[str] = None,
    # Flexible synonyms (including double typos)
    canvasId: Optional[str] = None,
    canvasa_id: Optional[str] = None,
    canvasaa_id: Optional[str] = None,  # Double typo
    uid: Optional[str] = None,
    userId: Optional[str] = None,
    usera_id: Optional[str] = None,
    useraa_id: Optional[str] = None,  # Double typo
    correlation_id: Optional[str] = None,
    correlationId: Optional[str] = None,
    correlationa_id: Optional[str] = None,
) -> Dict[str, Any]:
    # Convert old format (list of strings) to new format
    texts: List[str] = []
    
    # Handle single question first
    if question:
        texts = [str(question)]
    else:
        # Handle lists
        for lst in (question_texts, questiona_texts, questions):
            if isinstance(lst, list):
                for x in lst:
                    if isinstance(x, (str, int, float)):
                        texts.append(str(x))
    
    # Convert to ONE question with clickable options
    question_list = []
    
    # Take only the FIRST question and convert to choice format
    if texts and len(texts) > 0:
        first_q = texts[0].lower()
        
        if "goal" in first_q or "fitness goal" in first_q:
            question_list = [{
                "text": "What's your primary fitness goal?",
                "type": "choice",
                "options": ["Strength", "Hypertrophy", "Endurance", "Fat loss", "General fitness"]
            }]
        elif "fitness level" in first_q or "experience" in first_q:
            question_list = [{
                "text": "What's your current fitness level?",
                "type": "choice",
                "options": ["Beginner", "Intermediate", "Advanced"]
            }]
        elif "days" in first_q or "week" in first_q or "frequency" in first_q:
            question_list = [{
                "text": "How many days per week can you train?",
                "type": "choice",
                "options": ["2 days", "3 days", "4 days", "5 days", "6+ days"]
            }]
        elif "equipment" in first_q:
            question_list = [{
                "text": "What equipment do you have access to?",
                "type": "choice",
                "options": ["Full gym", "Dumbbells only", "Barbell & rack", "Bodyweight only", "Limited equipment"]
            }]
        else:
            # For any other question, use text input but still only ONE
            question_list = [{"text": texts[0], "type": "text"}]
    else:
        # Default single question with options
        question_list = [{
            "text": "What's your primary training goal?",
            "type": "choice",
            "options": ["Strength", "Hypertrophy", "Endurance", "Fat loss", "General fitness"]
        }]

    resolved_canvas = canvas_id or canvasId or canvasa_id or canvasaa_id
    resolved_user = user_id or userId or uid or usera_id or useraa_id
    resolved_corr = correlation_id or correlationId or correlationa_id
    
    logger.info(f"tool_publish_clarify_questions: resolved canvas={resolved_canvas} user={resolved_user} corr={resolved_corr}")

    if resolved_canvas is not None or resolved_user is not None:
        _update_context(canvas_id=resolved_canvas, user_id=resolved_user)
    ctx = _context()
    cid = (resolved_canvas or ctx.get("canvas_id") or os.getenv("TEST_CANVAS_ID") or "").strip()
    uid_val = (resolved_user or ctx.get("user_id") or os.getenv("X_USER_ID") or os.getenv("PIPELINE_USER_ID") or "").strip()
    
    logger.info(f"tool_publish_clarify_questions: final canvas_id={cid} user_id={uid_val} from context={ctx}")
    
    if not cid:
        logger.error(f"tool_publish_clarify_questions: missing canvas_id, context={ctx}")
        return {"ok": False, "error": "canvas_id is required (or set TEST_CANVAS_ID env var)"}
    if not uid_val:
        logger.error(f"tool_publish_clarify_questions: missing user_id, context={ctx}")
        return {"ok": False, "error": "user_id is required (include in context or pass explicitly)"}

    card = tool_build_clarify_card(question_list, title="Quick question")
    logger.info(f"tool_publish_clarify_questions: publishing card to canvas_id={cid} user_id={uid_val}")
    result = tool_canvas_publish([card], canvas_id=cid, user_id=uid_val, correlation_id=resolved_corr)
    logger.info(f"tool_publish_clarify_questions: result={result}")
    return result


# --- Agents ---
def _router_instruction() -> str:
    return (
        "You are the General Router. Use tool_route_intent(raw_input=<full_user_message>) with the ENTIRE last user message string (do not trim context prefixes). "
        "Decide the route: 'workout'|'analysis'|'progress'. If intent is ambiguous, produce a short list of clarify questions and immediately call tool_publish_clarify_questions(question_texts=[...], canvas_id=?, user_id=?). "
        "Output JSON: {route, entities, confidence, clarify_questions?}. When context like (context: canvas_id=... user_id=...) is present, surface it in entities and ensure downstream tools receive it. "
        "If route='workout', immediately call tool_workout_stage1_publish(canvas_id=?, user_id=?)."
    )


def tool_route_intent(instruction_text: Optional[str] = None, raw_input: Optional[str] = None) -> Dict[str, Any]:
    # Accept both legacy (instruction_text) and new (raw_input) parameter names
    raw = (raw_input if raw_input is not None else instruction_text) or ""
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
    # Telemetry: emit route_decided event (no UI noise)
    try:
        ctx = _context()
        cid = ctx.get("canvas_id") or os.getenv("TEST_CANVAS_ID") or canvas_id
        uid = ctx.get("user_id") or os.getenv("X_USER_ID") or os.getenv("PIPELINE_USER_ID") or user_id
        if cid and uid:
            # Emit route_decided as event (best-effort)
            try:
                client = _canvas_client()
                payload = {"route": route, "entities": entities}
                client._http.post("emitEvent", {"userId": uid, "canvasId": cid, "type": "route_decided", "payload": payload}, headers=None)
            except Exception:
                pass
    except Exception:
        pass
    return {"route": route, "entities": entities, "confidence": confidence}


def _card_fingerprint(card: Dict[str, Any]) -> str:
    try:
        meta = card.get("meta") if isinstance(card, dict) else None
        group_id = meta.get("groupId") if isinstance(meta, dict) else None
        relevant = {
            "type": card.get("type") if isinstance(card, dict) else None,
            "lane": card.get("lane") if isinstance(card, dict) else None,
            "content": card.get("content") if isinstance(card, dict) else None,
            "groupId": group_id,
        }
        s = json.dumps(relevant, sort_keys=True, separators=(",", ":"))
    except Exception:
        s = str(card)
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def tool_canvas_publish(
    cards: Optional[List[Dict[str, Any]]] = None,
    canvas_id: Optional[str] = None,
    user_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
    # Flexible synonyms / common typos
    canvasId: Optional[str] = None,
    canvasa_id: Optional[str] = None,
    uid: Optional[str] = None,
    userId: Optional[str] = None,
    usera_id: Optional[str] = None,
    correlationId: Optional[str] = None,
    correlationa_id: Optional[str] = None,
) -> Dict[str, Any]:
    # Resolve flexible args
    resolved_canvas = canvas_id or canvasId or canvasa_id
    resolved_user = user_id or userId or uid or usera_id
    resolved_corr = correlation_id or correlationId or correlationa_id
    
    logger.info(f"tool_canvas_publish: resolved canvas={resolved_canvas} user={resolved_user} corr={resolved_corr}")

    if resolved_canvas is not None or resolved_user is not None:
        _update_context(canvas_id=resolved_canvas, user_id=resolved_user)
    ctx = _context()
    cid = (resolved_canvas or ctx.get("canvas_id") or os.getenv("TEST_CANVAS_ID") or "").strip()
    uid_val = (resolved_user or ctx.get("user_id") or os.getenv("X_USER_ID") or os.getenv("PIPELINE_USER_ID") or "").strip()
    
    logger.info(f"tool_canvas_publish: final canvas_id={cid} user_id={uid_val} from context={ctx}")
    
    if not cid:
        logger.error(f"tool_canvas_publish: missing canvas_id, context={ctx}")
        return {"ok": False, "error": "canvas_id is required (or set TEST_CANVAS_ID env var)"}
    if not uid_val:
        logger.error(f"tool_canvas_publish: missing user_id, context={ctx}")
        return {"ok": False, "error": "user_id is required (include in context or pass explicitly)"}

    # Deduplicate identical cards within this process for this canvas
    incoming = list(cards or [])
    seen = _canvas_card_fingerprints.setdefault(cid, set())
    unique_cards: List[Dict[str, Any]] = []
    for c in incoming:
        if not isinstance(c, dict):
            continue
        fp = _card_fingerprint(c)
        if fp in seen:
            continue
        seen.add(fp)
        unique_cards.append(c)

    if not unique_cards:
        try:
            logger.info("tool_canvas_publish: skip duplicate set", extra={"canvas_id": cid, "user_id": uid_val, "correlation_id": resolved_corr})
        except Exception:
            pass
        return {"ok": True, "created_card_ids": [], "deduped": True}

    try:
        logger.info("tool_canvas_publish: begin", extra={"canvas_id": cid, "user_id": uid_val, "count": len(unique_cards), "correlation_id": resolved_corr})
    except Exception:
        pass

    res = tool_propose_cards(cid, unique_cards, user_id=uid_val, correlation_id=resolved_corr)
    try:
        logger.info("tool_canvas_publish: ok", extra={"canvas_id": cid, "user_id": uid_val, "correlation_id": resolved_corr, "ok": res.get("ok", True)})
    except Exception:
        pass
    return res


def tool_stage1_plan(entities: Dict[str, Any]) -> Dict[str, Any]:
    _update_context_from_entities(entities)
    # Leave planning to the model; provide empty skeleton
    return {"plan": {"blocks": []}, "first_target": {}}


class RouterAdapter(BaseAgent):
    async def _run_async_impl(self, ctx):
        # Placeholder adapter (no-op)
        if False:
            yield None


router_tools = [
    FunctionTool(func=tool_set_user_context),
    FunctionTool(func=tool_route_intent),
    FunctionTool(func=tool_build_clarify_card),
    FunctionTool(func=tool_publish_clarify_questions),
    FunctionTool(func=tool_canvas_publish),
]

workout_tools = [
    FunctionTool(func=tool_stage1_plan),
    FunctionTool(func=tool_build_stage1_workout_cards),
    FunctionTool(func=tool_canvas_publish),
]


# --- MVP fast-path wrapper to make Router able to complete Stage-1 end-to-end ---

def tool_workout_stage1_publish(
    entities: Optional[Dict[str, Any]] = None,
    canvas_id: Optional[str] = None,
    user_id: Optional[str] = None,
    # Flexible synonyms / common typos
    canvasId: Optional[str] = None,
    canvasa_id: Optional[str] = None,
    uid: Optional[str] = None,
    userId: Optional[str] = None,
    usera_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
    correlationId: Optional[str] = None,
    correlationa_id: Optional[str] = None,
) -> Dict[str, Any]:
    # Resolve flexible args
    resolved_canvas = canvas_id or canvasId or canvasa_id
    resolved_user = user_id or userId or uid or usera_id
    resolved_corr = correlation_id or correlationId or correlationa_id

    # Update context from provided entities first
    try:
        if entities:
            _update_context_from_entities(entities)
    except Exception:
        pass

    # Apply explicit overrides to context
    if resolved_canvas is not None or resolved_user is not None:
        _update_context(canvas_id=resolved_canvas, user_id=resolved_user)

    ctx = _context()
    cid = (resolved_canvas or ctx.get("canvas_id") or os.getenv("TEST_CANVAS_ID") or "").strip()
    uid_val = (resolved_user or ctx.get("user_id") or os.getenv("X_USER_ID") or os.getenv("PIPELINE_USER_ID") or "").strip()
    if not cid:
        raise ValueError("canvas_id is required (or set TEST_CANVAS_ID env var)")
    if not uid_val:
        raise ValueError("user_id is required (include in context or pass explicitly)")

    # Idempotency: avoid publishing stage1 multiple times per canvas in a single stream
    if cid in _published_canvases:
        try:
            logger.info("tool_workout_stage1_publish: skip duplicate", extra={"canvas_id": cid, "user_id": uid_val, "correlation_id": resolved_corr})
        except Exception:
            pass
        return {"ok": True, "published_cards": 0, "skipped": "duplicate"}
    _published_canvases.add(cid)

    data = tool_stage1_plan(entities or {})
    plan = data.get("plan") or {}
    first_target = data.get("first_target") or {}
    group_id = _make_stage_group_id(uid_val, cid)
    cards = tool_build_stage1_workout_cards(plan, first_target, group_id)
    try:
        logger.info("tool_workout_stage1_publish: begin", extra={"canvas_id": cid, "user_id": uid_val, "cards": len(cards), "correlation_id": resolved_corr})
    except Exception:
        pass
    res = tool_canvas_publish(cards, canvas_id=cid, correlation_id=resolved_corr, user_id=uid_val)
    try:
        count = len(cards)
    except Exception:
        count = 1
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
        " Always pass canvas_id and user_id (from context/entities) when calling publishing tools."
        " After publishing, reply with a short line like 'published stage1 cards=2'."
    ),
    tools=workout_tools,
)


def _root_instruction() -> str:
    return (
        "You are the Canvas Root Agent. Use RouterAgent (transfer) to decide route and orchestrate. "
        "If the user intent is training-related or ambiguous, prefer the workout path: generate a concise session plan (blocks with exercise_id/name and sets array), "
        "call tool_build_stage1_workout_cards(plan=..., first_target={}), and publish with tool_canvas_publish. Keep outputs compact."
    )


root_agent = Agent(
    name="CanvasRoot",
    model=os.getenv("CANVAS_ROOT_MODEL", "gemini-2.0-flash-exp"),  # Use Gemini 2.5 Flash (fastest)
    instruction=(
        "You orchestrate workout planning. Execute these steps IN ORDER:\n"
        "1. IMMEDIATELY call tool_publish_agent_message with 'Understanding your request...'\n"
        "2. Extract context and call tool_set_user_context(user_id=Y, canvas_id=X)\n"
        "3. Call tool_get_user_preferences()\n"
        "4. If preferences missing, call tool_publish_clarify_questions with ONE question\n"
        "5. For workouts: tool_stage1_plan → tool_build_stage1_workout_cards → tool_canvas_publish\n\n"
        "ALWAYS show progress to user via tool_publish_agent_message.\n"
        "Pass canvas_id and user_id to EVERY tool call.\n"
        "Be fast and decisive - no extra thinking."
    ),
    sub_agents=[],
    tools=[
        FunctionTool(func=tool_set_user_context),
        FunctionTool(func=tool_get_user_preferences),  # Check user data first
        FunctionTool(func=tool_publish_agent_message),  # New tool for narration
        FunctionTool(func=tool_publish_clarify_questions),
        FunctionTool(func=tool_canvas_publish),
        FunctionTool(func=tool_build_stage1_workout_cards),
        FunctionTool(func=tool_stage1_plan),
        FunctionTool(func=tool_build_clarify_card),
    ],
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=True,
)



