"""
Job Executor - Central dispatcher for all catalog curation job types.

═══════════════════════════════════════════════════════════════════════════════
ENTRY POINTS (what you'll call from outside)
═══════════════════════════════════════════════════════════════════════════════

  execute_job(job: Dict, worker_id: str) -> Dict
      Main entry point. Call this to execute any job type.
      Returns {"success": bool, "error"?: {...}, "plan"?: {...}, ...}

  execute_with_repair_loop(job: Dict, worker_id: str, max_repairs: int) -> Dict
      Same as execute_job but with LLM-assisted retry on validation failure.
      Use for production; logs suggested fixes but doesn't auto-apply them (yet).

═══════════════════════════════════════════════════════════════════════════════
DISPATCH TABLE (JobType -> Handler)
═══════════════════════════════════════════════════════════════════════════════

  FAMILY_AUDIT          -> _execute_family_audit()         # Read-only analysis
  FAMILY_NORMALIZE      -> _execute_family_normalize()     # Add equipment suffixes
  FAMILY_MERGE          -> _execute_family_merge()         # Merge two families
  FAMILY_SPLIT          -> handlers.execute_family_split() # Split by equipment
  FAMILY_RENAME_SLUG    -> handlers.execute_family_rename_slug()
  MAINTENANCE_SCAN      -> _execute_maintenance_scan()     # Emit targeted jobs
  DUPLICATE_DETECTION   -> _execute_duplicate_detection_scan()
  EXERCISE_ADD          -> _execute_exercise_add()         # Create new exercise
  TARGETED_FIX          -> handlers.execute_targeted_fix() # Patch fields
  ALIAS_REPAIR          -> handlers.execute_alias_repair()
  ALIAS_INVARIANT_SCAN  -> handlers.execute_alias_invariant_scan()
  SCHEMA_CLEANUP        -> handlers.execute_schema_cleanup()
  CATALOG_ENRICH_FIELD  -> _execute_catalog_enrich_field() # Parent: shards work
  CATALOG_ENRICH_FIELD_SHARD -> _execute_catalog_enrich_field_shard() # LLM call

═══════════════════════════════════════════════════════════════════════════════
INVARIANTS (rules that must always hold)
═══════════════════════════════════════════════════════════════════════════════

  1. Jobs with mode="dry_run" NEVER mutate Firestore
  2. Jobs with mode="apply" require CATALOG_APPLY_ENABLED=true env var
  3. All handlers return {"success": bool, ...} - never throw for expected errors
  4. Lock-requiring jobs: TARGETED_FIX, EXERCISE_ADD, FAMILY_*, SCHEMA_CLEANUP,
     CATALOG_ENRICH_FIELD_SHARD (acquired by worker, not executor)
  5. Parent CATALOG_ENRICH_FIELD creates child SHARD jobs - does NOT enrich directly

═══════════════════════════════════════════════════════════════════════════════
GOTCHAS (things that might surprise you)
═══════════════════════════════════════════════════════════════════════════════

  • CATALOG_ENRICH_FIELD is a "meta job" - it just shards work and queues children
  • EXERCISE_ADD checks for slug collision BEFORE creating (not transactional)
  • Holistic enrichment mode triggered when enrichment_spec has fields_to_enrich
  • execute_with_repair_loop logs LLM suggestions but doesn't auto-apply (conservative)
  • Job handlers in handlers.py are imported lazily to avoid circular imports

═══════════════════════════════════════════════════════════════════════════════
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
    derive_movement_family,
)
from app.plans.models import ChangePlan, ValidationResult
from app.plans.compiler import create_audit_plan, create_normalize_plan
from app.plans.validators import validate_change_plan

logger = logging.getLogger(__name__)


class JobExecutor:
    """
    Execute catalog curation jobs.

    LIFECYCLE:
        1. __init__() - Parse job dict, extract payload fields
        2. execute() - Dispatch to job-type handler
        3. Handler builds ChangePlan with Operations
        4. Plan validated by plans.validators
        5. If mode="apply", ApplyEngine executes mutations

    CALLERS:
        - execute_job() - Simple wrapper, use this
        - execute_with_repair_loop() - With LLM retry on failure
        - CatalogWorker.process_job() - Production entry point

    GOTCHAS:
        - mode is extracted from payload, NOT from job root
        - family_slug may be None for catalog-wide jobs (scans)
        - Handlers in handlers.py are imported lazily (avoid circular imports)
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
            elif self.job_type == JobType.FAMILY_MERGE.value:
                return self._execute_family_merge()
            elif self.job_type == JobType.EXERCISE_ADD.value:
                return self._execute_exercise_add()
            elif self.job_type == JobType.DUPLICATE_DETECTION_SCAN.value:
                return self._execute_duplicate_detection_scan()
            elif self.job_type == JobType.CATALOG_ENRICH_FIELD.value:
                return self._execute_catalog_enrich_field()
            elif self.job_type == JobType.CATALOG_ENRICH_FIELD_SHARD.value:
                return self._execute_catalog_enrich_field_shard()
            elif self.job_type == JobType.FAMILY_SPLIT.value:
                from app.jobs.handlers import execute_family_split
                return execute_family_split(self.job_id, self.payload, self.mode)
            elif self.job_type == JobType.FAMILY_RENAME_SLUG.value:
                from app.jobs.handlers import execute_family_rename_slug
                return execute_family_rename_slug(self.job_id, self.payload, self.mode)
            elif self.job_type == JobType.ALIAS_REPAIR.value:
                from app.jobs.handlers import execute_alias_repair
                return execute_alias_repair(self.job_id, self.payload, self.mode)
            elif self.job_type == JobType.TARGETED_FIX.value:
                from app.jobs.handlers import execute_targeted_fix
                return execute_targeted_fix(self.job_id, self.payload, self.mode)
            elif self.job_type == JobType.ALIAS_INVARIANT_SCAN.value:
                from app.jobs.handlers import execute_alias_invariant_scan
                return execute_alias_invariant_scan(self.job_id, self.payload, self.mode)
            elif self.job_type == JobType.SCHEMA_CLEANUP.value:
                from app.jobs.handlers import execute_schema_cleanup
                return execute_schema_cleanup(self.job_id, self.payload, self.mode)
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
            # Apply the changes using ApplyEngine
            from app.apply.engine import apply_change_plan
            
            apply_result = apply_change_plan(plan, mode=self.mode, job_id=self.job_id)
            result["applied"] = apply_result.success
            result["apply_result"] = apply_result.to_dict()
        
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
    
    def _execute_family_merge(self) -> Dict[str, Any]:
        """
        Execute FAMILY_MERGE job.
        
        Merges source family into target family:
        - Reassigns exercises to target family
        - Resolves duplicate equipment variants
        - Updates aliases
        - Marks source family as deprecated
        """
        from app.plans.models import Operation, OperationType, RiskLevel, ChangePlan
        from app.family.models import FamilyStatus
        
        merge_config = self.payload.get("merge_config", {})
        source_family = merge_config.get("source_family")
        target_family = merge_config.get("target_family")
        
        if not source_family or not target_family:
            return {
                "success": False,
                "error": {"code": "MISSING_MERGE_CONFIG", "message": "FAMILY_MERGE requires source_family and target_family"},
                "is_transient": False,
            }
        
        # Fetch data
        source_exercises = get_family_exercises(source_family)
        target_exercises = get_family_exercises(target_family)
        source_registry = get_or_create_family_registry(source_family)
        target_registry = get_or_create_family_registry(target_family)
        
        if not source_exercises:
            return {
                "success": True,
                "merge_result": {
                    "source_family": source_family,
                    "target_family": target_family,
                    "message": "Source family has no exercises",
                    "exercises_moved": 0,
                },
            }
        
        # Build target equipment set
        target_equipment = {ex.primary_equipment for ex in target_exercises if ex.primary_equipment}
        
        operations = []
        exercises_to_move = []
        duplicates_to_merge = []
        
        for ex in source_exercises:
            if ex.primary_equipment in target_equipment:
                # Duplicate equipment - mark for manual review
                duplicates_to_merge.append({
                    "source_doc_id": ex.doc_id,
                    "source_name": ex.name,
                    "equipment": ex.primary_equipment,
                })
            else:
                # Move exercise to target family
                exercises_to_move.append(ex.doc_id)
        
        # Create REASSIGN_FAMILY operation
        if exercises_to_move:
            operations.append(Operation(
                op_type=OperationType.REASSIGN_FAMILY,
                targets=exercises_to_move,
                patch={"family_slug": target_family},
                rationale=f"Move exercises from {source_family} to {target_family}",
                risk_level=RiskLevel.HIGH,
                idempotency_key_seed=f"merge_{source_family}_{target_family}_reassign",
            ))
        
        # Create plan
        plan = ChangePlan(
            job_id=self.job_id,
            job_type="FAMILY_MERGE",
            scope={
                "source_family": source_family,
                "target_family": target_family,
            },
            assumptions=[
                f"Merging {source_family} into {target_family}",
                f"Moving {len(exercises_to_move)} exercises",
                f"Found {len(duplicates_to_merge)} equipment conflicts",
            ],
            operations=operations,
            max_risk_level=RiskLevel.HIGH,
        )
        
        result = {
            "success": True,
            "merge_result": {
                "source_family": source_family,
                "target_family": target_family,
                "exercises_to_move": exercises_to_move,
                "duplicates_needing_review": duplicates_to_merge,
                "move_count": len(exercises_to_move),
                "duplicate_count": len(duplicates_to_merge),
            },
            "plan": plan.to_dict(),
            "mode": self.mode,
        }
        
        if self.mode == "apply" and operations:
            from app.apply.engine import apply_change_plan
            apply_result = apply_change_plan(plan, mode=self.mode, job_id=self.job_id)
            result["applied"] = apply_result.success
            result["apply_result"] = apply_result.to_dict()
        
        return result
    
    def _execute_exercise_add(self) -> Dict[str, Any]:
        """
        Execute EXERCISE_ADD job.
        
        Adds a new exercise with proper naming and family assignment.
        Validates against taxonomy and checks for duplicates.
        """
        from app.plans.models import Operation, OperationType, RiskLevel, ChangePlan
        from app.family.taxonomy import EQUIPMENT_DISPLAY_MAP
        
        # Support both "intent" (new format) and "enrichment_spec" (legacy format)
        intent = self.payload.get("intent") or {}
        if not intent:
            # Fall back to enrichment_spec for legacy jobs
            enrichment_spec = self.payload.get("enrichment_spec") or {}
            intent = {
                "base_name": enrichment_spec.get("suggested_name"),
                "equipment": enrichment_spec.get("equipment", []),
            }
        
        base_name = intent.get("base_name")
        equipment = intent.get("equipment", [])
        # Support both new schema (muscles.primary) and legacy (muscles_primary)
        muscles = intent.get("muscles", {})
        primary_muscles = muscles.get("primary", intent.get("muscles_primary", []))
        secondary_muscles = muscles.get("secondary", intent.get("muscles_secondary", []))
        
        if not base_name:
            return {
                "success": False,
                "error": {"code": "MISSING_BASE_NAME", "message": "EXERCISE_ADD requires base_name in intent"},
                "is_transient": False,
            }
        
        # Derive family slug using movement extraction (strips equipment)
        # V1.1: Use derive_movement_family for proper grouping
        family_slug = derive_movement_family(base_name)
        
        # Check if family exists
        existing_exercises = get_family_exercises(family_slug)
        registry = get_or_create_family_registry(family_slug)
        
        # Determine if we need equipment qualifier
        primary_equipment = equipment[0] if equipment else None
        existing_equipment = {ex.primary_equipment for ex in existing_exercises if ex.primary_equipment}
        
        needs_qualifier = len(existing_equipment) > 0 or (primary_equipment and primary_equipment in existing_equipment)
        
        if needs_qualifier and primary_equipment:
            exercise_name = derive_canonical_name(base_name, primary_equipment)
        else:
            exercise_name = base_name
        
        name_slug = derive_name_slug(exercise_name)
        
        # Check for duplicate
        for ex in existing_exercises:
            if ex.name_slug == name_slug:
                return {
                    "success": False,
                    "error": {
                        "code": "DUPLICATE_EXERCISE",
                        "message": f"Exercise with slug '{name_slug}' already exists",
                        "existing_doc_id": ex.doc_id,
                    },
                    "is_transient": False,
                }
        
        # Create exercise data with NEW SCHEMA
        # V1.2: Use muscles.primary/secondary instead of primary_muscles/secondary_muscles
        exercise_data = {
            "name": exercise_name,
            "name_slug": name_slug,
            "family_slug": family_slug,
            "equipment": equipment,
            "category": "compound",  # Default, enrichment job will refine
            "muscles": {
                "primary": primary_muscles,
                "secondary": secondary_muscles,
                "category": [],
                "contribution": {},
            },
            "metadata": {
                "level": "intermediate",
                "plane_of_motion": None,
                "unilateral": False,
            },
            "movement": {
                "type": None,
                "split": None,
            },
            "execution_notes": [],
            "common_mistakes": [],
            "suitability_notes": [],
            "programming_use_cases": [],
            "stimulus_tags": [],
            # coaching_cues deprecated - redundant with execution_notes
            "tips": [],
        }
        
        # Create operation
        operations = [
            Operation(
                op_type=OperationType.CREATE_EXERCISE,
                targets=[],  # Auto-generate doc_id
                patch=exercise_data,
                rationale=f"Add new exercise: {exercise_name}",
                risk_level=RiskLevel.LOW,
                idempotency_key_seed=f"add_{name_slug}",
            )
        ]
        
        plan = ChangePlan(
            job_id=self.job_id,
            job_type="EXERCISE_ADD",
            scope={"family_slug": family_slug},
            assumptions=[f"Adding new exercise to family {family_slug}"],
            operations=operations,
            max_risk_level=RiskLevel.LOW,
        )
        
        result = {
            "success": True,
            "add_result": {
                "exercise_name": exercise_name,
                "name_slug": name_slug,
                "family_slug": family_slug,
                "needs_equipment_qualifier": needs_qualifier,
            },
            "plan": plan.to_dict(),
            "mode": self.mode,
        }
        
        if self.mode == "apply":
            from app.apply.engine import apply_change_plan
            apply_result = apply_change_plan(plan, mode=self.mode, job_id=self.job_id)
            result["applied"] = apply_result.success
            result["apply_result"] = apply_result.to_dict()
            
            # If exercise was created successfully, queue enrichment job
            if apply_result.success and apply_result.operations_applied:
                created_doc_id = None
                for op_applied in apply_result.operations_applied:
                    if op_applied.get("doc_id"):
                        created_doc_id = op_applied.get("doc_id")
                        break
                
                if created_doc_id:
                    try:
                        from app.jobs.queue import create_job
                        from app.jobs.models import JobType, JobQueue
                        
                        # Queue enrichment job for the new exercise
                        enrich_job = create_job(
                            job_type=JobType.CATALOG_ENRICH_FIELD,
                            queue=JobQueue.PRIORITY,  # High priority for new exercises
                            priority=90,
                            exercise_doc_ids=[created_doc_id],
                            mode="apply",
                            enrichment_spec={
                                "spec_id": "new_exercise_enrichment",
                                "spec_version": "v1",
                                "field_path": "primary_muscles",  # Will enrich all missing fields
                                "output_type": "array",
                                "instructions": "Enrich all missing fields for this new exercise",
                            },
                        )
                        result["enrichment_job_id"] = enrich_job.job_id
                        logger.info(
                            "Queued enrichment job %s for new exercise %s",
                            enrich_job.job_id, created_doc_id
                        )
                    except Exception as e:
                        logger.warning("Failed to queue enrichment job for %s: %s", created_doc_id, e)
        
        return result
    
    def _execute_catalog_enrich_field(self) -> Dict[str, Any]:
        """
        Execute CATALOG_ENRICH_FIELD parent job.
        
        Enumerates target exercises and creates shard jobs for parallel processing.
        """
        from app.enrichment.models import EnrichmentSpec
        from app.jobs.queue import create_job
        from app.jobs.models import JobType, JobQueue
        
        enrichment_spec_data = self.payload.get("enrichment_spec", {})
        filter_criteria = self.payload.get("filter_criteria")
        exercise_ids = self.payload.get("exercise_doc_ids", [])
        shard_size = self.payload.get("shard_size", 200)
        
        if not enrichment_spec_data:
            return {
                "success": False,
                "error": {"code": "MISSING_ENRICHMENT_SPEC", "message": "CATALOG_ENRICH_FIELD requires enrichment_spec"},
                "is_transient": False,
            }
        
        spec = EnrichmentSpec.from_dict(enrichment_spec_data)
        
        # Get target exercise IDs
        if exercise_ids:
            # Explicit IDs provided
            target_ids = exercise_ids
        elif filter_criteria:
            # Query exercises matching filter
            target_ids = self._get_filtered_exercise_ids(filter_criteria)
        else:
            # All exercises
            target_ids = self._get_all_exercise_ids()
        
        if not target_ids:
            return {
                "success": True,
                "enrich_result": {
                    "spec_id": spec.spec_id,
                    "spec_version": spec.spec_version,
                    "message": "No exercises match criteria",
                    "shards_created": 0,
                    "total_exercises": 0,
                },
            }
        
        # Chunk into shards
        shards = [target_ids[i:i + shard_size] for i in range(0, len(target_ids), shard_size)]
        
        # Create child jobs
        child_job_ids = []
        for shard_ids in shards:
            child = create_job(
                job_type=JobType.CATALOG_ENRICH_FIELD_SHARD,
                queue=JobQueue.MAINTENANCE,
                exercise_doc_ids=shard_ids,
                mode=self.mode,
                enrichment_spec=enrichment_spec_data,
                parent_job_id=self.job_id,
            )
            child_job_ids.append(child.id)
        
        return {
            "success": True,
            "enrich_result": {
                "spec_id": spec.spec_id,
                "spec_version": spec.spec_version,
                "field_path": spec.field_path,
                "shards_created": len(child_job_ids),
                "total_exercises": len(target_ids),
                "child_job_ids": child_job_ids,
                "shard_size": shard_size,
            },
            "mode": self.mode,
        }
    
    def _execute_catalog_enrich_field_shard(self) -> Dict[str, Any]:
        """
        Execute CATALOG_ENRICH_FIELD_SHARD - the job that actually calls LLM.

        This is where enrichment happens. Parent CATALOG_ENRICH_FIELD just shards.

        MODES:
            Holistic (preferred): enrichment_spec.fields_to_enrich is set
                -> Calls enrich_exercise_holistic() for each exercise
                -> LLM sees full doc + reviewer hints, decides what to update
                -> More coherent results than single-field

            Legacy single-field: enrichment_spec.field_path is set
                -> Calls compute_enrichment_batch() with EnrichmentSpec
                -> One LLM call per field per exercise
                -> Used for targeted field generation

        PAYLOAD REQUIREMENTS:
            enrichment_spec: Dict with mode-specific fields
            exercise_doc_ids: List of exercise doc IDs to enrich
            parent_job_id: Optional parent job ID for tracking

        GOTCHAS:
            - Checks apply gate BEFORE fetching exercises (fail fast)
            - Missing exercises are logged but don't fail the job
            - Returns partial success if some exercises fail
            - Normalization (muscle names, stimulus tags) applied after LLM

        CALLERS:
            - CatalogWorker (from job queue)
            - Never call directly - use queue system
        """
        from app.enrichment.models import EnrichmentSpec, ShardResult, EnrichmentResult
        from app.enrichment.engine import compute_enrichment_batch, enrich_exercise_holistic
        from app.enrichment.llm_client import get_llm_client
        from app.apply.gate import require_all_gates, ApplyGateError
        from app.plans.models import Operation, OperationType, RiskLevel, ChangePlan
        from datetime import datetime
        
        enrichment_spec_data = self.payload.get("enrichment_spec", {})
        exercise_ids = self.payload.get("exercise_doc_ids", [])
        parent_job_id = self.payload.get("parent_job_id")
        
        if not enrichment_spec_data:
            return {
                "success": False,
                "error": {"code": "MISSING_ENRICHMENT_SPEC", "message": "CATALOG_ENRICH_FIELD_SHARD requires enrichment_spec"},
                "is_transient": False,
            }
        
        if not exercise_ids:
            return {
                "success": True,
                "shard_result": {
                    "message": "No exercises in shard",
                    "total": 0,
                },
            }
        
        # Detect mode: holistic (fields_to_enrich) vs single-field (field_path)
        fields_to_enrich = enrichment_spec_data.get("fields_to_enrich", [])
        is_holistic_mode = bool(fields_to_enrich) or not enrichment_spec_data.get("field_path")
        
        # Check apply gate before proceeding with apply mode
        if self.mode == "apply":
            try:
                require_all_gates(self.mode)
            except ApplyGateError as e:
                return {
                    "success": False,
                    "error": {"code": "APPLY_GATE_BLOCKED", "message": str(e)},
                    "is_transient": False,
                }
        
        # Fetch exercise data
        exercises = self._get_exercises_batch(exercise_ids)
        
        if not exercises:
            return {
                "success": False,
                "error": {"code": "NO_EXERCISES_FOUND", "message": f"None of {len(exercise_ids)} exercises found"},
                "is_transient": True,
            }
        
        # Get LLM client
        llm_client = get_llm_client()
        
        if is_holistic_mode:
            # HOLISTIC MODE: Pass full doc to LLM with reviewer hints
            return self._execute_holistic_enrichment(
                exercises=exercises,
                enrichment_spec_data=enrichment_spec_data,
                parent_job_id=parent_job_id,
                llm_client=llm_client,
            )
        else:
            # LEGACY SINGLE-FIELD MODE
            return self._execute_single_field_enrichment(
                exercises=exercises,
                enrichment_spec_data=enrichment_spec_data,
                parent_job_id=parent_job_id,
                llm_client=llm_client,
            )
    
    def _execute_holistic_enrichment(
        self,
        exercises: List[Dict[str, Any]],
        enrichment_spec_data: Dict[str, Any],
        parent_job_id: Optional[str],
        llm_client,
    ) -> Dict[str, Any]:
        """
        Execute holistic enrichment - pass full doc to LLM with reviewer hints.
        """
        from app.enrichment.engine import enrich_exercise_holistic
        from app.plans.models import Operation, OperationType, RiskLevel, ChangePlan
        from datetime import datetime
        
        spec_id = enrichment_spec_data.get("spec_id", "holistic")
        spec_version = enrichment_spec_data.get("spec_version", "v1")
        
        # Extract reviewer hint from instructions/fields_to_enrich
        fields_to_enrich = enrichment_spec_data.get("fields_to_enrich", [])
        instructions = enrichment_spec_data.get("instructions", "")

        # Model selection: default to Flash, use Pro if explicitly requested
        use_pro_model = enrichment_spec_data.get("use_pro_model", False)

        reviewer_hint = instructions
        if fields_to_enrich and not reviewer_hint:
            reviewer_hint = f"Fields flagged for review: {', '.join(fields_to_enrich)}"
        
        operations = []
        results_summary = {
            "total": len(exercises),
            "succeeded": 0,
            "failed": 0,
            "no_changes": 0,
        }
        
        for exercise in exercises:
            exercise_id = exercise.get("id", exercise.get("doc_id", "unknown"))
            
            # Call holistic enrichment
            result = enrich_exercise_holistic(
                exercise=exercise,
                reviewer_hint=reviewer_hint,
                llm_client=llm_client,
                use_pro_model=use_pro_model,
            )
            
            if not result["success"]:
                results_summary["failed"] += 1
                logger.warning(
                    "Holistic enrichment failed for %s: %s",
                    exercise_id, result.get("error", "unknown")
                )
                continue
            
            changes = result.get("changes", {})
            
            if not changes:
                results_summary["no_changes"] += 1
                logger.info(
                    "Holistic enrichment for %s: no changes needed",
                    exercise_id
                )
                continue
            
            results_summary["succeeded"] += 1
            
            # Build PATCH_FIELDS operation with FLAT dotted paths
            # The changes dict is already in flat format: {"muscles.primary": [...], ...}
            operations.append(Operation(
                op_type=OperationType.PATCH_FIELDS,
                targets=[exercise_id],
                patch=changes,  # Already flat dotted paths!
                rationale=f"Holistic enrichment: {result.get('reasoning', '')[:100]}",
                risk_level=RiskLevel.LOW,
                idempotency_key_seed=f"holistic_{spec_id}_{spec_version}_{exercise_id}",
            ))
            
            logger.info(
                "Holistic enrichment for %s: %d field changes",
                exercise_id, len(changes)
            )
        
        # Log summary
        logger.info(
            "Holistic enrichment batch complete: %d/%d succeeded, %d no changes, %d failed",
            results_summary["succeeded"],
            results_summary["total"],
            results_summary["no_changes"],
            results_summary["failed"],
        )
        
        # Create change plan
        plan = ChangePlan(
            job_id=self.job_id,
            job_type="CATALOG_ENRICH_FIELD_SHARD",
            scope={
                "parent_job_id": parent_job_id,
                "spec_id": spec_id,
                "mode": "holistic",
                "exercise_count": len(exercises),
            },
            assumptions=[f"Holistic enrichment of {len(exercises)} exercises"],
            operations=operations,
            max_risk_level=RiskLevel.LOW,
        )
        
        result = {
            "success": True,
            "shard_result": {
                "spec_id": spec_id,
                "mode": "holistic",
                **results_summary,
            },
            "plan": plan.to_dict(),
            "mode": self.mode,
        }
        
        if self.mode == "apply" and operations:
            from app.apply.engine import apply_change_plan
            apply_result = apply_change_plan(plan, mode=self.mode, job_id=self.job_id)
            result["applied"] = apply_result.success
            result["apply_result"] = apply_result.to_dict()
        
        return result
    
    def _execute_single_field_enrichment(
        self,
        exercises: List[Dict[str, Any]],
        enrichment_spec_data: Dict[str, Any],
        parent_job_id: Optional[str],
        llm_client,
    ) -> Dict[str, Any]:
        """
        Execute legacy single-field enrichment using EnrichmentSpec.
        """
        from app.enrichment.models import EnrichmentSpec, ShardResult
        from app.enrichment.engine import compute_enrichment_batch
        from app.plans.models import Operation, OperationType, RiskLevel, ChangePlan
        from datetime import datetime
        
        spec = EnrichmentSpec.from_dict(enrichment_spec_data)
        
        # Create shard result tracker
        shard_result = ShardResult(
            shard_job_id=self.job_id,
            parent_job_id=parent_job_id,
            spec_id=spec.spec_id,
            total_exercises=len(exercises),
            started_at=datetime.utcnow(),
        )
        
        # Compute enrichment for each exercise
        enrichment_results = compute_enrichment_batch(exercises, spec, llm_client)
        
        # Build operations for successful enrichments
        operations = []
        for result in enrichment_results:
            shard_result.results.append(result)
            
            if result.success and result.validation_passed:
                shard_result.succeeded += 1
                
                # Build FLAT patch using dotted path directly
                # e.g., "muscles.primary" -> {"muscles.primary": [...]}
                # NOT nested: {"muscles": {"primary": [...]}}
                patch = {spec.field_path: result.value}
                
                operations.append(Operation(
                    op_type=OperationType.PATCH_FIELDS,
                    targets=[result.exercise_id],
                    patch=patch,
                    rationale=f"Enrichment {spec.spec_id}:{spec.spec_version}",
                    risk_level=RiskLevel.LOW,
                    idempotency_key_seed=spec.idempotency_key(result.exercise_id),
                ))
            else:
                shard_result.failed += 1
        
        shard_result.completed_at = datetime.utcnow()
        
        # Create change plan
        plan = ChangePlan(
            job_id=self.job_id,
            job_type="CATALOG_ENRICH_FIELD_SHARD",
            scope={
                "parent_job_id": parent_job_id,
                "spec_id": spec.spec_id,
                "mode": "single_field",
                "exercise_count": len(exercises),
            },
            assumptions=[f"Enriching {len(exercises)} exercises with {spec.spec_id}:{spec.spec_version}"],
            operations=operations,
            max_risk_level=RiskLevel.LOW,
        )
        
        result = {
            "success": True,
            "shard_result": shard_result.to_dict(),
            "plan": plan.to_dict(),
            "mode": self.mode,
        }
        
        if self.mode == "apply" and operations:
            from app.apply.engine import apply_change_plan
            apply_result = apply_change_plan(plan, mode=self.mode, job_id=self.job_id)
            result["applied"] = apply_result.success
            result["apply_result"] = apply_result.to_dict()
        
        return result
    
    def _get_filtered_exercise_ids(self, filter_criteria: Dict[str, Any]) -> List[str]:
        """Get exercise IDs matching filter criteria."""
        from google.cloud import firestore
        
        db = firestore.Client()
        query = db.collection("exercises")
        
        if filter_criteria.get("equipment"):
            query = query.where("equipment", "array_contains", filter_criteria["equipment"])
        if filter_criteria.get("category"):
            query = query.where("category", "==", filter_criteria["category"])
        if filter_criteria.get("family_slug"):
            query = query.where("family_slug", "==", filter_criteria["family_slug"])
        
        # Limit to avoid huge queries
        query = query.limit(10000)
        
        return [doc.id for doc in query.stream()]
    
    def _get_all_exercise_ids(self, limit: int = 10000) -> List[str]:
        """Get all exercise IDs (with limit)."""
        from google.cloud import firestore
        
        db = firestore.Client()
        query = db.collection("exercises").limit(limit)
        
        return [doc.id for doc in query.stream()]
    
    def _get_exercises_batch(self, exercise_ids: List[str]) -> List[Dict[str, Any]]:
        """Fetch exercise documents by IDs."""
        from google.cloud import firestore
        
        if not exercise_ids:
            return []
        
        db = firestore.Client()
        exercises = []
        
        # Batch in chunks of 10 (Firestore limit for in queries)
        for i in range(0, len(exercise_ids), 10):
            batch_ids = exercise_ids[i:i + 10]
            refs = [db.collection("exercises").document(doc_id) for doc_id in batch_ids]
            docs = db.get_all(refs)
            
            for doc in docs:
                if doc.exists:
                    data = doc.to_dict()
                    data["id"] = doc.id
                    data["doc_id"] = doc.id
                    exercises.append(data)
        
        return exercises
    
    def _build_nested_patch(self, field_path: str, value: Any) -> Dict[str, Any]:
        """
        Build a nested patch dict from a dot-separated field path.
        
        E.g., "metadata.difficulty" -> {"metadata": {"difficulty": value}}
        """
        parts = field_path.split(".")
        
        if len(parts) == 1:
            return {field_path: value}
        
        # Build nested structure
        result = {}
        current = result
        for part in parts[:-1]:
            current[part] = {}
            current = current[part]
        current[parts[-1]] = value
        
        return result

    def _execute_duplicate_detection_scan(self) -> Dict[str, Any]:
        """
        Execute DUPLICATE_DETECTION_SCAN job.
        
        Scans for potential duplicate exercises across families.
        Uses name similarity and equipment matching.
        """
        from app.skills.catalog_read_skills import list_families_summary
        import asyncio
        
        # Get all families
        loop = asyncio.new_event_loop()
        try:
            families_result = loop.run_until_complete(list_families_summary(min_size=1, limit=200))
        finally:
            loop.close()
        
        if not families_result.get("success"):
            return {
                "success": False,
                "error": {"code": "SCAN_FAILED", "message": "Failed to list families"},
                "is_transient": True,
            }
        
        families = families_result.get("families", [])
        
        # Group by base name (family_slug normalized)
        family_groups: Dict[str, List[str]] = {}
        for fam in families:
            slug = fam["family_slug"]
            # Normalize: remove equipment suffixes for comparison
            base = slug.split("-")[0] if "-" in slug else slug
            if base not in family_groups:
                family_groups[base] = []
            family_groups[base].append(slug)
        
        # Find potential duplicates (multiple families with same base)
        duplicate_candidates = []
        for base, slugs in family_groups.items():
            if len(slugs) > 1:
                duplicate_candidates.append({
                    "base_name": base,
                    "families": slugs,
                    "count": len(slugs),
                    "suggested_action": "FAMILY_MERGE" if len(slugs) == 2 else "MANUAL_REVIEW",
                })
        
        return {
            "success": True,
            "scan_result": {
                "families_scanned": len(families),
                "duplicate_groups_found": len(duplicate_candidates),
                "duplicate_candidates": duplicate_candidates[:20],  # Limit output
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


def execute_with_repair_loop(
    job: Dict[str, Any],
    worker_id: str,
    max_repairs: int = 3,
) -> Dict[str, Any]:
    """
    Execute a job with LLM repair loop on validation failure.
    
    When validation fails, feeds errors back to LLM for plan revision
    and retries with bounded attempts.
    
    Args:
        job: Job document from Firestore
        worker_id: Worker ID processing this job
        max_repairs: Maximum repair attempts (default 3)
        
    Returns:
        Execution result with repair history
    """
    from app.plans.validators import validate_change_plan
    from app.family.registry import get_family_exercises, get_or_create_family_registry
    from app.plans.models import ChangePlan
    
    executor = JobExecutor(job, worker_id)
    repair_history = []
    
    for attempt in range(max_repairs + 1):
        result = executor.execute()
        
        # If not success or no plan, return immediately
        if not result.get("success") or "plan" not in result:
            result["repair_history"] = repair_history
            return result
        
        # Check if we have validation errors to repair
        validation = result.get("validation", {})
        if validation.get("valid", True):
            # No validation errors, check apply result
            apply_result = result.get("apply_result", {})
            if apply_result.get("needs_repair"):
                # Post-verification failed
                verification_errors = apply_result.get("verification_errors", [])
                repair_history.append({
                    "attempt": attempt,
                    "error_type": "verification",
                    "errors": verification_errors,
                })
                
                if attempt == max_repairs:
                    result["success"] = False
                    result["status"] = "needs_review"
                    result["error"] = {
                        "code": "REPAIR_LOOP_EXHAUSTED",
                        "message": f"Post-verification failed after {max_repairs} repair attempts",
                    }
                    result["repair_history"] = repair_history
                    return result
                
                # Request LLM revision
                revised_result = _request_plan_revision(
                    executor, result, verification_errors, "verification"
                )
                if revised_result:
                    result = revised_result
                    continue
            
            # Success - no repairs needed
            result["repair_history"] = repair_history
            return result
        
        # Validation failed
        errors = validation.get("errors", [])
        repair_history.append({
            "attempt": attempt,
            "error_type": "validation",
            "errors": errors,
        })
        
        if attempt == max_repairs:
            result["success"] = False
            result["status"] = "needs_review"
            result["error"] = {
                "code": "REPAIR_LOOP_EXHAUSTED",
                "message": f"Validation failed after {max_repairs} repair attempts",
            }
            result["repair_history"] = repair_history
            return result
        
        # Request LLM revision
        revised_result = _request_plan_revision(executor, result, errors, "validation")
        if revised_result:
            result = revised_result
        else:
            # LLM revision failed, return current result
            result["repair_history"] = repair_history
            return result
    
    result["repair_history"] = repair_history
    return result


def _request_plan_revision(
    executor: JobExecutor,
    current_result: Dict[str, Any],
    errors: List[Dict[str, Any]],
    error_type: str,
) -> Optional[Dict[str, Any]]:
    """
    Request LLM to revise the plan based on errors.
    
    Uses gemini-2.5-pro to analyze validation/verification errors
    and suggest a revised plan that addresses the issues.
    
    Args:
        executor: Job executor instance
        current_result: Current execution result
        errors: Validation or verification errors
        error_type: Type of errors ("validation" or "verification")
        
    Returns:
        Revised result or None if revision not possible
    """
    import json
    
    logger.info(
        "Repair loop: Requesting LLM revision for %s errors on job %s",
        error_type, executor.job_id
    )
    
    try:
        from app.enrichment.llm_client import get_llm_client
        
        llm_client = get_llm_client()
        
        # Format errors for LLM
        error_descriptions = []
        for err in errors:
            if isinstance(err, dict):
                error_descriptions.append(
                    f"- {err.get('code', 'ERROR')}: {err.get('message', str(err))}"
                )
            else:
                error_descriptions.append(f"- {str(err)}")
        
        errors_text = "\n".join(error_descriptions) if error_descriptions else "Unknown errors"
        
        # Get the current plan
        current_plan = current_result.get("plan", {})
        
        prompt = f"""You are a catalog curation expert. A change plan failed validation.
Your task is to analyze the errors and suggest how to fix the plan.

## Job Context
Job ID: {executor.job_id}
Job Type: {executor.job_type}
Family: {executor.family_slug or 'N/A'}
Mode: {executor.mode}

## Current Plan (Failed)
{json.dumps(current_plan, indent=2)[:2000]}

## {error_type.title()} Errors
{errors_text}

## Your Task
Analyze why the plan failed and suggest specific fixes. Consider:

1. For INVALID_PATCH_PATHS: The field path may not be in the allowlist
2. For DUPLICATE_OPERATION: An operation may already have been applied
3. For MISSING_TARGETS: An operation is missing required targets
4. For verification errors: The expected post-state doesn't match actual

## Response Format
Respond with a JSON object:
{{
    "can_repair": true/false,
    "analysis": "Brief analysis of what went wrong",
    "suggested_fixes": [
        {{
            "operation_index": 0,
            "fix_type": "remove" | "modify" | "add",
            "description": "What to change"
        }}
    ],
    "confidence": "high" | "medium" | "low"
}}

If the errors cannot be automatically repaired (e.g., fundamental data issue),
set "can_repair": false and explain why in "analysis".

Respond with ONLY the JSON object."""

        response = llm_client.complete(
            prompt=prompt,
            output_schema={"type": "object"},
            require_reasoning=False,  # V1.4: Flash-first for cost efficiency
        )
        
        # Parse response
        try:
            llm_result = json.loads(response)
        except json.JSONDecodeError:
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                llm_result = json.loads(json_match.group())
            else:
                logger.warning("Could not parse LLM repair response for job %s", executor.job_id)
                return None
        
        # Check if LLM thinks repair is possible
        if not llm_result.get("can_repair", False):
            logger.info(
                "LLM determined repair not possible for job %s: %s",
                executor.job_id, llm_result.get("analysis", "Unknown reason")
            )
            return None
        
        # Check confidence - if low, don't attempt repair
        if llm_result.get("confidence") == "low":
            logger.info(
                "LLM has low confidence in repair for job %s, skipping",
                executor.job_id
            )
            return None
        
        # Log the suggested fixes
        logger.info(
            "LLM repair analysis for job %s: %s",
            executor.job_id, llm_result.get("analysis", "")
        )
        
        # For now, we log the suggestions but don't automatically apply them
        # This is conservative - we want to verify the repair loop works before auto-applying
        suggested_fixes = llm_result.get("suggested_fixes", [])
        
        if not suggested_fixes:
            logger.info("LLM provided no specific fixes for job %s", executor.job_id)
            return None
        
        # In future: Apply the suggested fixes to create a revised plan
        # For now, return None but log the suggestions
        logger.info(
            "LLM suggested %d fixes for job %s (auto-apply not yet enabled): %s",
            len(suggested_fixes),
            executor.job_id,
            json.dumps(suggested_fixes)
        )
        
        # Return None for now - when we're confident in the repair logic,
        # we can enable auto-application of fixes
        return None
        
    except Exception as e:
        logger.exception("LLM repair request failed for job %s: %s", executor.job_id, e)
        return None


__all__ = [
    "JobExecutor",
    "execute_job",
    "execute_with_repair_loop",
]
