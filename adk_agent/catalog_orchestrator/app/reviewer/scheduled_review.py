"""
Scheduled Review - Cloud Run Job entrypoint for periodic catalog reviews.

This module provides the scheduled review runner that uses the unified
CatalogReviewAgent to:
1. Page through the catalog in batches
2. Review exercises for health (KEEP, ENRICH, FIX, ARCHIVE, MERGE)
3. Detect duplicates
4. Analyze equipment gaps
5. Create jobs for all decisions
6. Report summary metrics

Architecture:
- Single LLM call per batch (not fragmented)
- Concurrent batch processing
- All decisions in one response
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.reviewer.review_agent import (
    CatalogReviewAgent,
    BatchReviewResult,
    ExerciseDecision,
    review_catalog,
)
from app.jobs.models import JobType, JobQueue

logger = logging.getLogger(__name__)

# Configuration
# V1.2: Reverted batch_size to 20 for better LLM response parsing stability
# Larger batches (50) caused JSON parsing failures in 80% of batches
DEFAULT_BATCH_SIZE = 20  # Stable batch size - larger values cause LLM truncation issues
DEFAULT_MAX_EXERCISES = 1000  # Review full catalog
DEFAULT_MAX_JOBS = 500  # Create more jobs per run


def _get_firestore_client():
    """Get Firestore client for catalog reads."""
    try:
        from google.cloud import firestore
        
        # Check if using emulator - use demo project for emulator
        emulator_host = os.environ.get("FIRESTORE_EMULATOR_HOST")
        if emulator_host:
            logger.info("Using Firestore emulator at %s", emulator_host)
            return firestore.Client(project="demo-povver")
        
        # Production - use default ADC project
        return firestore.Client()
    except Exception as e:
        logger.warning("Failed to get Firestore client: %s", e)
        return None


def fetch_all_exercises(
    db,
    max_exercises: int = 500,
) -> List[Dict[str, Any]]:
    """
    Fetch exercises from Firestore.
    
    Args:
        db: Firestore client
        max_exercises: Maximum exercises to fetch
        
    Returns:
        List of exercise dicts
    """
    if not db:
        return []
    
    exercises = []
    last_doc = None
    
    while len(exercises) < max_exercises:
        batch_size = min(500, max_exercises - len(exercises))
        query = db.collection("exercises").order_by("name").limit(batch_size)
        
        if last_doc:
            query = query.start_after(last_doc)
        
        docs = list(query.stream())
        
        if not docs:
            break
        
        for doc in docs:
            data = doc.to_dict()
            data["id"] = doc.id
            data["doc_id"] = doc.id
            exercises.append(data)
        
        last_doc = docs[-1]
        
        if len(docs) < batch_size:
            break
    
    logger.info("Fetched %d exercises from Firestore", len(exercises))
    return exercises


def create_jobs_from_decisions(
    batch_results: List[BatchReviewResult],
    exercises: List[Dict[str, Any]],
    dry_run: bool = True,
    max_jobs: int = 100,
) -> Dict[str, Any]:
    """
    Create jobs from review agent decisions.
    
    Args:
        batch_results: List of BatchReviewResult from review agent
        exercises: Original exercise data (for lookup)
        dry_run: If True, don't actually create jobs
        max_jobs: Maximum jobs to create
        
    Returns:
        Summary of jobs created
    """
    from app.jobs.queue import create_job
    
    # Determine job mode based on dry_run flag
    job_mode = "dry_run" if dry_run else "apply"
    
    # Build exercise lookup for family_slug extraction
    exercise_lookup: Dict[str, Dict[str, Any]] = {}
    for ex in exercises:
        ex_id = ex.get("id") or ex.get("doc_id", "")
        if ex_id:
            exercise_lookup[ex_id] = ex
    
    jobs_created = {
        "enrich": [],
        "fixidentity": [],
        "archive": [],
        "merge": [],
        "add_exercise": [],
    }
    total_jobs = 0
    
    # Process all batch results
    for batch in batch_results:
        for decision in batch.decisions:
            if total_jobs >= max_jobs:
                break
            
            if decision.decision == "KEEP":
                continue
            
            # Get exercise data for family_slug
            ex_data = exercise_lookup.get(decision.exercise_id, {})
            family_slug = ex_data.get("family_slug", "")
            
            job_info = {
                "exercise_id": decision.exercise_id,
                "exercise_name": decision.exercise_name,
                "family_slug": family_slug,
                "decision": decision.decision,
                "confidence": decision.confidence,
                "reasoning": decision.reasoning,
            }
            
            if not dry_run:
                try:
                    if decision.decision == "ENRICH":
                        job = create_job(
                            job_type=JobType.CATALOG_ENRICH_FIELD,
                            queue=JobQueue.MAINTENANCE,
                            priority=50,
                            mode=job_mode,
                            exercise_doc_ids=[decision.exercise_id],
                            enrichment_spec={
                                "type": "full_enrich",
                                "reason": decision.reasoning,
                            },
                        )
                        job_info["job_id"] = job.id
                        jobs_created["enrich"].append(job_info)
                        
                    elif decision.decision == "FIX_IDENTITY":
                        # FIX_IDENTITY -> TARGETED_FIX (not FAMILY_NORMALIZE)
                        # TARGETED_FIX handles individual exercise fixes
                        job = create_job(
                            job_type=JobType.TARGETED_FIX,
                            queue=JobQueue.PRIORITY,
                            priority=70,
                            mode=job_mode,
                            family_slug=family_slug or None,
                            exercise_doc_ids=[decision.exercise_id],
                            enrichment_spec={
                                "type": "fix_identity",
                                "fix_details": decision.fix_details,
                                "reason": decision.reasoning,
                            },
                        )
                        job_info["job_id"] = job.id
                        jobs_created["fixidentity"].append(job_info)
                        
                    elif decision.decision == "ARCHIVE":
                        job = create_job(
                            job_type=JobType.TARGETED_FIX,
                            queue=JobQueue.MAINTENANCE,
                            priority=30,
                            mode=job_mode,
                            exercise_doc_ids=[decision.exercise_id],
                            enrichment_spec={
                                "type": "archive",
                                "reason": decision.reasoning,
                            },
                        )
                        job_info["job_id"] = job.id
                        jobs_created["archive"].append(job_info)
                        
                    elif decision.decision == "MERGE":
                        # MERGE -> TARGETED_FIX with merge details
                        # Full FAMILY_MERGE is complex and needs manual review
                        job = create_job(
                            job_type=JobType.TARGETED_FIX,
                            queue=JobQueue.PRIORITY,
                            priority=60,
                            mode=job_mode,
                            family_slug=family_slug or None,
                            exercise_doc_ids=[decision.exercise_id],
                            enrichment_spec={
                                "type": "merge_candidate",
                                "merge_into": decision.merge_into,
                                "reason": decision.reasoning,
                            },
                        )
                        job_info["job_id"] = job.id
                        jobs_created["merge"].append(job_info)
                    
                    total_jobs += 1
                    
                except Exception as e:
                    logger.exception("Failed to create job for %s: %s", decision.exercise_id, e)
                    job_info["error"] = str(e)
            else:
                # Dry-run: just record what would be created
                job_info["job_id"] = f"dry-run-{decision.decision.lower()}-{decision.exercise_id}"
                jobs_created[decision.decision.lower().replace("_", "")].append(job_info)
                total_jobs += 1
        
        # Process gaps (suggested new exercises)
        # First, get Firestore client and import helpers for duplicate check
        from app.family.taxonomy import derive_name_slug, derive_canonical_name
        from google.cloud import firestore as fs
        from google.cloud.firestore_v1 import FieldFilter
        
        gap_db = fs.Client() if not dry_run else None
        
        for gap in batch.gaps:
            if total_jobs >= max_jobs:
                break
            
            job_info = {
                "family_slug": gap.family_slug,
                "suggested_name": gap.suggested_name,
                "missing_equipment": gap.missing_equipment,
                "confidence": gap.confidence,
                "reasoning": gap.reasoning,
            }
            
            # Compute expected slug and check for duplicates
            if not dry_run and gap_db:
                exercise_name = derive_canonical_name(gap.suggested_name, gap.missing_equipment)
                expected_slug = derive_name_slug(exercise_name)
                
                # Check if exercise with this slug already exists
                query = gap_db.collection('exercises').where(
                    filter=FieldFilter('name_slug', '==', expected_slug)
                ).limit(1)
                existing_docs = list(query.stream())
                
                if existing_docs:
                    existing_doc_id = existing_docs[0].id
                    logger.info(
                        "Skipping EXERCISE_ADD gap for '%s' (slug: %s) - already exists: %s",
                        gap.suggested_name, expected_slug, existing_doc_id
                    )
                    job_info["skipped"] = True
                    job_info["skip_reason"] = f"Exercise already exists: {existing_doc_id}"
                    jobs_created["add_exercise"].append(job_info)
                    continue
            
            if not dry_run:
                try:
                    job = create_job(
                        job_type=JobType.EXERCISE_ADD,
                        queue=JobQueue.MAINTENANCE,
                        priority=30,
                        mode=job_mode,
                        family_slug=gap.family_slug,
                        intent={
                            "base_name": gap.suggested_name,
                            "equipment": [gap.missing_equipment],
                            "source": "unified_review_agent",
                        },
                    )
                    job_info["job_id"] = job.id
                    total_jobs += 1
                except Exception as e:
                    logger.exception("Failed to create gap job: %s", e)
                    job_info["error"] = str(e)
            else:
                job_info["job_id"] = f"dry-run-gap-{gap.family_slug}-{gap.missing_equipment}"
                total_jobs += 1
            
            jobs_created["add_exercise"].append(job_info)
    
    return {
        "total_jobs": total_jobs,
        "dry_run": dry_run,
        "jobs": jobs_created,
        "by_type": {
            "enrich": len(jobs_created["enrich"]),
            "fix_identity": len(jobs_created["fixidentity"]),
            "archive": len(jobs_created["archive"]),
            "merge": len(jobs_created["merge"]),
            "add_exercise": len(jobs_created["add_exercise"]),
        },
    }


def run_scheduled_review(
    max_exercises: int = DEFAULT_MAX_EXERCISES,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_jobs: int = DEFAULT_MAX_JOBS,
    dry_run: bool = True,
    run_gap_analysis: bool = True,
    enable_llm_review: bool = True,  # Now True by default since we're LLM-first
) -> Dict[str, Any]:
    """
    Run a scheduled catalog review using the unified LLM review agent.
    
    Args:
        max_exercises: Maximum exercises to review
        batch_size: Exercises per LLM batch
        max_jobs: Maximum jobs to create
        dry_run: If True, don't create jobs
        run_gap_analysis: If True, include gap suggestions in review
        enable_llm_review: Must be True for unified agent
        
    Returns:
        Summary of review and jobs created
    """
    start_time = datetime.now(timezone.utc)
    logger.info(
        "Starting scheduled review: max_exercises=%d, batch_size=%d, dry_run=%s, gap_analysis=%s",
        max_exercises, batch_size, dry_run, run_gap_analysis
    )
    
    db = _get_firestore_client()
    
    # Fetch all exercises
    exercises = fetch_all_exercises(db, max_exercises)
    
    if not exercises:
        logger.warning("No exercises found to review")
        return {
            "started_at": start_time.isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": 0,
            "dry_run": dry_run,
            "review": {"total_reviewed": 0},
            "jobs": {"total_created": 0},
        }
    
    # Run unified review agent
    batch_results = review_catalog(
        exercises=exercises,
        batch_size=batch_size,
        include_gap_analysis=run_gap_analysis,
    )
    
    # Aggregate results
    total_reviewed = sum(r.exercises_reviewed for r in batch_results)
    total_keep = sum(r.keep_count for r in batch_results)
    total_enrich = sum(r.enrich_count for r in batch_results)
    total_fix = sum(r.fix_count for r in batch_results)
    total_archive = sum(r.archive_count for r in batch_results)
    total_merge = sum(r.merge_count for r in batch_results)
    total_gaps = sum(len(r.gaps) for r in batch_results)
    total_duplicates = sum(len(r.duplicates) for r in batch_results)
    
    logger.info(
        "Review complete: %d exercises | KEEP=%d ENRICH=%d FIX=%d ARCHIVE=%d MERGE=%d | %d gaps",
        total_reviewed, total_keep, total_enrich, total_fix, total_archive, total_merge, total_gaps
    )
    
    # Create jobs from decisions
    job_result = create_jobs_from_decisions(
        batch_results,
        exercises=exercises,
        dry_run=dry_run,
        max_jobs=max_jobs,
    )
    
    end_time = datetime.now(timezone.utc)
    duration_secs = (end_time - start_time).total_seconds()
    
    summary = {
        "started_at": start_time.isoformat(),
        "completed_at": end_time.isoformat(),
        "duration_seconds": duration_secs,
        "dry_run": dry_run,
        "review": {
            "total_reviewed": total_reviewed,
            "decisions": {
                "keep": total_keep,
                "enrich": total_enrich,
                "fix_identity": total_fix,
                "archive": total_archive,
                "merge": total_merge,
            },
            "gaps_suggested": total_gaps,
            "duplicates_found": total_duplicates,
        },
        "jobs": {
            "total_created": job_result["total_jobs"],
            "by_type": job_result["by_type"],
            "dry_run": dry_run,
        },
    }
    
    logger.info(
        "Scheduled review complete: reviewed %d exercises, created %d jobs in %.1f seconds",
        total_reviewed,
        job_result["total_jobs"],
        duration_secs,
    )
    
    return summary


def main():
    """CLI entrypoint for scheduled review."""
    parser = argparse.ArgumentParser(description="Run scheduled catalog review")
    parser.add_argument(
        "--max-exercises", type=int, default=DEFAULT_MAX_EXERCISES,
        help="Maximum exercises to review"
    )
    parser.add_argument(
        "--batch-size", type=int, default=DEFAULT_BATCH_SIZE,
        help="Exercises per LLM batch"
    )
    parser.add_argument(
        "--max-jobs", type=int, default=DEFAULT_MAX_JOBS,
        help="Maximum jobs to create"
    )
    parser.add_argument(
        "--dry-run", action="store_true", default=True,
        help="Dry run mode (default: True)"
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Actually create jobs (disables dry-run)"
    )
    parser.add_argument(
        "--skip-gap-analysis", action="store_true",
        help="Skip equipment gap analysis"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Verbose logging"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # Run review
    dry_run = not args.apply
    summary = run_scheduled_review(
        max_exercises=args.max_exercises,
        batch_size=args.batch_size,
        max_jobs=args.max_jobs,
        dry_run=dry_run,
        run_gap_analysis=not args.skip_gap_analysis,
    )
    
    # Print summary
    print("\n" + "=" * 60)
    print("SCHEDULED REVIEW SUMMARY")
    print("=" * 60)
    print(json.dumps(summary, indent=2))
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
