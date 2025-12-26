# Multi-Agent Architecture for Canvas Orchestrator

## Overview

The canvas orchestrator implements a scalable multi-agent system that replaces the monolithic "Unified Agent" approach. The architecture enforces strict permission boundaries and provides debuggable routing through explicit intent classification.

The system separates concerns into four specialist agents, each with clearly defined responsibilities and tool access. This design prevents routing ambiguity, tool misuse, and chatty leakage that occurs when a single agent handles coaching, analysis, planning, and execution.

## Why Multi-Agent?

The previous unified agent blended multiple jobs, creating predictable problems:

1. **Routing ambiguity**: The same user prompt could require explanation, diagnosis, or plan changes, with no clear boundary.
2. **Tool misuse risk**: A general agent was too likely to write to the wrong artifact or active workout.
3. **Chatty leakage**: Without strict role boundaries, the model narrated, over-explained, and undermined the "two-way canvas" behavior.
4. **Scaling issues**: As history, progression deltas, and execution signals were added, the monolithic prompt became brittle.

The multi-agent split enforces permission boundaries and predictable behavior:
- **Coach**: Explanation and principles, no artifact writes
- **Analysis**: Longitudinal insights artifacts, read-heavy
- **Planner**: Proposes and edits workout and routine draft artifacts, minimal chat
- **Copilot**: Runs the live session, the only writer to active workout state
- **Orchestrator**: Routes intent and maintains the user's current "mode" across the session

## Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           ORCHESTRATOR                                    │
│                                                                          │
│   Input: User message + session context                                  │
│   Output: RoutingDecision { intent, target_agent, confidence, signals }  │
│                                                                          │
│   Method:                                                                │
│   1. Apply deterministic regex rules first                               │
│   2. Fall back to LLM classifier if ambiguous                            │
│   3. Track session mode (coach | analyze | plan | execute)               │
└──────────────────────────┬───────────────────────────────────────────────┘
                           │
         ┌─────────────────┼─────────────────┬─────────────────┐
         ▼                 ▼                 ▼                 ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│     COACH       │ │    ANALYSIS     │ │     PLANNER     │ │     COPILOT     │
│                 │ │                 │ │                 │ │                 │
│ Education &     │ │ Progress        │ │ Workout &       │ │ Live workout    │
│ principles      │ │ analysis        │ │ routine drafts  │ │ execution       │
│                 │ │                 │ │                 │ │                 │
│ PERMISSION:     │ │ PERMISSION:     │ │ PERMISSION:     │ │ PERMISSION:     │
│ Read-only       │ │ Read all +      │ │ Read + Write    │ │ Read + Write    │
│ No writes       │ │ Write analysis  │ │ drafts only     │ │ activeWorkout   │
│                 │ │ artifacts       │ │                 │ │ ONLY            │
└─────────────────┘ └─────────────────┘ └─────────────────┘ └─────────────────┘
```

## Agents

### Orchestrator (`orchestrator.py`)

The orchestrator classifies user intent and routes to the correct specialist agent. It uses a rules-first approach with regex pattern matching, falling back to an LLM classifier for ambiguous cases.

**Key Responsibilities:**
- Classify intent using deterministic rules first
- Use LLM classifier when rules are insufficient
- Output structured routing decision for observability
- Track session mode across conversation turns

**Routing Decision Schema:**
```python
@dataclass
class RoutingDecision:
    intent: str           # COACH_GENERAL, PLAN_WORKOUT, etc.
    target_agent: str     # coach, analysis, planner, copilot
    confidence: str       # low, medium, high
    mode_transition: str  # Optional: "coach→plan", "plan→execute"
    matched_rule: str     # e.g., "pattern:create_workout"
    signals: List[str]    # ["has_create_verb", "mentions_routine"]
