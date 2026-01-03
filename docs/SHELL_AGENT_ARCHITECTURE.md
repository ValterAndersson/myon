# Shell Agent Architecture

## Executive Summary

The Shell Agent consolidates the previous "Router + Sub-Agents" (CoachAgent, PlannerAgent) architecture into a **single unified agent** with consistent persona. This document provides comprehensive implementation details for the current state on branch `refactor/single-shell-agent`.

### Problems Solved

| Problem | Previous Architecture | Shell Agent Solution |
|---------|----------------------|---------------------|
| **Fragmented UX** | Switching between Coach/Planner voices | Single unified persona across all interactions |
| **Persona Drift** | Each agent had different personality | One instruction defines the voice |
| **Dead Ends** | "That's not my domain" responses | Shell handles everything |
| **Global State Leakage** | `_context` dicts persisted across requests | Per-request immutable `SessionContext` |
| **Latency** | All requests went through LLM | Fast Lane bypasses LLM for copilot commands |

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         VERTEX AGENT ENGINE                                     │
│                                                                                 │
│  ┌───────────────────────────────────────────────────────────────────────────┐  │
│  │                      AgentEngineApp.stream_query()                        │  │
│  │                                                                           │  │
│  │   USER MESSAGE                                                            │  │
│  │        │                                                                  │  │
│  │        ▼                                                                  │  │
│  │   ┌─────────────────────────────────────────────────────────────────┐     │  │
│  │   │                       ROUTER                                    │     │  │
│  │   │  • Parse context prefix (canvas_id, user_id, corr_id)          │     │  │
│  │   │  • Match Fast Lane regex patterns                               │     │  │
│  │   │  • Match Slow Lane patterns (for observability)                 │     │  │
│  │   │  • Extract signals (has_first_person, has_metric_word, etc.)    │     │  │
│  │   └─────────────────────────────────────────────────────────────────┘     │  │
│  │        │                                                                  │  │
│  │   ┌────┴────┐                                                             │  │
│  │   │         │                                                             │  │
│  │   ▼         ▼                                                             │  │
│  │  FAST      SLOW                                                           │  │
│  │  LANE      LANE                                                           │  │
│  │   │         │                                                             │  │
│  │   │         ▼                                                             │  │
│  │   │   ┌─────────────────────────────────────────────────────────────┐     │  │
│  │   │   │                    TOOL PLANNER                             │     │  │
│  │   │   │  • Generates internal plan for complex intents              │     │  │
│  │   │   │  • Template-based: ANALYZE_PROGRESS, PLAN_ROUTINE, etc.     │     │  │
│  │   │   │  • Injects plan as system prompt to guide LLM               │     │  │
│  │   │   └─────────────────────────────────────────────────────────────┘     │  │
│  │   │         │                                                             │  │
│  │   │         ▼                                                             │  │
│  │   │   ┌─────────────────────────────────────────────────────────────┐     │  │
│  │   │   │                    SHELL AGENT                              │     │  │
│  │   │   │  • Model: gemini-2.5-pro                                    │     │  │
│  │   │   │  • Unified instruction (Coach + Planner combined)           │     │  │
│  │   │   │  • All tools from both legacy agents                        │     │  │
│  │   │   │  • Native CoT reasoning                                     │     │  │
│  │   │   └─────────────────────────────────────────────────────────────┘     │  │
│  │   │         │                                                             │  │
│  │   │         ▼                                                             │  │
│  │   │   ┌─────────────────────────────────────────────────────────────┐     │  │
│  │   │   │                    SAFETY GATE                              │     │  │
│  │   │   │  • For write operations (propose_workout, propose_routine)  │     │  │
│  │   │   │  • Enforces dry_run unless explicit confirmation            │     │  │
│  │   │   │  • Detects confirmation keywords in messages                │     │  │
│  │   │   └─────────────────────────────────────────────────────────────┘     │  │
│  │   │         │                                                             │  │
│  │   ▼         ▼                                                             │  │
│  │ ┌───────────────────────────────────────────────────────────────────┐     │  │
│  │ │                    RESPONSE STREAM                                │     │  │
│  │ │  • Chunks yielded to client in real-time                          │     │  │
│  │ │  • Text collected for critic pass                                 │     │  │
│  │ └───────────────────────────────────────────────────────────────────┘     │  │
│  │        │                                                                  │  │
│  │        ▼                                                                  │  │
│  │   ┌─────────────────────────────────────────────────────────────────┐     │  │
│  │   │                    CRITIC PASS                                  │     │  │
│  │   │  • Post-response validation (async, non-blocking)               │     │  │
│  │   │  • Safety pattern detection (dangerous advice)                  │     │  │
│  │   │  • Hallucination detection (claims without data)                │     │  │
│  │   │  • Artifact quality checks                                      │     │  │
│  │   │  • Logs warnings, doesn't block (already streamed)              │     │  │
│  │   └─────────────────────────────────────────────────────────────────┘     │  │
│  │                                                                           │  │
│  └───────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## File Structure

