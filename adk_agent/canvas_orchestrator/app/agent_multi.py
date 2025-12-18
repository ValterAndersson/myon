"""Re-export the production root agent for the Canvas system.

Set USE_UNIFIED_AGENT=true to use the new simplified single-agent architecture.
Default is the unified agent (recommended for stability).
"""

import os
import logging

logger = logging.getLogger(__name__)

USE_UNIFIED = os.getenv("USE_UNIFIED_AGENT", "true").lower() in ("true", "1", "yes")

if USE_UNIFIED:
    from app.unified_agent import root_agent
    logger.info("Using UNIFIED single-agent architecture")
else:
    from app.multi_agent_orchestrator import root_agent  # type: ignore
    logger.info("Using LEGACY multi-agent transfer architecture")

__all__ = ["root_agent"]
