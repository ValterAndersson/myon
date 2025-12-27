"""
Orchestrator Agent - Intent classification and routing.

Design principles:
- Rules first, LLM fallback only when necessary
- Structured routing decisions for observability
- No artifact writes - routing only
- Maintains session mode state (computed per-turn, not persisted)
- Safety re-route: If target agent lacks tools for request, fallback to Planner/Coach
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional

from google.adk import Agent
from google.adk.tools import FunctionTool

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


# ============================================================================
# Intent Taxonomy
# ============================================================================

class Intent(str, Enum):
    """Canonical intent labels for routing."""
    COACH_GENERAL = "COACH_GENERAL"
    ANALYZE_PROGRESS = "ANALYZE_PROGRESS"
    PLAN_WORKOUT = "PLAN_WORKOUT"
    PLAN_ROUTINE = "PLAN_ROUTINE"
    EDIT_PLAN = "EDIT_PLAN"
    EXECUTE_WORKOUT = "EXECUTE_WORKOUT"
    NEXT_WORKOUT = "NEXT_WORKOUT"


class TargetAgent(str, Enum):
    """Target agent identifiers."""
    COACH = "coach"
    ANALYSIS = "analysis"
    PLANNER = "planner"
    COPILOT = "copilot"


class Confidence(str, Enum):
    """Routing confidence levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# ============================================================================
# Routing Decision
# ============================================================================

@dataclass
class RoutingDecision:
    """Structured routing decision for observability."""
    intent: str
    target_agent: str
    confidence: str
    mode_transition: Optional[str] = None
    matched_rule: Optional[str] = None
    signals: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def to_context_string(self) -> str:
        """Format for injection into agent context."""
        parts = [
            f"intent={self.intent}",
            f"target={self.target_agent}",
            f"confidence={self.confidence}",
        ]
        if self.matched_rule:
            parts.append(f"rule={self.matched_rule}")
        if self.signals:
            parts.append(f"signals=[{','.join(self.signals)}]")
        return f"(routing: {' '.join(parts)})"


# ============================================================================
# Rule-Based Intent Classification
# ============================================================================