```
adk_agent/canvas_orchestrator/app/
├── agent_engine_app.py      # Entry point with full pipeline
├── agent_multi.py           # Feature flag routing (USE_SHELL_AGENT)
├── agent.py                 # Legacy entry point (for backwards compat)
│
├── shell/                   # NEW: Shell Agent module
│   ├── __init__.py          # Module exports
│   ├── context.py           # Per-request SessionContext (immutable)
│   ├── router.py            # Fast/Slow lane routing with regex
│   ├── instruction.py       # Unified Coach + Planner instruction
│   ├── agent.py             # ShellAgent definition (gemini-2.5-pro)
│   ├── planner.py           # Tool planning for Slow Lane
│   ├── safety_gate.py       # Write operation confirmation
│   └── critic.py            # Response validation
│
├── skills/                  # NEW: Pure function skills
│   ├── __init__.py          # Module exports
│   ├── copilot_skills.py    # Fast Lane (log_set, get_next_set)
│   ├── coach_skills.py      # Analytics (from coach_agent.py)
│   └── planner_skills.py    # Artifacts (from planner_agent.py)
│
└── agents/                  # LEGACY: To be deprecated
    ├── coach_agent.py       # Tools still imported by ShellAgent
    ├── planner_agent.py     # Tools still imported by ShellAgent
    └── orchestrator.py      # Legacy router (not used when USE_SHELL_AGENT=true)
```

---

## Component Details

### 1. Router (`shell/router.py`)

The Router is the first stage of the pipeline. It determines whether a message should go to the Fast Lane (bypass LLM) or Slow Lane (use Shell Agent).

#### Fast Lane Patterns

These regex patterns match **unambiguous copilot commands** that require no reasoning:

| Pattern | Intent | Example | Action |
|---------|--------|---------|--------|
| `^(log\|done\|finished\|completed)(\s+set)?$` | LOG_SET | "done", "log set" | Log current set |
| `^(\d+)\s*@\s*(\d+(?:\.\d+)?)\s*(kg\|lbs?)?$` | LOG_SET_SHORTHAND | "8 @ 100", "8@100kg" | Log with explicit reps/weight |
| `^next(\s+set)?$` | NEXT_SET | "next", "next set" | Get next set target |
| `^what.?s\s+next\??$` | NEXT_SET | "what's next?" | Get next set target |
| `^(rest\|resting\|ok\|ready)$` | REST_ACK | "rest", "ok" | Acknowledge rest period |

#### Slow Lane Patterns (for observability)

These patterns help with logging/telemetry but still route to Shell Agent:

| Pattern | Intent | Example |
|---------|--------|---------|
| `\b(create\|build\|make\|design\|plan)\s+...\s+(routine\|program\|workout\|split)` | PLAN_ARTIFACT | "create a PPL routine" |
| `\b(i\s+(want\|need)\|give\s+me)\s+...\s+(routine\|program)` | PLAN_ROUTINE | "I want a new routine" |
| `\bhow.?s\s+my\s+(progress\|chest\|back\|...)` | ANALYZE_PROGRESS | "how's my chest progress?" |
| `\bstart\s+...\s+(workout\|session\|training)` | START_WORKOUT | "start my workout" |

