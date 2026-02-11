# Enrichment Module — Architecture

LLM-powered field generation and normalization for exercises. This is the core "brain" that populates missing data on exercise documents.

## File Inventory

| File | Purpose |
|------|---------|
| `engine.py` | Core enrichment logic. Entry points, normalization pipeline, validation. |
| `exercise_field_guide.py` | **Single source of truth** for all canonical values (categories, muscles, equipment, movement types/splits). Also provides field specs, golden examples, and LLM prompt fragments. |
| `llm_client.py` | Vertex AI abstraction. Flash (default) vs Pro model selection. Supports `response_schema` for native structured output. Mock client for tests. |
| `models.py` | `EnrichmentSpec`, `EnrichmentResult` dataclasses. |
| `validators.py` | Output parsing (JSON extraction from LLM text, markdown code block handling). |

## Data Flow

```
Exercise Doc
    │
    ▼
engine.py: enrich_exercise_holistic()
    │
    ├── Build prompt (field guide + golden examples + exercise data)
    ├── Call LLM (Flash default, Pro if require_reasoning)
    │     └── response_schema = HOLISTIC_ENRICHMENT_SCHEMA
    ├── Parse JSON response
    │
    ▼
normalize_enrichment_output()
    │
    ├── _normalize_category()       → maps "stretching" → "mobility", etc.
    ├── _normalize_movement_type()  → maps "press" → "push", etc.
    ├── _normalize_movement_split() → maps "full body" → "full_body", etc.
    ├── _normalize_muscle_names()   → underscores → spaces, lowercase, dedupe
    ├── _resolve_muscle_aliases()   → "lats" → "latissimus dorsi", etc.
    ├── _normalize_contribution_map() → key normalization + alias resolution, value clamping
    ├── _normalize_stimulus_tags()  → title case, dedupe
    └── _normalize_content_array()  → strips markdown/step/bullet prefixes from content arrays
    │
    ▼
validate_normalized_output()
    │
    ├── category: must be in CATEGORIES
    ├── movement.type: must be in MOVEMENT_TYPES
    ├── movement.split: must be in MOVEMENT_SPLITS
    ├── equipment: warn on non-standard values but keep all (LLM-guided)
    ├── description: must be >= 50 chars (aligned with quality_scanner)
    ├── muscles.contribution: sum re-normalized if not ~1.0
    └── locked fields silently dropped
    │
    ▼
Validated changes dict → returned to caller
```

## Source of Truth: exercise_field_guide.py

All canonical value sets live here. Never hardcode these elsewhere.

| Constant | Used By | Values |
|----------|---------|--------|
| `CATEGORIES` | engine.py, quality_scanner.py | compound, isolation, cardio, mobility, core |
| `MOVEMENT_TYPES` | engine.py, quality_scanner.py | push, pull, hinge, squat, carry, rotation, flexion, extension, abduction, adduction, other |
| `MOVEMENT_SPLITS` | engine.py, quality_scanner.py | upper, lower, full_body, core |
| `PRIMARY_MUSCLES` | engine.py, quality_scanner.py | 20 canonical muscle names (lowercase, spaces not underscores) |
| `MUSCLE_ALIASES` | engine.py (normalization + contribution map) | Short names → canonical (e.g. "lats" → "latissimus dorsi") |
| `EQUIPMENT_TYPES` | engine.py (warn-only), quality_scanner.py | 18 canonical equipment values (lowercase, hyphens). Non-standard values are logged but kept. |

## Key Design Decisions

**Flash-first model selection.** Default is `gemini-2.5-flash` for cost efficiency (~100x cheaper than Pro). Pro is only used when `require_reasoning=True` is explicitly passed.

**Three-stage output pipeline.** LLM output goes through normalize → validate → return. This catches common LLM mistakes (e.g. returning "press" instead of "push" for movement type) without re-prompting.

**Response schema.** `HOLISTIC_ENRICHMENT_SCHEMA` is passed as native Gemini `response_schema` for deterministic JSON structure. This is more reliable than appending schema as text.

**Description threshold = 50 chars.** Aligned with `quality_scanner.py` to prevent enrichment loops. If the scanner flags descriptions < 50 chars, the engine must also reject them — otherwise a 30-char description would pass validation, get saved, then get flagged again.

## Entry Points

| Function | Use Case | Model |
|----------|----------|-------|
| `enrich_exercise_holistic()` | Preferred. Full exercise → LLM decides what to update. | Flash (default) |
| `compute_enrichment()` | Single-field enrichment via `EnrichmentSpec`. Legacy. | Flash |
| `enrich_field_with_guide()` | Single-field using field guide specs. | Flash |

## Cross-References

- Quality scanner (consumer of same canonical values): `app/reviewer/quality_scanner.py`
- Job executor (calls enrichment): `app/jobs/executor.py`
- Apply engine (writes enriched data): `app/apply/engine.py`
- Tests: `tests/test_enrichment_validation.py` (74 tests)