# Compile patterns once for performance
RULE_PATTERNS: List[tuple] = [
    # Copilot: Execution mode signals (highest priority)
    (re.compile(r"\b(start|begin|let.?s\s+go|i.?m\s+(at\s+the\s+)?gym|training\s+now|ready\s+to\s+train)\b", re.I),
     Intent.EXECUTE_WORKOUT, TargetAgent.COPILOT, Confidence.HIGH, "pattern:gym_now"),
    (re.compile(r"\b(next\s+set|current\s+set|swap.*(exercise|movement)|adjust.*(weight|load)|rest\s+timer|how\s+much\s+rest)\b", re.I),
     Intent.EXECUTE_WORKOUT, TargetAgent.COPILOT, Confidence.HIGH, "pattern:in_workout_action"),
    (re.compile(r"\b(log|record|done|finished|completed)\s+(this\s+)?(set|exercise)\b", re.I),
     Intent.EXECUTE_WORKOUT, TargetAgent.COPILOT, Confidence.HIGH, "pattern:log_set"),
    
    # Copilot: Next workout request
    (re.compile(r"\b(what.?s?\s+)?(next|today.?s?)\s+(workout|session|training)\b", re.I),
     Intent.NEXT_WORKOUT, TargetAgent.COPILOT, Confidence.HIGH, "pattern:next_workout"),
    (re.compile(r"\b(give\s+me|show\s+me|start)\s+(my\s+)?(next|today.?s?)\s+(workout|session)\b", re.I),
     Intent.NEXT_WORKOUT, TargetAgent.COPILOT, Confidence.HIGH, "pattern:start_next"),
    
    # Planner: Routine/program creation (multi-day)
    (re.compile(r"\b(create|build|make|design|set\s+up)\s+(a\s+)?(new\s+)?(workout\s+)?(routine|program|split|ppl|push.?pull.?legs|upper.?lower)\b", re.I),
     Intent.PLAN_ROUTINE, TargetAgent.PLANNER, Confidence.HIGH, "pattern:create_routine"),
    (re.compile(r"\b(i\s+(want|need)|give\s+me)\s+(a\s+)?(new\s+)?(workout\s+)?(routine|program|split)\b", re.I),
     Intent.PLAN_ROUTINE, TargetAgent.PLANNER, Confidence.HIGH, "pattern:want_routine"),
    (re.compile(r"\b(weekly|multi.?day|\d+\s*day)\s+(workout\s+)?(plan|routine|split)\b", re.I),
     Intent.PLAN_ROUTINE, TargetAgent.PLANNER, Confidence.HIGH, "pattern:multiday_plan"),
    
    # Planner: Single workout creation
    (re.compile(r"\b(create|build|make|design|plan)\s+(a\s+)?(new\s+)?(single\s+)?(workout|session|training)\b", re.I),
     Intent.PLAN_WORKOUT, TargetAgent.PLANNER, Confidence.HIGH, "pattern:create_workout"),
    (re.compile(r"\b(i\s+(want|need)|give\s+me)\s+(a\s+)?(new\s+)?(single\s+)?(workout|session)\b", re.I),
     Intent.PLAN_WORKOUT, TargetAgent.PLANNER, Confidence.HIGH, "pattern:want_workout"),
    (re.compile(r"\b(chest|back|leg|shoulder|arm|push|pull)\s+(day|workout|session)\b", re.I),
     Intent.PLAN_WORKOUT, TargetAgent.PLANNER, Confidence.MEDIUM, "pattern:bodypart_day"),
    
    # Planner: Edit existing plan
    (re.compile(r"\b(edit|modify|change|update|adjust|tweak)\s+(the\s+)?(workout|routine|plan|exercises?)\b", re.I),
     Intent.EDIT_PLAN, TargetAgent.PLANNER, Confidence.HIGH, "pattern:edit_plan"),
    (re.compile(r"\b(add|remove|swap|replace)\s+(an?\s+)?(exercise|movement|set)\b", re.I),
     Intent.EDIT_PLAN, TargetAgent.PLANNER, Confidence.HIGH, "pattern:modify_exercise"),
    (re.compile(r"\b(more|less|fewer)\s+(sets?|reps?|volume|exercises?)\b", re.I),
     Intent.EDIT_PLAN, TargetAgent.PLANNER, Confidence.MEDIUM, "pattern:volume_adjust"),
    
    # Analysis: Progress and data review
    (re.compile(r"\b(analyze|review|assess|evaluate)\s+(my\s+)?(progress|history|data|performance|workouts?)\b", re.I),
     Intent.ANALYZE_PROGRESS, TargetAgent.ANALYSIS, Confidence.HIGH, "pattern:analyze_progress"),
    (re.compile(r"\b(how\s+(am\s+i|have\s+i\s+been)|what.?s\s+my)\s+(doing|progress|performance|trend)\b", re.I),
     Intent.ANALYZE_PROGRESS, TargetAgent.ANALYSIS, Confidence.HIGH, "pattern:check_progress"),
    (re.compile(r"\b(what\s+should\s+i\s+(improve|focus|work\s+on)|weak\s*point|lagging|imbalance)\b", re.I),
     Intent.ANALYZE_PROGRESS, TargetAgent.ANALYSIS, Confidence.MEDIUM, "pattern:find_weakness"),
    (re.compile(r"\b(volume|frequency|intensity)\s+(analysis|breakdown|distribution)\b", re.I),
     Intent.ANALYZE_PROGRESS, TargetAgent.ANALYSIS, Confidence.HIGH, "pattern:volume_analysis"),
    # Muscle/volume/training questions
    (re.compile(r"\b(which|what)\s+(muscles?|muscle\s+groups?)\b.*(most|least|volume|train|hit|work)", re.I),
     Intent.ANALYZE_PROGRESS, TargetAgent.ANALYSIS, Confidence.HIGH, "pattern:muscle_volume_query"),
    (re.compile(r"\b(how\s+much|how\s+many)\s+(volume|sets?|reps?|workouts?)\b", re.I),
     Intent.ANALYZE_PROGRESS, TargetAgent.ANALYSIS, Confidence.HIGH, "pattern:volume_query"),
    (re.compile(r"\b(am\s+i\s+training|have\s+i\s+trained|been\s+training)\b", re.I),
     Intent.ANALYZE_PROGRESS, TargetAgent.ANALYSIS, Confidence.MEDIUM, "pattern:training_query"),
    (re.compile(r"\b(lately|recently|last\s+\d+\s+weeks?|past\s+\d+\s+weeks?)\b.*\b(volume|sets?|train)", re.I),
     Intent.ANALYZE_PROGRESS, TargetAgent.ANALYSIS, Confidence.HIGH, "pattern:recent_volume"),
    (re.compile(r"\b(consistent|consistency|adherence|how\s+often)\b", re.I),
     Intent.ANALYZE_PROGRESS, TargetAgent.ANALYSIS, Confidence.MEDIUM, "pattern:consistency"),
    # Strength and 1RM progress (data-focused, not advice-seeking)
    (re.compile(r"\b(1\s*r[mp]|one\s*rep\s*max|e1rm|max\s+weight)\b", re.I),
     Intent.ANALYZE_PROGRESS, TargetAgent.ANALYSIS, Confidence.HIGH, "pattern:1rm_query"),
    (re.compile(r"\b(how\s+has|how.?s)\s+(my\s+)?(chest|back|shoulder|leg|arm|bicep|tricep|quad|hamstring|bench|squat|deadlift).*(develop|improv|progress|chang|grow)\b", re.I),
     Intent.ANALYZE_PROGRESS, TargetAgent.ANALYSIS, Confidence.HIGH, "pattern:specific_development"),
    (re.compile(r"\b(chest|back|shoulder|leg|arm|bicep|tricep|quad|hamstring)\s+(1rm|e1rm|progress|develop)\b", re.I),
     Intent.ANALYZE_PROGRESS, TargetAgent.ANALYSIS, Confidence.HIGH, "pattern:muscle_progress"),
    
    # Coach: Education and explanation (lower priority, catch-all for questions)
    (re.compile(r"\b(why\s+(should|do|is)|how\s+does?|what\s+is|explain|tell\s+me\s+about|help\s+me\s+understand)\b", re.I),
     Intent.COACH_GENERAL, TargetAgent.COACH, Confidence.MEDIUM, "pattern:education_question"),
    (re.compile(r"\b(principle|science|research|evidence|optimal|best\s+practice)\b", re.I),
     Intent.COACH_GENERAL, TargetAgent.COACH, Confidence.MEDIUM, "pattern:science_question"),
    (re.compile(r"\b(hypertrophy|strength|endurance|technique|form|injury|pain)\s+(tips?|advice|question)\b", re.I),
     Intent.COACH_GENERAL, TargetAgent.COACH, Confidence.MEDIUM, "pattern:training_advice"),
]

