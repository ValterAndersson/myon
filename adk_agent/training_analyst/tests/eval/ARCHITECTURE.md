# Training Analyst Eval System

## Purpose

Automated quality testing for the training recommendation pipeline. Tests the full path: analyzer LLM output -> recommendation processing -> final recommendation document.

## Architecture

```
test_cases.py  -- RecommendationTestCase dataclass + 30 cases (3 categories x 10)
fixtures.py    -- Training data builders (progression, stall, overreach, etc.)
runner.py      -- Calls analyzer LLM, simulates JS processing, routes to judge
judge.py       -- Stage 1: deterministic checks + Stage 2: LLM judge (Gemini Flash)
analyze.py     -- Results analysis + A/B run comparison
results/       -- JSONL + summary JSON output (gitignored)
```

## Data Flow

1. `runner.py` loads test case from `test_cases.py`
2. Builds analyzer input from `fixtures.py` training data
3. Calls `PostWorkoutAnalyzer` or `WeeklyReviewAnalyzer` LLM directly (no Firestore)
4. Simulates `process-recommendations.js` logic (Python port in runner)
5. Passes final recommendation doc to `judge.py`
6. Judge runs deterministic checks, then LLM judge (Gemini 2.5 Flash)
7. Results saved to `results/` as JSONL + summary JSON

## Test Categories

| Category | Count | What it tests |
|----------|-------|---------------|
| auto_pilot | 10 | Auto-applied recs (past tense, template context, signals) |
| pending_review | 10 | Pending recs (imperative, accept outcome, evidence) |
| exercise_scoped | 10 | No-routine recs (observation-first, no template jargon) |

## Judge Dimensions

| Dimension | Weight | Measures |
|-----------|--------|----------|
| Clarity | 35% | Summary+rationale understandability |
| Data Grounding | 30% | Specific numbers/signals from input |
| Actionability | 25% | User knows what will happen and where |
| Contextual Fit | 10% | Language matches scenario type |

## CLI

```bash
make eval                           # Full suite
make eval-category CAT=auto_pilot   # Filter by category
make eval-single ID=ap_001          # Single case
make eval-analyze                   # Analyze latest results
make eval-compare B=baseline N=new  # Compare two runs
```

## Key Design Decisions

- **No Firestore**: Runner calls analyzer LLM directly with synthetic data
- **Python port of JS**: Runner includes a port of `process-recommendations.js` summary/rationale logic so the full pipeline is testable without Firebase Functions
- **Two-stage judge**: Deterministic checks catch structural issues (bare templates, missing fields), LLM judge scores nuance (clarity, grounding)
- **Scenario-specific criteria**: Judge prompt includes different quality bars for auto_pilot vs pending_review vs exercise_scoped
