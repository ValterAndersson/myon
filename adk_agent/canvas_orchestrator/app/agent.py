import os
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent_selector")

# Ensure genai uses Vertex backend
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")

# Switch to multi-agent root
from app.agent_multi import root_agent  # type: ignore
logger.info(f"root_agent loaded: {root_agent}")
print(f"root_agent loaded: {root_agent}", flush=True)


