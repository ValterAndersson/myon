"""
coach_tools.py - Coach Agent Tool Definitions

PURPOSE:
Defines the tool set available to CoachAgent. The Coach handles education,
training advice, and data analysis - all READ-ONLY operations.

ARCHITECTURE CONTEXT:
┌─────────────────────────────────────────────────────────────────────────────┐
│ COACH AGENT TOOL BOUNDARY                                                   │
│                                                                             │
│ ALLOWED ACTIONS (READ-ONLY):                                                │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ TRAINING CONTEXT:                                                       │ │
│ │  • tool_get_training_context → Aggregated user training state          │ │
│ │  • tool_get_analytics_features → Volume/frequency/progress metrics     │ │
│ │  • tool_get_user_profile → User attributes and preferences             │ │
│ │  • tool_get_recent_workouts → Last N completed workouts                │ │
│ │                                                                         │ │
│ │ EXERCISE CATALOG:                                                       │ │
│ │  • tool_get_user_exercises_by_muscle → User's exercises for muscle     │ │
│ │  • tool_search_exercises → Global exercise catalog search              │ │
│ │  • tool_get_exercise_details → Specific exercise info                  │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│ NOT ALLOWED (Coach is education/advice only):                               │
│  • No canvas writes (no tool_propose_workout)                              │
│  • No routine management (no tool_create_routine)                          │
│  • No active workout writes (no tool_log_set)                              │
│                                                                             │
│ DESIGN PRINCIPLE: Coach provides text responses informed by data.          │
│ If user wants to CREATE something, orchestrator routes to Planner.        │
└─────────────────────────────────────────────────────────────────────────────┘

TOOL IMPLEMENTATIONS:
Tool functions are defined in coach_agent.py with full implementation.
COACH_TOOLS is imported as `all_tools` from coach_agent.py.

FIREBASE FUNCTIONS CALLED:
- get-user.js (via tool_get_user_profile)
- search-exercises.js (via tool_search_exercises)
- workouts collection reads (via tool_get_recent_workouts)
- analytics aggregation (via tool_get_analytics_features)

RELATED FILES:
- coach_agent.py: Tool implementations and CoachAgent definition
- planner_tools.py: PlannerAgent tools (artifact creation)
- copilot_tools.py: CopilotAgent tools (live workout execution)

UNUSED CODE CHECK: ✅ No unused code in this file

"""

from app.agents.coach_agent import all_tools as COACH_TOOLS

# Individual tool exports for direct access if needed
from app.agents.coach_agent import (
    tool_get_training_context,
    tool_get_analytics_features,
    tool_get_user_profile,
    tool_get_recent_workouts,
    tool_get_user_exercises_by_muscle,
    tool_search_exercises,
    tool_get_exercise_details,
)

__all__ = [
    "COACH_TOOLS",
    "tool_get_training_context",
    "tool_get_analytics_features",
    "tool_get_user_profile",
    "tool_get_recent_workouts",
    "tool_get_user_exercises_by_muscle",
    "tool_search_exercises",
    "tool_get_exercise_details",
]
