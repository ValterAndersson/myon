"""
ADK Agent Engine Application for Catalog Orchestrator.

This is the entry point for the Google Agent Engine deployment.
It exposes the CatalogShellAgent for the ADK framework.

Usage:
    # Local development
    adk api_server app

    # Deploy to Agent Engine
    adk deploy app --project=PROJECT_ID
"""

from app.shell.agent import root_agent

# Export for ADK discovery
__all__ = ["root_agent"]
