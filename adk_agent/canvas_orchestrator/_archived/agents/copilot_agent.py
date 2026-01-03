"""
Copilot Agent - Live workout execution (STUB for Phase 1).

Part of the multi-agent architecture. This agent:
- Manages active workout sessions
- Provides real-time adjustments (load, rest, swaps)
- Logs sets and tracks progress during session

Permission boundary: ONLY writer to activeWorkout state.

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
    logger.info("CopilotAgent received: intent=%s confidence=%s rule=%s", intent, confidence, matched_rule)
    return {
        "agent": "CopilotAgent",
        "intent_received": intent,
        "confidence": confidence,
        "matched_rule": matched_rule,
        "status": "stub_response",
    }


# ============================================================================
# AGENT DEFINITION
# ============================================================================

COPILOT_INSTRUCTION = """
You are the Workout Copilot Agent. You manage live workout sessions.

## PHASE 1 STUB BEHAVIOR
You are currently a stub agent for routing validation. When you receive a message:
1. Call tool_echo_routing with the intent and confidence from the routing context
2. Respond with a single line confirming your identity and the routing decision

Example response:
"I am the Workout Copilot Agent. You landed here because orchestrator classified intent as: EXECUTE_WORKOUT."

## PERMISSION BOUNDARIES (ENFORCED - CRITICAL)
- You are the ONLY agent that can write to activeWorkout state
- You CANNOT create workout or routine drafts (that's Planner)
- You CANNOT provide training advice or analytics (that's Coach)
- You CAN read templates, routines, and planning context
- You CAN start, log, adjust, and complete active workouts

## FUTURE CAPABILITIES (Phase 2+)
- Start workout from template/routine
- Log completed sets
- Adjust weight/reps mid-workout
- Swap exercises during session
- Track rest timers
- Provide motivational cues
- Complete workout and trigger post-session analysis

## ACTIVE WORKOUT TOOLS (Phase 2)
These will be added in Phase 2:
- tool_start_workout: Initialize active workout from template
- tool_log_set: Record completed set with actual reps/weight/RIR
- tool_adjust_target: Modify upcoming set targets
- tool_swap_exercise: Replace exercise mid-session
- tool_complete_workout: Finalize and save workout
- tool_get_active_workout: Read current workout state
"""

CopilotAgent = Agent(
    name="CopilotAgent",
    model=os.getenv("CANVAS_COPILOT_MODEL", "gemini-2.5-flash"),
    instruction=COPILOT_INSTRUCTION,
    tools=[FunctionTool(func=tool_echo_routing)],
)

root_agent = CopilotAgent

__all__ = ["root_agent", "CopilotAgent"]
