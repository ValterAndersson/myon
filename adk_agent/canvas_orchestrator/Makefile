install:
	python3 -m pip install -r agent_engine_requirements.txt

deploy:
	PROJECT_ID=$$(gcloud config get-value project) && \
	PYTHONPATH=. python3 -m app.agent_engine_app \
		--project $$PROJECT_ID \
		--location us-central1 \
		--agent-name canvas-orchestrator \
		--set-env-vars FIREBASE_API_KEY=$${FIREBASE_API_KEY:-myon-agent-key-2024},MYON_API_KEY=$${MYON_API_KEY:-myon-agent-key-2024},MYON_FUNCTIONS_BASE_URL=$${MYON_FUNCTIONS_BASE_URL:-https://us-central1-myon-53d85.cloudfunctions.net},PIPELINE_USER_ID=$${PIPELINE_USER_ID:-canvas_orchestrator_engine}

bootstrap:
	@USER_ID=$${USER_ID:-canvas_orchestrator_engine}; \
	PURPOSE=$${PURPOSE:-workout}; \
	BASE=$${MYON_FUNCTIONS_BASE_URL:-https://us-central1-myon-53d85.cloudfunctions.net}; \
	KEY=$${FIREBASE_API_KEY:-myon-agent-key-2024}; \
	CANVAS_ID=$$(curl -s -X POST "$$BASE/bootstrapCanvas" -H "X-API-Key: $$KEY" -H "Content-Type: application/json" -d '{"userId":"'"$$USER_ID"'","purpose":"'"$$PURPOSE"'"}' | jq -r '.data.canvasId'); \
	echo "Bootstrapped canvas: $$CANVAS_ID"; \
	export TEST_CANVAS_ID=$$CANVAS_ID; \
	( [ -n "$$CANVAS_ID" ] && echo $$CANVAS_ID > .canvas_id ) || true

chat:
	python3 interactive_chat.py

inspect:
	python3 scripts/inspect_canvas.py --user-id $${USER_ID:-$${PIPELINE_USER_ID:-canvas_orchestrator_engine}} --canvas-id $${CANVAS_ID:-$${TEST_CANVAS_ID:-}} --limit $${LIMIT:-10}


