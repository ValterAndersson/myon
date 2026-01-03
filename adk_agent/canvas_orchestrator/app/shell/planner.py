"""
Tool Planner - Internal planning step for Slow Lane requests.

Before the Shell Agent executes tools, the Tool Planner generates an internal plan
describing what data is needed and why. This:
1. Improves reasoning quality by explicit planning
2. Enables better observability of agent decision-making
3. Provides audit trail for debugging

The plan is injected as a system message to guide tool selection.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.shell.router import RoutingResult

logger = logging.getLogger(__name__)


@dataclass
class ToolPlan:
    """Generated plan for tool execution."""
    intent: str
    data_needed: List[str]
    rationale: str
    suggested_tools: List[str]
    skip_planning: bool = False
    
    def to_system_prompt(self) -> str:
        """Convert plan to system prompt injection."""
        if self.skip_planning:
            return ""
        
        tools_str = ", ".join(self.suggested_tools) if self.suggested_tools else "determine based on context"
        data_str = "\n".join(f"  - {d}" for d in self.data_needed) if self.data_needed else "  - None required"
        
        return f"""
## INTERNAL PLAN (Auto-generated)
Intent detected: {self.intent}
Data needed:
{data_str}
Rationale: {self.rationale}
Suggested tools: {tools_str}

Execute the plan above, then synthesize a response.
"""


# ============================================================================
# INTENT-SPECIFIC PLANNING TEMPLATES
# ============================================================================

PLANNING_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "ANALYZE_PROGRESS": {
        "data_needed": [
            "Analytics features (8-12 weeks) for volume and intensity trends",
            "Exercise IDs for the relevant muscle group",
            "Per-exercise e1RM slopes to measure progression",
        ],
        "suggested_tools": [
            "tool_get_analytics_features",
            "tool_get_user_exercises_by_muscle",
            "tool_get_analytics_features (with exercise_ids)",
        ],
        "rationale": "Progress analysis requires comparing current metrics to historical data. Check e1rm_slope for progression, intensity_ratio for training quality.",
    },
    "PLAN_ARTIFACT": {
        "data_needed": [
            "User profile for goals and experience level",
            "Planning context for existing routine",
            "Exercise catalog search for suitable exercises",
        ],
        "suggested_tools": [
            "tool_get_planning_context",
            "tool_search_exercises",
            "tool_propose_workout OR tool_propose_routine",
        ],
        "rationale": "Artifact creation requires understanding user context before building. Search exercises broadly, then filter locally.",
    },
    "PLAN_ROUTINE": {
        "data_needed": [
            "User profile for frequency preference",
            "Planning context for existing templates",
            "Exercise catalog search for each muscle group/day type",
        ],
        "suggested_tools": [
            "tool_get_planning_context",
            "tool_search_exercises (one per day type)",
            "tool_propose_routine (once with all days)",
        ],
        "rationale": "Routine creation is a multi-step process. Build all days first, then propose once.",
    },
    "EDIT_PLAN": {
        "data_needed": [
            "Current routine/template to understand existing structure",
            "User's specific edit request",
        ],
        "suggested_tools": [
            "tool_get_planning_context",
            "tool_get_template",
            "tool_propose_workout (with modifications)",
        ],
        "rationale": "Edits should preserve working parts and apply minimal changes.",
    },
    "START_WORKOUT": {
        "data_needed": [
            "Next workout from rotation",
            "User's active routine",
        ],
        "suggested_tools": [
            "tool_get_next_workout",
            "tool_propose_workout",
        ],
        "rationale": "Start workout requires determining which template is next in rotation.",
    },
}


def generate_plan(routing: RoutingResult, message: str) -> ToolPlan:
    """
    Generate a tool execution plan based on detected intent.
    
    Args:
        routing: Routing result from router
        message: User's message
        
    Returns:
        ToolPlan with data requirements and suggested tools
    """
    intent = routing.intent
    
    # No planning needed for Fast Lane (already handled)
    # or if no specific intent was detected
    if intent is None:
        logger.info("PLANNER: No specific intent, skipping planning")
        return ToolPlan(
            intent="general",
            data_needed=[],
            rationale="General query - let LLM determine approach",
            suggested_tools=[],
            skip_planning=True,
        )
    
    # Get template for this intent
    template = PLANNING_TEMPLATES.get(intent)
    
    if template is None:
        logger.info("PLANNER: No template for intent %s", intent)
        return ToolPlan(
            intent=intent,
            data_needed=[],
            rationale=f"Handle {intent} request",
            suggested_tools=[],
            skip_planning=True,
        )
    
    logger.info("PLANNER: Generated plan for %s", intent)
    
    return ToolPlan(
        intent=intent,
        data_needed=template["data_needed"],
        rationale=template["rationale"],
        suggested_tools=template["suggested_tools"],
    )


def should_generate_plan(routing: RoutingResult) -> bool:
    """
    Determine if we should generate a plan for this request.
    
    Only generates plans for complex intents that benefit from explicit planning.
    Fast Lane requests skip planning entirely.
    
    Args:
        routing: Routing result from router
        
    Returns:
        True if planning should be generated
    """
    from app.shell.router import Lane
    
    # Never plan for Fast Lane
    if routing.lane == Lane.FAST:
        return False
    
    # Plan for known complex intents
    if routing.intent in PLANNING_TEMPLATES:
        return True
    
    # Don't plan for general/unknown intents
    return False


__all__ = [
    "ToolPlan",
    "generate_plan",
    "should_generate_plan",
]