# Negative patterns to exclude (e.g., "split squat" should not trigger routine)
NEGATIVE_PATTERNS = [
    re.compile(r"\b(split\s+squat|bulgarian\s+split|split\s+stance)\b", re.I),
]


def _extract_signals(message: str) -> List[str]:
    """Extract signal flags from message for observability."""
    signals = []
    lower = message.lower()
    
    # Verb signals
    if re.search(r"\b(create|build|make|design)\b", lower):
        signals.append("has_create_verb")
    if re.search(r"\b(edit|modify|change|update)\b", lower):
        signals.append("has_edit_verb")
    if re.search(r"\b(analyze|review|assess)\b", lower):
        signals.append("has_analysis_verb")
    if re.search(r"\b(start|begin|go|ready)\b", lower):
        signals.append("has_action_verb")
    
    # Subject signals
    if re.search(r"\b(workout|session|training)\b", lower):
        signals.append("mentions_workout")
    if re.search(r"\b(routine|program|split|ppl)\b", lower):
        signals.append("mentions_routine")
    if re.search(r"\b(progress|history|data|performance)\b", lower):
        signals.append("mentions_data")
    if re.search(r"\b(gym|training\s+now|ready\s+to)\b", lower):
        signals.append("execution_context")
    
    # Question patterns
    if re.search(r"\b(why|how|what\s+is|explain)\b", lower):
        signals.append("is_question")
    
    return signals


