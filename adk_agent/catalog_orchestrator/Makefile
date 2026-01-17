# Catalog Orchestrator Makefile
# ================================
# Targets for development, testing, and deployment

.PHONY: help install dev test lint format clean run deploy \
        worker worker-local watchdog-local \
        docker-build docker-push deploy-worker deploy-watchdog \
        trigger-worker trigger-watchdog

# Configuration (override with: make deploy-worker PROJECT_ID=my-project REGION=us-central1)
PROJECT_ID ?= your-project-id
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
	@echo "  make deploy-worker   - Deploy worker job to Cloud Run"
	@echo "  make deploy-watchdog - Deploy watchdog job to Cloud Run"
	@echo "  make trigger-worker  - Trigger worker execution"
	@echo "  make trigger-watchdog - Trigger watchdog execution"
	@echo ""
	@echo "Agent Engine:"
	@echo "  make deploy        - Deploy to Agent Engine"
	@echo "  make deploy-dry    - Dry-run deploy"
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

# Check Python syntax
check:
	python -m py_compile app/__init__.py
	python -m py_compile app/agent_engine_app.py
	python -m py_compile app/shell/__init__.py
	python -m py_compile app/shell/context.py
	python -m py_compile app/shell/leasing.py
	python -m py_compile app/shell/instruction.py
	python -m py_compile app/shell/tools.py
	python -m py_compile app/shell/planner.py
	python -m py_compile app/shell/agent.py
	python -m py_compile app/skills/__init__.py
	python -m py_compile app/skills/catalog_read_skills.py
	python -m py_compile app/skills/catalog_write_skills.py
	@echo "All files compile OK"

# Deploy to Agent Engine
deploy:
	adk deploy app --project=$(PROJECT_ID)

# Dry-run deploy
deploy-dry:
	adk deploy app --project=$(PROJECT_ID) --dry-run

# Clean build artifacts
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache
	rm -rf dist build *.egg-info

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

# Build worker Docker image
docker-build:
	docker build -t catalog-worker:$(IMAGE_TAG) .
	docker tag catalog-worker:$(IMAGE_TAG) gcr.io/$(PROJECT_ID)/catalog-worker:$(IMAGE_TAG)

# Push to Google Container Registry
docker-push: docker-build
	docker push gcr.io/$(PROJECT_ID)/catalog-worker:$(IMAGE_TAG)

# =============================================================================
# CLOUD RUN JOBS
# =============================================================================

# Deploy worker job (requires gcloud auth)
deploy-worker:
	@echo "Deploying catalog-worker to Cloud Run Jobs..."
	@echo "Project: $(PROJECT_ID), Region: $(REGION)"
	sed 's/PROJECT_ID/$(PROJECT_ID)/g' cloud-run-job.yaml | \
		gcloud run jobs replace - --region=$(REGION)

# Deploy watchdog job (uses same image, different command)
deploy-watchdog:
	@echo "Deploying catalog-watchdog to Cloud Run Jobs..."
	@echo "Project: $(PROJECT_ID), Region: $(REGION)"
	sed 's/PROJECT_ID/$(PROJECT_ID)/g' cloud-run-job.yaml | \
		gcloud run jobs replace - --region=$(REGION)

# Trigger worker execution (on-demand)
trigger-worker:
	gcloud run jobs execute catalog-worker --region=$(REGION) --wait

# Trigger watchdog execution
trigger-watchdog:
	gcloud run jobs execute catalog-watchdog --region=$(REGION) --wait

# Deploy both worker and watchdog
deploy-jobs: docker-push deploy-worker deploy-watchdog
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
