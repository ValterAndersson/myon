"""
Coach Agent - Education and training principles (STUB for Phase 1).

Part of the multi-agent architecture. This agent:
- Answers general questions about training, hypertrophy, form, etc.
- Provides explanations and education
- Does NOT create or modify artifacts

Permission boundary: Read-only. No artifact writes.

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
    logger.info("CoachAgent received: intent=%s confidence=%s rule=%s", intent, confidence, matched_rule)
    return {
        "agent": "CoachAgent",
        "intent_received": intent,
        "confidence": confidence,
        "matched_rule": matched_rule,
        "status": "stub_response",
    }


# ============================================================================
# AGENT DEFINITION
# ============================================================================

COACH_INSTRUCTION = """
You are the Coach Agent. You provide education and explanations about training principles.

## PHASE 1 STUB BEHAVIOR
You are currently a stub agent for routing validation. When you receive a message:
1. Call tool_echo_routing with the intent and confidence from the routing context
2. Respond with a single line confirming your identity and the routing decision

Example response:
"I am the Coach Agent. You landed here because orchestrator classified intent as: COACH_GENERAL."

## PERMISSION BOUNDARIES (ENFORCED)
- You CANNOT create workout or routine drafts
- You CANNOT modify active workouts
- You CANNOT propose canvas artifacts
- You CAN read user profile and history for context (Phase 2)
- You CAN provide text-based explanations and advice

## FUTURE CAPABILITIES (Phase 2+)
- Explain hypertrophy principles
- Discuss training techniques and form
- Answer "why" questions about programming
- Provide science-backed recommendations without creating plans
"""

CoachAgent = Agent(
    name="CoachAgent",
    model=os.getenv("CANVAS_COACH_MODEL", "gemini-2.5-flash"),
    instruction=COACH_INSTRUCTION,
    tools=[FunctionTool(func=tool_echo_routing)],
)

root_agent = CoachAgent

__all__ = ["root_agent", "CoachAgent"]