def classify_intent_rules(message: str) -> Optional[RoutingDecision]:
    """
    Classify intent using deterministic rules.
    Returns None if no rule matches (fallback to LLM needed).
    """
    # Check negative patterns first
    for neg_pattern in NEGATIVE_PATTERNS:
        if neg_pattern.search(message):
            # Don't let this influence routine detection
            pass  # For now just continue, could log
    
    signals = _extract_signals(message)
    
    # Try each pattern in priority order
    for pattern, intent, target, confidence, rule_name in RULE_PATTERNS:
        # Skip if negative pattern would give false positive
        is_negated = False
        for neg_pattern in NEGATIVE_PATTERNS:
            if neg_pattern.search(message):
                # Check if this pattern is affected
                if "routine" in rule_name or "split" in rule_name:
                    is_negated = True
                    break
        
        if is_negated:
            continue
            
        if pattern.search(message):
            return RoutingDecision(
                intent=intent.value,
                target_agent=target.value,
                confidence=confidence.value,
                matched_rule=rule_name,
                signals=signals,
            )
    
    return None


def classify_intent_llm(message: str, signals: List[str]) -> RoutingDecision:
    """
    Classify intent using LLM when rules don't match.
    Uses Gemini with a minimal prompt for fast classification.
    """
    logger.info("LLM fallback triggered for message: %s", message[:100])
    
    try:
        import google.generativeai as genai
        
        # Use flash model for fast classification
        model = genai.GenerativeModel(os.getenv("CANVAS_ORCHESTRATOR_MODEL", "gemini-2.5-flash"))
        
        prompt = f"""Classify this fitness app user message into ONE category:

COACH - User wants advice, explanations, education about training principles, "how do I get stronger", technique tips
ANALYSIS - User wants to see their data, progress review, historical trends, volume stats, "how am I doing"  
PLANNER - User wants to create or modify a workout plan or routine
COPILOT - User is at the gym, ready to train, asking about their next set or exercise

Message: "{message}"

Respond with ONLY the category name (COACH, ANALYSIS, PLANNER, or COPILOT):"""

        response = model.generate_content(prompt)
        result = response.text.strip().upper()
        
        # Map to target agent
        target_map = {
            "COACH": (Intent.COACH_GENERAL, TargetAgent.COACH),
            "ANALYSIS": (Intent.ANALYZE_PROGRESS, TargetAgent.ANALYSIS),
            "PLANNER": (Intent.PLAN_WORKOUT, TargetAgent.PLANNER),
            "COPILOT": (Intent.EXECUTE_WORKOUT, TargetAgent.COPILOT),
        }
        
        if result in target_map:
            intent, target = target_map[result]
            logger.info("LLM classified as: %s -> %s", result, target.value)
            return RoutingDecision(
                intent=intent.value,
                target_agent=target.value,
                confidence=Confidence.MEDIUM.value,
                matched_rule=f"fallback:llm_{result.lower()}",
                signals=signals,
            )
        
        # If LLM gives unexpected response, fall back to Coach
        logger.warning("LLM returned unexpected: %s, defaulting to COACH", result)
        
    except Exception as e:
        logger.error("LLM fallback failed: %s, defaulting to COACH", str(e))
    
    # Default to Coach if LLM fails or returns unexpected
    return RoutingDecision(
        intent=Intent.COACH_GENERAL.value,
        target_agent=TargetAgent.COACH.value,
        confidence=Confidence.LOW.value,
        matched_rule="fallback:llm_error",
        signals=signals,
    )


