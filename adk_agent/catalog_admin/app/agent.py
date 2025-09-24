import os

# Force google-genai to use Vertex AI backend like strengthos-v2
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")

# Re-export the orchestrator as root_agent (same pattern as strengthos-v2)
from app.orchestrator import root_agent  # type: ignore
