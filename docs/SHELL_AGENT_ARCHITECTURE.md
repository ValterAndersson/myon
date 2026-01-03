# Shell Agent Architecture: 4-Lane "Shared Brain" System

## Executive Summary

The Shell Agent architecture consolidates the previous "Router + Sub-Agents" (CoachAgent, PlannerAgent) into a **4-Lane unified system** with consistent persona and shared intelligence. The core principle: **"Shared Skills, Distinct Runtimes."**

Whether the user is chatting, clicking a button, or sleeping while a background job runs, the system uses the **exact same logic functions** (`app/skills/`), just invoked differently.

### Problems Solved

| Problem | Previous Architecture | Shell Agent Solution |
|---------|----------------------|---------------------|
| **Fragmented UX** | Switching between Coach/Planner voices | Single unified persona across all interactions |
| **Persona Drift** | Each agent had different personality | One instruction defines the voice |
| **Dead Ends** | "That's not my domain" responses | Shell handles everything |
| **Global State Leakage** | `_context` dicts persisted across requests | Per-request immutable `SessionContext` |
| **Latency** | All requests went through LLM | Fast Lane bypasses LLM for copilot commands |
| **Smart Buttons** | No support for structured UI actions | Functional Lane with Flash |
| **Background Analysis** | No offline processing | Worker Lane with shared skills |

---

## Architecture Diagram: The 4-Lane System

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              ENTRY POINT                                        │
│                         agent_engine_app.py                                     │
│                                                                                 │
│   REQUEST (str or JSON)                                                         │
│          │                                                                      │
│          ▼                                                                      │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │                          ROUTER                                         │   │
│   │                     route_request()                                     │   │
│   │  1. Try json.loads(message) for JSON payloads                           │   │
│   │  2. Check for "intent" field → Functional Lane                          │   │
│   │  3. Check regex patterns → Fast Lane or Slow Lane                       │   │
│   └─────────────────────────────────────────────────────────────────────────┘   │
│          │                                                                      │
│   ┌──────┼──────────────────┬─────────────────────────────┐                     │
│   │      │                  │                             │                     │
│   ▼      ▼                  ▼                             │                     │
│                                                           │                     │
│  LANE 1              LANE 2                LANE 3         │    LANE 4           │
│  FAST                SLOW                  FUNCTIONAL     │    WORKER           │
│  ────────            ────────              ─────────────  │    ────────         │
│                                                           │                     │
│  Regex Match →       Shell Agent →         Flash Agent →  │    PubSub →         │
│  copilot_skills      CoT Reasoning         JSON Logic     │    Standalone       │
│                                                           │                     │
│  Model: NONE         Model: Pro            Model: Flash   │    Model: Pro       │
│  Latency: <500ms     Latency: 2-5s         Latency: <1s   │    Latency: N/A     │
│                                                           │                     │
│  Input: Text         Input: Text           Input: JSON    │    Trigger: Event   │
│  Output: Text        Output: Stream        Output: JSON   │    Output: DB Write │
│                                                           │                     │
│  Example:            Example:              Example:       │    Example:         │
│  "done"              "create PPL"          SWAP_EXERCISE  │    workout_complete │
│  "8 @ 100"           "how's my chest?"     MONITOR_STATE  │    → InsightCard    │
│                                                           │                     │
└───────────────────────────────────────────────────────────┴─────────────────────┘
                                    │
                                    ▼
                      ┌─────────────────────────────────┐
                      │       SHARED SKILLS             │
                      │       app/skills/               │
                      │                                 │
                      │  • coach_skills.py (analytics)  │
                      │  • planner_skills.py (artifacts)│
                      │  • copilot_skills.py (logging)  │
                      │  • gated_planner.py (safety)    │
                      └─────────────────────────────────┘
