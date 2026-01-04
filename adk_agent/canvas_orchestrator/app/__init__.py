# =============================================================================
# Canvas Orchestrator App - Shell Agent Architecture
# =============================================================================
#
# This module exports the root_agent from the Shell Agent.
#
# ARCHITECTURE:
# - app/shell/       ← Current 4-Lane Shell Agent system
# - app/skills/      ← Pure logic modules (shared brain)
# - _archived/       ← Legacy multi-agent code (DO NOT IMPORT)
#
# See docs/SHELL_AGENT_ARCHITECTURE.md for details.
# =============================================================================

from app.shell.agent import root_agent

__all__ = ["root_agent"]