def _apply_safety_reroute(decision: RoutingDecision, signals: List[str]) -> RoutingDecision:
    """
    Safety re-route: If the target agent lacks tools for the request, fallback.
    
    Rules:
    - If user asks for artifact creation but lands on Coach: re-route to Planner
      (Coach is education-only, cannot create drafts)
    - Analysis and Copilot agents are fully functional - no reroute needed
    """
    # Check if request implies artifact creation but target is Coach
    if decision.target_agent == TargetAgent.COACH.value:
        if "has_create_verb" in signals and ("mentions_workout" in signals or "mentions_routine" in signals):
            logger.info("Safety re-route: Coach cannot create artifacts, redirecting to Planner")
            return RoutingDecision(
                intent=Intent.PLAN_WORKOUT.value,
                target_agent=TargetAgent.PLANNER.value,
                confidence=Confidence.MEDIUM.value,
                matched_rule="safety_reroute:coach_to_planner",
                signals=signals + ["safety_rerouted"],
            )
    
    # Analysis agent is fully implemented - no reroute needed
    # It fetches data and provides text responses
    
    # Copilot agent handles execution - no special reroute needed
    
    return decision


def classify_intent(message: str) -> RoutingDecision:
    """
    Main entry point for intent classification.
    Tries rules first, falls back to LLM, then applies safety re-routes.
    """
    # Try rule-based classification first
    decision = classify_intent_rules(message)
    if decision:
        logger.info("Rule-based routing: %s -> %s (rule=%s)", 
                   decision.intent, decision.target_agent, decision.matched_rule)
        # Apply safety re-route
        decision = _apply_safety_reroute(decision, decision.signals)
        return decision
    
    # Fall back to LLM classification
    signals = _extract_signals(message)
    decision = classify_intent_llm(message, signals)
    logger.info("LLM-based routing: %s -> %s", decision.intent, decision.target_agent)
    # Apply safety re-route
    decision = _apply_safety_reroute(decision, decision.signals)
    return decision


# ============================================================================
# Context Management
# ============================================================================

_context: Dict[str, Any] = {
    "canvas_id": None,
    "user_id": None,
    "correlation_id": None,
    "current_mode": "coach",  # coach | analyze | plan | execute
}
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
        logger.info("Parsed context: canvas=%s user=%s corr=%s",
                   _context.get("canvas_id"), _context.get("user_id"), _context.get("correlation_id"))


def _strip_context_prefix(message: str) -> str:
    """Remove context prefix from message for cleaner routing."""
    return re.sub(r'\(context:\s*canvas_id=\S+\s+user_id=\S+\s+corr=\S+\)\s*', '', message).strip()


# ============================================================================
# Agent Imports (lazy to avoid circular imports)
# ============================================================================

_planner_agent = None
_coach_agent = None
_analysis_agent = None
_copilot_agent = None


def _get_planner_agent():
    global _planner_agent
    if _planner_agent is None:
        from app.agents.planner_agent import PlannerAgent
        _planner_agent = PlannerAgent
    return _planner_agent


def _get_coach_agent():
    global _coach_agent
    if _coach_agent is None:
        from app.agents.coach_agent import CoachAgent
        _coach_agent = CoachAgent
    return _coach_agent


def _get_analysis_agent():
    global _analysis_agent
    if _analysis_agent is None:
        from app.agents.analysis_agent import AnalysisAgent
        _analysis_agent = AnalysisAgent
    return _analysis_agent


def _get_copilot_agent():
    global _copilot_agent
    if _copilot_agent is None:
        from app.agents.copilot_agent import CopilotAgent
        _copilot_agent = CopilotAgent
    return _copilot_agent


# ============================================================================
# Orchestrator Tools
# ============================================================================