#### Signal Extraction

The router also extracts signals for observability:

```python
signals = [
    "has_first_person",   # "my", "I", "I'm", etc.
    "has_create_verb",    # "create", "build", "make"
    "has_edit_verb",      # "edit", "modify", "change"
    "has_analysis_verb",  # "analyze", "review", "assess"
    "mentions_workout",   # "workout", "session", "training"
    "mentions_routine",   # "routine", "program", "split"
    "mentions_data",      # "progress", "history", "data"
    "has_metric_word",    # "sets", "volume", "1rm", "e1rm"
]
```

### 2. Session Context (`shell/context.py`)

**Key principle: No global state.** The previous architecture used global `_context` dictionaries that leaked state between requests:

```python
# OLD (dangerous)
_context = {"canvas_id": None, "user_id": None}  # Global mutable state

def some_tool():
    canvas_id = _context["canvas_id"]  # Race condition!
```

The new approach uses **per-request immutable context**:

```python
@dataclass(frozen=True)  # Immutable!
class SessionContext:
    canvas_id: str
    user_id: str
    correlation_id: Optional[str] = None
    
    @classmethod
    def from_message(cls, message: str) -> "SessionContext":
        """Parse context from message prefix."""
        # Format: (context: canvas_id=xxx user_id=yyy corr=zzz) actual message
        match = re.search(
            r'\(context:\s*canvas_id=(\S+)\s+user_id=(\S+)\s+corr=(\S+)\)', 
            message
        )
        if match:
            return cls(
                canvas_id=match.group(1),
                user_id=match.group(2),
                correlation_id=match.group(3) if match.group(3) != "none" else None,
            )
        return cls(canvas_id="", user_id="", correlation_id=None)
```

Context is:
1. Parsed from message prefix on each request
2. Passed explicitly to skills
3. Never stored in global state
4. Immutable (frozen dataclass)

### 3. Tool Planner (`shell/planner.py`)

For Slow Lane requests with recognized intents, the Tool Planner generates an internal execution plan **before** the LLM runs. This improves reasoning quality by making tool selection explicit.

#### Intent Templates

```python
PLANNING_TEMPLATES = {
    "ANALYZE_PROGRESS": {
        "data_needed": [
            "Analytics features (8-12 weeks) for volume and intensity trends",
            "Exercise IDs for the relevant muscle group",
            "Per-exercise e1RM slopes to measure progression",
        ],
        "suggested_tools": [
            "tool_get_analytics_features",
            "tool_get_user_exercises_by_muscle",
            "tool_get_analytics_features (with exercise_ids)",
        ],
        "rationale": "Progress analysis requires comparing current metrics to historical data.",
    },
    "PLAN_ROUTINE": {
        "data_needed": [
            "User profile for frequency preference",
            "Planning context for existing templates",
            "Exercise catalog search for each muscle group/day type",
        ],
        "suggested_tools": [
            "tool_get_planning_context",
            "tool_search_exercises (one per day type)",
            "tool_propose_routine (once with all days)",
        ],
        "rationale": "Routine creation is a multi-step process. Build all days first, then propose once.",
    },
    # ... more templates
}
```

#### Plan Injection

The plan is converted to a system prompt and appended to the user message:

```python
def to_system_prompt(self) -> str:
    return f"""
## INTERNAL PLAN (Auto-generated)
Intent detected: {self.intent}
Data needed:
  - {self.data_needed[0]}
  - {self.data_needed[1]}
Rationale: {self.rationale}
Suggested tools: {', '.join(self.suggested_tools)}

Execute the plan above, then synthesize a response.
"""
```

### 4. Shell Agent (`shell/agent.py`)

The ShellAgent is the unified LLM agent that handles all Slow Lane requests.

