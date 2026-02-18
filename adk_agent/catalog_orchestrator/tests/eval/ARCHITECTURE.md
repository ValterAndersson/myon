# Enrichment Content Quality Eval

Automated eval pipeline that tests the exercise enrichment system's ability
to produce consistent, style-guide-compliant content across all exercise
types and scenarios.

## Architecture

```
fixtures.py ──> test_cases.py ──> runner.py ──> judge.py
   │                │                 │              │
   │                │                 │              ├─ Deterministic checks
   │                │                 │              └─ LLM judge (4 dimensions)
   │                │                 │
   │                │                 └─ Calls enrich_exercise_holistic()
   │                │
   │                └─ 12 cases: 5 generate + 5 fix + 2 preserve
   │
   └─ Synthetic exercise documents (deterministic, no Firestore)
```

## Files

| File | Purpose |
|------|---------|
| `fixtures.py` | Synthetic exercise documents (bare, inconsistent, good) |
| `test_cases.py` | Test case definitions with gold standards and quality requirements |
| `judge.py` | Two-stage scorer: deterministic checks + LLM judge |
| `runner.py` | Orchestrates eval: enrichment call → judge → results |
| `results/` | JSONL per-case results + summary JSON (gitignored) |

## Test Case Categories

- **generate** (5 cases): Bare exercises with no content — enrichment must generate all fields
- **fix** (5 cases): Exercises with bad formatting, wrong voice, or vague content — enrichment must fix
- **preserve** (2 cases): Well-formatted exercises — enrichment should leave mostly alone

## Scoring Dimensions

| Dimension | Weight | Measures |
|-----------|--------|---------|
| Format Compliance | 20% | No markdown, correct length bounds, proper array counts |
| Style Consistency | 35% | Voice, sentence structure, patterns match the Content Style Guide |
| Content Accuracy | 30% | Factually correct, specific to exercise, useful cues |
| Coherence | 15% | Items feel unified, no contradictions, logical ordering |

## Running

```bash
make eval                         # Full suite (12 cases, ~2 min)
make eval-id ID=gen_001           # Single case
make eval-filter FILTER=category=fix  # By category
make eval-no-judge                # Deterministic only (fast, no LLM cost)
```

## How It Drives Quality

The eval pipeline measures enrichment output quality, but the actual quality
improvement comes from changes to the **prompt guidance** — specifically:

1. `app/reviewer/what_good_looks_like.py` → `CONTENT_STYLE_GUIDE`
2. `app/enrichment/engine.py` → Enrichment prompt instructions and auto-detection

The eval→diagnose→fix loop:
1. Run eval, identify low-scoring dimensions
2. Trace the issue to the prompt guidance (not the test cases)
3. Improve the guidance
4. Re-run eval to verify improvement

This ensures we improve the underlying model reasoning rather than gaming
individual test cases.
