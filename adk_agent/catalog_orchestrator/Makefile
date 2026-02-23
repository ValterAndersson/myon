# Catalog Orchestrator Makefile
# ================================
# Targets for development, testing, and deployment

.PHONY: help install dev test lint format clean run deploy \
        worker worker-local watchdog-local \
        docker-build docker-push cloud-build deploy-worker deploy-review deploy-cleanup deploy-watchdog \
        deploy-jobs trigger-worker trigger-watchdog \
        eval eval-filter eval-id eval-no-judge

# Configuration (override with: make deploy-worker PROJECT_ID=my-project REGION=us-central1)
PROJECT_ID ?= myon-53d85
REGION ?= europe-west1
IMAGE_TAG ?= latest

# Default target
help:
	@echo "Catalog Orchestrator"
	@echo "===================="
	@echo ""
	@echo "Development:"
	@echo "  make install       - Install dependencies"
	@echo "  make dev           - Run local development server"
	@echo "  make chat          - Run interactive chat"
	@echo "  make test          - Run tests"
	@echo "  make lint          - Run linting"
	@echo "  make format        - Format code"
	@echo ""
	@echo "Local Testing (Emulator - No GCP auth needed):"
	@echo "  make emulator-start       - Start Firestore emulator"
	@echo "  make emulator-seed        - Seed test data"
	@echo "  make worker-emulator      - Run worker against emulator (dry-run)"
	@echo "  make worker-emulator-apply - Run with writes enabled"
	@echo ""
	@echo "Local Worker (Uses Production Firestore via ADC):"
	@echo "  make worker-local  - Run worker locally (dry-run)"
	@echo "  make watchdog-local - Run watchdog locally (dry-run)"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-build  - Build worker Docker image"
	@echo "  make docker-push   - Push to GCR (requires gcloud auth)"
	@echo ""
	@echo "Cloud Run Jobs:"
	@echo "  make deploy          - Build, push, deploy all jobs"
	@echo "  make deploy-worker   - Deploy worker job to Cloud Run"
	@echo "  make deploy-review   - Deploy review job to Cloud Run"
	@echo "  make deploy-cleanup  - Deploy cleanup job to Cloud Run"
	@echo "  make deploy-watchdog - Deploy watchdog job to Cloud Run"
	@echo "  make trigger-worker  - Trigger worker execution"
	@echo "  make trigger-watchdog - Trigger watchdog execution"
	@echo ""
	@echo "Eval (Content Quality):"
	@echo "  make eval          - Run full eval suite (enrichment + LLM judge)"
	@echo "  make eval-filter FILTER=category=fix  - Filter by category or tags"
	@echo "  make eval-id ID=gen_001               - Run single test case"
	@echo "  make eval-no-judge - Deterministic checks only (no LLM judge)"
	@echo ""
	@echo "Utilities:"
	@echo "  make clean         - Clean build artifacts"
	@echo "  make check         - Check Python syntax"

# Install dependencies
install:
	pip install -r agent_engine_requirements.txt

# Run local development API server
dev:
	adk api_server app

# Run interactive chat
chat:
	python interactive_chat.py

# Run tests (Phase 1+)
test:
	python -m pytest tests/ -v

# Lint code
lint:
	python -m flake8 app/ --max-line-length=100

# Format code
format:
	python -m black app/ --line-length=100

# Check Python syntax (core modules + Cloud Run worker path)
check:
	python -m py_compile app/__init__.py
	python -m py_compile app/jobs/__init__.py
	python -m py_compile app/jobs/context.py
	python -m py_compile app/jobs/models.py
	python -m py_compile app/jobs/queue.py
	python -m py_compile app/jobs/executor.py
	python -m py_compile app/jobs/handlers.py
	python -m py_compile app/jobs/watchdog.py
	python -m py_compile app/jobs/run_history.py
	python -m py_compile app/enrichment/engine.py
	python -m py_compile app/enrichment/exercise_field_guide.py
	python -m py_compile app/enrichment/llm_client.py
	python -m py_compile app/reviewer/quality_scanner.py
	python -m py_compile app/reviewer/review_agent.py
	python -m py_compile app/reviewer/scheduled_review.py
	python -m py_compile workers/catalog_worker.py
	python -m py_compile cli.py
	@echo "All files compile OK"

# Deploy all (build, push, deploy all Cloud Run Jobs)
deploy: deploy-jobs

# Clean build artifacts
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache
	rm -rf dist build *.egg-info

# =============================================================================
# EVAL PIPELINE (content quality scoring)
# =============================================================================

# Run full eval suite (enrichment + LLM judge)
eval:
	python3 tests/eval/runner.py

# Filter by category (generate, fix, preserve) or tags
eval-filter:
	@echo "Usage: make eval-filter FILTER=category=fix"
	python3 tests/eval/runner.py --filter $(FILTER)

# Run a single test case by ID
eval-id:
	@echo "Usage: make eval-id ID=gen_001"
	python3 tests/eval/runner.py --id $(ID)

# Run eval with deterministic checks only (no LLM judge, faster)
eval-no-judge:
	python3 tests/eval/runner.py --no-judge

# =============================================================================
# FIREBASE EMULATOR (LOCAL TESTING)
# =============================================================================

