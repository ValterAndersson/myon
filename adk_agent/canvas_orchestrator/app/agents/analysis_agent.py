"""
Analysis Agent - Progress analysis and insights (STUB for Phase 1).

Part of the multi-agent architecture. This agent:
- Analyzes workout history and progression
- Identifies trends, weaknesses, and opportunities
- Creates analysis artifacts (charts, tables)

Permission boundary: Can read all data, can write analysis artifacts only.

Phase 1: Stub that echoes routing metadata for observability.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict

from google.adk import Agent
from google.adk.tools import FunctionTool

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


# ============================================================================
# STUB TOOLS
# ============================================================================

def tool_echo_routing(*, intent: str, confidence: str, matched_rule: str = "unknown") -> Dict[str, Any]:
    """
    Debug tool: Echo the routing decision that brought us here.
    Used during Phase 1 to validate orchestrator routing.
    """
    logger.info("AnalysisAgent received: intent=%s confidence=%s rule=%s", intent, confidence, matched_rule)
    return {
        "agent": "AnalysisAgent",
        "intent_received": intent,
        "confidence": confidence,
        "matched_rule": matched_rule,
        "status": "stub_response",
    }


# ============================================================================
# AGENT DEFINITION
# ============================================================================

ANALYSIS_INSTRUCTION = """
You are the Analysis Agent. You analyze training data and provide insights.

## PHASE 1 STUB BEHAVIOR
You are currently a stub agent for routing validation. When you receive a message:
1. Call tool_echo_routing with the intent and confidence from the routing context
2. Respond with a single line confirming your identity and the routing decision

Example response:
"I am the Analysis Agent. You landed here because orchestrator classified intent as: ANALYZE_PROGRESS."

## PERMISSION BOUNDARIES (ENFORCED)
- You CANNOT create workout or routine drafts
- You CANNOT modify active workouts
- You CAN read workout history, progression data, templates, routines
- You CAN create analysis artifacts (charts, tables, insights cards)

## FUTURE CAPABILITIES (Phase 2+)
- Volume distribution analysis by muscle group
- Progression tracking (load, reps, RIR trends)
- Workout frequency and consistency metrics
- Weak point identification
- Recovery and fatigue indicators
- Generate analysis_summary canvas cards
"""

AnalysisAgent = Agent(
    name="AnalysisAgent",
    model=os.getenv("CANVAS_ANALYSIS_MODEL", "gemini-2.5-flash"),
    instruction=ANALYSIS_INSTRUCTION,
    tools=[FunctionTool(func=tool_echo_routing)],
)

root_agent = AnalysisAgent

__all__ = ["root_agent", "AnalysisAgent"]
