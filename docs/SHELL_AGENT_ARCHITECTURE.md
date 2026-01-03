# Shell Agent Architecture

## Overview

The Shell Agent architecture consolidates the previous "Router + Sub-Agents" pattern into a single unified agent with consistent persona. This eliminates the fragmented UX, persona drift, and "dead ends" that occurred when the orchestrator transferred control between CoachAgent and PlannerAgent.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      VERTEX AGENT ENGINE                                    │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │ AgentEngineApp.stream_query()                                        │  │
│  │                                                                       │  │
│  │   message → route_message() → Lane?                                  │  │
│  │                                                                       │  │
│  │   Lane.FAST ──────────────────────────────────────────┐              │  │
│  │        │                                               │              │  │
│  │        ▼                                               │              │  │
│  │   execute_fast_lane()                                  │              │  │
│  │        │                                               │              │  │
│  │        ▼                                               │              │  │
│  │   copilot_skills.log_set() ──→ yield response ────────┘              │  │
│  │                                                                       │  │
│  │   Lane.SLOW ──────────────────────────────────────────┐              │  │
│  │        │                                               │              │  │
│  │        ▼                                               │              │  │
│  │   super().stream_query()                               │              │  │
│  │        │                                               │              │  │
│  │        ▼                                               │              │  │
│  │   ShellAgent (gemini-2.5-pro)                          │              │  │
│  │        │                                               │              │  │
│  │        ▼                                               │              │  │
│  │   [CoT] → [Tool Calls] → [Response] ──────────────────┘              │  │
│  │                                                                       │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Feature Flag

Enable with environment variable:

```bash
USE_SHELL_AGENT=true
```

- `USE_SHELL_AGENT=true` - Unified Shell Agent with Fast Lane bypass
- `USE_SHELL_AGENT=false` - Legacy multi-agent orchestrator (default)

## Processing Lanes

### Fast Lane (No LLM)

Target latency: **<500ms end-to-end**

Fast lane patterns are unambiguous copilot commands that require no reasoning:

| Pattern | Intent | Example |
|---------|--------|---------|
| `done`, `log set`, `finished` | LOG_SET | Mark current set complete |
| `8 @ 100`, `8@100kg` | LOG_SET_SHORTHAND | Log specific reps/weight |
| `next`, `next set` | NEXT_SET | Get next set target |
| `rest`, `ok`, `ready` | REST_ACK | Acknowledge rest period |

Fast lane requests:
1. Are matched by regex patterns in `router.py`
2. Execute skills directly via `copilot_skills.py`
3. Call Firebase functions directly (no LLM involved)
4. Return formatted response immediately

### Slow Lane (LLM Reasoning)

All other requests go to the Shell Agent (gemini-2.5-pro) for:
- Complex reasoning and planning
- Workout/routine artifact creation
- Analytics interpretation and coaching advice
- Multi-turn conversations

## File Structure

```
app/
├── agent_engine_app.py     # Entry point with fast lane bypass
├── agent_multi.py          # Feature flag routing
├── agent.py                # Legacy entry point (imported by agent_multi)
│
├── shell/                  # NEW: Shell Agent module
│   ├── __init__.py         # Module exports
│   ├── agent.py            # ShellAgent definition
│   ├── context.py          # Stateless per-request context
│   ├── instruction.py      # Unified instruction (Coach + Planner)
│   └── router.py           # Fast/Slow lane routing logic
│
├── skills/                 # NEW: Pure function skills
│   ├── __init__.py         # Module exports
│   └── copilot_skills.py   # Fast lane operations (log_set, etc.)
│
└── agents/                 # LEGACY: To be deprecated
    ├── coach_agent.py      # Tools still used by Shell
    ├── planner_agent.py    # Tools still used by Shell
    └── orchestrator.py     # To be removed
```

## State Management

### Problem Solved

The old architecture used global `_context` dictionaries that leaked state between requests:

```python
# OLD (dangerous)
_context = {"canvas_id": None, "user_id": None}  # Global mutable state

def some_tool():
    canvas_id = _context["canvas_id"]  # Race condition!
```

### New Approach

**Per-request context only.** No persistent state across requests.

```python
# NEW (safe)
@dataclass(frozen=True)  # Immutable
class SessionContext:
    canvas_id: str
    user_id: str
    correlation_id: Optional[str]
    
    @classmethod
    def from_message(cls, message: str) -> "SessionContext":
        # Parse from message prefix
        ...
```

The context is:
1. Parsed from the message prefix on each request
2. Passed explicitly to skills
3. Never stored in global state
4. Immutable (frozen dataclass)

For multi-turn flows (e.g., "create routine"), the LLM reads conversation history to understand context. No session state is persisted in the agent.

## Copilot Skills

Skills are pure Python functions that:
- Take explicit parameters (no global state)
- Call Firebase functions directly via HTTP
- Return structured `SkillResult` objects

```python
def log_set(ctx: SessionContext) -> SkillResult:
    """Log current set as completed."""
    result = _call_firebase("logSet", {"action": "complete_current"}, ctx.user_id)
    return SkillResult(success=True, message="Set logged.")
```

## Latency Targets

| Lane | Target | Description |
|------|--------|-------------|
| Fast | <500ms | Regex match → skill execution → response |
| Slow | 2-5s | LLM reasoning with tool calls |

## Migration Path

1. **Phase 1** (Complete): Create Shell Agent structure, feature flag
2. **Phase 2** (In Progress): Extract skills from coach_agent/planner_agent
3. **Phase 3**: Enable fast lane for more patterns
4. **Phase 4**: Deprecate legacy multi-agent architecture

## Enabling the Shell Agent

### For Local Development

```bash
export USE_SHELL_AGENT=true
python interactive_chat.py
```

### For Deployment

```bash
python agent_engine_app.py \
  --project myon-53d85 \
  --set-env-vars USE_SHELL_AGENT=true
```

## Observability

Fast lane requests include metadata in the response:

```json
{
  "_metadata": {
    "fast_lane": true,
    "intent": "LOG_SET",
    "latency_class": "fast"
  }
}
```

Slow lane requests log:
- Detected signals (first person, metric words, etc.)
- Matched patterns for telemetry
- Routing decisions

## Benefits

1. **Consistent Persona**: Single voice across all interactions
2. **No Dead Ends**: Shell can answer any question, not "that's not my domain"
3. **Lower Latency**: Fast lane bypasses LLM entirely for copilot commands
4. **Simpler State**: No global mutable state, no race conditions
5. **Easier Testing**: Skills are pure functions with explicit inputs/outputs
