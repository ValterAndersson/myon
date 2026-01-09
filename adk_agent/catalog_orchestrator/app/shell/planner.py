"""
Job Planner - Planning templates for each job type.

Generates structured plans that guide the LLM in producing correct Change Plans.
Each job type has a template describing:
- What data to fetch
- What analysis to perform
- What operations are expected
- What constraints to follow
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class JobPlan:
    """Generated plan for job execution."""
    job_type: str
    data_needed: List[str]
    analysis_steps: List[str]
    expected_operations: List[str]
    constraints: List[str]
    
    def to_system_prompt(self) -> str:
        """Convert plan to system prompt injection."""
        data_str = "\n".join(f"  - {d}" for d in self.data_needed)
        analysis_str = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(self.analysis_steps))
        ops_str = "\n".join(f"  - {o}" for o in self.expected_operations)
        constraints_str = "\n".join(f"  - {c}" for c in self.constraints)
        
        return f"""
## JOB EXECUTION PLAN

Job Type: {self.job_type}

### Data to Fetch:
{data_str}

### Analysis Steps:
{analysis_str}

### Expected Operations:
{ops_str}

### Constraints:
{constraints_str}

Execute this plan step by step, then produce a structured Change Plan.
"""


# =============================================================================
# JOB TYPE PLANNING TEMPLATES
# =============================================================================

PLANNING_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "FAMILY_AUDIT": {
        "data_needed": [
            "Family summary (exercise list, equipment types)",
            "Family aliases",
            "Family registry entry (if exists)",
        ],
        "analysis_steps": [
            "Check if all exercises follow equipment-split naming when family has multiple equipment types",
            "Identify any duplicate equipment variants within the family",
            "Check for missing or conflicting aliases",
            "Verify all exercises have required fields (name, equipment, muscles)",
            "Assess overall family health and identify issues",
        ],
        "expected_operations": [
            "No operations for audit - produce report only",
            "Recommend follow-up jobs (FAMILY_NORMALIZE, TARGETED_FIX) if issues found",
        ],
        "constraints": [
            "Audit is read-only - do not propose mutations",
            "Be specific about each issue found",
            "Categorize issues by severity (critical, warning, info)",
        ],
    },
    
    "FAMILY_NORMALIZE": {
        "data_needed": [
            "Family summary with all exercises",
            "Family aliases (to create redirects for old slugs)",
            "Family registry entry for base_name reference",
        ],
        "analysis_steps": [
            "Determine if family needs equipment-split naming (>1 primary equipment types)",
            "For each exercise needing rename: compute new name with equipment suffix",
            "For each rename: plan alias creation for old name_slug",
            "Check for potential duplicate exercises after normalization",
        ],
        "expected_operations": [
            "rename_exercise: Update name and name_slug with equipment suffix",
            "upsert_alias: Create alias from old slug to new exercise",
            "upsert_alias: Make bare family name point to family_slug (if ambiguous)",
        ],
        "constraints": [
            "Use canonical equipment labels in names: (Barbell), (Dumbbell), etc.",
            "First item in equipment[] array is primary and must match name suffix",
            "Every rename MUST have corresponding alias for old slug",
            "Maximum 50 operations per plan",
        ],
    },
    
    "FAMILY_MERGE": {
        "data_needed": [
            "Source family summary",
            "Target family summary",
            "Aliases for both families",
            "Registry entries for both families",
        ],
        "analysis_steps": [
            "Verify source and target are semantically the same movement",
            "Identify which exercises from source can be moved vs merged",
            "Plan alias transfers for all source exercises",
            "Determine target canonical naming if equipment variants differ",
        ],
        "expected_operations": [
            "reassign_family: Move source exercises to target family_slug",
            "merge_exercises: Merge duplicate equipment variants",
            "upsert_alias: Transfer all source aliases to target exercises",
            "deprecate_family: Mark source family as merged_into target",
        ],
        "constraints": [
            "Only merge exercises with identical equipment (no cross-equipment merge)",
            "Preserve the richer exercise (more fields, approved status)",
            "All source aliases must be transferred",
            "Source family must be deprecated after merge",
        ],
    },
    
    "EXERCISE_ADD": {
        "data_needed": [
            "Target family summary (to check for duplicates)",
            "Family registry (for naming convention)",
            "Existing aliases (to avoid conflicts)",
        ],
        "analysis_steps": [
            "Verify exercise doesn't already exist in family",
            "Determine correct name following family conventions",
            "Plan required aliases",
            "Validate required fields are provided",
        ],
        "expected_operations": [
            "create_exercise: Create new exercise document",
            "upsert_alias: Create alias for name_slug",
            "upsert_alias: Create additional common aliases if applicable",
        ],
        "constraints": [
            "Follow equipment-split naming if family has multiple equipment types",
            "All required fields must be provided: name, equipment, muscles.primary",
            "Check for alias conflicts before creating",
        ],
    },
    
    "TARGETED_FIX": {
        "data_needed": [
            "Full exercise documents for target exercises",
            "Current aliases for those exercises",
        ],
        "analysis_steps": [
            "Identify specific fields that need correction",
            "Validate proposed fixes against schema",
            "Check for side effects on aliases or family structure",
        ],
        "expected_operations": [
            "patch_fields: Update specific fields on target exercises",
        ],
        "constraints": [
            "Only patch explicitly specified fields",
            "Use dotted paths for nested fields",
            "Validate against schema before proposing",
        ],
    },
    
    "ALIAS_REPAIR": {
        "data_needed": [
            "Alias documents for target slugs",
            "Exercise documents for referenced exercises",
            "Family information for context",
        ],
        "analysis_steps": [
            "Verify target exercise exists for each alias",
            "Check for orphan aliases (target doesn't exist)",
            "Identify conflicting aliases (multiple exercises)",
        ],
        "expected_operations": [
            "upsert_alias: Fix broken alias targets",
            "delete_alias: Remove orphan aliases",
        ],
        "constraints": [
            "Exactly one of exercise_id or family_slug must be set",
            "Target must exist before alias is created/updated",
        ],
    },
    
    "ALIAS_INVARIANT_SCAN": {
        "data_needed": [
            "All aliases (paginated if necessary)",
            "Exercise document IDs for verification",
            "Family registry for family_slug validation",
        ],
        "analysis_steps": [
            "Check each alias has exactly one of exercise_id or family_slug",
            "Verify exercise_id targets exist",
            "Verify family_slug targets exist and have exercises",
            "Report violations without auto-fixing",
        ],
        "expected_operations": [
            "No operations - produce report only",
            "Recommend ALIAS_REPAIR jobs for violations found",
        ],
        "constraints": [
            "Scan is read-only",
            "Report must include specific alias_slug and violation type",
        ],
    },
    
    "MAINTENANCE_SCAN": {
        "data_needed": [
            "Family list with basic stats",
            "Sample exercises for quality checks",
        ],
        "analysis_steps": [
            "Identify families needing normalization (multi-equipment without proper naming)",
            "Find potential duplicates across families",
            "Check for exercises missing required fields",
            "Assess overall catalog health",
        ],
        "expected_operations": [
            "No operations - emit targeted jobs",
        ],
        "constraints": [
            "Do not propose direct mutations",
            "Create targeted jobs for issues found",
            "Prioritize by severity",
        ],
    },
    
    "DUPLICATE_DETECTION_SCAN": {
        "data_needed": [
            "Family summaries for all families",
            "Exercise names and equipment across families",
        ],
        "analysis_steps": [
            "Find exercises with similar names in different families",
            "Identify potential family merges",
            "Check for near-duplicate slugs",
        ],
        "expected_operations": [
            "No operations - emit FAMILY_MERGE or FAMILY_AUDIT jobs",
        ],
        "constraints": [
            "Conservative matching - prefer false negatives",
            "Emit jobs for human review, not auto-merge",
        ],
    },
}


def generate_job_plan(job_type: str, payload: Dict[str, Any]) -> JobPlan:
    """
    Generate an execution plan for a job.
    
    Args:
        job_type: Type of job to plan
        payload: Job payload with scope and parameters
        
    Returns:
        JobPlan with execution guidance
    """
    template = PLANNING_TEMPLATES.get(job_type)
    
    if template is None:
        logger.warning("No planning template for job type: %s", job_type)
        return JobPlan(
            job_type=job_type,
            data_needed=["Fetch relevant context for this job type"],
            analysis_steps=["Analyze the data and determine required changes"],
            expected_operations=["Produce appropriate operations for the job"],
            constraints=["Follow general catalog curation guidelines"],
        )
    
    return JobPlan(
        job_type=job_type,
        data_needed=template["data_needed"],
        analysis_steps=template["analysis_steps"],
        expected_operations=template["expected_operations"],
        constraints=template["constraints"],
    )


__all__ = [
    "JobPlan",
    "generate_job_plan",
    "PLANNING_TEMPLATES",
]