```python
ShellAgent = Agent(
    name="ShellAgent",
    model=os.getenv("CANVAS_SHELL_MODEL", "gemini-2.5-pro"),
    instruction=UNIFIED_INSTRUCTION,
    tools=all_tools,  # Combined from coach_agent + planner_agent
    before_tool_callback=_before_tool_callback,
    before_model_callback=_before_model_callback,
)
```

#### Tools

The ShellAgent has access to ALL tools from both legacy agents:

**From Coach Agent:**
- `tool_get_training_context`
- `tool_get_analytics_features`
- `tool_get_user_profile`
- `tool_get_recent_workouts`
- `tool_get_user_exercises_by_muscle`
- `tool_search_exercises`
- `tool_get_exercise_details`

**From Planner Agent:**
- `tool_get_planning_context`
- `tool_get_next_workout`
- `tool_get_template`
- `tool_propose_workout`
- `tool_propose_routine`
- `tool_manage_routine`
- `tool_ask_user`
- `tool_send_message`

### 5. Safety Gate (`shell/safety_gate.py`)

The Safety Gate enforces confirmation for write operations. This prevents accidental artifact creation.

#### Write Operations Tracked

```python
class WriteOperation(str, Enum):
    PROPOSE_WORKOUT = "propose_workout"
    PROPOSE_ROUTINE = "propose_routine"
    CREATE_TEMPLATE = "create_template"
    UPDATE_ROUTINE = "update_routine"
```

#### Confirmation Keywords

```python
CONFIRM_KEYWORDS = frozenset([
    "confirm", "yes", "do it", "go ahead", "publish", "save",
    "create it", "make it", "build it", "looks good", "approved",
])
```

#### Flow

1. User asks for artifact: "create a PPL routine"
2. Shell Agent generates routine with `dry_run=True`
3. Safety Gate returns preview: "Ready to publish 'PPL' (3 workouts). Say 'confirm' to publish."
4. User says: "confirm"
5. Safety Gate detects confirmation → `dry_run=False`
6. Artifact is published

### 6. Critic (`shell/critic.py`)

The Critic runs a **post-response validation pass** for complex intents. It checks for:

#### Safety Patterns (ERROR severity)

```python
SAFETY_PATTERNS = [
    # "Work through the pain" → ERROR
    (re.compile(r"\b(work through|push through|ignore)\b.{0,20}\bpain\b", re.I),
     "Advising to ignore pain is dangerous", CriticSeverity.ERROR),
]
```

#### Hallucination Patterns (WARNING severity)

```python
HALLUCINATION_PATTERNS = [
    # "Your e1RM is 120kg" without calling analytics tool
    (re.compile(r"your\s+(e1rm|1rm|max)\s+(is|was|hit)\s+\d+", re.I),
     "Specific e1RM claim - verify data was fetched"),
]
```

#### When Critic Runs

```python
def should_run_critic(routing_intent: Optional[str], response_length: int) -> bool:
    # Intents that require critic
    critic_intents = {
        "ANALYZE_PROGRESS",
        "PLAN_ARTIFACT",
        "PLAN_ROUTINE",
        "EDIT_PLAN",
    }
    
    if routing_intent in critic_intents:
        return True
    
    # Long responses get critic pass
    if response_length > 500:
        return True
    
    return False
```

### 7. Skills

Skills are **pure Python functions** that:
- Take explicit parameters (no global state)
- Return structured `SkillResult` objects
- Can be called directly (Fast Lane) or via LLM tools (Slow Lane)

#### Copilot Skills (`skills/copilot_skills.py`)

Fast Lane operations that call Firebase directly:

```python
def log_set(ctx: SessionContext) -> SkillResult:
    """Log current set as completed."""
    result = _call_firebase("logSet", {"action": "complete_current"}, ctx.user_id)
    return SkillResult(success=True, message="Set logged.")

def log_set_shorthand(ctx: SessionContext, reps: int, weight: float, unit: str) -> SkillResult:
    """Log set with explicit reps/weight."""
    ...

def get_next_set(ctx: SessionContext) -> SkillResult:
    """Get next set target from active workout."""
    ...
```

