"""
Shell Agent - Single unified agent with Coach persona.

Model: gemini-2.5-pro

This is the main agent that handles all "Slow Lane" requests. It combines
the capabilities of the former CoachAgent and PlannerAgent into a single
unified agent with consistent voice and behavior.

For "Fast Lane" requests (copilot commands), see router.py which bypasses
this agent entirely.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict

from google.adk import Agent
from google.adk.tools import FunctionTool

from app.shell.context import SessionContext
from app.shell.instruction import SHELL_INSTRUCTION
from app.shell.router import Lane, RoutingResult, execute_fast_lane, route_message

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ============================================================================
# CONTEXT MANAGEMENT
# Use a simple thread-local-like pattern for the current request context.
# This replaces the global _context dicts in the old agents.
# ============================================================================

_current_context: SessionContext = None


def _set_context(ctx: SessionContext) -> None:
    """Set the current request context. Called by callbacks."""
    global _current_context
    _current_context = ctx


def _get_context() -> SessionContext:
    """Get current request context."""
    return _current_context or SessionContext(canvas_id="", user_id="", correlation_id=None)


# ============================================================================
# TOOL IMPORTS
# Import tools from existing agents. These will be refactored to skills later.
# For now, we reuse the existing tool functions.
# ============================================================================

# Import planner tools
from app.agents.planner_agent import (
    tool_get_planning_context,
    tool_get_recent_workouts as planner_get_recent_workouts,
    tool_get_template,
    tool_get_user_profile as planner_get_user_profile,
    tool_propose_routine,
    tool_propose_workout,
    tool_search_exercises as planner_search_exercises,
)

# Import coach tools
from app.agents.coach_agent import (
    tool_get_analytics_features,
    tool_get_exercise_details,
    tool_get_recent_workouts as coach_get_recent_workouts,
    tool_get_training_context,
    tool_get_user_exercises_by_muscle,
    tool_get_user_profile as coach_get_user_profile,
    tool_search_exercises as coach_search_exercises,
)

# Unified tool list - deduplicated
# Use planner versions for artifact creation, coach versions for analysis
all_tools = [
    # Planning tools (for artifact creation)
    FunctionTool(func=tool_get_planning_context),
    FunctionTool(func=tool_propose_workout),
    FunctionTool(func=tool_propose_routine),
    FunctionTool(func=tool_get_template),
    FunctionTool(func=planner_search_exercises),  # Use planner version (lean output)
    
    # Coach tools (for analysis)
    FunctionTool(func=tool_get_analytics_features),
    FunctionTool(func=tool_get_training_context),
    FunctionTool(func=tool_get_user_exercises_by_muscle),
    FunctionTool(func=tool_get_exercise_details),
    FunctionTool(func=coach_get_recent_workouts),
    FunctionTool(func=coach_get_user_profile),
]


# ============================================================================
# AGENT CALLBACKS
# These inject context before tool/model calls.
# ============================================================================

def _before_tool_callback(tool, args, tool_context):
    """Inject context before tool execution."""
    try:
        ctx = tool_context.invocation_context
        if ctx and hasattr(ctx, "user_content"):
            msg = ""
            if ctx.user_content and ctx.user_content.parts:
                msg = str(ctx.user_content.parts[0].text)
            session_ctx = SessionContext.from_message(msg)
            _set_context(session_ctx)
            
            # Also update the old global contexts for backwards compatibility
            # TODO: Remove this once skills are fully extracted
            from app.agents import planner_agent, coach_agent
            planner_agent._context["canvas_id"] = session_ctx.canvas_id
            planner_agent._context["user_id"] = session_ctx.user_id
            planner_agent._context["correlation_id"] = session_ctx.correlation_id
            coach_agent._context["canvas_id"] = session_ctx.canvas_id
            coach_agent._context["user_id"] = session_ctx.user_id
            coach_agent._context["correlation_id"] = session_ctx.correlation_id
            
    except Exception as e:
        logger.debug("before_tool_callback error: %s", e)
    return None


def _before_model_callback(callback_context, llm_request):
    """Parse context before LLM inference."""
    try:
        for content in llm_request.contents or []:
            if hasattr(content, "role") and content.role == "user":
                for part in content.parts or []:
                    if hasattr(part, "text") and part.text:
                        session_ctx = SessionContext.from_message(part.text)
                        _set_context(session_ctx)
                        
                        # Also update old global contexts
                        from app.agents import planner_agent, coach_agent
                        planner_agent._context["canvas_id"] = session_ctx.canvas_id
                        planner_agent._context["user_id"] = session_ctx.user_id
                        planner_agent._context["correlation_id"] = session_ctx.correlation_id
                        coach_agent._context["canvas_id"] = session_ctx.canvas_id
                        coach_agent._context["user_id"] = session_ctx.user_id
                        coach_agent._context["correlation_id"] = session_ctx.correlation_id
                        break
    except Exception as e:
        logger.debug("before_model_callback error: %s", e)
    return None


# ============================================================================
# SHELL AGENT DEFINITION
# ============================================================================

ShellAgent = Agent(
    name="ShellAgent",
    model=os.getenv("CANVAS_SHELL_MODEL", "gemini-2.5-pro"),
    instruction=SHELL_INSTRUCTION,
    tools=all_tools,
    before_tool_callback=_before_tool_callback,
    before_model_callback=_before_model_callback,
)


# ============================================================================
# ENTRY POINT
# ============================================================================

def handle_message(message: str) -> Dict[str, Any]:
    """
    Main entry point for message handling.
    
    Checks fast lane first, then routes to Shell Agent for slow lane.
    
    Note: This is called by agent_engine_app.py's stream_query override.
    For slow lane, the actual invocation happens through ADK's standard flow.
    
    Args:
        message: Raw message with context prefix
        
    Returns:
        For fast lane: Dict with skill result
        For slow lane: Dict indicating routing to ShellAgent
    """
    ctx = SessionContext.from_message(message)
    routing = route_message(message)
    
    if routing.lane == Lane.FAST:
        # Execute directly, no LLM
        logger.info("handle_message: FAST LANE → %s", routing.intent)
        return execute_fast_lane(routing, message, ctx)
    
    # Slow lane: Let Shell Agent handle via ADK
    logger.info("handle_message: SLOW LANE → ShellAgent")
    return {
        "lane": "slow",
        "agent": "ShellAgent",
        "intent": routing.intent,
        "signals": routing.signals,
    }


# Export for ADK and imports
root_agent = ShellAgent

__all__ = [
    "root_agent",
    "ShellAgent",
    "handle_message",
    "_get_context",
    "_set_context",
]
