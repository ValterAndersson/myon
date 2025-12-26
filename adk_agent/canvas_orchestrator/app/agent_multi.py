"""
Multi-Agent System Entry Point for Canvas Orchestrator.

Agent Architecture:
- Orchestrator: Intent classification and routing (rules-first, LLM fallback)
- PlannerAgent: Creates/edits workout and routine drafts
- CoachAgent: Education and training principles (Phase 1 stub)
- AnalysisAgent: Progress analysis and insights (Phase 1 stub)  
- CopilotAgent: Live workout execution (Phase 1 stub)

Environment Variables:
- USE_MULTI_AGENT=true: Use the new multi-agent orchestrator (default)
- USE_MULTI_AGENT=false: Use the Planner agent directly (backwards compat)

The multi-agent system enforces permission boundaries at the code level:
- Only Planner can write workout/routine drafts
- Only Copilot can write activeWorkout (Phase 2)
- Only Analysis can write analysis artifacts
- Coach has no artifact write permissions
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
