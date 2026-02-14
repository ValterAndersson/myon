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

## Production Environment: Vertex AI Agent Engine

### Runtime Characteristics (CRITICAL FOR AI AGENTS TO UNDERSTAND)

This system deploys to **Google Vertex AI Agent Engine**, a serverless, highly concurrent runtime environment. Understanding the runtime constraints is essential for any AI agent that will modify, extend, or debug this codebase.

**Key Runtime Properties:**

| Property | Implication | Solution Applied |
|----------|-------------|------------------|
| **Serverless** | No persistent process state between cold starts | All state derived from message/database |
| **Highly Concurrent** | Multiple requests may hit the same warm instance simultaneously | Thread-safe ContextVars, not module globals |
| **Async/Await** | ADK uses async generators for streaming | All handlers support async patterns |
| **Auto-scaled** | Instances spawn/die unpredictably | No instance-level caching of user state |

### The Concurrency Bug (CONTEXT FOR WHY WE USE CONTEXTVARS)

**Scenario that broke the old architecture:**

```
Timeline:
  t0: Request A arrives, sets _current_context = {"user_id": "alice"}
  t1: Request B arrives, sets _current_context = {"user_id": "bob"}  
  t2: Request A's tool reads _current_context → Gets BOB's user_id!
  t3: Request A writes data to BOB's account ← DATA LEAK
```

**Why this happens:**
- Python module-level variables (`_current_context = {}`) are shared across all coroutines in a single process.
- In serverless environments, one process handles multiple concurrent requests.
- Without isolation, any request can read/write any other request's state.

**Why ContextVars solve it:**
- `contextvars.ContextVar` provides task-local storage in Python.
- Each async task (request) gets its own copy of the context variable.
- Setting context in Request A does NOT affect Request B, even in the same process.

### File Responsibility Matrix

| File | Responsibility | Concurrency Safety |
|------|----------------|-------------------|
| `shell/context.py` | Define ContextVar storage and accessors | ✅ Uses `ContextVar[SessionContext]` |
| `agent_engine_app.py` | Set context BEFORE any routing | ✅ Calls `set_current_context()` first |
| `shell/tools.py` | Retrieve context from ContextVar | ✅ Calls `get_current_context()` |
| Legacy `coach_agent.py` | ❌ DEPRECATED - Uses module globals | ⛔ DO NOT USE |

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
│  Model: NONE         Model: Flash          Model: Flash   │    Model: Flash     │
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
│   │   ├── agent.py              # ShellAgent (gemini-2.5-flash)
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
| **Model** | gemini-2.5-flash |
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
| **Model** | gemini-2.5-flash |
| **Latency** | N/A (async) |
| **Output** | Database write (InsightCard) |

**Shared Brain Principle:**

The worker imports the **exact same skills** as the Chat Agent:

```python
# workers/post_workout_analyst.py
from app.skills.coach_skills import (
    get_training_context,
    get_training_analysis,
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
| `get_training_analysis` | ❌ Read-only, no gate |
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
    workout_mode: bool = False
    active_workout_id: Optional[str] = None
    today: Optional[str] = None  # YYYY-MM-DD, injected by streamAgentNormalized

    @classmethod
    def from_message(cls, message: str) -> "SessionContext":
        # Parse from context prefix in message
        ...

# Usage
ctx = SessionContext.from_message(message)  # Created fresh per request
result = some_skill(ctx)  # Context passed explicitly
```

---

## ContextVars Implementation Deep-Dive (FOR AI AGENT COMPREHENSION)

This section provides exhaustive detail on how thread-safe context is implemented. AI agents modifying this codebase MUST understand this pattern.

### File: `shell/context.py` - The Context Container

**Purpose:** Define thread-safe, async-safe storage using Python's `contextvars` module.

**Complete Implementation Pattern:**

```python
# shell/context.py - ACTUAL CODE STRUCTURE
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Optional

# =============================================================================
# CONTEXT VARIABLES (Module-level, but SAFE because ContextVar is thread-safe)
# =============================================================================

# Session context for the current request
_session_context_var: ContextVar[Optional["SessionContext"]] = ContextVar(
    "session_context",   # Debug name
    default=None         # Default if not set
)

# User message for the current request (for Safety Gate checks)
_message_context_var: ContextVar[str] = ContextVar(
    "message_context",
    default=""
)


def set_current_context(ctx: "SessionContext", message: str = "") -> None:
    """
    Set the context for the current request.
    
    CRITICAL: This MUST be called at the start of stream_query() in 
    agent_engine_app.py, BEFORE any routing or tool execution.
    
    The ContextVar.set() method returns a Token, but we don't use it here
    because asyncio automatically handles context isolation per-task.
    """
    _session_context_var.set(ctx)
    _message_context_var.set(message)


def get_current_context() -> "SessionContext":
    """
    Get the context for the current request.
    
    Called by tool wrappers (tool_get_training_context, etc.) to retrieve
    user_id and canvas_id without those values being passed as function args.
    
    SECURITY: This ensures the LLM cannot hallucinate a user_id.
    The user_id comes from the authenticated request, not the LLM.
    
    Raises:
        RuntimeError: If called outside an active request context.
                      This indicates a bug in the calling code.
    """
    ctx = _session_context_var.get()
    if ctx is None:
        raise RuntimeError(
            "get_current_context() called outside request context. "
            "Ensure set_current_context() is called in stream_query."
        )
    return ctx


def get_current_message() -> str:
    """
    Get the raw user message for the current request.
    
    Used by Safety Gate to check for confirmation keywords like "confirm",
    "yes", "do it" before allowing write operations.
    """
    return _message_context_var.get()
```

