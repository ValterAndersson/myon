import os

# Ensure genai uses Vertex backend
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")

from app.orchestrator import root_agent  # type: ignore