```

---

## File Structure

```
adk_agent/canvas_orchestrator/
├── app/
│   ├── agent_engine_app.py       # Entry point - routes to 4 lanes
│   ├── agent_multi.py            # Feature flag (USE_SHELL_AGENT)
│   │
│   ├── shell/                    # Shell Agent module
│   │   ├── __init__.py
│   │   ├── context.py            # Per-request SessionContext (immutable)
│   │   ├── router.py             # 4-Lane routing with route_request()
│   │   ├── instruction.py        # Unified Coach + Planner voice
│   │   ├── agent.py              # ShellAgent (gemini-2.5-pro)
│   │   ├── tools.py              # Tool definitions from pure skills
│   │   ├── planner.py            # Intent-specific tool planning
│   │   ├── safety_gate.py        # Write operation confirmation
│   │   ├── critic.py             # Response validation
│   │   └── functional_handler.py # Functional Lane (Flash, JSON)
│   │
│   ├── skills/                   # SHARED BRAIN - Pure logic
│   │   ├── __init__.py
│   │   ├── copilot_skills.py     # Lane 1: log_set, get_next_set
│   │   ├── coach_skills.py       # Analytics, user data
│   │   ├── planner_skills.py     # Artifact creation
│   │   └── gated_planner.py      # Safety Gate wrapper
│   │
│   └── agents/                   # LEGACY (deprecated)
│       ├── coach_agent.py
│       ├── planner_agent.py
│       └── orchestrator.py
│
└── workers/                      # Lane 4: Background workers
    └── post_workout_analyst.py   # Post-workout insight generation
```

---

## Lane Details

### Lane 1: Fast Lane (Copilot Commands)

**Purpose:** Immediate execution of known commands with no LLM involved.

| Aspect | Value |
|--------|-------|
| **Input** | Text matching regex patterns |
| **Model** | None (pure Python) |
| **Latency** | < 500ms |
| **Output** | Formatted text response |

**Patterns:**

| Pattern | Intent | Example |
|---------|--------|---------|
| `^(log\|done\|finished)(\s+set)?$` | LOG_SET | "done", "log set" |
| `^(\d+)\s*@\s*(\d+)$` | LOG_SET_SHORTHAND | "8 @ 100" |
| `^next(\s+set)?$` | NEXT_SET | "next" |
| `^(rest\|ok\|ready)$` | REST_ACK | "rest" |

**Code Path:**
```
route_request("done") 
  → RoutingResult(lane=FAST, intent="LOG_SET")
  → execute_fast_lane() 
  → copilot_skills.log_set(ctx)
  → Response: "Set logged ✓"
```

---

### Lane 2: Slow Lane (Conversational AI)

**Purpose:** Complex coaching and planning that requires reasoning.

| Aspect | Value |
|--------|-------|
| **Input** | Text (conversational) |
| **Model** | gemini-2.5-pro |
| **Latency** | 2-5 seconds |
| **Output** | Streaming text |

**Flow:**
```
route_request("create a PPL routine")
  → RoutingResult(lane=SLOW, intent="PLAN_ROUTINE")
  → ShellAgent.run()
    → Tool Planner injects: "INTERNAL PLAN: Use search_exercises, propose_routine"
    → LLM CoT reasoning
    → tool_propose_routine() with dry_run=True (Safety Gate)
    → Critic validates response
  → Stream: "I've designed a 3-day PPL routine..."
```

**Safety Gate Integration:**
```python
# First call returns preview
tool_propose_routine(name="PPL", workouts=[...])  
# → dry_run=True → "Preview: 3 workouts. Say 'confirm' to publish."