```

**Intent Patterns:**
| Intent | Triggers | Target |
|--------|----------|--------|
| `PLAN_WORKOUT` | "create workout", "build me a workout", "make a push day" | Planner |
| `PLAN_ROUTINE` | "routine", "program", "split", "ppl", "weekly plan" | Planner |
| `EDIT_PLAN` | "add", "remove", "swap", "change", "more sets" | Planner |
| `EXECUTE_WORKOUT` | "start workout", "I'm at the gym", "begin session" | Copilot |
| `NEXT_WORKOUT` | "next workout", "what's today", "ready to train" | Copilot |
| `ANALYZE_PROGRESS` | "progress", "analyze", "how am I doing", "trends" | Analysis |
| `COACH_GENERAL` | "why", "explain", "how does", "what is" | Coach |

### PlannerAgent (`planner_agent.py`)

The Planner is the workhorse agent that creates and edits workout and routine drafts. It implements the "canvas editor" behavior where the card is the output and chat text is only a control surface.

**Permission Boundary:**
- ✅ Can write `session_plan` cards
- ✅ Can write `routine_summary` cards
- ✅ Can create/update templates
- ✅ Can search exercises
- ❌ Cannot write to activeWorkout state
- ❌ Cannot write analysis artifacts

**Current Tools (Fully Implemented):**
| Tool | Purpose |
|------|---------|
| `tool_get_user_profile` | Read user fitness profile and preferences |
| `tool_get_recent_workouts` | Read recent workout history |
| `tool_get_planning_context` | Get complete context in one call |
| `tool_get_next_workout` | Get next workout from active routine |
| `tool_get_template` | Get specific template details |
| `tool_save_workout_as_template` | Save plan as reusable template |
| `tool_create_routine` | Create new routine with templates |
| `tool_manage_routine` | Add/remove/reorder templates in routine |
| `tool_search_exercises` | Search exercise catalog |
| `tool_propose_workout` | Publish single workout draft to canvas |
| `tool_propose_routine` | Publish complete routine draft to canvas |
| `tool_ask_user` | Ask clarifying question |
| `tool_send_message` | Send text message to user |

### CoachAgent (`coach_agent.py`)

The Coach provides education and explanations about training principles. It answers "why" questions without creating or modifying artifacts.

**Permission Boundary:**
- ✅ Can read user profile and history
- ✅ Can send text responses
- ❌ Cannot create workout or routine drafts
- ❌ Cannot modify active workouts
- ❌ Cannot write any canvas artifacts

**Current Tools (Stub for Routing Validation):**
| Tool | Purpose |
|------|---------|
| `tool_echo_routing` | Debug: Echo routing decision metadata |

**Planned Tools:**
- `tool_get_user_profile` (read)
- `tool_get_recent_workouts` (read)
- `tool_send_message` (text-only response)

### AnalysisAgent (`analysis_agent.py`)

The Analysis agent produces longitudinal progress insights as canvas artifacts. It reads workout history and progression data to identify trends and opportunities.

**Permission Boundary:**
- ✅ Can read all workout data
- ✅ Can write analysis artifacts (charts, tables)
- ❌ Cannot create workout or routine drafts
- ❌ Cannot modify active workouts

**Current Tools (Stub for Routing Validation):**
| Tool | Purpose |
|------|---------|
| `tool_echo_routing` | Debug: Echo routing decision metadata |

**Planned Tools:**
- `tool_get_user_profile` (read)
- `tool_get_recent_workouts` (read, extended limit)
- `tool_get_progression_data` (read exercise-level trends)
- `tool_get_volume_distribution` (read muscle group volumes)
- `tool_propose_analysis` (write analysis_summary cards)

### CopilotAgent (`copilot_agent.py`)

The Copilot manages live workout sessions. It is the ONLY agent that can write to activeWorkout state, providing the critical permission boundary for execution-time safety.

**Permission Boundary:**
- ✅ Can read templates and planning context
- ✅ Can write to activeWorkout state (EXCLUSIVE)
- ❌ Cannot create workout or routine drafts
- ❌ Cannot write analysis artifacts

**Current Tools (Stub for Routing Validation):**
| Tool | Purpose |
|------|---------|
| `tool_echo_routing` | Debug: Echo routing decision metadata |

**Planned Tools:**
- `tool_get_active_workout` (read current session)
- `tool_start_workout` (initialize from template)
- `tool_log_set` (record completed set)
- `tool_adjust_target` (modify upcoming sets)
- `tool_swap_exercise` (replace exercise mid-session)
- `tool_complete_workout` (finalize and save)

## Intent Taxonomy

| Intent | Target Agent | Description |
|--------|--------------|-------------|
| `COACH_GENERAL` | Coach | Education, explanations, "why" questions |
| `ANALYZE_PROGRESS` | Analysis | Progress review, data analysis, trends |
| `PLAN_WORKOUT` | Planner | Create single workout |
| `PLAN_ROUTINE` | Planner | Create multi-day routine |
| `EDIT_PLAN` | Planner | Modify existing workout/routine |
| `EXECUTE_WORKOUT` | Copilot | Live session, adjustments |
| `NEXT_WORKOUT` | Copilot | Start next workout from routine |

## Mode Transitions

The system supports natural progression between modes:

```
┌─────────┐     "analyze my data"      ┌──────────┐
│  Coach  │ ─────────────────────────> │ Analysis │
└─────────┘                            └──────────┘
                                             │
                                             │ "apply this to my plan"
                                             ▼
