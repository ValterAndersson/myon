# Multi-Agent Architecture for Canvas Orchestrator

## Overview

The canvas orchestrator implements a scalable multi-agent system. The architecture enforces strict permission boundaries and provides debuggable routing through explicit intent classification.

The system separates concerns into **three specialist agents**, each with clearly defined responsibilities and tool access:

| Agent | Role | Key Capability |
|-------|------|----------------|
| **Coach** | Education + data-informed advice | Has analytics tools, no artifact writes |
| **Planner** | Workout/routine artifact creation | Writes drafts, minimal chat |
| **Copilot** | Live workout execution | Writes activeWorkout state ONLY |

## Why Multi-Agent?

The previous unified agent blended multiple jobs, creating predictable problems:

1. **Routing ambiguity**: The same user prompt could require explanation, diagnosis, or plan changes, with no clear boundary.
2. **Tool misuse risk**: A general agent was too likely to write to the wrong artifact or active workout.
3. **Chatty leakage**: Without strict role boundaries, the model narrated, over-explained, and undermined the "two-way canvas" behavior.
4. **Scaling issues**: As history, progression deltas, and execution signals were added, the monolithic prompt became brittle.

The multi-agent split enforces permission boundaries and predictable behavior:
- **Coach**: Education, principles, AND data-informed advice (merged with former Analysis)
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
│   3. Track session mode (coach | plan | execute)                         │
└──────────────────────────┬───────────────────────────────────────────────┘
                           │
         ┌─────────────────┼─────────────────┐
         ▼                 ▼                 ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│     COACH       │ │     PLANNER     │ │     COPILOT     │
│                 │ │                 │ │                 │
│ Education +     │ │ Workout &       │ │ Live workout    │
│ data-informed   │ │ routine drafts  │ │ execution       │
│ advice          │ │                 │ │                 │
│                 │ │                 │ │                 │
│ PERMISSION:     │ │ PERMISSION:     │ │ PERMISSION:     │
│ Read all +      │ │ Read + Write    │ │ Read + Write    │
│ analytics tools │ │ drafts only     │ │ activeWorkout   │
│ No artifact     │ │                 │ │ ONLY            │
│ writes          │ │                 │ │                 │
└─────────────────┘ └─────────────────┘ └─────────────────┘
```

## Agents

### Orchestrator (`orchestrator.py`)

The orchestrator classifies user intent and routes to the correct specialist agent. It uses a rules-first approach with regex pattern matching, falling back to an LLM classifier for ambiguous cases.

**Key Responsibilities:**
- Classify intent using deterministic rules first (~80% coverage)
- Use "metric words gate" for first-person + metrics patterns
- Use LLM classifier when rules are insufficient
- Output structured routing decision for observability
- Apply safety re-route if target agent lacks tools for request

**Routing Decision Schema:**
```python
@dataclass
class RoutingDecision:
    intent: str           # COACH_GENERAL, ANALYZE_PROGRESS, PLAN_WORKOUT, etc.
    target_agent: str     # coach, planner, copilot
    confidence: str       # low, medium, high
    mode_transition: str  # Optional: "coach→plan", "plan→execute"
    matched_rule: str     # e.g., "pattern:create_workout", "gate:first_person_plus_metrics"
    signals: List[str]    # ["has_create_verb", "mentions_routine", "first_person_plus_metrics"]
