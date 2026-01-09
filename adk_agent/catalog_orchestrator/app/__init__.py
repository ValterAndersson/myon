"""
Catalog Orchestrator - Job-driven catalog curation system.

This package provides:
- shell: Core components (context, leasing, tools, agent)
- skills: Pure skill functions for catalog operations
- libs: HTTP clients and utilities

Entry points:
- agent_engine_app.py: ADK Agent Engine application
- workers/: Job processing workers (Phase 1+)
"""

from app.shell import root_agent

__all__ = ["root_agent"]
