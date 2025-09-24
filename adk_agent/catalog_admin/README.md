# Catalog Admin Agent

Agent dedicated to exercise and alias curation. Independent from `strengthos-v2`; uses shared libs in `adk_agent/libs` and calls Firebase Functions tools.

## Capabilities
- Resolve/get exercises
- Ensure or upsert exercises (canonical names, family_slug, variant_key)
- Manage alias registry (upsert/delete/search)
- Inspect families and normalize catalog pages

## Layout
```
adk_agent/catalog_admin/
  ├─ app/
  │  ├─ orchestrator.py            # Agent + tool bindings + LLM orchestration tools
  │  ├─ agent_engine_app.py        # Deploy to Vertex AI Agent Engine
  │  └─ utils/gcs.py               # Minimal GCS helper
  ├─ agent_engine_requirements.txt # Minimal deployment deps
  └─ cli.py                        # Smoke tests (health, list-families, search-aliases)
```

## Prereqs
- Python 3.9–3.12
- gcloud ADC for deployment:
```
gcloud auth application-default login
```
- Env vars for tools:
```
export MYON_FUNCTIONS_BASE_URL="https://us-central1-myon-53d85.cloudfunctions.net"
export FIREBASE_API_KEY="<your-key>"
```

## Deploy
```
python3 adk_agent/catalog_admin/app/agent_engine_app.py \
  --project myon-53d85 \
  --location us-central1 \
  --agent-name catalog-admin \
  --requirements-file adk_agent/catalog_admin/agent_engine_requirements.txt \
  --extra-packages ./adk_agent/catalog_admin/app ./adk_agent/libs ./adk_agent/catalog_admin/multi_agent_system \
  --set-env-vars FIREBASE_API_KEY=${FIREBASE_API_KEY},MYON_FUNCTIONS_BASE_URL=${MYON_FUNCTIONS_BASE_URL}
```

The script writes `deployment_metadata.json` with the Agent Engine resource name.

## Smoke tests
Use the CLI to verify Firebase tools connectivity (no Agent Engine required):
```
PYTHONPATH=adk_agent python3 adk_agent/catalog_admin/cli.py --action health
PYTHONPATH=adk_agent python3 adk_agent/catalog_admin/cli.py --action list-families
PYTHONPATH=adk_agent python3 adk_agent/catalog_admin/cli.py --action search-aliases --q ohp
```

## Notes
- This agent intentionally avoids any imports from `strengthos-v2`.
- Shared clients live in `adk_agent/libs` and are included via `--extra-packages` during deployment.
