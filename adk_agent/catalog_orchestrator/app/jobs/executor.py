"""
Job Executor - Execute catalog curation jobs.

This module implements the full job execution pipeline:
1. Fetch context (family summary, exercises, aliases)
2. For audit jobs: analyze and create audit plan
3. For normalize jobs: analyze and create normalize plan
4. Validate plan using deterministic validators
5. For dry_run: return plan preview
6. For apply: apply changes (Phase 4)

The executor does NOT call LLM for Phase 2/3. It uses deterministic
logic to generate plans from data. LLM integration comes in Phase 4+.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.jobs.models import Job, JobType
from app.family.registry import (
    get_family_summary,
    get_family_exercises,
    get_or_create_family_registry,
)
from app.family.taxonomy import (
    validate_equipment_naming,
    validate_slug_derivation,
    detect_duplicate_equipment,
    derive_canonical_name,
    derive_name_slug,
)
from app.plans.models import ChangePlan, ValidationResult
from app.plans.compiler import create_audit_plan, create_normalize_plan
from app.plans.validators import validate_change_plan

logger = logging.getLogger(__name__)


class JobExecutor:
    """
    Execute catalog curation jobs.
    
    Uses deterministic logic for plan generation in Phase 2/3.
    LLM integration added in Phase 4+.
    """
    
    def __init__(self, job: Dict[str, Any], worker_id: str):
        """
        Initialize executor for a job.
        
        Args:
            job: Job document from Firestore
            worker_id: Worker ID processing this job
        """
        self.job_id = job.get("id", "unknown")
        self.job_type = job.get("type", "UNKNOWN")
        self.payload = job.get("payload", {})
        self.worker_id = worker_id
        
        self.family_slug = self.payload.get("family_slug")
        self.mode = self.payload.get("mode", "dry_run")
        
        self._plan: Optional[ChangePlan] = None
        self._validation: Optional[ValidationResult] = None
    
    def execute(self) -> Dict[str, Any]:
        """
        Execute the job.
        
        Returns:
            Result dict with success, plan, validation, etc.
        """
        logger.info("Executing job: %s, type=%s, family=%s, mode=%s",
                   self.job_id, self.job_type, self.family_slug, self.mode)
        
        try:
            # Dispatch to job-type handler
            if self.job_type == JobType.FAMILY_AUDIT.value:
                return self._execute_family_audit()
            elif self.job_type == JobType.FAMILY_NORMALIZE.value:
                return self._execute_family_normalize()
            elif self.job_type == JobType.MAINTENANCE_SCAN.value:
                return self._execute_maintenance_scan()
            else:
                return {
                    "success": False,
                    "error": {
                        "code": "UNSUPPORTED_JOB_TYPE",
                        "message": f"Job type {self.job_type} not yet implemented",
                    },
                    "is_transient": False,
                }
        except Exception as e:
            logger.exception("Job execution failed: %s", self.job_id)
            return {
                "success": False,
                "error": {
                    "code": "EXECUTION_ERROR",
                    "message": str(e),
                    "type": type(e).__name__,
                },
                "is_transient": True,
            }
    
    def _execute_family_audit(self) -> Dict[str, Any]:
        """
        Execute FAMILY_AUDIT job.
        
        Analyzes a family and reports issues without making changes.
        """
        if not self.family_slug:
            return {
                "success": False,
                "error": {"code": "MISSING_FAMILY_SLUG", "message": "FAMILY_AUDIT requires family_slug"},
                "is_transient": False,
            }
        
        # Fetch family data
        summary = get_family_summary(self.family_slug)
        exercises = get_family_exercises(self.family_slug)
        registry = get_or_create_family_registry(self.family_slug)
        
        if not exercises:
            return {
                "success": True,
                "audit_result": {
                    "family_slug": self.family_slug,
                    "exercise_count": 0,
                    "findings": [{"type": "info", "message": "Empty family - no exercises found"}],
                },
            }
        
        # Collect findings
        findings = []
        
        # Check naming issues
        for ex in exercises:
            naming_errors = validate_equipment_naming(ex, registry)
            for err in naming_errors:
                findings.append({
                    "type": "naming_error",
                    "doc_ids": [ex.doc_id],
                    "code": err["code"],
                    "description": err["message"],
                    "suggestion": err.get("suggestion"),
                })
            
            slug_errors = validate_slug_derivation(ex)
            for err in slug_errors:
                findings.append({
                    "type": "slug_error",
                    "doc_ids": [ex.doc_id],
                    "code": err["code"],
                    "description": err["message"],
                })
        
        # Check duplicates
        duplicates = detect_duplicate_equipment(exercises)
        for dup in duplicates:
            findings.append({
                "type": "duplicate_equipment",
                "doc_ids": [e["doc_id"] for e in dup["exercises"]],
                "code": "DUPLICATE_EQUIPMENT_VARIANT",
                "description": f"Multiple exercises with equipment '{dup['equipment']}': {dup['count']} found",
                "exercises": dup["exercises"],
            })
        
        # Create audit plan (no mutations)
        plan = create_audit_plan(self.job_id, self.family_slug, findings)
        
        return {
            "success": True,
            "audit_result": {
                "family_slug": self.family_slug,
                "base_name": registry.base_name,
                "exercise_count": len(exercises),
                "is_multi_equipment": registry.is_multi_equipment(),
                "primary_equipment_set": list(registry.primary_equipment_set),
                "findings": findings,
                "finding_count": len(findings),
            },
            "plan": plan.to_dict(),
        }
    
    def _execute_family_normalize(self) -> Dict[str, Any]:
        """
        Execute FAMILY_NORMALIZE job.
        
        Generates a plan to normalize exercise naming in a family.
        For multi-equipment families, adds equipment qualifiers.
        """
        if not self.family_slug:
            return {
                "success": False,
                "error": {"code": "MISSING_FAMILY_SLUG", "message": "FAMILY_NORMALIZE requires family_slug"},
                "is_transient": False,
            }
        
        # Fetch family data
        exercises = get_family_exercises(self.family_slug)
        registry = get_or_create_family_registry(self.family_slug)
        
        if not exercises:
            return {
                "success": True,
                "normalize_result": {
                    "family_slug": self.family_slug,
                    "renames": [],
                    "alias_updates": [],
                    "message": "No exercises to normalize",
                },
            }
        
        renames = []
        alias_updates = []
        
        # Check if family needs equipment suffixes
        if registry.needs_equipment_suffixes():
            for ex in exercises:
                # Check if exercise needs renaming
                if not ex.has_equipment_in_name() and ex.primary_equipment:
                    new_name = derive_canonical_name(ex.name, ex.primary_equipment)
                    new_slug = derive_name_slug(new_name)
                    
                    renames.append({
                        "doc_id": ex.doc_id,
                        "old_name": ex.name,
                        "old_slug": ex.name_slug,
                        "new_name": new_name,
                        "new_slug": new_slug,
                        "equipment": ex.primary_equipment,
                        "rationale": f"Multi-equipment family requires equipment qualifier",
                    })
                    
                    # Old slug becomes alias to new exercise
                    if ex.name_slug != new_slug:
                        alias_updates.append({
                            "alias_slug": ex.name_slug,
                            "exercise_id": ex.doc_id,
                            "rationale": f"Redirect old slug to renamed exercise",
                        })
        
        # Create normalize plan
        plan = create_normalize_plan(
            self.job_id,
            self.family_slug,
            renames,
            alias_updates,
        )
        
        # Validate the plan
        # For validation, we need full exercise docs and aliases
        # For now, use simplified validation
        validation = ValidationResult(valid=True)
        if not renames and not alias_updates:
            validation.add_warning(
                "NO_CHANGES",
                "Family is already normalized, no changes needed",
            )
        
        result = {
            "success": True,
            "normalize_result": {
                "family_slug": self.family_slug,
                "base_name": registry.base_name,
                "is_multi_equipment": registry.is_multi_equipment(),
                "renames": renames,
                "alias_updates": alias_updates,
                "rename_count": len(renames),
                "alias_count": len(alias_updates),
            },
            "plan": plan.to_dict(),
            "validation": validation.to_dict(),
            "mode": self.mode,
        }
        
        if self.mode == "apply":
            # Phase 4: Actually apply the changes
            result["applied"] = False
            result["apply_message"] = "Apply engine not yet implemented (Phase 4)"
        
        return result
    
    def _execute_maintenance_scan(self) -> Dict[str, Any]:
        """
        Execute MAINTENANCE_SCAN job.
        
        Scans for families that need attention and emits targeted jobs.
        """
        from app.skills.catalog_read_skills import list_families_summary
        import asyncio
        
        # Get family summary
        loop = asyncio.new_event_loop()
        try:
            families_result = loop.run_until_complete(list_families_summary(min_size=1, limit=100))
        finally:
            loop.close()
        
        if not families_result.get("success"):
            return {
                "success": False,
                "error": {"code": "SCAN_FAILED", "message": "Failed to list families"},
                "is_transient": True,
            }
        
        families = families_result.get("families", [])
        
        # For each family, check if it needs attention
        needs_audit = []
        
        for fam in families[:20]:  # Limit to avoid too many
            family_slug = fam["family_slug"]
            try:
                registry = get_or_create_family_registry(family_slug)
                exercises = get_family_exercises(family_slug)
                
                # Check for issues
                issues = []
                
                if registry.is_multi_equipment():
                    for ex in exercises:
                        if not ex.has_equipment_in_name():
                            issues.append("missing_equipment_qualifier")
                            break
                
                duplicates = detect_duplicate_equipment(exercises)
                if duplicates:
                    issues.append("duplicate_equipment")
                
                if issues:
                    needs_audit.append({
                        "family_slug": family_slug,
                        "exercise_count": len(exercises),
                        "issues": issues,
                    })
            except Exception as e:
                logger.warning("Error scanning family %s: %s", family_slug, e)
        
        return {
            "success": True,
            "scan_result": {
                "families_scanned": len(families[:20]),
                "families_needing_audit": len(needs_audit),
                "families": needs_audit,
            },
        }


def execute_job(job: Dict[str, Any], worker_id: str) -> Dict[str, Any]:
    """
    Execute a catalog curation job.
    
    Main entry point for job processing.
    
    Args:
        job: Job document from Firestore
        worker_id: ID of the worker processing this job
        
    Returns:
        Execution result with status and details
    """
    executor = JobExecutor(job, worker_id)
    return executor.execute()


__all__ = [
    "JobExecutor",
    "execute_job",
]
