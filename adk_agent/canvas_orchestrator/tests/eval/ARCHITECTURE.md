# Canvas Orchestrator Eval Pipeline

Automated evaluation framework for the shell agent. Sends real prompts to the **deployed** agent via `streamAgentNormalized` SSE, collects responses (text, tools, timing), and scores them with an LLM-as-Judge (gemini-2.5-flash) plus deterministic checks.

## How It Works

```
test_cases.py          runner.py                       judge.py
┌──────────┐    ┌─────────────────────┐    ┌────────────────────────┐
│ TestCase  │───>│ send_prompt()       │───>│ Deterministic checks   │
│ - query   │    │   POST to SSE       │    │   line count, ID leak, │
│ - expected│    │   collect events    │    │   tool name leak,      │
│ - brief   │    │   extract tools     │    │   hallucination detect │
│ - gold std│    │                     │    │                        │
└──────────┘    │ run_single_case()   │    │ LLM judge (Flash)      │
                │   retry on 401s     │    │   correctness  40%     │
                │   prepend brief     │    │   safety       30%     │
                │   set workoutId     │    │   quality      20%     │
                └──────┬──────────────┘    │   persona      10%     │
                       │                   └──────────┬─────────────┘
                       v                              │
                 results/*.jsonl                      v
                 results/*_summary.json         JudgeResult (0-100)
```

## File Structure

| File | Purpose |
|------|---------|
| `test_cases.py` | 108 test cases across 9 categories. Defines `TestCase` dataclass, `SAMPLE_WORKOUT_BRIEF`, `LATE_WORKOUT_BRIEF`, and case registry with filtering. |
| `runner.py` | Eval runner. Sends prompts to deployed agent via SSE, collects responses, passes to judge. Supports parallel execution, category/tag/ID filtering. |
| `judge.py` | LLM-as-Judge scorer. Deterministic checks (line count, ID leaks, tool name leaks, hallucination detection) + Gemini Flash scoring across 4 weighted dimensions. |
| `analyze.py` | Post-run analysis. Reads JSONL results, ranks weak dimensions, counts common issues, supports `--compare` mode between two runs. |
| `seed_eval_workouts.js` | Utility script for creating Firestore workout fixtures matching sample briefs. Not used in normal eval flow (see Active Workout section). |
| `results/` | Eval output directory. Per-run JSONL (one JSON object per test case) + summary JSON. |

## Test Case Structure

```python
@dataclass
class TestCase:
    id: str                         # e.g., "workout_017"
    query: str                      # User input sent to agent
    category: str                   # One of 9 categories
    expected_tools: List[str]       # Tool names the agent should call
    expected_behavior: str          # What the agent should do (for judge)
    gold_standard: str              # Ideal response description (for judge)
    workout_brief: Optional[str]    # If set, prepended to query + workoutId sent
    tags: List[str]                 # For tag-based filtering
```

### Categories (108 total)

| Category | Count | What it tests |
|----------|-------|---------------|
| `easy` | 12 | Single-tool, straightforward queries |
| `moderate` | 15 | Date reasoning, multi-step tool selection |
| `complex` | 10 | Multi-tool, ambiguity, boundary cases |
| `edge` | 8 | No data, adversarial, out-of-scope |
| `active_workout` | 25 | Mid-workout coaching with brief injection |
| `science` | 10 | Evidence-based reasoning |
| `periodization` | 8 | Programming structure |
| `analysis` | 10 | Deep data interpretation |
| `routine_building` | 10 | Workout/routine artifact creation |

## Running Evals

```bash
cd adk_agent/canvas_orchestrator

# Full suite (108 cases, sequential)
python3 -u tests/eval/runner.py

# Single category
python3 -u tests/eval/runner.py --filter category=active_workout

# Single case
python3 -u tests/eval/runner.py --id workout_017

# Parallel execution (recommended for full suite)
python3 -u tests/eval/runner.py --parallel 3

# Skip LLM judge (deterministic checks only)
python3 -u tests/eval/runner.py --no-judge

# Analyze latest run
python3 tests/eval/analyze.py

# Compare two runs
python3 tests/eval/analyze.py --compare results/eval_A.jsonl results/eval_B.jsonl
```

## Scoring System

### Deterministic Checks (applied as penalty to overall score, max -30)

| Check | Penalty | Trigger |
|-------|---------|---------|
| Response too long | -10 to -15 | >12 lines standard, >4 lines workout |
| Empty response | -30 | No text returned |
| Tool name leaked | -20 | `tool_*` or `function_call` in response text |
| User ID requested | -40 | Agent asks user for their ID |
| Hallucinated weights | -30 | Specific kg/lb cited without tool data |
| Raw doc ID exposed | -25 | 20+ char alphanumeric strings in response |

### LLM Judge Dimensions (gemini-2.5-flash, temperature=0.1)

| Dimension | Weight | Sub-scores | What it measures |
|-----------|--------|------------|------------------|
| **Correctness** | 40% | tool_selection (50), data_citation (25), completeness (25) | Right tools called, numbers from data, query fully answered |
| **Safety** | 30% | no_hallucinated_numbers (40), no_leaked_ids (30), no_tool_leakage (30) | No invented data, no internal IDs, no tool names |
| **Quality** | 20% | conciseness (50), actionability (50) | 3-8 lines (2 sentences for workout), concrete next step |
| **Persona** | 10% | direct_neutral (50), no_over_coaching (50) | No hype, answers only what's asked |

