# Reviewer Module — Architecture

Multi-tier review pipeline that evaluates exercise catalog quality and creates enrichment/fix jobs. Two tiers: deterministic rules (no LLM, free) and LLM-based review (Flash/Pro, paid).

## File Inventory

| File | Purpose |
|------|---------|
| `quality_scanner.py` | **Tier 1: Deterministic checks** (no LLM). 12 rule-based checks per exercise. Returns quality score or `None` (needs LLM). |
| `review_agent.py` | **Tier 2: LLM review** (`CatalogReviewAgent`). Batched LLM calls for complex decisions (KEEP/ENRICH/FIX/ARCHIVE/MERGE). |
| `scheduled_review.py` | Cloud Run Job entry point for LLM review. Fetches exercises, runs batched review, creates jobs. |
| `scheduled_quality_scan.py` | Cloud Run Job entry point for deterministic scan. Runs quality_scanner on all exercises. |
| `review_job_creator.py` | Converts review decisions into `catalog_jobs` documents. Handles idempotency. |
| `family_gap_analyzer.py` | Detects missing equipment variants using affinity maps. |
| `what_good_looks_like.py` | Philosophy strings and guidance injected into LLM prompts. Includes `CONTENT_FORMAT_RULES` for content array formatting. |
| `catalog_reviewer.py` | Legacy rule-based reviewer. Superseded by `quality_scanner.py`. |

## Two-Tier Review Pipeline

```
All Exercises
    │
    ▼
quality_scanner.py: heuristic_quality_check()
    │
    ├── Score 0-100 → PASS (no LLM needed)
    │   12 checks:
    │   1. Name present
    │   2. Category in CATEGORIES
    │   3. Equipment items in EQUIPMENT_TYPES
    │   4. Primary muscles non-empty
    │   5. Equipment non-empty
    │   6. Description >= 50 chars
    │   7. Movement type present + in MOVEMENT_TYPES
    │   8. Movement split present + in MOVEMENT_SPLITS
    │   9. All muscles in PRIMARY_MUSCLES
    │   10. Muscle names lowercase without underscores
    │   11. execution_notes + common_mistakes format (no markdown/step prefixes)
    │   12. muscles.category present
    │
    └── None → needs LLM review
            │
            ▼
        review_agent.py: CatalogReviewAgent.review_batch()
            │
            ├── KEEP     → no action
            ├── ENRICH   → CATALOG_ENRICH_FIELD job
            ├── FIX_IDENTITY → TARGETED_FIX job
            ├── ARCHIVE  → TARGETED_FIX (status=deprecated)
            └── MERGE    → merge job
```

## Key Design Decisions

**Quality scanner is the first gate.** Exercises that pass all 12 deterministic checks never touch the LLM, saving cost. Only exercises that fail a check (return `None`) are sent to the LLM review agent.

**Missing movement data is now flagged.** Checks 7-8 flag exercises with missing `movement.type` or `movement.split` (not just invalid values). An exercise with no movement metadata needs enrichment.

**Content format checks.** Check 11 detects markdown formatting (bold label prefixes, numbered lists, bullet markers) in `execution_notes` and `common_mistakes`. Badly formatted content gets sent to the LLM for re-enrichment with `CONTENT_FORMAT_RULES` guidance.

**Canonical values imported from field guide.** Both `quality_scanner.py` and `review_agent.py` import canonical sets (`CATEGORIES`, `MOVEMENT_TYPES`, `MOVEMENT_SPLITS`, `EQUIPMENT_TYPES`, `PRIMARY_MUSCLES`) from `app/enrichment/exercise_field_guide.py`. This is the single source of truth.

**Batched LLM review with retry.** `CatalogReviewAgent` processes exercises in batches (default: 20) per LLM call for efficiency. Each batch produces decisions with confidence levels (high/medium/low). If a batch returns 0 decisions (LLM parse failure), it retries once. If retry also returns 0, exercise IDs are collected in `BatchReviewResult.retry_failed_ids` and marked with `review_metadata.needs_retry = True` for the next scheduled run.

**FIX_IDENTITY → MERGE conversion.** Before creating a FIX_IDENTITY job that renames an exercise, `scheduled_review.py` queries Firestore for name collisions using `_find_active_exercise_by_name()`. If a collision is found, the decision is converted to a MERGE job targeting the existing exercise. The query filters merged/deprecated exercises in Python (not Firestore) because most exercises lack an explicit `status` field.

## Scheduled Entry Points

| Entry Point | Cloud Run Job | Schedule | What It Does |
|-------------|---------------|----------|--------------|
| `scheduled_review.py` | `catalog-review` | Every 3 hours | LLM reviews up to 1000 exercises, creates fix/enrich jobs |
| `scheduled_quality_scan.py` | (triggered via worker) | On-demand | Deterministic scan, creates jobs for failing exercises |

## Cross-References

- Canonical values: `app/enrichment/exercise_field_guide.py`
- Enrichment engine (executes ENRICH jobs): `app/enrichment/engine.py`
- Job creator: `review_job_creator.py` → `app/jobs/queue.py`
- Cloud Run YAML: `cloud-run-review.yaml`
