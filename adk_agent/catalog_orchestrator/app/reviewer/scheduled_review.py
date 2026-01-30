"""
Scheduled Review - Production catalog review pipeline.

V1.4: Flash-first architecture for cost-efficient production use.
Uses gemini-2.5-flash for all operations:
- FIX_IDENTITY: Naming taxonomy violations
- MERGE: Duplicate detection and merging
- ARCHIVE: Unsalvageable exercises
- ENRICH: Holistic enrichment (description, muscles, etc.)
- GAP ANALYSIS: Equipment family expansion suggestions

Production workflow:
1. Review all exercises for quality issues
2. Queue enrichment jobs for missing fields (description, etc.)
3. Detect and suggest equipment variants for families
4. Handle user-added exercises automatically

Architecture:
- Uses gemini-2.5-flash for cost efficiency (~10x cheaper than Pro)
- Single LLM call per batch (not fragmented)
- Concurrent batch processing
- All decisions in one response

See also:
- scheduled_quality_scan.py: Tier 1 quality scanning (Flash)
- quality_scanner.py: Heuristic + Flash quality scoring
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

# V1.3: Cost-efficient review - skip recently reviewed high-quality exercises
QUALITY_THRESHOLD = 0.9  # Exercises with quality_score >= this are skipped
REVIEW_VERSION = "1.3"  # Bump when review logic changes significantly


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


def filter_exercises_for_review(
    exercises: List[Dict[str, Any]],
    quality_threshold: float = QUALITY_THRESHOLD,
    force_review: bool = False,
) -> List[Dict[str, Any]]:
    """
    Filter exercises to only include those flagged for full review.

    Multi-tier pipeline:
    - Tier 1 (quality_scanner) sets needs_full_review=true for complex issues
    - Tier 2 (this module) only processes flagged exercises

    Args:
        exercises: All fetched exercises
        quality_threshold: Fallback threshold if not scanned by Tier 1
        force_review: If True, review all exercises regardless of flags

    Returns:
        List of exercises that need full review
    """
    if force_review:
        logger.info("Force review enabled - including all %d exercises", len(exercises))
        return exercises

    needs_review = []
    skipped_not_flagged = 0
    skipped_high_quality = 0
    not_scanned = 0

    for ex in exercises:
        review_meta = ex.get("review_metadata", {})

        # Check if scanned by Tier 1 quality scanner
        scanner_version = review_meta.get("scanner_version")

        if scanner_version:
            # Tier 1 has scanned this exercise - check the flag
            needs_full_review = review_meta.get("needs_full_review", False)
            if needs_full_review:
                needs_review.append(ex)
            else:
                skipped_not_flagged += 1
        else:
            # Not scanned by Tier 1 yet - use legacy quality threshold
            quality_score = review_meta.get("quality_score", 0)
            review_version = review_meta.get("review_version", "")

            # Skip if already reviewed with current version and high quality
            if review_version == REVIEW_VERSION and quality_score >= quality_threshold:
                skipped_high_quality += 1
                continue

            # Include unscanned exercises for review (legacy mode)
            needs_review.append(ex)
            not_scanned += 1

    logger.info(
        "Filtered for full review: %d need review (%d not scanned by Tier 1), "
        "%d skipped (not flagged), %d skipped (high quality), %d total",
        len(needs_review),
        not_scanned,
        skipped_not_flagged,
        skipped_high_quality,
        len(exercises),
    )

    return needs_review


def save_review_metadata(
    db,
    decisions: List[ExerciseDecision],
    dry_run: bool = True,
) -> Dict[str, int]:
    """
    Save review metadata back to Firestore using batched writes.

    Updates each exercise with:
    - review_metadata.last_reviewed_at: timestamp
    - review_metadata.review_version: current version
    - review_metadata.quality_score: from LLM decision
    - review_metadata.needs_review: False (reviewed) or True (needs action)
    - review_metadata.needs_full_review: False (reviewed by Pro)

    Args:
        db: Firestore client
        decisions: List of ExerciseDecision from review
        dry_run: If True, don't actually update Firestore

    Returns:
        Summary of updates made
    """
    if not db:
        logger.warning("No Firestore client - cannot save review metadata")
        return {"updated": 0, "errors": 0}

    updated = 0
    errors = 0
    now = datetime.now(timezone.utc)

    # Firestore batch limit is 500 operations
    BATCH_SIZE = 400

    if dry_run:
        for decision in decisions:
            if not decision.exercise_id:
                continue
            logger.debug(
                "Would update %s with review_metadata: quality_score=%.2f",
                decision.exercise_id,
                decision.quality_score,
            )
            updated += 1
    else:
        # Process in batches for efficiency
        batch = db.batch()
        batch_count = 0

        for decision in decisions:
            if not decision.exercise_id:
                continue

            # Build review_metadata update
            review_metadata = {
                "review_metadata.last_reviewed_at": now,
                "review_metadata.review_version": REVIEW_VERSION,
                "review_metadata.quality_score": decision.quality_score,
                # needs_review = True if action needed (not KEEP), False if good
                "review_metadata.needs_review": decision.decision != "KEEP",
                # Clear the needs_full_review flag since Pro has reviewed it
                "review_metadata.needs_full_review": False,
            }

            doc_ref = db.collection("exercises").document(decision.exercise_id)
            batch.update(doc_ref, review_metadata)
            batch_count += 1
            updated += 1

            # Commit batch when it reaches the limit
            if batch_count >= BATCH_SIZE:
                try:
                    batch.commit()
                    logger.debug("Committed batch of %d updates", batch_count)
                except Exception as e:
                    logger.warning("Batch commit failed: %s", e)
                    errors += batch_count
                    updated -= batch_count
                batch = db.batch()
                batch_count = 0

        # Commit remaining
        if batch_count > 0:
            try:
                batch.commit()
                logger.debug("Committed final batch of %d updates", batch_count)
            except Exception as e:
                logger.warning("Final batch commit failed: %s", e)
                errors += batch_count
                updated -= batch_count

    logger.info(
        "Review metadata: updated=%d, errors=%d, dry_run=%s",
        updated,
        errors,
        dry_run,
    )

    return {"updated": updated, "errors": errors}


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
        
        # V1.3: Gaps are informational only - NO auto-creation of exercises
        # Just log and track gaps for the summary, but don't create EXERCISE_ADD jobs
        for gap in batch.gaps:
            gap_info = {
                "family_slug": gap.family_slug,
                "suggested_name": gap.suggested_name,
                "missing_equipment": gap.missing_equipment,
                "confidence": gap.confidence,
                "reasoning": gap.reasoning,
                "status": "informational_only",
            }
            jobs_created["add_exercise"].append(gap_info)

        if batch.gaps:
            logger.info(
                "Detected %d equipment gaps (informational only, no auto-creation)",
                len(batch.gaps),
            )
    
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
    force_review: bool = False,  # V1.3: Force review all, ignoring quality filter
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
        force_review: If True, review all exercises (ignore quality filter)

    Returns:
        Summary of review and jobs created
    """
    start_time = datetime.now(timezone.utc)
    logger.info(
        "Starting scheduled review: max_exercises=%d, batch_size=%d, dry_run=%s, gap_analysis=%s, force=%s",
        max_exercises, batch_size, dry_run, run_gap_analysis, force_review
    )

    db = _get_firestore_client()

    # Fetch all exercises
    all_exercises = fetch_all_exercises(db, max_exercises)

    # V1.3: Filter to only exercises that need review (cost optimization)
    exercises = filter_exercises_for_review(
        all_exercises,
        quality_threshold=QUALITY_THRESHOLD,
        force_review=force_review,
    )
    
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

    # V1.3: Save review metadata back to Firestore (quality scores, timestamps)
    all_decisions = []
    for batch in batch_results:
        all_decisions.extend(batch.decisions)

    metadata_result = save_review_metadata(db, all_decisions, dry_run=dry_run)

    end_time = datetime.now(timezone.utc)
    duration_secs = (end_time - start_time).total_seconds()

    summary = {
        "started_at": start_time.isoformat(),
        "completed_at": end_time.isoformat(),
        "duration_seconds": duration_secs,
        "dry_run": dry_run,
        "review_version": REVIEW_VERSION,
        "review": {
            "total_fetched": len(all_exercises),
            "total_reviewed": total_reviewed,
            "skipped_high_quality": len(all_exercises) - len(exercises),
            "decisions": {
                "keep": total_keep,
                "enrich": total_enrich,
                "fix_identity": total_fix,
                "archive": total_archive,
                "merge": total_merge,
            },
            "gaps_detected": total_gaps,
            "duplicates_found": total_duplicates,
        },
        "jobs": {
            "total_created": job_result["total_jobs"],
            "by_type": job_result["by_type"],
            "dry_run": dry_run,
        },
        "review_metadata": {
            "updated": metadata_result["updated"],
            "errors": metadata_result["errors"],
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
        "--force-review", action="store_true",
        help="Force review all exercises (ignore quality-based filtering)"
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
        force_review=args.force_review,
    )
    
    # Print summary
    print("\n" + "=" * 60)
    print("SCHEDULED REVIEW SUMMARY")
    print("=" * 60)
    print(json.dumps(summary, indent=2))
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
