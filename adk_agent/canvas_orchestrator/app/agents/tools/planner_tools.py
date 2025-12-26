"""
Planner Agent Tools - Workout and routine draft creation.

Permission Boundary: Can write session_plan and routine_summary artifacts.
Cannot: Write to activeWorkout state, send chat messages (canvas-only output).

Tools:
- User context (read)
- Routine & template context (read + write templates)
- Exercise catalog (read)
- Workout/routine drafts (write)
- Clarification (ask_user only, not send_message)

Removed tools (enforced permission boundaries):
- tool_get_next_workout: Copilot-only (execution context)
- tool_send_message: Removed to prevent chat leakage. The card IS the output.
"""

from google.adk.tools import FunctionTool

# Import tool implementations from planner_agent
# These are the actual tool functions with full implementation
from app.agents.planner_agent import (
    tool_get_user_profile,
    tool_get_recent_workouts,
    tool_get_planning_context,
    tool_get_template,
    tool_save_workout_as_template,
    tool_create_routine,
    tool_manage_routine,
    tool_search_exercises,
    tool_propose_workout,
    tool_propose_routine,
    tool_ask_user,
)

# Planner gets planning toolkit with canvas-only output
PLANNER_TOOLS = [
    # User context (read-only)
    FunctionTool(func=tool_get_user_profile),
    FunctionTool(func=tool_get_recent_workouts),
    
    # Routine & template context (read + write templates)
    FunctionTool(func=tool_get_planning_context),
    FunctionTool(func=tool_get_template),
    FunctionTool(func=tool_save_workout_as_template),
    FunctionTool(func=tool_create_routine),
    FunctionTool(func=tool_manage_routine),
    
    # Exercise catalog
    FunctionTool(func=tool_search_exercises),
    
    # Draft creation (the main purpose of this agent)
    FunctionTool(func=tool_propose_workout),
    FunctionTool(func=tool_propose_routine),
    
    # Clarification only (no chat messages - canvas is the output)
    FunctionTool(func=tool_ask_user),
]

__all__ = ["PLANNER_TOOLS"]
