"""
Coach Agent Tools - Education and training principles.

Permission Boundary: Read-only. No artifact writes allowed.
Cannot: Create drafts, modify active workouts, write any artifacts.

Current Tools (stub):
- tool_echo_routing: Debug tool for routing validation

Future Tools:
- tool_get_user_profile: Read user context
- tool_get_recent_workouts: Read workout history
- tool_send_message: Text-only responses
"""

from google.adk.tools import FunctionTool
from app.agents.coach_agent import tool_echo_routing

# Coach has NO write tools - strictly read-only with text responses
COACH_TOOLS = [
    FunctionTool(func=tool_echo_routing),
]

# Future tools to add (all read-only):
# - tool_get_user_profile (imported from shared tools)
# - tool_get_recent_workouts (imported from shared tools)
# - tool_send_message (text response only, no artifacts)

__all__ = ["COACH_TOOLS"]
