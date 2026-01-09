# Catalog Orchestrator Makefile
# ================================
# Targets for development, testing, and deployment

.PHONY: help install dev test lint format clean run deploy

# Default target
help:
	@echo "Catalog Orchestrator"
	@echo "===================="
	@echo ""
	@echo "Development:"
	@echo "  make install    - Install dependencies"
	@echo "  make dev        - Run local development server"
	@echo "  make chat       - Run interactive chat"
	@echo "  make test       - Run tests"
	@echo "  make lint       - Run linting"
	@echo "  make format     - Format code"
	@echo ""
	@echo "Deployment:"
	@echo "  make deploy     - Deploy to Agent Engine"
	@echo "  make deploy-dry - Dry-run deploy"
	@echo ""
	@echo "Utilities:"
	@echo "  make clean      - Clean build artifacts"
	@echo "  make check      - Check Python syntax"

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
