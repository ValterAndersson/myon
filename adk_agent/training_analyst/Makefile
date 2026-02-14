# Training Analyst Makefile
# =========================

.PHONY: help install test worker-local watchdog-local scheduler-local \
        docker-build docker-push deploy-worker deploy-watchdog deploy-scheduler \
        trigger-worker trigger-watchdog trigger-scheduler deploy

# Configuration
PROJECT_ID ?= myon-53d85
REGION ?= europe-west1
IMAGE_TAG ?= latest

help:
	@echo "Training Analyst"
	@echo "================"
	@echo ""
	@echo "Development:"
	@echo "  make install         - Install dependencies"
	@echo "  make test            - Run tests"
	@echo ""
	@echo "Local Testing:"
	@echo "  make worker-local    - Run worker locally"
	@echo "  make watchdog-local  - Run watchdog locally"
	@echo "  make scheduler-local - Run scheduler locally"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-build    - Build Docker image"
	@echo "  make docker-push     - Push to GCR"
	@echo ""
	@echo "Cloud Run Jobs:"
	@echo "  make deploy          - Deploy all jobs"
	@echo "  make deploy-worker   - Deploy worker job"
	@echo "  make deploy-watchdog - Deploy watchdog job"
	@echo "  make deploy-scheduler - Deploy scheduler job"
	@echo "  make trigger-worker  - Trigger worker execution"
	@echo "  make trigger-watchdog - Trigger watchdog execution"
	@echo "  make trigger-scheduler - Trigger scheduler execution"

# Install dependencies
install:
	pip install -r worker_requirements.txt

# Run tests
test:
	python -m pytest tests/ -v

# Run worker locally
worker-local:
	python workers/analyst_worker.py

# Run watchdog locally
watchdog-local:
	WATCHDOG_DRY_RUN=true python workers/analyst_worker.py watchdog

# Run scheduler locally
scheduler-local:
	python workers/scheduler.py

# Build Docker image
docker-build:
	docker build -t training-analyst-worker:$(IMAGE_TAG) .
	docker tag training-analyst-worker:$(IMAGE_TAG) gcr.io/$(PROJECT_ID)/training-analyst-worker:$(IMAGE_TAG)

# Push to Google Container Registry
docker-push: docker-build
	docker push gcr.io/$(PROJECT_ID)/training-analyst-worker:$(IMAGE_TAG)

# Deploy worker job
deploy-worker:
	@echo "Deploying training-analyst-worker to Cloud Run Jobs..."
	gcloud run jobs replace cloud-run-worker.yaml --region=$(REGION)

# Deploy watchdog job
deploy-watchdog:
	@echo "Deploying training-analyst-watchdog to Cloud Run Jobs..."
	gcloud run jobs replace cloud-run-watchdog.yaml --region=$(REGION)

# Deploy scheduler job
deploy-scheduler:
	@echo "Deploying training-analyst-scheduler to Cloud Run Jobs..."
	gcloud run jobs replace cloud-run-scheduler.yaml --region=$(REGION)

# Trigger worker execution
trigger-worker:
	gcloud run jobs execute training-analyst-worker --region=$(REGION) --wait

# Trigger watchdog execution
trigger-watchdog:
	gcloud run jobs execute training-analyst-watchdog --region=$(REGION) --wait

# Trigger scheduler execution
trigger-scheduler:
	gcloud run jobs execute training-analyst-scheduler --region=$(REGION) --wait

# Deploy all jobs
deploy: docker-push deploy-worker deploy-watchdog deploy-scheduler
	@echo "All Cloud Run Jobs deployed"
