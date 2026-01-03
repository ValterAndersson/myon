import os
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent_selector")

# Ensure genai uses Vertex backend
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")

# Use multi-agent system
from app.agent_multi import root_agent  # type: ignore
logger.info(f"Using MULTI-AGENT system: {root_agent}")
print(f"Using MULTI-AGENT system: {root_agent}", flush=True)