#### Coach Skills (`skills/coach_skills.py`)

Analytics functions extracted from coach_agent.py:

```python
def get_analytics_features(user_id: str, weeks: int = 8, ...) -> SkillResult:
    """Fetch analytics for progress analysis."""
    # Takes user_id explicitly, no global state
    ...

def get_training_context(user_id: str) -> SkillResult:
    """Get user's routine structure."""
    ...
```

#### Planner Skills (`skills/planner_skills.py`)

Artifact creation with `dry_run` support:

```python
def propose_workout(
    canvas_id: str,
    user_id: str,
    title: str,
    exercises: List[Dict],
    dry_run: bool = False,  # Safety Gate integration
) -> SkillResult:
    """Create and optionally publish workout."""
    
    if dry_run:
        return SkillResult(
            success=True,
            dry_run=True,
            data={
                "status": "preview",
                "message": f"Ready to publish '{title}'",
                "preview": {...},
            }
        )
    
    # Actual publish
    ...
```

---

## Feature Flag

Enable Shell Agent with environment variable:

```bash
# Local development
export USE_SHELL_AGENT=true
python interactive_chat.py

# Deployment
python agent_engine_app.py \
  --project myon-53d85 \
  --set-env-vars USE_SHELL_AGENT=true
```

When `USE_SHELL_AGENT=false` (default), the legacy multi-agent orchestrator is used.

---

## Latency Targets

| Lane | Target | Description |
|------|--------|-------------|
| **Fast** | <500ms | Regex match → skill execution → response (no LLM) |
| **Slow** | 2-5s | Plan → LLM CoT → tools → response → critic |

Fast Lane achieves low latency by:
1. Skipping the LLM entirely
2. Calling Firebase functions directly via HTTP
3. Returning formatted response immediately

---

## Observability

### Fast Lane Metadata

```json
{
  "_metadata": {
    "fast_lane": true,
    "intent": "LOG_SET",
    "latency_class": "fast"
  }
}
```

### Slow Lane Logging

```
INFO  | SLOW LANE: how's my chest progress? (intent=ANALYZE_PROGRESS)
INFO  | PLANNER: Generated plan for ANALYZE_PROGRESS
INFO  | PLANNER: Injected plan for ANALYZE_PROGRESS
INFO  | CRITIC: 0 warnings (passed)
```

### Critic Findings

```
WARNING | CRITIC: Response failed safety check: ['Advising to ignore pain is dangerous']
```

---

## Current Limitations / Known Issues

### 1. Safety Gate Not Wired to Tools

The Safety Gate module exists but is **not yet enforced** in the actual tool functions. Currently:
- `planner_skills.py` supports `dry_run=True`
- But the Shell Agent tools in `shell/agent.py` still use the legacy tool functions from `planner_agent.py`

**TODO:** Update Shell Agent to use skill functions with Safety Gate integration.

### 2. Critic is Non-Blocking

The Critic runs **after** the response is streamed. If it finds an error:
- It logs a warning
- The response has already been sent

**Rationale:** Blocking would add latency and require response buffering. Current approach is observability-first.

**TODO (optional):** Add "response buffering" mode for high-risk intents where blocking is preferred.

### 3. Legacy Agent Dependencies

The ShellAgent still imports tools directly from `coach_agent.py` and `planner_agent.py`. These legacy files:
- Still have global `_context` dicts
- Use the old context parsing

**TODO:** Migrate Shell Agent to use skill functions exclusively, then deprecate legacy agents.

### 4. Plan Injection is Simple String Append

Currently the plan is appended to the user message:

```python
augmented_message = f"{message}\n\n{plan.to_system_prompt()}"
```

This works but isn't ideal. Better approach would be to inject as a system message or use ADK's native planning features.

---

## Next Steps / Potential Changes

### High Priority

