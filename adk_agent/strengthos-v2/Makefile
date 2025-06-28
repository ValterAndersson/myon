install:
	@command -v uv >/dev/null 2>&1 || { echo "uv is not installed. Installing uv..."; curl -LsSf https://astral.sh/uv/0.6.12/install.sh | sh; source ~/.bashrc; }
	uv sync --dev --extra jupyter --frozen

test:
	uv run pytest tests/unit && uv run pytest tests/integration

playground:
	@echo "==============================================================================="
	@echo "| 🚀 Starting your agent playground...                                        |"
	@echo "|                                                                             |"
	@echo "| 💡 Try asking: What's the weather in San Francisco?                         |"
	@echo "|                                                                             |"
	@echo "| 🔍 IMPORTANT: Select the 'app' folder to interact with your agent.          |"
	@echo "==============================================================================="
	uv run adk web --port 8501

backend:
	# Export dependencies to requirements file using uv export.
	uv export --no-hashes --no-header --no-dev --no-emit-project --no-annotate --frozen > .requirements.txt 2>/dev/null || \
	uv export --no-hashes --no-header --no-dev --no-emit-project --frozen > .requirements.txt && uv run app/agent_engine_app.py

deploy-agent-engine:
	@echo "==============================================================================="
	@echo "| 🚀 Deploying StrengthOS to Agent Engine...                                 |"
	@echo "==============================================================================="
	# Export dependencies
	uv export --no-hashes --no-header --no-dev --no-emit-project --no-annotate --frozen > .requirements.txt 2>/dev/null || \
	uv export --no-hashes --no-header --no-dev --no-emit-project --frozen > .requirements.txt
	# Deploy to Agent Engine
	PROJECT_ID=$$(gcloud config get-value project) && \
	uv run python app/agent_engine_app.py \
		--project $$PROJECT_ID \
		--location us-central1 \
		--agent-name strengthos-v2 \
		--set-env-vars FIREBASE_API_KEY=$${FIREBASE_API_KEY:-myon-agent-key-2024}

update-agent-engine:
	@echo "==============================================================================="
	@echo "| 🔄 Updating StrengthOS Agent Engine deployment...                          |"
	@echo "==============================================================================="
	# Export dependencies
	uv export --no-hashes --no-header --no-dev --no-emit-project --no-annotate --frozen > .requirements.txt 2>/dev/null || \
	uv export --no-hashes --no-header --no-dev --no-emit-project --frozen > .requirements.txt
	# Update existing deployment
	PROJECT_ID=$$(gcloud config get-value project) && \
	uv run python app/agent_engine_app.py \
		--project $$PROJECT_ID \
		--location us-central1 \
		--agent-name strengthos-v2 \
		--set-env-vars FIREBASE_API_KEY=$${FIREBASE_API_KEY:-myon-agent-key-2024}

test-agent-engine:
	@echo "==============================================================================="
	@echo "| 🧪 Testing deployed Agent Engine...                                        |"
	@echo "==============================================================================="
	@if [ -f deployment_metadata.json ]; then \
		AGENT_ID=$$(jq -r '.remote_agent_engine_id' deployment_metadata.json); \
		echo "Testing agent: $$AGENT_ID"; \
		uv run python -c "from vertexai import agent_engines; \
agent = agent_engines.get('$$AGENT_ID'); \
response = agent.stream_query(input='Hello, test the connection'); \
for chunk in response: print(chunk, end='', flush=True)"; \
	else \
		echo "❌ No deployment_metadata.json found. Deploy the agent first."; \
	fi

setup-dev-env:
	PROJECT_ID=$$(gcloud config get-value project) && \
	(cd deployment/terraform/dev && terraform init && terraform apply --var-file vars/env.tfvars --var dev_project_id=$$PROJECT_ID --auto-approve)

lint:
	uv run codespell
	uv run ruff check . --diff
	uv run ruff format . --check --diff
	uv run mypy .
