"""
Multi-Agent System Entry Point for Canvas Orchestrator.

Agent Architecture:
- Orchestrator: Intent classification and routing (rules-first, LLM fallback)
- Planner: Creates/edits workout and routine drafts (fully implemented)
- Coach: Education, analytics, and data-informed advice (fully implemented)
- Copilot: Live workout execution (stub)

Environment Variables:
- USE_MULTI_AGENT=true: Use the new multi-agent orchestrator (default)
- USE_MULTI_AGENT=false: Use the Planner agent directly (backwards compat)

The multi-agent system enforces permission boundaries at the code level:
- Only Planner can write workout/routine drafts
- Only Copilot can write activeWorkout (stub, Phase 2)
- Coach has read-only access to analytics and exercise catalog
"""

import os
import logging

logger = logging.getLogger(__name__)

USE_MULTI_AGENT = os.getenv("USE_MULTI_AGENT", "true").lower() in ("true", "1", "yes")

if USE_MULTI_AGENT:
    # New multi-agent architecture with orchestrator routing
    from app.agents import root_agent
    logger.info("Using MULTI-AGENT orchestrator architecture")
else:
    # Fallback to Planner agent directly (same as old unified agent)
    from app.agents.planner_agent import PlannerAgent as root_agent
    logger.info("Using PLANNER agent directly (multi-agent disabled)")

__all__ = ["root_agent"]
