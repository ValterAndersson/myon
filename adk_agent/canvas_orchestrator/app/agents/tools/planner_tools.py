"""
Planner Agent Tools - Workout and routine draft creation.

Permission Boundary: Can write session_plan and routine_summary artifacts.
Cannot: Write to activeWorkout state.

Tools:
- User context (read)
- Routine & template context (read + write templates)
- Exercise catalog (read)
- Workout/routine drafts (write)
- Communication (clarification, messages)
"""

from google.adk.tools import FunctionTool

# Import tool implementations from planner_agent
# These are the actual tool functions with full implementation
from app.agents.planner_agent import (
    tool_get_user_profile,
    tool_get_recent_workouts,
    tool_get_planning_context,
    tool_get_next_workout,
    tool_get_template,
    tool_save_workout_as_template,
    tool_create_routine,
    tool_manage_routine,
    tool_search_exercises,
    tool_propose_workout,
    tool_propose_routine,
    tool_ask_user,
    tool_send_message,
)

# Planner gets the full planning toolkit
PLANNER_TOOLS = [
    # User context (read-only)
    FunctionTool(func=tool_get_user_profile),
    FunctionTool(func=tool_get_recent_workouts),
    
    # Routine & template context
    FunctionTool(func=tool_get_planning_context),
    FunctionTool(func=tool_get_next_workout),
    FunctionTool(func=tool_get_template),
    FunctionTool(func=tool_save_workout_as_template),
    FunctionTool(func=tool_create_routine),
    FunctionTool(func=tool_manage_routine),
    
    # Exercise catalog
    FunctionTool(func=tool_search_exercises),
    
    # Draft creation (the main purpose of this agent)
    FunctionTool(func=tool_propose_workout),
    FunctionTool(func=tool_propose_routine),
    
    # Communication
    FunctionTool(func=tool_ask_user),
    FunctionTool(func=tool_send_message),
]

__all__ = ["PLANNER_TOOLS"]
