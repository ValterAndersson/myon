"""
Catalog Orchestrator - Job-driven catalog curation system.

This package provides:
- jobs: Job queue, executor, and handlers
- enrichment: LLM-powered exercise enrichment
- reviewer: Quality scanning and scheduled review
- apply: Firestore mutation engine with idempotency
- family: Taxonomy and naming utilities
- libs: HTTP clients and utilities

Entry points:
- workers/catalog_worker.py: Cloud Run Job worker
- app/reviewer/scheduled_review.py: Cloud Run Job reviewer
- app/reviewer/scheduled_quality_scan.py: Cloud Run Job quality scanner

NOTE: The ADK shell agent (app.shell) is NOT imported here.
Cloud Run workers must not depend on google.adk which requires
the Agent Engine runtime. Import app.shell explicitly only in
agent_engine_app.py.
"""
