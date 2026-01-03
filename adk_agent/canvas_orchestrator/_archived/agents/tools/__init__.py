"""
Per-Agent Tool Definitions.

This module defines tool sets with enforced permission boundaries:
- PlannerTools: Draft creation and exercise search
- CoachTools: Training context, analytics, and exercise catalog access
- CopilotTools: Active workout manipulation (stub)

Each agent receives only the tools it is permitted to use.
"""

from app.agents.tools.planner_tools import PLANNER_TOOLS
from app.agents.tools.coach_tools import COACH_TOOLS
from app.agents.tools.copilot_tools import COPILOT_TOOLS

__all__ = [
    "PLANNER_TOOLS",
    "COACH_TOOLS",
    "COPILOT_TOOLS",
]
