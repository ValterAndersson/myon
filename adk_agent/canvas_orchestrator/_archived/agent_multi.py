"""
Multi-Agent System Entry Point for Canvas Orchestrator.

Agent Architecture Modes:
1. USE_SHELL_AGENT=true (NEW): Single Shell Agent with unified persona
   - Combines Coach + Planner capabilities into one agent
   - Fast Lane bypass for copilot commands (sub-500ms)
   - Consistent voice and behavior across all domains

2. USE_MULTI_AGENT=true (LEGACY): Multi-agent orchestrator routing
   - Orchestrator: Intent classification and routing
   - Planner: Creates/edits workout and routine drafts
   - Coach: Education, analytics, and data-informed advice

3. USE_MULTI_AGENT=false: Planner agent directly (backwards compat)

Environment Variables:
- USE_SHELL_AGENT=true: Use the new unified Shell Agent (recommended)
- USE_MULTI_AGENT=true: Use the legacy multi-agent orchestrator
- USE_MULTI_AGENT=false: Use the Planner agent directly
"""

import os
import logging

logger = logging.getLogger(__name__)

# Feature flags
# NOTE: On refactor/single-shell-agent branch, Shell Agent is the default
USE_SHELL_AGENT = os.getenv("USE_SHELL_AGENT", "true").lower() in ("true", "1", "yes")
USE_MULTI_AGENT = os.getenv("USE_MULTI_AGENT", "false").lower() in ("true", "1", "yes")

if USE_SHELL_AGENT:
    # New unified Shell Agent architecture
    from app.shell import root_agent
    logger.info("Using SHELL AGENT architecture (unified persona)")
    
elif USE_MULTI_AGENT:
    # Legacy multi-agent architecture with orchestrator routing
    from app.agents import root_agent
    logger.info("Using MULTI-AGENT orchestrator architecture (legacy)")
    
else:
    # Fallback to Planner agent directly (same as old unified agent)
    from app.agents.planner_agent import PlannerAgent as root_agent
    logger.info("Using PLANNER agent directly (multi-agent disabled)")

__all__ = ["root_agent"]
