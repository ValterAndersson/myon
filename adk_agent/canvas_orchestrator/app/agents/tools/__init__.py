"""
Per-Agent Tool Definitions.

This module defines tool sets with enforced permission boundaries:
- PlannerTools: Draft creation and exercise search
- CoachTools: Read-only context access (future)
- AnalysisTools: Read data + write analysis artifacts (future)
- CopilotTools: Active workout manipulation (future)

Each agent receives only the tools it is permitted to use.
"""

from app.agents.tools.planner_tools import PLANNER_TOOLS
from app.agents.tools.coach_tools import COACH_TOOLS
from app.agents.tools.analysis_tools import ANALYSIS_TOOLS
from app.agents.tools.copilot_tools import COPILOT_TOOLS

__all__ = [
    "PLANNER_TOOLS",
    "COACH_TOOLS",
    "ANALYSIS_TOOLS",
    "COPILOT_TOOLS",
]
