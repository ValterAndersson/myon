"""
planner_tools.py - Planner Agent Tool Definitions

PURPOSE:
Defines the tool set available to PlannerAgent. Tools are the interface between
agent reasoning and external systems (Firebase Functions, Firestore).

ARCHITECTURE CONTEXT:
┌─────────────────────────────────────────────────────────────────────────────┐
│ PLANNER AGENT TOOL BOUNDARY                                                 │
│                                                                             │
│ ALLOWED ACTIONS:                                                            │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ READ:                                                                   │ │
│ │  • tool_get_user_profile → get-user.js                                 │ │
│ │  • tool_get_recent_workouts → workouts collection                      │ │
│ │  • tool_get_planning_context → get-planning-context.js                 │ │
│ │  • tool_get_template → templates collection                            │ │
│ │  • tool_search_exercises → search-exercises.js                         │ │
│ │                                                                         │ │
│ │ WRITE (Canvas-only):                                                   │ │
│ │  • tool_propose_workout → propose-cards.js (session_plan)              │ │
│ │  • tool_propose_routine → propose-cards.js (routine_summary + days)    │ │
│ │  • tool_save_workout_as_template → create-template-from-plan.js        │ │
│ │  • tool_create_routine → routines collection                           │ │
│ │  • tool_manage_routine → patch-routine.js                              │ │
│ │                                                                         │ │
│ │ CLARIFICATION:                                                          │ │
│ │  • tool_ask_user → Emits clarification card for user input             │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│ NOT ALLOWED (enforced by not including in PLANNER_TOOLS):                  │
│  • tool_get_next_workout - Copilot-only (execution context)                │
│  • tool_log_set - Copilot-only (active workout writes)                     │
│  • tool_send_message - Removed to prevent chat leakage                     │
│                                                                             │
│ DESIGN PRINCIPLE: The card IS the output. No chat messages.               │
└─────────────────────────────────────────────────────────────────────────────┘

TOOL IMPLEMENTATIONS:
Tool functions are defined in planner_agent.py with full implementation.
This file wraps them in FunctionTool for ADK registration.

RELATED FILES:
- planner_agent.py: Tool implementations and PlannerAgent definition
- coach_tools.py: CoachAgent tools (education, analysis)
- copilot_tools.py: CopilotAgent tools (live workout execution)
- ../libs/tools_canvas/client.py: HTTP client for Firebase Functions

UNUSED CODE CHECK: ✅ No unused code in this file

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
