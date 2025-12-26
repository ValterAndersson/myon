"""
Analysis Agent Tools - Progress analysis and insights.

Permission Boundary: Can read all data, can write analysis artifacts only.
Cannot: Create workout/routine drafts, modify active workouts.

Current Tools (stub):
- tool_echo_routing: Debug tool for routing validation

Future Tools:
- tool_get_user_profile: Read user context
- tool_get_recent_workouts: Read workout history (extended limit)
- tool_get_progression_data: Read exercise-level progression
- tool_get_volume_distribution: Read muscle group volume trends
- tool_propose_analysis: Write analysis artifacts (charts, tables)
"""

from google.adk.tools import FunctionTool
from app.agents.analysis_agent import tool_echo_routing

# Analysis has read tools + analysis artifact write
ANALYSIS_TOOLS = [
    FunctionTool(func=tool_echo_routing),
]

# Future tools to add:
# Read:
# - tool_get_user_profile
# - tool_get_recent_workouts (with higher limit, e.g., 50)
# - tool_get_progression_data (new: exercise-level trends)
# - tool_get_volume_distribution (new: muscle group volumes)
#
# Write (analysis artifacts only):
# - tool_propose_analysis (creates analysis_summary cards)

__all__ = ["ANALYSIS_TOOLS"]
