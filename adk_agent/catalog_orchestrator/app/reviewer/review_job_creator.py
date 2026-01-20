"""
Review Job Creator - Translates catalog review findings into queued jobs.

Takes the output of CatalogReviewer and creates appropriate jobs in the
catalog_jobs queue for processing by workers.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.jobs.models import JobType, JobQueue
from app.jobs.queue import create_job, find_pending_job
from app.reviewer.catalog_reviewer import (
    BatchReviewResult,
    ReviewResult,
    IssueCategory,
    IssueSeverity,
    QualityIssue,
)

logger = logging.getLogger(__name__)


# Human review job type (for low confidence LLM decisions)
HUMAN_REVIEW_JOB_TYPE = JobType.FAMILY_AUDIT  # Audit jobs require human review

# Category to job type mapping
CATEGORY_TO_JOB_TYPE = {
    IssueCategory.CONTENT: JobType.CATALOG_ENRICH_FIELD,
    IssueCategory.ANATOMY: JobType.CATALOG_ENRICH_FIELD,
    IssueCategory.BIOMECHANICS: JobType.CATALOG_ENRICH_FIELD,
    IssueCategory.TAXONOMY: JobType.FAMILY_AUDIT,
}

# Severity to queue mapping
SEVERITY_TO_QUEUE = {
    IssueSeverity.CRITICAL: JobQueue.PRIORITY,
    IssueSeverity.HIGH: JobQueue.PRIORITY,
    IssueSeverity.MEDIUM: JobQueue.MAINTENANCE,
    IssueSeverity.LOW: JobQueue.MAINTENANCE,
}


class ReviewJobCreator:
    """
    Creates enrichment jobs from catalog review findings.
    
    Groups issues by exercise and category, creates appropriate job types,
    and submits them to the job queue.
    """
    
    def __init__(
        self,
        dry_run: bool = True,
        max_jobs_per_run: int = 50,
    ):
        """
        Initialize the job creator.
        
        Args:
            dry_run: If True, don't actually create jobs
            max_jobs_per_run: Maximum jobs to create per run
        """
        self.dry_run = dry_run
        self.max_jobs_per_run = max_jobs_per_run
        self._jobs_created = 0
    
    def create_jobs_from_batch_review(
        self,
        batch_result: BatchReviewResult,
    ) -> Dict[str, Any]:
        """
        Create jobs from a batch review result.
        
        Returns summary of jobs created.
        """
        jobs_created = []
        jobs_skipped = []
        
        for result in batch_result.results:
            if not result.needs_enrichment and not result.needs_human_review:
                continue
            
            if self._jobs_created >= self.max_jobs_per_run:
                jobs_skipped.append({
                    "exercise_id": result.exercise_id,
                    "reason": "max_jobs_per_run reached",
                })
                continue
            
            # Create job for this exercise
            job_info = self.create_job_for_exercise(result)
            if job_info:
                jobs_created.append(job_info)
        
        return {
            "jobs_created": len(jobs_created),
            "jobs_skipped": len(jobs_skipped),
            "dry_run": self.dry_run,
            "jobs": jobs_created,
            "skipped": jobs_skipped,
        }
    
    def create_job_for_exercise(
        self,
        result: ReviewResult,
    ) -> Optional[Dict[str, Any]]:
        """
        Create a single job for an exercise with issues.
        
        Groups issues by category and creates appropriate job type.
        If LLM confidence is low, escalates to human review instead of auto-fix.
        Skips job creation if a pending job already exists for this exercise.
        """
        if not result.issues:
            return None
        
        # Determine job type first for dedup check
        issues_by_category_preview: Dict[IssueCategory, List[QualityIssue]] = {}
        for issue in result.issues:
            if issue.category not in issues_by_category_preview:
                issues_by_category_preview[issue.category] = []
            issues_by_category_preview[issue.category].append(issue)
        
        primary_category = self._get_primary_category(issues_by_category_preview)
        job_type = CATEGORY_TO_JOB_TYPE.get(primary_category, JobType.CATALOG_ENRICH_FIELD)
        
        # Check for existing pending job (skip in dry-run mode)
        if not self.dry_run:
            existing_job_id = find_pending_job(job_type, result.exercise_id)
            if existing_job_id:
                logger.debug(
                    "Skipping exercise %s - pending job exists: %s",
                    result.exercise_id, existing_job_id
                )
                return {
                    "exercise_id": result.exercise_id,
                    "exercise_name": result.exercise_name,
                    "skipped": True,
                    "reason": f"Pending job exists: {existing_job_id}",
                    "existing_job_id": existing_job_id,
                }
        
        # Check for low-confidence LLM issues
        llm_issues = [i for i in result.issues if i.message and i.message.startswith("[LLM]")]
        needs_human_escalation = result.needs_human_review
        
        # If we have LLM issues and the result explicitly flags for human review,
        # create a human review job instead of auto-fix
        if needs_human_escalation and llm_issues:
            return self._create_human_review_job(result, llm_issues)
        
        # Group issues by category
        issues_by_category: Dict[IssueCategory, List[QualityIssue]] = {}
        for issue in result.issues:
            if issue.category not in issues_by_category:
                issues_by_category[issue.category] = []
            issues_by_category[issue.category].append(issue)
        
        # Determine primary job type from most severe category
        primary_category = self._get_primary_category(issues_by_category)
        job_type = CATEGORY_TO_JOB_TYPE.get(primary_category, JobType.CATALOG_ENRICH_FIELD)
        
        # Determine queue from most severe issue
        max_severity = max(i.severity for i in result.issues)
        queue = SEVERITY_TO_QUEUE.get(max_severity, JobQueue.MAINTENANCE)
        
        # Priority based on severity
        priority_map = {
            IssueSeverity.CRITICAL: 100,
            IssueSeverity.HIGH: 80,
            IssueSeverity.MEDIUM: 50,
            IssueSeverity.LOW: 20,
        }
        priority = priority_map.get(max_severity, 50)
        
        # Build enrichment spec for the job
        enrichment_spec = self._build_enrichment_spec(result, issues_by_category)
        
        job_info = {
            "exercise_id": result.exercise_id,
            "exercise_name": result.exercise_name,
            "family_slug": result.family_slug,
            "job_type": job_type.value,
            "queue": queue.value,
            "priority": priority,
            "issue_count": len(result.issues),
            "categories": list(issues_by_category.keys()),
            "enrichment_spec": enrichment_spec,
        }
        
        if not self.dry_run:
            try:
                job = create_job(
                    job_type=job_type,
                    queue=queue,
                    priority=priority,
                    family_slug=result.family_slug,
                    exercise_ids=[result.exercise_id],
                    enrichment_spec=enrichment_spec,
                )
                job_info["job_id"] = job.job_id
                self._jobs_created += 1
                logger.info(
                    "Created job %s for exercise %s",
                    job.job_id, result.exercise_id
                )
            except Exception as e:
                logger.exception("Failed to create job for %s: %s", result.exercise_id, e)
                job_info["error"] = str(e)
        else:
            job_info["job_id"] = f"dry-run-{result.exercise_id}"
            self._jobs_created += 1
        
        return job_info
    
    def _get_primary_category(
        self,
        issues_by_category: Dict[IssueCategory, List[QualityIssue]],
    ) -> IssueCategory:
        """Get the primary category based on issue severity and count."""
        # Priority order
        category_priority = [
            IssueCategory.TAXONOMY,
            IssueCategory.ANATOMY,
            IssueCategory.BIOMECHANICS,
            IssueCategory.CONTENT,
        ]
        
        # Find highest severity per category
        category_max_severity: Dict[IssueCategory, IssueSeverity] = {}
        for cat, issues in issues_by_category.items():
            max_sev = max(i.severity for i in issues)
            category_max_severity[cat] = max_sev
        
        # Return category with highest severity, using priority order as tiebreaker
        severity_order = [
            IssueSeverity.CRITICAL,
            IssueSeverity.HIGH,
            IssueSeverity.MEDIUM,
            IssueSeverity.LOW,
        ]
        
        for sev in severity_order:
            for cat in category_priority:
                if category_max_severity.get(cat) == sev:
                    return cat
        
        return IssueCategory.CONTENT
    
    def _create_human_review_job(
        self,
        result: ReviewResult,
        llm_issues: List[QualityIssue],
    ) -> Optional[Dict[str, Any]]:
        """
        Create a human review job when LLM confidence is low.
        
        Instead of auto-fixing, escalates to human for verification.
        """
        # Format issues for human review
        issue_descriptions = []
        for issue in llm_issues:
            desc = f"- {issue.field}: {issue.message}"
            if issue.suggested_fix:
                desc += f"\n  Suggested: {issue.suggested_fix}"
            issue_descriptions.append(desc)
        
        job_info = {
            "exercise_id": result.exercise_id,
            "exercise_name": result.exercise_name,
            "family_slug": result.family_slug,
            "job_type": "HUMAN_REVIEW",
            "queue": JobQueue.PRIORITY.value,
            "priority": 90,  # High priority for human review
            "issue_count": len(llm_issues),
            "requires_human": True,
            "escalation_reason": "Low confidence LLM analysis - needs human verification",
            "issues": issue_descriptions,
        }
        
        if not self.dry_run:
            try:
                # Create audit job for human review
                job = create_job(
                    job_type=HUMAN_REVIEW_JOB_TYPE,
                    queue=JobQueue.PRIORITY,
                    priority=90,
                    family_slug=result.family_slug,
                    exercise_ids=[result.exercise_id],
                    enrichment_spec={
                        "type": "human_review",
                        "exercise_id": result.exercise_id,
                        "issues": issue_descriptions,
                        "quality_score": result.quality_score,
                        "llm_issue_count": len(llm_issues),
                    },
                )
                job_info["job_id"] = job.job_id
                self._jobs_created += 1
                logger.info(
                    "Created HUMAN_REVIEW job %s for exercise %s (LLM low confidence)",
                    job.job_id, result.exercise_id
                )
            except Exception as e:
                logger.exception("Failed to create human review job for %s: %s", result.exercise_id, e)
                job_info["error"] = str(e)
        else:
            job_info["job_id"] = f"dry-run-human-{result.exercise_id}"
            self._jobs_created += 1
        
        return job_info
    
    def _build_enrichment_spec(
        self,
        result: ReviewResult,
        issues_by_category: Dict[IssueCategory, List[QualityIssue]],
    ) -> Dict[str, Any]:
        """Build enrichment spec based on issues found."""
        fields_to_enrich = set()
        instructions_parts = []
        
        for cat, issues in issues_by_category.items():
            for issue in issues:
                fields_to_enrich.add(issue.field)
                if issue.message:
                    instructions_parts.append(f"- {issue.message}")
                if issue.suggested_fix:
                    instructions_parts.append(f"  Suggested: {issue.suggested_fix}")
        
        return {
            "spec_id": f"review_fix_{result.exercise_id}",
            "spec_version": "v1",
            "fields_to_enrich": list(fields_to_enrich),
            "source": "catalog_review",
            "quality_score": result.quality_score,
            "instructions": "\n".join(instructions_parts),
            "review_timestamp": datetime.now(timezone.utc).isoformat(),
        }


def create_jobs_from_review(
    batch_result: BatchReviewResult,
    dry_run: bool = True,
    max_jobs: int = 50,
) -> Dict[str, Any]:
    """
    Convenience function to create jobs from a batch review.
    
    Args:
        batch_result: Result from CatalogReviewer.review_batch()
        dry_run: If True, don't actually create jobs
        max_jobs: Maximum jobs to create
        
    Returns:
        Summary of jobs created
    """
    creator = ReviewJobCreator(dry_run=dry_run, max_jobs_per_run=max_jobs)
    return creator.create_jobs_from_batch_review(batch_result)