### Why ContextVar and Not Threading.Local?

| Storage Type | Works in Asyncio? | Works Across Threads? | Correct Choice? |
|--------------|-------------------|----------------------|-----------------|
| `threading.local()` | ❌ NO - All coroutines share same thread | ✅ Yes | ❌ Wrong for this use case |
| `contextvars.ContextVar` | ✅ YES - Each task gets own context | ✅ Yes | ✅ Correct |
| Module-level global | ❌ NO - Shared across everything | ❌ NO | ❌ Never use for state |

**Asyncio Runtime Reality:**
- Vertex Agent Engine runs multiple requests as concurrent `asyncio` tasks.
- All tasks run on the SAME thread (single-threaded event loop).
- `threading.local()` would NOT isolate them because they're all on thread 1.
- `ContextVar` is specifically designed for async task isolation.

### The Lifecycle: Where Context Is Set and Used

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  agent_engine_app.py :: stream_query()                                      │
│                                                                             │
│  1. Parse context from message prefix                                       │
│     ctx = SessionContext.from_message(message)                              │
│                                                                             │
│  2. SET CONTEXT IMMEDIATELY (before any routing)                            │
│     set_current_context(ctx, message)  ← SECURITY BOUNDARY                  │
│                                                                             │
│  3. Route to appropriate lane                                               │
│     routing = route_request(message)                                        │
│                                                                             │
│  4. Execute lane logic...                                                   │
│     ...tools call get_current_context() to get user_id                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  shell/tools.py :: tool_get_training_context()                              │
│                                                                             │
│  def tool_get_training_context() -> Dict[str, Any]:                         │
│      # NOTICE: No user_id in function signature!                            │
│      # LLM cannot hallucinate the user_id.                                  │
│                                                                             │
│      ctx = get_current_context()  ← Retrieves from ContextVar               │
│                                                                             │
│      if not ctx.user_id:                                                    │
│          return {"error": "No user_id available in context"}                │
│                                                                             │
│      result = get_training_context(ctx.user_id)  ← Uses verified user_id    │
│      return result.to_dict()                                                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Security Implication: LLM Cannot Hallucinate User IDs

**Old (Dangerous) Pattern:**
```python
# LLM sees: tool_get_training_context(user_id="...")
# LLM could call: tool_get_training_context(user_id="admin123")
# → Accesses admin's data!
```