1. **Wire Safety Gate to Shell Agent tools** - Ensure `propose_workout` and `propose_routine` calls go through Safety Gate.

2. **Migrate Shell Agent to skill functions** - Replace direct tool imports from legacy agents with calls to `skills/` modules.

3. **Add telemetry** - Track Fast Lane hit rate, Critic findings, etc.

### Medium Priority

4. **Improve plan injection** - Use proper system message instead of string append.

5. **Add response buffering for Critic** - Option to block response until Critic passes for high-risk intents.

6. **Expand Fast Lane patterns** - Add more copilot commands (e.g., "skip", "pause", "finish workout").

### Low Priority

7. **Remove legacy agents** - Once Shell Agent uses skills exclusively, delete `coach_agent.py`, `planner_agent.py`, `orchestrator.py`.

8. **Add A/B testing** - Compare Shell Agent vs legacy architecture performance.

---

## API Reference

### `route_message(message: str) -> RoutingResult`

Route a message to Fast or Slow lane.

```python
routing = route_message("8 @ 100")
# RoutingResult(lane=Lane.FAST, intent="LOG_SET_SHORTHAND", confidence="high")

routing = route_message("create a push pull legs routine")
# RoutingResult(lane=Lane.SLOW, intent="PLAN_ROUTINE", confidence="high")
```

### `execute_fast_lane(routing, message, ctx) -> Dict`

Execute a Fast Lane skill directly.

```python
ctx = SessionContext.from_message(message)
result = execute_fast_lane(routing, message, ctx)
# {"lane": "fast", "intent": "LOG_SET", "result": {"success": True, "message": "Set logged."}}
```

### `generate_plan(routing, message) -> ToolPlan`

Generate a tool execution plan.

```python
plan = generate_plan(routing, message)
# ToolPlan(intent="ANALYZE_PROGRESS", data_needed=[...], suggested_tools=[...])

system_prompt = plan.to_system_prompt()
```

### `check_safety_gate(operation, message, ...) -> SafetyDecision`

Check if write operation should execute.

```python
decision = check_safety_gate(WriteOperation.PROPOSE_ROUTINE, "create a routine")
# SafetyDecision(allow_execute=False, dry_run=True, requires_confirmation=True)

decision = check_safety_gate(WriteOperation.PROPOSE_ROUTINE, "yes, confirm")
# SafetyDecision(allow_execute=True, dry_run=False)
```

### `run_critic(response, ...) -> CriticResult`

Run critic validation on a response.

```python
result = run_critic("You should work through the pain and keep lifting.")
# CriticResult(passed=False, findings=[CriticFinding(severity=ERROR, message="...")])
```

---

## Testing

### Test Fast Lane

```bash
export USE_SHELL_AGENT=true
python interactive_chat.py

> done
Set logged.

> 8 @ 100
Set logged: 8 reps @ 100kg

> next
Next: Bench Press — 8 reps @ 85kg (Set 2/4)
```

### Test Slow Lane with Plan

```bash
> how's my chest progress?

# Logs should show:
# INFO | SLOW LANE: how's my chest progress? (intent=ANALYZE_PROGRESS)
# INFO | PLANNER: Generated plan for ANALYZE_PROGRESS
# INFO | PLANNER: Injected plan for ANALYZE_PROGRESS
```

---

## Changelog

| Date | Change |
|------|--------|
| 2026-01-03 | Initial Shell Agent implementation |
| 2026-01-03 | Added copilot_skills.py for Fast Lane |
| 2026-01-03 | Extracted coach_skills.py and planner_skills.py |
| 2026-01-03 | Added Safety Gate and Critic modules |
| 2026-01-03 | Added Tool Planner module |
| 2026-01-03 | Wired Planner and Critic into stream_query pipeline |

---

## Contact

For questions or issues with the Shell Agent architecture, check:
- This document: `docs/SHELL_AGENT_ARCHITECTURE.md`
- Source code: `adk_agent/canvas_orchestrator/app/shell/`
- Branch: `refactor/single-shell-agent`