┌─────────┐    "start workout"         ┌──────────┐
│ Copilot │ <───────────────────────── │ Planner  │
└─────────┘                            └──────────┘
     │
     │ "post-session summary"
     ▼
┌──────────┐
│ Analysis │
└──────────┘
```

## Directory Structure

```
adk_agent/canvas_orchestrator/app/
├── __init__.py
├── agent.py                    # Original entry point
├── agent_engine_app.py         # Agent Engine integration
├── agent_multi.py              # Multi-agent entry point (USE_MULTI_AGENT toggle)
├── unified_agent.py            # DEPRECATED - kept for backwards compatibility
│
├── agents/
│   ├── __init__.py             # Exports root_agent (orchestrator)
│   ├── orchestrator.py         # Intent classifier + router
│   ├── planner_agent.py        # Workout/routine planning (fully implemented)
│   ├── coach_agent.py          # Education (stub)
│   ├── analysis_agent.py       # Progress analysis (stub)
│   ├── copilot_agent.py        # Live execution (stub)
│   │
│   └── tools/
│       ├── __init__.py         # Exports all tool sets
│       ├── planner_tools.py    # Planner tool definitions
│       ├── coach_tools.py      # Coach tool definitions
│       ├── analysis_tools.py   # Analysis tool definitions
│       └── copilot_tools.py    # Copilot tool definitions
│
└── libs/
    └── tools_canvas/
        └── client.py           # Firebase functions client
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `USE_MULTI_AGENT` | `true` | Use orchestrator routing (set to `false` for Planner-only fallback) |
| `CANVAS_ORCHESTRATOR_MODEL` | `gemini-2.5-flash` | Model for intent classification |
| `CANVAS_PLANNER_MODEL` | `gemini-2.5-flash` | Model for Planner agent |
| `CANVAS_COACH_MODEL` | `gemini-2.5-flash` | Model for Coach agent |
| `CANVAS_ANALYSIS_MODEL` | `gemini-2.5-flash` | Model for Analysis agent |
| `CANVAS_COPILOT_MODEL` | `gemini-2.5-flash` | Model for Copilot agent |

## Routing Validation (Stub Behavior)

The stub agents (Coach, Analysis, Copilot) echo routing metadata for debugging:

```
"I am the Coach Agent. You landed here because orchestrator 
classified intent as: COACH_GENERAL."
```

This allows validation of:
1. **Routing correctness**: Does the right agent receive the message?
2. **Intent classification accuracy**: Are intents labeled correctly?
3. **Mode transitions**: Do transitions flow as expected?
4. **Permission boundaries**: Can we verify tool access at runtime?

## Permission Enforcement

Permission boundaries are enforced at the code level through tool definitions, not prompts:

```python
# planner_tools.py - Planner gets full planning toolkit
PLANNER_TOOLS = [
    tool_get_planning_context,
    tool_search_exercises,
    tool_propose_workout,      # ✅ Planner can write drafts
    tool_propose_routine,      # ✅ Planner can write routines
    # tool_log_set,            # ❌ NOT included - Copilot only
]

# copilot_tools.py - Copilot gets activeWorkout tools
COPILOT_TOOLS = [
    tool_get_active_workout,
    tool_start_workout,        # ✅ Copilot can write activeWorkout
    tool_log_set,              # ✅ Copilot can log sets
    # tool_propose_workout,    # ❌ NOT included - Planner only
]
```

This ensures that even if an agent's prompt is manipulated, it cannot access tools outside its permission boundary.

## Adding New Capabilities

To add capability to an agent without changing orchestrator plumbing:

1. **Add tool function** to the agent's file (e.g., `planner_agent.py`)
2. **Add to tool list** in the tools definition (e.g., `planner_tools.py`)
3. **Update agent instruction** to document the new tool

No changes to orchestrator or other agents required.

## Key Success Criteria

1. **Planner behaves as a canvas editor** with minimal chat leakage
2. **Copilot is the only writer to active workout state**
3. **Orchestrator routing is visible and debuggable**
4. **Adding capability to an agent does not require changing other agents or loosening tool boundaries**
