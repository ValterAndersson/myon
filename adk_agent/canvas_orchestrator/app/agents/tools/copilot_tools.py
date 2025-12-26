"""
Copilot Agent Tools - Live workout execution.

Permission Boundary: ONLY agent that can write to activeWorkout state.
Cannot: Create workout/routine drafts, write analysis artifacts.

Current Tools (stub):
- tool_echo_routing: Debug tool for routing validation

Future Tools:
- tool_get_active_workout: Read current workout state
- tool_start_workout: Initialize active workout from template
- tool_log_set: Record completed set with actual reps/weight/RIR
- tool_adjust_target: Modify upcoming set targets
- tool_swap_exercise: Replace exercise mid-session
- tool_complete_workout: Finalize and save workout
- tool_get_template: Read template for reference
- tool_get_planning_context: Read context for informed decisions
"""

from google.adk.tools import FunctionTool
from app.agents.copilot_agent import tool_echo_routing

# Copilot has activeWorkout write tools (currently stub)
COPILOT_TOOLS = [
    FunctionTool(func=tool_echo_routing),
]

# Future tools to add:
# Read:
# - tool_get_active_workout (read current session state)
# - tool_get_template (read template for reference)
# - tool_get_planning_context (read user preferences)
#
# Write (activeWorkout ONLY - this is the critical permission):
# - tool_start_workout (initialize from template)
# - tool_log_set (record actual performance)
# - tool_adjust_target (modify upcoming sets)
# - tool_swap_exercise (replace exercise mid-session)
# - tool_complete_workout (finalize and save)

__all__ = ["COPILOT_TOOLS"]
