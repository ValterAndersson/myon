"""
Catalog Shell Agent - Single unified agent for catalog curation.

Model: gemini-2.5-pro

This agent handles catalog curation jobs. It:
1. Receives job context (family_slug, job_type, mode)
2. Fetches relevant data using read tools
3. Generates a structured Change Plan
4. Validates the plan using deterministic validators
5. Applies the plan (if mode=apply and validation passes)

Unlike the Canvas Orchestrator, this agent is job-driven rather than
conversational. It operates on family-scoped units of work.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict

from google.adk import Agent

from app.shell.context import JobContext, set_current_job_context
from app.shell.instruction import CATALOG_INSTRUCTION
from app.shell.planner import generate_job_plan
from app.shell.tools import all_tools

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


# ============================================================================
# AGENT CALLBACKS
# ============================================================================

def _before_tool_callback(tool, args, tool_context):
    """Log tool invocations for debugging."""
    try:
        logger.debug("Before tool: %s, args: %s", tool.name, args)
    except Exception as e:
        logger.debug("before_tool_callback error: %s", e)
    return None


def _before_model_callback(callback_context, llm_request):
    """Log model calls for debugging."""
    try:
        logger.debug("Before model call, contents count: %d", 
                    len(llm_request.contents or []))
    except Exception as e:
        logger.debug("before_model_callback error: %s", e)
    return None


# ============================================================================
# CATALOG SHELL AGENT DEFINITION
# ============================================================================

CatalogShellAgent = Agent(
    name="CatalogShellAgent",
    model=os.getenv("CATALOG_SHELL_MODEL", "gemini-2.5-pro"),
    instruction=CATALOG_INSTRUCTION,
    tools=all_tools,
    before_tool_callback=_before_tool_callback,
    before_model_callback=_before_model_callback,
)


# ============================================================================
# JOB EXECUTION INTERFACE
# ============================================================================

def execute_job(job: Dict[str, Any], worker_id: str) -> Dict[str, Any]:
    """
    Execute a catalog curation job.
    
    This is the main entry point for job processing. It:
    1. Sets up job context
    2. Generates execution plan based on job type
    3. Invokes the agent with the plan
    4. Returns the result
    
    Args:
        job: Job document from Firestore
        worker_id: ID of the worker processing this job
        
    Returns:
        Execution result with status and details
    """
    job_id = job.get("id", "unknown")
    job_type = job.get("type", "UNKNOWN")
    payload = job.get("payload", {})
    
    logger.info("execute_job: job=%s, type=%s, worker=%s", job_id, job_type, worker_id)
    
    # Create and set job context
    ctx = JobContext.from_job(job, worker_id)
    set_current_job_context(ctx)
    
    if not ctx.is_valid():
        return {
            "success": False,
            "error": "Invalid job context",
            "job_id": job_id,
        }
    
    # Generate execution plan
    plan = generate_job_plan(job_type, payload)
    
    # Build the prompt for the agent
    prompt = build_job_prompt(job, plan)
    
    # For Phase 0, return mock execution
    # Phase 1+ will invoke the actual agent
    logger.info("execute_job: would invoke agent with prompt length=%d", len(prompt))
    
    return {
        "success": True,
        "job_id": job_id,
        "job_type": job_type,
        "mode": ctx.mode,
        "plan_generated": True,
        "agent_invoked": False,  # Phase 0: not actually invoking
        "_mock": True,
    }


def build_job_prompt(job: Dict[str, Any], plan) -> str:
    """
    Build the prompt for the agent based on job and plan.
    
    Args:
        job: Job document
        plan: Generated JobPlan
        
    Returns:
        Prompt string for the agent
    """
    job_type = job.get("type", "UNKNOWN")
    payload = job.get("payload", {})
    family_slug = payload.get("family_slug", "")
    mode = payload.get("mode", "dry_run")
    
    # Start with plan guidance
    prompt_parts = [plan.to_system_prompt()]
    
    # Add job-specific context
    prompt_parts.append(f"""
## JOB DETAILS

Job ID: {job.get("id", "unknown")}
Job Type: {job_type}
Mode: {mode}
Family: {family_slug or "N/A"}
""")
    
    # Add any intent/seed data for creation jobs
    if job_type == "EXERCISE_ADD" and payload.get("intent"):
        intent = payload["intent"]
        prompt_parts.append(f"""
## EXERCISE TO ADD

Base Name: {intent.get("base_name", "")}
Equipment: {intent.get("equipment", [])}
Primary Muscles: {intent.get("muscles_primary", [])}
""")
    
    # Add merge config for merge jobs
    if job_type == "FAMILY_MERGE" and payload.get("merge_config"):
        config = payload["merge_config"]
        prompt_parts.append(f"""
## MERGE CONFIGURATION

Source Family: {config.get("source_family", "")}
Target Family: {config.get("target_family", "")}
Conflict Strategy: {config.get("equipment_conflict_strategy", "merge")}
""")
    
    # Final instruction
    prompt_parts.append("""
## YOUR TASK

1. Use the tools to fetch the data specified in the plan
2. Analyze the data following the analysis steps
3. Generate a structured Change Plan as JSON
4. If in dry_run mode, the plan will be validated but not applied
5. If in apply mode, the plan will be validated and applied if valid

Begin by fetching the required data.
""")
    
    return "\n".join(prompt_parts)


def create_catalog_agent() -> Agent:
    """
    Factory function to create a CatalogShellAgent instance.
    
    Useful for testing or creating multiple instances.
    """
    return Agent(
        name="CatalogShellAgent",
        model=os.getenv("CATALOG_SHELL_MODEL", "gemini-2.5-pro"),
        instruction=CATALOG_INSTRUCTION,
        tools=all_tools,
        before_tool_callback=_before_tool_callback,
        before_model_callback=_before_model_callback,
    )


# Export for ADK and imports
root_agent = CatalogShellAgent

__all__ = [
    "root_agent",
    "CatalogShellAgent",
    "create_catalog_agent",
    "execute_job",
    "build_job_prompt",
]
