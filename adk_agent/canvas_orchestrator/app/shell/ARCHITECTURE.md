# Shell Agent — Module Architecture

The Shell Agent is the single agent architecture that routes all user messages through a 4-lane system: FAST (pattern matching), FUNCTIONAL (structured intents), SLOW (LLM reasoning), and WORKER (async jobs).

## File Inventory

| File | Purpose |
|------|---------|
| `agent.py` | ShellAgent class: ADK agent definition, model config, before_model/before_tool callbacks for context injection |
| `router.py` | Lane router: classifies messages into FAST/FUNCTIONAL/SLOW lanes, dispatches to handlers |
| `context.py` | Per-request context via `ContextVar`. Thread-safe session context (`user_id`, `canvas_id`, `correlation_id`). Required because Vertex AI Agent Engine is concurrent serverless — module globals leak across requests |
| `tools.py` | ADK `FunctionTool` definitions wrapping skill modules. Tool registry (`all_tools`) consumed by `agent.py` |
| `functional_handler.py` | FUNCTIONAL lane: handles structured intent JSON (`SWAP_EXERCISE`, `ADJUST_LOAD`, etc.) |
| `planner.py` | SLOW lane planning logic |
| `critic.py` | Output quality validation |
| `safety_gate.py` | Safety checks for write operations |
| `instruction.py` | Current system instruction for ShellAgent |
| `instruction_v0.1.py` | Archived instruction version |
| `instruction_v0.2.py` | Archived instruction version |
| `__init__.py` | Module exports |

## Routing Flow

```
agent_engine_app.py
    → set_current_context(ctx, message)     # context.py
    → router.route(message)                 # router.py
        ├── FAST lane  → copilot_skills.*   # Pure pattern matching, no LLM
        ├── FUNCTIONAL → functional_handler  # Flash model, structured intent
        └── SLOW lane  → ShellAgent.run()   # Pro model, full tool access
```

## Context Management

`context.py` uses `ContextVar` (not module globals) because Vertex AI Agent Engine processes multiple requests concurrently in the same process. Module-level globals would leak user data between concurrent requests.

```python
# Set at request start (agent_engine_app.py)
set_current_context(ctx, message)

# Retrieved by tools (tools.py)
ctx = get_current_context()  # → SessionContext(user_id, canvas_id, correlation_id)
```

## Security

- `user_id` is never exposed in tool function signatures — prevents LLM hallucination
- `user_id` is always retrieved from `ContextVar` set by the authenticated request handler
- Tool signatures use keyword-only arguments to prevent positional injection

## Cross-References

- Entry point: `app/agent_engine_app.py`
- Skills (shared logic): `app/skills/`
- Instruction: `instruction.py` (system prompt for the LLM)
- Tool implementations: read tools from `skills/coach_skills.py`, write tools from `skills/planner_skills.py`