def tool_route_to_agent(*, message: str) -> Dict[str, Any]:
    """
    Classify intent and route to appropriate agent.
    Returns the routing decision for observability.
    """
    # Parse context if present
    _auto_parse_context(message)
    
    # Strip context for cleaner classification
    clean_message = _strip_context_prefix(message)
    
    # Classify intent
    decision = classify_intent(clean_message)
    
    # Update session mode based on routing
    mode_map = {
        TargetAgent.COACH.value: "coach",
        TargetAgent.ANALYSIS.value: "analyze",
        TargetAgent.PLANNER.value: "plan",
        TargetAgent.COPILOT.value: "execute",
    }
    old_mode = _context.get("current_mode", "coach")
    new_mode = mode_map.get(decision.target_agent, "coach")
    
    if old_mode != new_mode:
        decision.mode_transition = f"{old_mode}→{new_mode}"
        _context["current_mode"] = new_mode
    
    logger.info("Routing decision: %s", decision.to_dict())
    
    return {
        "routing_decision": decision.to_dict(),
        "context": {
            "canvas_id": _context.get("canvas_id"),
            "user_id": _context.get("user_id"),
            "correlation_id": _context.get("correlation_id"),
            "current_mode": _context.get("current_mode"),
        }
    }


# ============================================================================
# Orchestrator Agent Definition
# ============================================================================

ORCHESTRATOR_INSTRUCTION = """
You are the Orchestrator Agent. Your sole job is to classify user intent and route to the correct specialist agent.

PROCESS:
1. For every message, parse the context prefix (canvas_id, user_id, correlation_id)
2. Classify the user's intent using the routing rules
3. Transfer to the appropriate specialist agent with the routing context

ROUTING:
- Coach: Education, explanations, training principles (no artifact writes)
- Analysis: Progress review, data analysis, trend identification (read-heavy)
- Planner: Create/edit workouts and routines (draft artifacts)
- Copilot: Live workout execution, in-session adjustments (active workout writes)

You must ALWAYS route to one of the four specialist agents. Never respond directly.
Include the routing decision in your transfer for observability.
"""

# Orchestrator uses sub_agents for ADK transfer mechanism
OrchestratorAgent = Agent(
    name="Orchestrator",
    model=os.getenv("CANVAS_ORCHESTRATOR_MODEL", "gemini-2.5-flash"),
    instruction=ORCHESTRATOR_INSTRUCTION,
    tools=[FunctionTool(func=tool_route_to_agent)],
    sub_agents=[],  # Will be populated after agent definitions
)


def _build_orchestrator_with_agents() -> Agent:
    """Build orchestrator with all sub-agents attached."""
    return Agent(
        name="Orchestrator",
        model=os.getenv("CANVAS_ORCHESTRATOR_MODEL", "gemini-2.5-flash"),
        instruction=ORCHESTRATOR_INSTRUCTION,
        tools=[FunctionTool(func=tool_route_to_agent)],
        sub_agents=[
            _get_coach_agent(),
            _get_analysis_agent(),
            _get_planner_agent(),
            _get_copilot_agent(),
        ],
    )


# Lazy initialization for root_agent
_root_agent = None


def get_root_agent() -> Agent:
    """Get the fully initialized orchestrator agent."""
    global _root_agent
    if _root_agent is None:
        _root_agent = _build_orchestrator_with_agents()
    return _root_agent


# For module-level export compatibility
root_agent = property(lambda self: get_root_agent())


class _RootAgentProxy:
    """Proxy class to lazily initialize root_agent on first access."""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = get_root_agent()
        return cls._instance


# This will be the exported root_agent
root_agent = None  # Placeholder, actual initialization in __init__.py or agent.py


def initialize_root_agent() -> Agent:
    """Initialize and return the root orchestrator agent."""
    global root_agent
    root_agent = _build_orchestrator_with_agents()
    return root_agent


__all__ = [
    "OrchestratorAgent",
    "RoutingDecision",
    "Intent",
    "TargetAgent",
    "Confidence",
    "classify_intent",
    "initialize_root_agent",
    "root_agent",
]