**Overall score** = weighted sum of dimensions - deterministic penalty (capped at 30)

**Pass threshold**: score >= 75

### Special Scoring Rules

- **Active workout tool failures**: The eval uses a synthetic `workoutId` ("eval-test-workout") that doesn't exist in Firestore. Tools pass the gate check (`workout_mode=True`) but fail at Firebase execution. The judge scores **tool selection** (did it try the right tool?) separately from execution success. Partial credit (15/25 completeness) is given when the correct tool was called but execution failed.

- **Artifact responses**: When the agent calls `tool_propose_routine` or `tool_propose_workout`, the routine/workout is delivered as an interactive card. The text response is intentionally minimal (1-2 lines). The judge does not penalize short text for artifact responses.

## Active Workout Eval Architecture

Active workout cases require special handling because the eval environment lacks real Firestore workout data.

### How it works

1. **Brief injection**: `workout_brief` text (e.g., `SAMPLE_WORKOUT_BRIEF`) is prepended to the user query in the message body. This provides the agent with workout state (exercises, sets, history, IDs).

2. **Workout mode activation**: `workoutId="eval-test-workout"` is sent in the request body. Firebase's `streamAgentNormalized` includes this in the context prefix: `workout_id=eval-test-workout`. The agent's `SessionContext` parses this and sets `workout_mode=True`, allowing workout tool gate checks to pass.

3. **Real brief injection fails silently**: `agent_engine_app.py` tries to call `get_workout_state_formatted()` to inject a real brief from Firestore, but the synthetic workout doesn't exist. The try/except block fails silently, so only the sample brief in the message text provides context.

4. **Tool execution fails at Firebase**: Workout tools (log_set, swap_exercise, complete_workout, etc.) call Firebase Functions which look up the workout in Firestore. Since "eval-test-workout" doesn't exist, these calls return errors. The judge evaluates tool **selection**, not execution.

### Workout briefs

- `SAMPLE_WORKOUT_BRIEF`: Push Day, 2/17 sets done, currently on Bench Press set 3. 6 exercises including incline press, cable fly, lateral raise, tricep extension, face pull.
- `LATE_WORKOUT_BRIEF`: Pull Day, 14/17 sets done, currently on Bicep Curl set 3. Near-completion state for end-of-workout scenarios.

## Output Format

### Per-case JSONL (`results/eval_YYYYMMDD_HHMMSS.jsonl`)

One JSON object per line:
```json
{
  "test_id": "workout_017",
  "query": "same as last set",
  "category": "active_workout",
  "expected_tools": ["tool_log_set"],
  "response_text": "Logged: 8 x 100kg.",
  "tools_used": ["tool_log_set"],
  "tool_details": [{"tool": "tool_log_set", "label": "Logging set"}],
  "errors": [],
  "duration_s": 5.7,
  "session_id": "...",
  "judge": {
    "overall_score": 90.0,
    "dimensions": { ... },
    "deterministic_issues": [],
    "llm_issues": []
  }
}
```

### Summary JSON (`results/eval_YYYYMMDD_HHMMSS_summary.json`)

Aggregated scores: overall avg/min/max/pass_rate, per-category breakdown, per-dimension averages, failing tests with issues, top issues, timing stats.

## Environment

| Variable | Default | Purpose |
|----------|---------|---------|
| `TEST_USER_ID` | `Y4SJuNPOasaltF7TuKm1QCT7JIA3` | Firebase UID for eval requests |
| `MYON_FUNCTIONS_BASE_URL` | `https://us-central1-myon-53d85.cloudfunctions.net` | Firebase Functions endpoint |
| `MYON_API_KEY` | `myon-agent-key-2024` | API key for `X-API-Key` header |
| `TEST_CANVAS_ID` | `eval-suite` | Canvas/conversation ID |

The judge uses `gcloud auth print-access-token` for Vertex AI API calls (gemini-2.5-flash). Ensure `gcloud auth login` has been run.

## Adding New Test Cases

1. Add a `TestCase` to the appropriate `*_CASES` list in `test_cases.py`.
2. If it's a workout case, set `workout_brief=SAMPLE_WORKOUT_BRIEF` or `LATE_WORKOUT_BRIEF`.
3. Define `expected_tools` (what tools should be called), `expected_behavior` (what the agent should do), and `gold_standard` (ideal response characteristics for the judge).
4. Run the specific case: `python3 -u tests/eval/runner.py --id <case_id>`
5. If the agent fails, decide whether to fix the instruction (`instruction.py`) or adjust the test case expectation.
6. Update the header comment in `test_cases.py` with the new total count.

## Iterative Improvement Workflow

The eval is designed for an iterative test-fix-deploy-test cycle:

1. **Run eval** → identify failures
2. **Diagnose** — is it an instruction gap, test case issue, or backend bug?
3. **Fix** — update `instruction.py` (agent behavior), `judge.py` (scoring rules), or `test_cases.py` (expectations)
4. **Deploy** — `make deploy` in `adk_agent/canvas_orchestrator/`
5. **Re-run** — verify fix and check for regressions
6. **Repeat** until target score is met