# After confirmation
tool_propose_routine(name="PPL", workouts=[...])
# → User said "confirm" → dry_run=False → Published
```

---

### Lane 3: Functional Lane (Smart Buttons)

**Purpose:** Structured JSON logic for UI-initiated actions. Not conversational.

| Aspect | Value |
|--------|-------|
| **Input** | JSON payload with `intent` field |
| **Model** | gemini-2.5-flash (temp=0) |
| **Latency** | < 1 second |
| **Output** | JSON only (no chat text) |

**Supported Intents:**

| Intent | Description | Example Payload |
|--------|-------------|-----------------|
| `SWAP_EXERCISE` | Replace exercise with alternative | `{"intent": "SWAP_EXERCISE", "target": "Barbell Bench", "constraint": "machine"}` |
| `AUTOFILL_SET` | Predict values for set | `{"intent": "AUTOFILL_SET", "exercise_id": "...", "set_index": 2}` |
| `SUGGEST_WEIGHT` | Recommend weight based on history | `{"intent": "SUGGEST_WEIGHT", "exercise_id": "...", "target_reps": 8}` |
| `MONITOR_STATE` | Silent observer for workout | `{"event_type": "SET_COMPLETED", "state_diff": {...}}` |

**Monitor Heuristic Gate:**

Only significant events trigger Flash analysis:
- `SET_COMPLETED`
- `WORKOUT_COMPLETED`
- `EXERCISE_SWAPPED`

Non-significant events (e.g., `TIMER_TICK`, `RIR_UPDATED`) are skipped entirely.

**Code Path:**
```
route_request({"intent": "SWAP_EXERCISE", "target": "Bench Press", "constraint": "machine"})
  → RoutingResult(lane=FUNCTIONAL, intent="SWAP_EXERCISE")
  → execute_functional_lane()
  → FunctionalHandler._handle_swap_exercise()
    → search_exercises(equipment="machine")
    → Flash: "Select best alternative"
  → JSON: {"action": "REPLACE_EXERCISE", "data": {"old": "Bench Press", "new": {...}}}
```

---

### Lane 4: Worker Lane (Background Analyst)

**Purpose:** Offline analysis triggered by events (PubSub). Not user-facing.

| Aspect | Value |
|--------|-------|
| **Trigger** | PubSub event (e.g., `workout_completed`) |
| **Model** | gemini-2.5-pro |
| **Latency** | N/A (async) |
| **Output** | Database write (InsightCard) |

**Shared Brain Principle:**

The worker imports the **exact same skills** as the Chat Agent:

```python
# workers/post_workout_analyst.py
from app.skills.coach_skills import (
    get_analytics_features,  # SAME function used by ShellAgent
    get_training_context,
    get_recent_workouts,
)
```

This ensures consistent analysis across all access patterns.

**Usage:**
```bash
# CLI invocation
python post_workout_analyst.py --user-id USER_ID --workout-id WORKOUT_ID

# Cloud Run Job (via PubSub)
gcloud run jobs create post-workout-analyst \
  --image gcr.io/PROJECT/post-workout-analyst \
  --set-env-vars USER_ID=$USER_ID,WORKOUT_ID=$WORKOUT_ID
```

---

## Critical Security: Safety Gate

All write operations MUST go through the Safety Gate.

**Gated Operations:**

| Operation | Gate |
|-----------|------|
| `propose_workout` | ✅ Requires confirmation |
| `propose_routine` | ✅ Requires confirmation |
| `create_template` | ✅ Requires confirmation |
| `get_analytics_features` | ❌ Read-only, no gate |
| `search_exercises` | ❌ Read-only, no gate |

**Implementation:**

```python
# skills/gated_planner.py
from app.shell.safety_gate import check_safety_gate, WriteOperation

def propose_workout(ctx, message, **kwargs):
    decision = check_safety_gate(WriteOperation.PROPOSE_WORKOUT, message)
    
    # First call: dry_run=True (preview)
    # After "confirm": dry_run=False (execute)
    return _propose_workout(..., dry_run=decision.dry_run)
```

**Confirmation Keywords:**
```python
CONFIRM_KEYWORDS = {"confirm", "yes", "do it", "go ahead", "publish", "save", "approved"}
```

---

## State Management: No Globals

**Old Architecture (Dangerous):**
```python
# Legacy - DO NOT USE
_context = {"canvas_id": None, "user_id": None}  # Module-level mutable!

def some_tool():
    canvas_id = _context["canvas_id"]  # Race condition!
```

**New Architecture (Safe):**
```python
# shell/context.py
@dataclass(frozen=True)  # Immutable!
class SessionContext:
    canvas_id: str
    user_id: str
    correlation_id: Optional[str] = None
    
    @classmethod
    def from_message(cls, message: str) -> "SessionContext":
        # Parse from message prefix
        ...

