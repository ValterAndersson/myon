"""
copilot_tools.py - Copilot Agent Tool Definitions (STUB)

PURPOSE:
Defines the tool set for CopilotAgent - the ONLY agent allowed to write to
activeWorkout state. This is currently a stub with only a debug tool.

IMPLEMENTATION STATUS: ⚠️ STUB - NOT FULLY IMPLEMENTED
Active workout execution is currently handled by iOS without agent involvement.
This agent will be activated when real-time AI coaching during workouts is needed.

ARCHITECTURE CONTEXT:
┌─────────────────────────────────────────────────────────────────────────────┐
│ COPILOT AGENT TOOL BOUNDARY (PLANNED)                                       │
│                                                                             │
│ CURRENT IMPLEMENTATION:                                                     │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ • tool_echo_routing - Debug tool for routing validation only           │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│ PLANNED IMPLEMENTATION (when real-time coaching is built):                 │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ READ:                                                                   │ │
│ │  • tool_get_active_workout → Read current session state                │ │
│ │  • tool_get_template → Read template for reference                     │ │
│ │  • tool_get_planning_context → Read user preferences                   │ │
│ │                                                                         │ │
│ │ WRITE (activeWorkout ONLY - critical permission boundary):             │ │
│ │  • tool_start_workout → Initialize from template                       │ │
│ │  • tool_log_set → Record actual reps/weight/RIR                        │ │
│ │  • tool_adjust_target → Modify upcoming set targets                    │ │
│ │  • tool_swap_exercise → Replace exercise mid-session                   │ │
│ │  • tool_complete_workout → Finalize and archive                        │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│ NOT ALLOWED (Copilot is live execution only):                              │
│  • No canvas writes (no tool_propose_workout)                              │
│  • No routine management (no tool_create_routine)                          │
│  • No analysis artifacts (no tool_emit_visualization)                      │
└─────────────────────────────────────────────────────────────────────────────┘

CURRENT ACTIVE WORKOUT FLOW (iOS-only, no agent):
iOS ActiveWorkoutManager → start-active-workout.js → log-set.js → complete-active-workout.js

RELATED FILES:
- copilot_agent.py: Agent definition (stub)
- planner_tools.py: PlannerAgent tools (artifact creation)
- coach_tools.py: CoachAgent tools (education/analysis)
- ../active_workout/: Firebase functions for workout execution

UNUSED CODE CHECK: ✅ No unused code (only stub in use)

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