```

**Intent Patterns:**
| Intent | Triggers | Target |
|--------|----------|--------|
| `PLAN_WORKOUT` | "create workout", "build me a workout", "make a push day" | Planner |
| `PLAN_ROUTINE` | "routine", "program", "split", "ppl", "weekly plan" | Planner |
| `EDIT_PLAN` | "add", "remove", "swap", "change", "more sets" | Planner |
| `EXECUTE_WORKOUT` | "start workout", "I'm at the gym", "begin session" | Copilot |
| `NEXT_WORKOUT` | "next workout", "what's today", "ready to train" | Copilot |
| `ANALYZE_PROGRESS` | "my progress", "analyze", "how am I doing", "my volume" | **Coach** |
| `COACH_GENERAL` | "why", "explain", "how does", "what is", "technique" | Coach |

### CoachAgent (`coach_agent.py`)

The Coach provides evidence-based training advice that is **personalized using training data when it changes the recommendation**. This is a unified agent that combines education/principles with data-informed insights.

**Key Principle:** Truth over agreement. Use data only when it changes the recommendation.

**Permission Boundary:**
- ✅ Can read user profile and history
- ✅ Can read analytics features (weekly rollups, muscle series, e1RM trends)
- ✅ Can search exercise catalog for technique/comparison questions
- ✅ Can send text responses
- ❌ Cannot create workout or routine drafts
- ❌ Cannot modify active workouts
- ❌ Cannot write canvas artifacts

**Current Tools (Fully Implemented):**
| Tool | Purpose |
|------|---------|
| `tool_get_training_context` | Get split/balance/symmetry context |
| `tool_get_analytics_features` | Fetch weekly rollups, muscle series, exercise trends |
| `tool_get_user_profile` | Read user fitness profile for goal context |
| `tool_get_recent_workouts` | Read recent workout history |
| `tool_get_user_exercises_by_muscle` | Discover exercises by muscle group |
| `tool_search_exercises` | Search exercise catalog for comparisons |
| `tool_get_exercise_details` | Get technique steps, cues, mistakes |

**Output Control:**
- Default: 3-8 lines
- Hard cap: 12 lines unless user asks for detail or topic is injury/pain
- Never narrate tools or mention tool names
- 0-2 tool calls default, max 3

**Science Rules (Operating Heuristics):**
- Volume: ~10-20 hard sets/week per muscle (many grow at 6-10 with good intensity)
- Proximity to failure: 0-3 RIR for hypertrophy
- Frequency: ~2×/week per muscle default
- Progression: double progression (add reps → then small load)
- Split-aware balance: infer split before calling "imbalanced"

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
| `tool_get_planning_context` | Get complete context in one call |
| `tool_get_template` | Get specific template details |
| `tool_save_workout_as_template` | Save plan as reusable template |
| `tool_create_routine` | Create new routine with templates |
| `tool_manage_routine` | Add/remove/reorder templates in routine |
| `tool_search_exercises` | Search exercise catalog |
| `tool_propose_workout` | Publish single workout draft to canvas |
| `tool_propose_routine` | Publish complete routine draft to canvas |

### CopilotAgent (`copilot_agent.py`)

The Copilot manages live workout sessions. It is the ONLY agent that can write to activeWorkout state, providing the critical permission boundary for execution-time safety.

**Permission Boundary:**
- ✅ Can read templates and planning context
- ✅ Can write to activeWorkout state (EXCLUSIVE)
- ❌ Cannot create workout or routine drafts
- ❌ Cannot write analysis artifacts

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
| `ANALYZE_PROGRESS` | Coach | Progress review, data analysis, trends (Coach has analytics tools) |
| `PLAN_WORKOUT` | Planner | Create single workout |
| `PLAN_ROUTINE` | Planner | Create multi-day routine |
| `EDIT_PLAN` | Planner | Modify existing workout/routine |
| `EXECUTE_WORKOUT` | Copilot | Live session, adjustments |
| `NEXT_WORKOUT` | Copilot | Start next workout from routine |

## Mode Transitions

The system supports natural progression between modes:

```
┌─────────┐     "analyze my data"      ┌─────────┐
│  Coach  │ ─────────────────────────> │  Coach  │  (data-informed response)
└─────────┘                            └─────────┘
     │                                       │
     │ "create a routine"                    │ "apply this to my plan"
     ▼                                       ▼
┌─────────┐    "start workout"         ┌──────────┐
│ Copilot │ <───────────────────────── │ Planner  │
└─────────┘                            └──────────┘
```

## Directory Structure

```
adk_agent/canvas_orchestrator/app/
├── __init__.py
├── agent.py                    # Original entry point
├── agent_engine_app.py         # Agent Engine integration
├── agent_multi.py              # Multi-agent entry point
├── unified_agent.py            # DEPRECATED
│
├── agents/
│   ├── __init__.py             # Exports root_agent (orchestrator)
│   ├── shared_voice.py         # SHARED_VOICE constant for all agents
│   ├── orchestrator.py         # Intent classifier + router
│   ├── coach_agent.py          # Education + data-informed advice
│   ├── planner_agent.py        # Workout/routine planning
│   └── copilot_agent.py        # Live execution
│
└── libs/
    └── tools_canvas/
        └── client.py           # Firebase functions client
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `USE_MULTI_AGENT` | `true` | Use orchestrator routing |
| `CANVAS_ORCHESTRATOR_MODEL` | `gemini-2.5-flash` | Model for intent classification |
| `CANVAS_COACH_MODEL` | `gemini-2.5-flash` | Model for Coach agent |
| `CANVAS_PLANNER_MODEL` | `gemini-2.5-flash` | Model for Planner agent |
| `CANVAS_COPILOT_MODEL` | `gemini-2.5-flash` | Model for Copilot agent |

## Shared System Voice

All agents share a common voice defined in `shared_voice.py`:

```python
SHARED_VOICE = """
## SYSTEM VOICE
- Direct, neutral, high-signal. No hype, no fluff.
- No loop statements or redundant summaries.
- Use clear adult language. If you use jargon, define it in one short clause.
- Prioritize truth over agreement. Correct wrong assumptions plainly.
- Never narrate internal tool usage or internal reasoning.
"""
```

## Permission Enforcement

Permission boundaries are enforced at the code level through tool definitions, not prompts:

```python
# coach_agent.py - Coach has analytics tools but NO artifact writes
COACH_TOOLS = [
    tool_get_training_context,
    tool_get_analytics_features,  # ✅ Coach can read analytics
    tool_get_user_profile,
    tool_search_exercises,
    # tool_propose_workout,        # ❌ NOT included - Planner only
]

# planner_agent.py - Planner gets artifact creation tools
PLANNER_TOOLS = [
    tool_get_planning_context,
    tool_search_exercises,
    tool_propose_workout,          # ✅ Planner can write drafts
    tool_propose_routine,          # ✅ Planner can write routines
    # tool_get_analytics_features, # ❌ NOT included - Coach only
]
```

## Key Success Criteria

1. **Coach combines education + data-informed advice** in one unified agent
2. **Planner behaves as a canvas editor** with minimal chat leakage
3. **Copilot is the only writer to active workout state**
4. **Orchestrator routing is visible and debuggable**
5. **Adding capability to an agent does not require changing other agents or loosening tool boundaries**
