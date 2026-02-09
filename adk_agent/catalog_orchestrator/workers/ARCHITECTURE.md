# Catalog Workers — Module Architecture

Cloud Run Job workers for automated exercise catalog curation. Workers are dispatched by the catalog orchestrator based on job documents in the `catalog_jobs` Firestore collection.

## File Inventory

| File | Purpose |
|------|---------|
| `catalog_worker.py` | Main worker: processes catalog job queue. Handles job types including quality audit, gap analysis, LLM enrichment, and duplicate detection. Uses `gemini-2.5-flash` for LLM-based operations. |

## Job Queue Interaction

```
Firestore: catalog_jobs/{jobId}
    → status: "pending" | "processing" | "completed" | "failed"
    → type: "audit" | "enrich" | "dedup" | "gap_analysis"
    → target: { exercise_id?, family_slug?, batch_size? }

catalog_worker.py polls for pending jobs
    → Updates status to "processing"
    → Executes job logic
    → Updates status to "completed" or "failed"
```

## Cross-References

- Orchestrator entry: `adk_agent/catalog_orchestrator/`
- Exercise endpoints: `firebase_functions/functions/exercises/`
- Makefile targets: `make deploy`, `make dev`, `make test`