# Start Firestore emulator (requires Firebase CLI: npm install -g firebase-tools)
emulator-start:
	@echo "Starting Firestore emulator..."
	@echo "In another terminal, run: make worker-emulator"
	cd ../../firebase_functions && firebase emulators:start --only firestore

# Check if emulator is running
emulator-check:
	@curl -s http://localhost:8080 > /dev/null 2>&1 && echo "✓ Emulator running at localhost:8080" || echo "✗ Emulator not running. Run: make emulator-start"

# Seed test data into emulator
emulator-seed:
	FIRESTORE_EMULATOR_HOST="localhost:8080" python -c "\
from google.cloud import firestore; \
db = firestore.Client(); \
db.collection('exercises').document('test-ex-001').set({ \
    'name': 'Test Bench Press', \
    'name_slug': 'test-bench-press', \
    'equipment': 'barbell', \
    'family_slug': 'test-bench-press', \
    'primary_muscles': ['chest', 'triceps'], \
    'secondary_muscles': ['shoulders'], \
    'created_at': firestore.SERVER_TIMESTAMP \
}); \
print('✓ Seeded test exercise: test-ex-001')"

# =============================================================================
# LOCAL WORKER
# =============================================================================

# Run worker locally against PRODUCTION Firestore (dry-run mode)
worker-local:
	CATALOG_APPLY_ENABLED=false python workers/catalog_worker.py

# Run worker locally against EMULATOR (full read/write)
worker-emulator:
	@make emulator-check
	FIRESTORE_EMULATOR_HOST="localhost:8080" python workers/catalog_worker.py

# Run worker against emulator with apply ENABLED (writes to emulator only)
worker-emulator-apply:
	@make emulator-check
	FIRESTORE_EMULATOR_HOST="localhost:8080" CATALOG_APPLY_ENABLED=true python workers/catalog_worker.py

# Run watchdog locally (dry-run mode)
watchdog-local:
	WATCHDOG_DRY_RUN=true python workers/catalog_worker.py watchdog

# Run watchdog against emulator
watchdog-emulator:
	@make emulator-check
	FIRESTORE_EMULATOR_HOST="localhost:8080" python workers/catalog_worker.py watchdog

# =============================================================================
# DOCKER
# =============================================================================

# Build worker Docker image locally (linux/amd64 for Cloud Run)
# NOTE: On Apple Silicon, this requires Docker buildx or Rosetta emulation.
#       Prefer 'make cloud-build' which builds natively on x86_64.
docker-build:
	docker buildx build --platform linux/amd64 -t catalog-worker:$(IMAGE_TAG) .
	docker tag catalog-worker:$(IMAGE_TAG) gcr.io/$(PROJECT_ID)/catalog-worker:$(IMAGE_TAG)

# Push to Google Container Registry (local build)
docker-push: docker-build
	docker push gcr.io/$(PROJECT_ID)/catalog-worker:$(IMAGE_TAG)

# Build and push via Cloud Build (recommended — builds natively on x86_64)
# Copies shared/ into build context (Docker can't COPY from parent dirs)
cloud-build:
	cp -r ../shared shared/
	gcloud builds submit --tag gcr.io/$(PROJECT_ID)/catalog-worker:$(IMAGE_TAG) --project=$(PROJECT_ID); \
	rm -rf shared/

# =============================================================================
# CLOUD RUN JOBS
# =============================================================================

# Deploy worker job (requires gcloud auth)
deploy-worker:
	@echo "Deploying catalog-worker to Cloud Run Jobs..."
	gcloud run jobs replace cloud-run-worker.yaml --region=$(REGION)

# Deploy review job
deploy-review:
	@echo "Deploying catalog-review to Cloud Run Jobs..."
	gcloud run jobs replace cloud-run-review.yaml --region=$(REGION)

# Deploy cleanup job
deploy-cleanup:
	@echo "Deploying catalog-cleanup to Cloud Run Jobs..."
	gcloud run jobs replace cloud-run-cleanup.yaml --region=$(REGION)

# Deploy watchdog job
deploy-watchdog:
	@echo "Deploying catalog-watchdog to Cloud Run Jobs..."
	gcloud run jobs replace cloud-run-watchdog.yaml --region=$(REGION)

# Trigger worker execution (on-demand)
trigger-worker:
	gcloud run jobs execute catalog-worker --region=$(REGION) --wait

# Trigger watchdog execution
trigger-watchdog:
	gcloud run jobs execute catalog-watchdog --region=$(REGION) --wait

# Deploy all Cloud Run Jobs (builds via Cloud Build for correct x86_64 arch)
deploy-jobs: cloud-build deploy-worker deploy-review deploy-cleanup deploy-watchdog
	@echo "All Cloud Run Jobs deployed"

# =============================================================================
# CLI SHORTCUTS
# =============================================================================

# Create a test job (dry-run)
test-job:
	python cli.py insert-exercise --base-name "Test Exercise" --equipment dumbbell

# List recent jobs
list-jobs:
	python cli.py list-jobs --limit 10

# Check job status
job-status:
	@echo "Usage: make job-status JOB_ID=job-xxx"
	python cli.py job-status $(JOB_ID)