**New (Safe) Pattern:**
```python
# LLM sees: tool_get_training_context()
# LLM calls: tool_get_training_context()
# Tool internally: ctx = get_current_context()  # From authenticated request
# → Only accesses the requesting user's data
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
| Slow | gemini-2.5-flash | 0.3 | Conversational CoT (with thinking) |
| Functional | gemini-2.5-flash | 0.0 | Deterministic JSON |
| Worker | gemini-2.5-flash | 0.2 | Analytical precision |

Environment variables:
```bash
CANVAS_SHELL_MODEL=gemini-2.5-flash      # Slow Lane
CANVAS_FUNCTIONAL_MODEL=gemini-2.5-flash  # Functional Lane
```

---

## iOS Client Integration: Protocol Multiplexing

### Integration Strategy (CRITICAL FOR iOS DEVELOPERS AND AI AGENTS)

The iOS app (`Povver/`) communicates with the Shell Agent via a **single unified endpoint**: `:streamQuery`. All request types (chat, smart buttons, workout monitoring) are multiplexed over this endpoint.

**Why Multiplexing?**
- Single WebSocket/HTTP2 stream for all interactions
- No separate APIs to maintain
- Consistent authentication and error handling
- Reduces complexity in mobile networking layer

### Protocol Types Over `:streamQuery`

| Payload Type | Detection | Lane | Response Format |
|--------------|-----------|------|-----------------|
| Plain text string | `message` is `str` without JSON structure | Slow or Fast | Streaming text in chat bubbles |
| JSON with `intent` | `message` has `{"intent": "..."}` field | Functional | JSON object (parsed by iOS, not displayed as chat) |
| JSON with `event_type` | `message` has `{"event_type": "..."}` field | Functional (Monitor) | JSON with `action` field or `NULL` |

### Request Flow from iOS

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  iOS Client (Povver/Povver/Services/DirectStreamingService.swift)           │
│                                                                             │
│  CHAT REQUEST:                                                              │
│    streamQuery(message: "Help me with chest exercises")                     │
│    → Router: Plain string → Slow Lane                                       │
│    → Response: Streaming text → Display in chat bubbles                     │
│                                                                             │
│  SMART BUTTON REQUEST:                                                      │
│    streamQuery(message: '{"intent": "SWAP_EXERCISE", "target": "Bench"}')   │
│    → Router: JSON with intent → Functional Lane                             │
│    → Response: {"action": "REPLACE_EXERCISE", "data": {...}}                │
│    → iOS parses JSON, updates local state, shows toast                      │
│                                                                             │
│  WORKOUT MONITOR REQUEST:                                                   │
│    streamQuery(message: '{"event_type": "SET_COMPLETED", "diff": {...}}')   │
│    → Router: JSON with event_type → Monitor (Functional sub-type)           │
│    → Response: {"action": "NULL"} or {"action": "NUDGE", "text": "..."}     │
│    → iOS: NULL = ignore, NUDGE = show Coach Tip toast                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Response Parsing Logic for iOS Client

The iOS client must distinguish between:
1. **Streaming text** (chat responses) → Append to chat history
2. **JSON objects** (functional responses) → Parse and act, don't display as chat

**Detection Heuristic (iOS Side):**

```swift
// Povver/Povver/Services/DirectStreamingService.swift (pseudo-code)

func handleStreamChunk(_ chunk: String) {
    // Check if chunk starts with JSON structure indicators
    let trimmed = chunk.trimmingCharacters(in: .whitespaces)
    
    if trimmed.hasPrefix("{") && trimmed.hasSuffix("}") {
        // Attempt JSON parse
        if let json = try? JSONDecoder().decode(FunctionalResponse.self, from: chunk.data(using: .utf8)!) {
            handleFunctionalResponse(json)  // Update UI, show toast, etc.
            return
        }
    }
    
    // Not JSON → Regular chat text
    appendToChatHistory(chunk)
}

struct FunctionalResponse: Codable {
    let action: String      // "REPLACE_EXERCISE", "NUDGE", "NULL", etc.
    let data: AnyCodable?   // Action-specific data
}
```

### Monitor Lane Response Schema (FOR iOS CONSUMPTION)

When the iOS app sends workout state updates (e.g., set completed), it expects one of these response formats:

**1. No Intervention Needed (Most Common):**
```json
{
    "action": "NULL",
    "data": null
}
```
iOS Action: Ignore completely. No UI change. Silent observer passed.

**2. Coach Intervention (Nudge):**
```json
{
    "action": "NUDGE",
    "data": {
        "message": "Your rest time seems longer than usual. Feeling okay?",
        "severity": "info"  // "info" | "warning" | "alert"
    }
}
```
iOS Action: Show "Coach Tip" toast overlay. Does NOT go into chat history.

**3. Critical Alert:**
```json
{
    "action": "ALERT",
    "data": {
        "message": "Form concern: weight dropped significantly. Consider reducing intensity.",
        "severity": "warning"
    }
}
```
iOS Action: Show prominent alert. May pause workout timer.

### Canvas Cards vs Chat Bubbles (FOR iOS DEVELOPERS)

The iOS app renders two distinct UI elements from agent responses:

| Response Type | Detection | iOS Rendering |
|--------------|-----------|---------------|
| Chat text | Plain string in stream | `ChatBubble` view |
| Canvas Card | JSON with `card_type` | `SessionPlanCard`, `RoutineSummaryCard`, etc. |

**Canvas Card Detection (iOS):**

```swift
// Check for canvas card structure
struct CanvasCard: Codable {
    let card_type: String         // "session_plan", "routine_summary", etc.
    let card_id: String
    let payload: AnyCodable
}

