# Shell Agent — Module Architecture

The Shell Agent is the single agent architecture that routes all user messages through a 4-lane system: FAST (pattern matching), FUNCTIONAL (structured intents), SLOW (LLM reasoning), and WORKER (async jobs).

## File Inventory

| File | Purpose |
|------|---------|
| `agent.py` | ShellAgent class: ADK agent definition (gemini-2.5-flash, temp 0.3), before_model/before_tool callbacks for context injection |
| `router.py` | Lane router: classifies messages into FAST/FUNCTIONAL/SLOW lanes, dispatches to handlers |
| `context.py` | Per-request context via `ContextVar`. Thread-safe session context (`user_id`, `canvas_id`, `correlation_id`, `workout_mode`, `active_workout_id`, `today`). Required because Vertex AI Agent Engine is concurrent serverless — module globals leak across requests |
| `tools.py` | ADK `FunctionTool` definitions wrapping skill modules. Tool registry (`all_tools`) consumed by `agent.py`. 20 tools: 10 read + 4 canvas write + 6 workout |
| `functional_handler.py` | FUNCTIONAL lane: handles structured intent JSON (`SWAP_EXERCISE`, `ADJUST_LOAD`, etc.) |
| `planner.py` | SLOW lane planning logic |
| `critic.py` | Output quality validation |
| `safety_gate.py` | Safety checks for write operations |
| `instruction.py` | System instruction. Principles-over-rules design: teaches thinking patterns via examples with Think/Tool/Response chains. Includes DATE AWARENESS section (today from context prefix) and ACTIVE WORKOUT MODE section activated by workout_id in context. |
| `__init__.py` | Module exports |

## Routing Flow

```
agent_engine_app.py
    → set_current_context(ctx, message)     # context.py
    → router.route(message)                 # router.py
        ├── FAST lane  → copilot_skills.*   # Pure pattern matching, no LLM
        ├── FUNCTIONAL → functional_handler  # Flash model, structured intent
        └── SLOW lane  → ShellAgent.run()   # Flash model (temp 0.3), full tool access
```

## Workout Mode

When `workout_id` is present in the context prefix, the agent enters workout coaching mode:

1. **Context**: `SessionContext.workout_mode = True`, `active_workout_id` set
2. **Brief injection**: `agent_engine_app.py` front-loads a `[WORKOUT BRIEF]` (~1350 tokens) before the user message in the Slow Lane. Skipped for Fast Lane.
3. **Tool gating**: 6 workout tools (`tool_log_set`, `tool_add_exercise`, `tool_prescribe_set`, `tool_swap_exercise`, `tool_complete_workout`, `tool_get_workout_state`) validate `ctx.workout_mode` and return error if called outside workout mode.
4. **Instruction overlay**: ACTIVE WORKOUT MODE section in `instruction.py` constrains responses to 2 sentences max and provides workout-specific examples (logging, adding exercises, modifying plans, swaps, completion).

### Context prefix format

```
(context: canvas_id=X user_id=Y corr=Z workout_id=W today=YYYY-MM-DD)
```

When `workout_id=none` or absent, workout mode is off. Any other value activates it.

### Workout Brief

Built by `workout_skills.get_workout_state_formatted()`:

```
[WORKOUT BRIEF]
Push Day | Started 14:30 | 8/18 sets | Readiness: moderate

> Bench Press [instance-uuid] ← CURRENT
  ✓ Set 1 [set-uuid]: 100kg × 8 @ RIR 2
  → Set 3 [set-uuid]: 100kg × ? (planned)
  · Set 4 [set-uuid]: planned

History: 97.5kg×8, 100kg×8 | e1RM: 110→115 (↑)

Readiness: moderate — quads building fatigue
```

The LLM uses instance_ids and set_ids from the brief directly in tool calls.

## Instruction Design

The system instruction (`instruction.py`) follows a "principles over rules" approach optimized for Flash models:

- **No schema duplication**: Field-level schemas live only in tool docstrings (`tools.py`). The instruction teaches interpretation and response craft.
- **Examples do the heavy lifting**: Examples showing diverse reasoning paths (broad check, specific exercise, specific day, artifact creation, emotional framing, no-data handling, user-provided data).
- **Data claim gate**: "Every number you state about the user must come from data you fetched this turn." Integrated as a principle, not a negative rule.
- **Response format**: Verdict/Evidence/Action structure for data-backed answers. 3-8 lines target.
- **Workout mode**: 2-sentence max constraint with dedicated examples for logging, weight advice, swaps, and completion.

## Context Management

`context.py` uses `ContextVar` (not module globals) because Vertex AI Agent Engine processes multiple requests concurrently in the same process. Module-level globals would leak user data between concurrent requests.

```python
# Set at request start (agent_engine_app.py)
set_current_context(ctx, message)

# Retrieved by tools (tools.py)
ctx = get_current_context()
# → SessionContext(user_id, canvas_id, correlation_id, workout_mode, active_workout_id, today)
```

## Security

- `user_id` is never exposed in tool function signatures — prevents LLM hallucination
- `user_id` is always retrieved from `ContextVar` set by the authenticated request handler
- Tool signatures use keyword-only arguments to prevent positional injection
- Workout tools validate `ctx.workout_mode` before executing mutations

## Cross-References

- Entry point: `app/agent_engine_app.py`
- Skills (shared logic): `app/skills/`
- Workout skills: `app/skills/workout_skills.py`
- Instruction: `instruction.py` (system prompt for the LLM)
- Tool implementations: read tools from `skills/coach_skills.py`, write tools from `skills/planner_skills.py`, workout tools from `skills/workout_skills.py`
- Tests: `tests/test_shell_agent.py` (wiring), `tests/test_agent_e2e.py` (end-to-end with Gemini)
