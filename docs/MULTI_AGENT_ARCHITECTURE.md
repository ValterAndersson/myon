# Multi-Agent Architecture Documentation

> **Document Purpose**: Complete documentation of the two multi-agent systems in MYON: Canvas Orchestrator (user-facing fitness coach) and Catalog Admin (exercise catalog curation). Written for LLM/agentic coding agents.

---

## Table of Contents

1. [Canvas Orchestrator System](#canvas-orchestrator-system)
2. [Catalog Admin System](#catalog-admin-system)
3. [Shared Infrastructure](#shared-infrastructure)
4. [Directory Structure](#directory-structure)

---

## Canvas Orchestrator System

The canvas orchestrator implements a user-facing multi-agent system for fitness coaching, workout planning, and live workout execution. It uses Google ADK (Agent Development Kit) and deploys to Vertex AI Agent Engine.

### Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           ORCHESTRATOR                                    │
│                                                                          │
│   Input: User message + session context                                  │
│   Output: RoutingDecision { intent, target_agent, confidence, signals }  │
│                                                                          │
│   Method:                                                                │
│   1. Apply deterministic regex rules first (~80% coverage)               │
│   2. Apply metric-words gate for first-person + metrics patterns         │
│   3. Fall back to LLM classifier if ambiguous                            │
│   4. Apply safety re-route if target agent lacks tools for request       │
│   5. Track session mode (coach | plan | execute)                         │
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
│ STATUS:         │ │ STATUS:         │ │ STATUS:         │
│ FULLY           │ │ FULLY           │ │ Stub only       │
│ IMPLEMENTED     │ │ IMPLEMENTED     │ │ (echo routing)  │
└─────────────────┘ └─────────────────┘ └─────────────────┘
```

### Agent Implementation Status

| Agent | Status | Tools | Description |
|-------|--------|-------|-------------|
| **Orchestrator** | Implemented | `tool_route_to_agent` | Intent classification and routing |
| **Planner** | Implemented | 11 tools | Workout/routine draft creation |
| **Coach** | Implemented | 7 tools | Education, analytics, data-informed advice |
| **Copilot** | Stub | `tool_echo_routing` | Live workout execution |

### Orchestrator (`orchestrator.py`)

The orchestrator classifies user intent and routes to the correct specialist agent. It uses a rules-first approach with regex pattern matching, falling back to an LLM classifier for ambiguous cases.

**Intent Taxonomy:**
```python
class Intent(str, Enum):
    COACH_GENERAL = "COACH_GENERAL"      # Education, explanations
    ANALYZE_PROGRESS = "ANALYZE_PROGRESS" # Progress review, data analysis
    PLAN_WORKOUT = "PLAN_WORKOUT"         # Create single workout
    PLAN_ROUTINE = "PLAN_ROUTINE"         # Create multi-day routine
    EDIT_PLAN = "EDIT_PLAN"               # Modify existing plan
    EXECUTE_WORKOUT = "EXECUTE_WORKOUT"   # Live session
    NEXT_WORKOUT = "NEXT_WORKOUT"         # Start next workout from routine
```

**Routing Decision Schema:**
```python
@dataclass
class RoutingDecision:
    intent: str           # Intent enum value
    target_agent: str     # "coach", "planner", "copilot"
    confidence: str       # "low", "medium", "high"
    mode_transition: str  # Optional: "coach→plan", "plan→execute"
    matched_rule: str     # e.g., "pattern:create_workout", "gate:first_person_plus_metrics"
    signals: List[str]    # ["has_create_verb", "mentions_routine", "first_person_plus_metrics"]
```

**Rule-Based Classification Patterns:**

Priority order: Copilot > Planner > Coach > LLM fallback

| Category | Pattern Examples | Target |
|----------|------------------|--------|
| Copilot (highest) | "I'm at the gym", "next set", "log set", "start my workout" | Copilot |
| Planner | "create routine", "build workout", "make a push day", "add exercise" | Planner |
| Coach (data) | "how's my progress", "am I progressing", "my volume" | Coach |
| Coach (education) | "why", "explain", "how does", "technique" | Coach |

**Metric Words Gate:**
If message contains first-person pronouns (my, I, I've) + metric words (sets, volume, progress, trend), routes to Coach with high confidence.

**Safety Re-Route:**
If target agent lacks tools for the request (e.g., Coach asked to create workout), re-routes to Planner.

**Conversation History:**
Maintains last 4 turns for context-aware LLM routing of ambiguous messages like "okay, do it".

### PlannerAgent (`planner_agent.py`)

The Planner is the fully implemented workhorse agent that creates and edits workout and routine drafts. It implements the "canvas editor" behavior where the card is the output and chat text is only a control surface.

**Implemented Tools:**
| Tool | Purpose | Firebase Endpoint |
|------|---------|-------------------|
| `tool_get_user_profile` | Read user preferences and fitness profile | `getUser` |
| `tool_get_recent_workouts` | Read workout history | `getRecentWorkouts` |
| `tool_get_planning_context` | Complete context in one call | `getPlanningContext` |
| `tool_get_template` | Get specific template details | `getTemplate` |
| `tool_save_workout_as_template` | Save plan as reusable template | `createTemplateFromPlan` |
| `tool_create_routine` | Create new routine with templates | `createRoutine` |
| `tool_manage_routine` | Add/remove/reorder templates | `patchRoutine` |
| `tool_search_exercises` | Search exercise catalog | `searchExercises` |
| `tool_propose_workout` | Publish single workout draft to canvas | `proposeCards` |
| `tool_propose_routine` | Publish complete routine draft to canvas | `proposeCards` |
| `tool_ask_user` | Clarification questions (canvas card) | `proposeCards` |

**Permission Boundary:**
- ✅ Can write `session_plan` cards
- ✅ Can write `routine_summary` cards
- ✅ Can create/update templates
- ✅ Can search exercises
- ❌ Cannot write to activeWorkout state
- ❌ Cannot write analysis artifacts

### CoachAgent (`coach_agent.py`)

The Coach provides evidence-based, data-informed training advice. It combines training principles with the user's actual training data to personalize recommendations.

**Implemented Tools:**
| Tool | Purpose | Firebase Endpoint |
|------|---------|-------------------|
| `tool_get_training_context` | Get routine structure and split | `getPlanningContext` |
| `tool_get_analytics_features` | Fetch weekly rollups, muscle series, e1RM trends | `getAnalyticsFeatures` |
| `tool_get_user_profile` | Read user fitness profile | `getUser` |
| `tool_get_recent_workouts` | Read recent workout history | `getRecentWorkouts` |
| `tool_get_user_exercises_by_muscle` | Find exercises user performs for a muscle | `getRecentWorkouts` |
| `tool_search_exercises` | Search exercise catalog | `searchExercises` |
| `tool_get_exercise_details` | Get technique steps, cues, mistakes | `searchExercises` |

**Permission Boundary:**
- ✅ Can read user profile and history
- ✅ Can read analytics features
- ✅ Can search exercise catalog
- ✅ Can send text responses
- ❌ Cannot create workout or routine drafts
- ❌ Cannot modify active workouts
- ❌ Cannot write canvas artifacts

### CopilotAgent (`copilot_agent.py`)

The Copilot manages live workout sessions. Currently stub-only with planned activeWorkout tools.

**Current Tools (Stub):**
| Tool | Purpose |
|------|---------|
| `tool_echo_routing` | Debug tool - returns routing context |

**Planned Tools:**
- `tool_get_active_workout` - Read current session state
- `tool_start_workout` - Initialize active workout from template
- `tool_log_set` - Record completed set with actual reps/weight/RIR
- `tool_adjust_target` - Modify upcoming set targets
- `tool_swap_exercise` - Replace exercise mid-session
- `tool_complete_workout` - Finalize and save workout

**Permission Boundary (Planned):**
- ✅ Can read templates and planning context
- ✅ Can write to activeWorkout state (EXCLUSIVE)
- ❌ Cannot create workout or routine drafts
- ❌ Cannot write analysis artifacts

### Shared System Voice

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

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `USE_MULTI_AGENT` | `true` | Use orchestrator routing |
| `CANVAS_ORCHESTRATOR_MODEL` | `gemini-2.5-flash` | Model for intent classification |
| `CANVAS_COACH_MODEL` | `gemini-2.5-flash` | Model for Coach agent |
| `CANVAS_PLANNER_MODEL` | `gemini-2.5-flash` | Model for Planner agent |
| `CANVAS_COPILOT_MODEL` | `gemini-2.5-flash` | Model for Copilot agent |

---

## Catalog Admin System

The catalog admin implements a background multi-agent system for exercise catalog curation. It operates autonomously to normalize, enrich, deduplicate, and quality-audit the global exercise catalog.

### Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│                     CATALOG ORCHESTRATOR                                  │
│                                                                          │
│   Input: Catalog state assessment                                        │
│   Output: Batch jobs with tasks per agent type                           │
│                                                                          │
│   Pipeline Phases:                                                       │
│   1. Assess catalog state (unnormalized, unapproved, missing aliases)    │
│   2. Create batch jobs by agent type                                     │
│   3. Execute tasks in parallel with ThreadPoolExecutor                   │
│   4. Generate summary reports                                            │
└──────────────────────────┬───────────────────────────────────────────────┘
                           │
    ┌──────┬──────┬────────┼────────┬──────┬──────┐
    ▼      ▼      ▼        ▼        ▼      ▼      ▼
┌──────┐┌──────┐┌──────┐┌──────┐┌──────┐┌──────┐┌──────┐
│TRIAGE││ENRICH││JANITOR││SCOUT││ANALYST││APPROVE││SPEC. │
│      ││      ││       ││     ││       ││      ││AGENTS│
│Family││Add   ││Dedup  ││Find ││Quality││Gate  ││Bio/  │
│assign││aliases││within││gaps ││audit  ││status││Anat/ │
│      ││      ││family ││     ││       ││      ││Cont/ │
│      ││      ││       ││     ││       ││      ││Prog  │
└──────┘└──────┘└──────┘└──────┘└──────┘└──────┘└──────┘
```

### Agent Types

```python
class AgentType(Enum):
    TRIAGE = "triage"        # Normalizes exercises (family/variant assignment)
    ENRICHMENT = "enrichment" # Adds aliases
    JANITOR = "janitor"      # Deduplicates within families
    SCOUT = "scout"          # Finds gaps from search logs
    ANALYST = "analyst"      # Analyzes exercise quality
    AUDITOR = "auditor"      # Weekly quality audits
    APPROVAL = "approval"    # Approves production-ready exercises
    CREATOR = "creator"      # Creates new exercises from gaps
    BIOMECHANICS = "biomechanics" # Improves movement patterns
    ANATOMY = "anatomy"      # Improves muscle mappings
    CONTENT = "content"      # Improves descriptions and instructions
    PROGRAMMING = "programming" # Improves programming context
```

### Implemented Agents

| Agent | File | Status | Description |
|-------|------|--------|-------------|
| TriageAgent | `triage_agent.py` | Implemented | Assigns `family_slug` and `variant_key` to exercises |
| EnrichmentAgent | `enrichment_agent.py` | Implemented | LLM-powered alias generation |
| ScoutAgent | `scout_agent.py` | Implemented | Finds catalog gaps from search logs |
| AnalystAgent | `analyst_agent.py` | Implemented | Quality analysis with issue severity |
| SpecialistAgent | `specialist_agent.py` | Implemented | Role-based improvements (creator/biomechanics/anatomy/content/programming) |
| ApproverAgent | `approver_agent.py` | Implemented | Gates exercise approval status |
| SchemaValidatorAgent | `schema_validator_agent.py` | Implemented | Pre-flight schema validation |
| BaseLLMAgent | `base_llm_agent.py` | Base class | Common LLM interaction patterns |

### Task and Job System

```python
@dataclass
class Task:
    id: str
    agent_type: AgentType
    payload: Dict[str, Any]
    status: TaskStatus  # PENDING, IN_PROGRESS, COMPLETED, FAILED, RETRY
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    error: Optional[str]
    result: Optional[Dict[str, Any]]
    retry_count: int = 0
    max_retries: int = 3

@dataclass
class BatchJob:
    id: str
    tasks: List[Task]
    created_at: datetime
    completed_at: Optional[datetime]
```

### Pipeline Execution

The orchestrator runs a configurable pipeline:

```python
def run_pipeline(self, pipeline_config: Dict[str, Any] = None):
    # 1. Assess current state
    state = self.assess_catalog_state()
    
    # 2. Phase 1: Triage unnormalized exercises
    if state["exercises"]["unnormalized"] > 0:
        job = self.create_batch_job(AgentType.TRIAGE, unnormalized, batch_size=5)
        self.execute_batch_job(job, parallel=True)
    
    # 3. Phase 2: Enrich exercises without aliases
    if state["exercises"]["total"] > 0:
        job = self.create_batch_job(AgentType.ENRICHMENT, approved_exercises, batch_size=5)
        self.execute_batch_job(job, parallel=True)
    
    # 4. Generate summary report
    self.generate_summary_report()
```

### Firebase Integration

The catalog admin uses a dedicated `FirebaseFunctionsClient` that calls the same Firebase Functions as the canvas orchestrator but with system-level (API key) authentication:

| Function | Purpose |
|----------|---------|
| `getExercises` | List all exercises |
| `searchExercises` | Search by name/alias |
| `upsertExercise` | Create/update exercise |
| `mergeExercises` | Merge duplicate exercises |
| `listFamilies` | Get exercise family list |
| `backfillNormalizeFamily` | Deduplicate within family |
| `upsertAlias` | Add exercise alias |
| `deleteAlias` | Remove exercise alias |

### Robustness Patterns

The catalog admin implements several robustness patterns documented in `catalog_admin_agent_review.md`:

1. **Policy Middleware**: Enforces schemas, checks evidence/confidence thresholds, toggles dry-run/apply
2. **Idempotent Mutations**: Operation hashes from `family_slug`, `variant_key`, payload
3. **Structured Change Journal**: Every mutation emits `{op_type, idempotency_key, target_ids, before, after, evidence, mode, timestamp}`
4. **Per-Family Locking**: Wrap mutating tools with lock acquisition/release guard
5. **Observation-First Mode**: Start in dry-run, compare proposed changes to expectations

### Deployment

The catalog admin supports multiple deployment modes:

- **CLI**: `multi_agent_system/cli.py` for interactive testing
- **API Server**: `multi_agent_system/api_server.py` for HTTP triggers
- **Cloud Run Job**: `multi_agent_system/job_runner/` for scheduled execution
- **Agent Engine**: `app/agent_engine_app.py` for Vertex AI deployment

---

## Shared Infrastructure

### Firebase Functions Client

Both agent systems use HTTP clients to call Firebase Functions:

**Canvas Orchestrator**: `adk_agent/canvas_orchestrator/app/libs/tools_canvas/client.py`
- Uses Bearer token authentication (user context)
- Supports canvas-specific operations

**Catalog Admin**: `adk_agent/catalog_admin/multi_agent_system/utils/firebase_client.py`
- Uses API key authentication (system context)
- Supports exercise catalog operations

### Response Helpers

`adk_agent/canvas_orchestrator/app/libs/tools_common/response_helpers.py` provides consistent tool output formatting with `_display` metadata:

```python
{
  "exercises": [...],
  "_display": {
    "running": "Searching chest exercises",
    "complete": "Found 12 exercises",
    "phase": "searching"
  }
}
```

---

## Directory Structure

```
adk_agent/
├── requirements.txt
├── canvas_orchestrator/           # User-facing multi-agent system
│   ├── agent_engine_requirements.txt
│   ├── interactive_chat.py       # Local testing
│   ├── Makefile                  # Deployment automation
│   ├── app/
│   │   ├── __init__.py
│   │   ├── agent.py              # Entry point
│   │   ├── agent_engine_app.py   # Agent Engine integration
│   │   ├── agent_multi.py        # Multi-agent entry point
│   │   ├── agents/
│   │   │   ├── __init__.py       # Exports root_agent
│   │   │   ├── shared_voice.py   # SHARED_VOICE constant
│   │   │   ├── orchestrator.py   # Intent classifier + router
│   │   │   ├── coach_agent.py    # Education + analytics (implemented)
│   │   │   ├── planner_agent.py  # Workout/routine planning (implemented)
│   │   │   ├── copilot_agent.py  # Live execution (stub)
│   │   │   └── tools/
│   │   │       ├── __init__.py
│   │   │       ├── planner_tools.py  # 11 tools
│   │   │       ├── coach_tools.py    # 7 tools (re-exports from coach_agent)
│   │   │       └── copilot_tools.py  # 1 stub tool
│   │   └── libs/
│   │       ├── llm.py
│   │       ├── tools_canvas/
│   │       │   └── client.py     # Firebase client
│   │       └── tools_common/
│   │           ├── __init__.py
│   │           ├── http.py
│   │           └── response_helpers.py
│   └── scripts/
│       └── inspect_canvas.py
│
└── catalog_admin/                 # Background catalog curation system
    ├── agent_engine_requirements.txt
    ├── cli.py                    # Interactive testing
    ├── interactive_chat.py
    ├── README.md
    ├── app/
    │   ├── __init__.py
    │   ├── agent.py
    │   ├── agent_engine_app.py
    │   ├── orchestrator.py
    │   └── libs/
    │       ├── agent_core/
    │       ├── tools_common/
    │       └── tools_firebase/
    │           └── client.py
    └── multi_agent_system/        # Full multi-agent implementation
        ├── api_server.py
        ├── cli.py
        ├── scheduler.py
        ├── deploy.sh
        ├── Dockerfile
        ├── agents/
        │   ├── analyst_agent.py
        │   ├── approver_agent.py
        │   ├── base_llm_agent.py
        │   ├── enrichment_agent.py
        │   ├── firebase_tools.py
        │   ├── schema_validator_agent.py
        │   ├── scout_agent.py
        │   ├── specialist_agent.py
        │   └── triage_agent.py
        ├── config/
        │   └── production_config.json
        ├── orchestrator/
        │   └── orchestrator.py
        ├── job_runner/
        │   ├── Dockerfile
        │   └── run_job.py
        └── utils/
            └── firebase_client.py
```