// In stream handler:
if let card = try? JSONDecoder().decode(CanvasCard.self, from: data) {
    renderCanvasCard(card)  // Specialized UI component
} else {
    renderChatBubble(text)  // Standard chat display
}
```

### iOS Files Involved in Agent Integration

| iOS File | Purpose |
|----------|---------|
| `Services/DirectStreamingService.swift` | WebSocket/HTTP2 streaming client |
| `Services/CanvasActions.swift` | Handle canvas card actions (confirm, dismiss) |
| `Services/AgentsApi.swift` | API wrapper for agent invocation |
| `UI/Canvas/Cards/*.swift` | Render specific card types |
| `ViewModels/CanvasViewModel.swift` | State management for canvas items |

---

## Verification Checklist (PRODUCTION READINESS)

### Concurrency Safety (Vertex Agent Engine)

| Check | Expected | Verified |
|-------|----------|----------|
| Are module-level globals (`_current_context = {}`) removed from `tools.py`? | YES | ✅ |
| Does `agent_engine_app.py` call `set_current_context()` BEFORE routing? | YES | ✅ |
| Do tool functions use `get_current_context()` to retrieve user_id? | YES | ✅ |
| Is `user_id` EXCLUDED from tool function signatures (LLM-facing)? | YES | ✅ |
| Does `get_current_context()` raise RuntimeError if called outside request? | YES | ✅ |

### Write Safety (Mutation Prevention)

| Check | Expected | Verified |
|-------|----------|----------|
| Is `tool_manage_routine` excluded from `tools.py`? | YES | ✅ |
| Does `propose_workout` require confirmation before writing? | YES | ✅ |
| Does `propose_routine` require confirmation before writing? | YES | ✅ |
| Are read-only tools (`search_exercises`, progress summaries) ungated? | YES | ✅ |

### Token-Safe Analytics (v2 - 2026-02-14)

| Check | Expected | Verified |
|-------|----------|----------|
| Is `tool_get_training_analysis` available (PRE-COMPUTED, PREFERRED START)? | YES | ✅ |
| Is `tool_get_muscle_group_progress` available (LIVE DRILLDOWN)? | YES | ✅ |
| Is `tool_get_muscle_progress` available? | YES | ✅ |
| Is `tool_get_exercise_progress` available? | YES | ✅ |
| Is `tool_query_training_sets` available (RAW SET DATA)? | YES | ✅ |
| Are dead tools REMOVED (`coaching_context`, `analytics_features`, `recent_workouts`)? | YES | ✅ |
| Are all progress summaries bounded under 15KB? | YES | ✅ |

### iOS Integration (Protocol Multiplexing)

| Check | Expected | Verified |
|-------|----------|----------|
| Does `route_request()` handle JSON string payloads? | YES | ✅ |
| Does Functional Lane return pure JSON (not chat text)? | YES | ✅ |
| Does MONITOR_STATE return `{"action": "NULL"}` when no intervention? | YES | ✅ |
| Does MONITOR_STATE return `{"action": "NUDGE", ...}` for interventions? | YES | ✅ |

### Performance (Latency Targets)

| Check | Expected | Verified |
|-------|----------|----------|
| Does "log set" / "done" bypass the LLM? | YES | ✅ |
| Is Fast Lane latency < 500ms? | YES | ✅ (target) |
| Is Functional Lane latency < 1s? | YES | ✅ (target) |

### Architecture (No Legacy Dependencies)

| Check | Expected | Verified |
|-------|----------|----------|
| Are `coach_agent.py` imports in `shell/agent.py`? | NO | ✅ |
| Does worker use same analytics function as chat agent? | YES | ✅ |
| Is Shell Agent enabled via `USE_SHELL_AGENT=true`? | YES | ✅ |

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
| 2026-01-03 | ContextVars hardening for Vertex Agent Engine |
| 2026-01-03 | **Production Integration Documentation**: Added Vertex AI runtime section, ContextVars deep-dive, iOS protocol multiplexing, Monitor Lane schema, comprehensive verification checklist |
| 2026-01-04 | **Token-Safe Analytics v2**: Removed `tool_get_analytics_features` and `tool_get_recent_workouts` from agent tools. Replaced with bounded, paginated endpoints: `tool_get_muscle_group_progress`, `tool_get_muscle_progress`, `tool_get_exercise_progress`, and `tool_query_training_sets` (drilldown only). All summaries guaranteed under 15KB. |
| 2026-02-14 | **Pre-computed Analysis + Instruction Rewrite**: Consolidated 3 pre-computed tools (`tool_get_recent_insights`, `tool_get_daily_brief`, `tool_get_latest_weekly_review`) + `tool_get_coaching_context` into single `tool_get_training_analysis`. Switched Slow Lane model from `gemini-2.5-flash` to `gemini-2.5-flash` (temp 0.3, thinking enabled). Rewrote system instruction from 190→140 lines: principles over rules, removed schema duplication, added 7 rich examples with Think/Tool/Response chains. Added hallucination guardrails via data-claim principles and no-data examples. Increased streaming timeout to 300s/180s. |

---

## Contact

Branch: `refactor/single-shell-agent`
Source: `adk_agent/canvas_orchestrator/app/shell/`
Documentation: `docs/SHELL_AGENT_ARCHITECTURE.md`