# Usage
ctx = SessionContext.from_message(message)  # Created fresh per request
result = some_skill(ctx)  # Context passed explicitly
```

---

## Router API

### `route_request(payload: Union[str, Dict]) -> RoutingResult`

Main entry point for 4-Lane routing.

```python
# Text message → Fast or Slow Lane
route_request("done")
# → RoutingResult(lane=FAST, intent="LOG_SET")

route_request("create a PPL routine")
# → RoutingResult(lane=SLOW, intent="PLAN_ROUTINE")

# JSON payload → Functional Lane
route_request({"intent": "SWAP_EXERCISE", "target": "Bench"})
# → RoutingResult(lane=FUNCTIONAL, intent="SWAP_EXERCISE")

# JSON with workout state → Monitor (Functional sub-type)
route_request({"event_type": "SET_COMPLETED", "state_diff": {...}})
# → RoutingResult(lane=FUNCTIONAL, intent="MONITOR_STATE")
```

### String JSON Parsing

Per specification, the router tries `json.loads(message)` first:

```python
# Frontend may serialize JSON as string
message = '{"intent": "SWAP_EXERCISE", "target": "Bench"}'
route_request(message)  # Parses JSON, routes to Functional Lane
```

---

## Model Assignment

| Lane | Model | Temperature | Purpose |
|------|-------|-------------|---------|
| Fast | None | N/A | Pure Python execution |
| Slow | gemini-2.5-pro | Default | Conversational CoT |
| Functional | gemini-2.5-flash | 0.0 | Deterministic JSON |
| Worker | gemini-2.5-pro | 0.2 | Analytical precision |

Environment variables:
```bash
CANVAS_SHELL_MODEL=gemini-2.5-pro       # Slow Lane
CANVAS_FUNCTIONAL_MODEL=gemini-2.5-flash  # Functional Lane
```

---

## Verification Checklist

| Check | Expected | Verified |
|-------|----------|----------|
| Safety: Can `propose_workout` execute without confirmation? | NO | ✅ |
| Latency: Does "log set" bypass the LLM? | YES | ✅ |
| Legacy: Are `coach_agent.py` imports in `shell/agent.py`? | NO | ✅ |
| Intelligence: Does worker use same analytics function as chat? | YES | ✅ |
| JSON: Does Functional Lane output chat text? | NO | ✅ |

---

## Testing

### Test Fast Lane
```bash
export USE_SHELL_AGENT=true
python interactive_chat.py

> done
Set logged ✓

> 8 @ 100
Set logged: 8 reps @ 100kg
```

### Test Functional Lane
```python
# In agent_engine_app.py context
result = await execute_functional_lane(
    routing=RoutingResult(lane=Lane.FUNCTIONAL, intent="SWAP_EXERCISE"),
    payload={"target": "Barbell Bench", "constraint": "machine"},
    ctx=SessionContext(canvas_id="c1", user_id="u1")
)
# → {"action": "REPLACE_EXERCISE", "data": {...}}
```

### Test Worker
```bash
python workers/post_workout_analyst.py \
  --user-id test-user \
  --workout-id test-workout \
  --dry-run
```

---

## Next Steps

### High Priority
1. **Wire Functional Lane to agent_engine_app.py** - Currently defined, needs integration
2. **Add telemetry** - Track lane usage, latency, errors

### Medium Priority
3. **Expand Monitor patterns** - Add form degradation detection
4. **Add response buffering** - Optional blocking for Critic on high-risk intents

### Low Priority
5. **Remove legacy agents** - Delete `coach_agent.py`, `planner_agent.py`
6. **A/B testing** - Compare 4-Lane vs legacy performance

---

## Changelog

| Date | Change |
|------|--------|
| 2026-01-03 | Initial Shell Agent (2-Lane) |
| 2026-01-03 | Phase 1: Security hardening, Safety Gate |
| 2026-01-03 | Phase 2: Functional Lane, route_request() |
| 2026-01-03 | Phase 3: Worker Lane, post_workout_analyst.py |
| 2026-01-03 | Complete 4-Lane architecture documentation |

---

## Contact

Branch: `refactor/single-shell-agent`
Source: `adk_agent/canvas_orchestrator/app/shell/`
Documentation: `docs/SHELL_AGENT_ARCHITECTURE.md`
