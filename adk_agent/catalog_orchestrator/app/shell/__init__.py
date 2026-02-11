"""
Catalog Shell - ADK Agent Engine components.

This package is ONLY for the ADK Agent Engine runtime (agent_engine_app.py).
Cloud Run workers MUST NOT import from this package.

Components:
- context: Re-exports from app.jobs.context (canonical location)
- leasing: Job lease, family lock, and heartbeat management (Phase 0 stubs)
- instruction: System prompt for the curation agent
- planner: Job-type planning templates for the LLM
- tools: ADK FunctionTool definitions (requires google.adk)
- agent: CatalogShellAgent definition (requires google.adk)

Worker code should import from:
- app.jobs.context for JobContext
- app.jobs.executor for execute_job
- app.jobs.queue for queue operations
"""

# NOTE: Nothing is eagerly imported here.
#
# ADK-dependent modules (tools, agent) require google.adk which is only
# available in the Agent Engine runtime. Importing them at package level
# would crash Cloud Run workers.
#
# Pure-Python modules (context, leasing, instruction, planner) could be
# imported, but are deliberately kept lazy to enforce the boundary:
# Cloud Run code should import from app.jobs, not app.shell.
#
# To use the agent:
#   from app.shell.agent import root_agent, CatalogShellAgent
#
# To use tools:
#   from app.shell.tools import all_tools
