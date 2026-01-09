"""
Catalog Shell - Core components for the Catalog Orchestrator.

This package contains:
- context: JobContext and contextvars for job-scoped state
- leasing: Job lease, family lock, and heartbeat management
- instruction: System prompt for the curation agent
- tools: Tool definitions for catalog operations
- planner: Job-type planning templates
- agent: CatalogShellAgent definition
"""

from app.shell.context import (
    JobContext,
    JobMode,
    JobStatus,
    set_current_job_context,
    get_current_job_context,
    clear_current_job_context,
)

from app.shell.leasing import (
    LeaseHeartbeat,
    FamilyLock,
    JobLease,
)

from app.shell.instruction import CATALOG_INSTRUCTION

from app.shell.tools import all_tools

from app.shell.planner import (
    JobPlan,
    generate_job_plan,
    PLANNING_TEMPLATES,
)

from app.shell.agent import (
    root_agent,
    CatalogShellAgent,
    create_catalog_agent,
    execute_job,
)


__all__ = [
    # Context
    "JobContext",
    "JobMode",
    "JobStatus",
    "set_current_job_context",
    "get_current_job_context",
    "clear_current_job_context",
    # Leasing
    "LeaseHeartbeat",
    "FamilyLock",
    "JobLease",
    # Instruction
    "CATALOG_INSTRUCTION",
    # Tools
    "all_tools",
    # Planner
    "JobPlan",
    "generate_job_plan",
    "PLANNING_TEMPLATES",
    # Agent
    "root_agent",
    "CatalogShellAgent",
    "create_catalog_agent",
    "execute_job",
]
