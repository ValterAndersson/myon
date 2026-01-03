"""
Router - Fast Lane bypass + Slow Lane handoff.

Fast Lane: Regex patterns match copilot commands → execute skills directly (no LLM)
Slow Lane: Pass to Shell Agent for CoT reasoning

Model assignment:
- Fast Lane: No LLM (direct skill execution)
- Slow Lane: gemini-2.5-pro (Shell Agent)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.shell.context import SessionContext

logger = logging.getLogger(__name__)


class Lane(str, Enum):
    """Request processing lanes."""
    FAST = "fast"    # Bypass LLM entirely - direct skill execution
    SLOW = "slow"    # Route to Shell Agent for reasoning
    ADMIN = "admin"  # System commands (future)


@dataclass
class RoutingResult:
    """Result of routing decision."""
    lane: Lane
    intent: Optional[str] = None
    confidence: str = "high"
    matched_rule: Optional[str] = None
    signals: List[str] = None
    
    def __post_init__(self):
        if self.signals is None:
            self.signals = []


# ============================================================================
# FAST LANE PATTERNS
# These bypass the LLM entirely for sub-500ms response times.
# Only include patterns that are UNAMBIGUOUS and require no reasoning.
# ============================================================================

FAST_LANE_PATTERNS: List[Tuple[re.Pattern, str, str]] = [
    # Set logging - ultra fast path
    # "log set", "done", "finished", "completed"
    (re.compile(r"^(log|done|finished|completed)(\s+set)?$", re.I), 
     "LOG_SET", "pattern:log_set"),
    
    # Shorthand set logging: "8 @ 100" or "8@100kg"
    (re.compile(r"^(\d+)\s*@\s*(\d+(?:\.\d+)?)\s*(kg|lbs?)?$", re.I), 
     "LOG_SET_SHORTHAND", "pattern:log_shorthand"),
    
    # Next set query: "next", "next set"
    (re.compile(r"^next(\s+set)?$", re.I), 
     "NEXT_SET", "pattern:next_set"),
    
    # What's next query
    (re.compile(r"^what.?s\s+next\??$", re.I), 
     "NEXT_SET", "pattern:whats_next"),
    
    # Rest acknowledgment: "rest", "resting", "ok", "ready"
    (re.compile(r"^(rest|resting|ok|ready)$", re.I), 
     "REST_ACK", "pattern:rest_ack"),
]


# ============================================================================
# SLOW LANE PATTERNS (for observability, not bypassing LLM)
# These help with logging/telemetry but still route to Shell Agent.
# ============================================================================

SLOW_LANE_PATTERNS: List[Tuple[re.Pattern, str, str]] = [
    # Explicit creation intents
    (re.compile(r"\b(create|build|make|design|plan)\s+(a\s+)?(new\s+)?(routine|program|workout|split)", re.I), 
     "PLAN_ARTIFACT", "pattern:create_artifact"),
    
    # Routine requests
    (re.compile(r"\b(i\s+(want|need)|give\s+me)\s+(a\s+)?(new\s+)?(routine|program|split)\b", re.I),
     "PLAN_ROUTINE", "pattern:want_routine"),
    
    # Edit/modify intents
    (re.compile(r"\b(edit|modify|update|change)\s+(the\s+)?(my\s+)?(routine|workout|plan)\b", re.I),
     "EDIT_PLAN", "pattern:edit_plan"),
    
    # Progress analysis
    (re.compile(r"\bhow.?s\s+my\s+(progress|chest|back|shoulder|leg|arm)", re.I), 
     "ANALYZE_PROGRESS", "pattern:hows_my"),
    
    # Am I progressing
    (re.compile(r"\b(am\s+i|have\s+i)\s+(progressing|improving|stall|plateau)", re.I), 
     "ANALYZE_PROGRESS", "pattern:am_i_progress"),
    
    # Volume adequacy
    (re.compile(r"\b(is\s+my|are\s+my)\s+(volume|sets|frequency)\s+(enough|sufficient|too)", re.I),
     "ANALYZE_PROGRESS", "pattern:volume_check"),
    
    # Start workout (goes to Shell for context)
    (re.compile(r"\bstart\s+(my\s+)?(today.?s?\s+)?(workout|session|training)\b", re.I),
     "START_WORKOUT", "pattern:start_workout"),
]


def _extract_signals(message: str) -> List[str]:
    """Extract signal flags from message for observability."""
    signals = []
    lower = message.lower()
    
    # First-person detection
    if re.search(r"\b(my|mine|i|i'm|i've|i'll|i'd)\b", lower):
        signals.append("has_first_person")
    
    # Verb signals
    if re.search(r"\b(create|build|make|design|plan)\b", lower):
        signals.append("has_create_verb")
    if re.search(r"\b(edit|modify|change|update)\b", lower):
        signals.append("has_edit_verb")
    if re.search(r"\b(analyze|review|assess)\b", lower):
        signals.append("has_analysis_verb")
    
    # Subject signals
    if re.search(r"\b(workout|session|training)\b", lower):
        signals.append("mentions_workout")
    if re.search(r"\b(routine|program|split|ppl)\b", lower):
        signals.append("mentions_routine")
    if re.search(r"\b(progress|history|data|performance)\b", lower):
        signals.append("mentions_data")
    
    # Metric words (strong signal for analysis)
    if re.search(r"\b(sets?|volume|frequency|1rm|e1rm|pr|personal\s+record)\b", lower):
        signals.append("has_metric_word")
    
    return signals


def route_message(message: str) -> RoutingResult:
    """
    Route message to appropriate lane.
    
    Fast lane: Regex match → direct skill execution (no LLM)
    Slow lane: Pass to Shell Agent for CoT reasoning
    
    Args:
        message: Raw message (may include context prefix)
        
    Returns:
        RoutingResult with lane and intent information
    """
    # Strip context prefix for pattern matching
    clean = SessionContext.strip_prefix(message).strip()
    
    # 1. Check FAST lane patterns first (bypass LLM)
    for pattern, intent, rule_name in FAST_LANE_PATTERNS:
        if pattern.match(clean):
            logger.info("FAST LANE: '%s' → %s (%s)", clean[:30], intent, rule_name)
            return RoutingResult(
                lane=Lane.FAST,
                intent=intent,
                confidence="high",
                matched_rule=rule_name,
            )
    
    # 2. Check SLOW lane patterns (for observability)
    signals = _extract_signals(clean)
    for pattern, intent, rule_name in SLOW_LANE_PATTERNS:
        if pattern.search(clean):
            logger.info("SLOW LANE (pattern): '%s' → %s (%s)", clean[:30], intent, rule_name)
            return RoutingResult(
                lane=Lane.SLOW,
                intent=intent,
                confidence="high",
                matched_rule=rule_name,
                signals=signals,
            )
    
    # 3. Default to SLOW lane (let Shell Agent figure it out)
    logger.info("SLOW LANE (default): '%s'", clean[:50])
    return RoutingResult(
        lane=Lane.SLOW,
        intent=None,
        confidence="low",
        matched_rule="default",
        signals=signals,
    )


def execute_fast_lane(
    routing: RoutingResult, 
    message: str, 
    ctx: SessionContext
) -> Dict[str, Any]:
    """
    Execute fast lane skill directly. No LLM involved.
    
    This function will be fleshed out when copilot_skills are implemented.
    For now, returns a stub response.
    
    Args:
        routing: Routing result from route_message
        message: Raw message
        ctx: Session context with user_id, canvas_id, etc.
        
    Returns:
        Dict with skill result, ready for response formatting
    """
    clean = SessionContext.strip_prefix(message).strip()
    
    # TODO: Wire up actual copilot_skills once implemented
    # For now, return stub responses
    
    if routing.intent == "LOG_SET":
        return {
            "lane": "fast",
            "intent": routing.intent,
            "result": {
                "status": "logged",
                "message": "Set logged.",
            }
        }
    
    elif routing.intent == "LOG_SET_SHORTHAND":
        # Parse "8 @ 100" format
        match = re.match(r"^(\d+)\s*@\s*(\d+(?:\.\d+)?)", clean)
        if match:
            reps = int(match.group(1))
            weight = float(match.group(2))
            return {
                "lane": "fast",
                "intent": routing.intent,
                "result": {
                    "status": "logged",
                    "message": f"Set logged: {reps} reps @ {weight}kg",
                    "reps": reps,
                    "weight": weight,
                }
            }
    
    elif routing.intent in ("NEXT_SET", "REST_ACK"):
        return {
            "lane": "fast",
            "intent": routing.intent,
            "result": {
                "status": "ready",
                "message": "Next set ready.",
            }
        }
    
    # Fallback
    return {
        "lane": "fast",
        "intent": routing.intent,
        "result": {
            "status": "unknown",
            "message": f"Fast lane handler for {routing.intent} not implemented.",
        }
    }


__all__ = [
    "Lane",
    "RoutingResult", 
    "route_message",
    "execute_fast_lane",
]
