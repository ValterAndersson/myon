"""
Scheduled Quality Scan - Cloud Run Job entrypoint for Tier 1 quality scanning.

This is the first tier of the multi-tier review pipeline:
1. Fetches exercises from Firestore
2. Applies heuristic pre-filter (no LLM cost)
3. Scans remaining with Flash LLM
4. Saves quality scores and flags to Firestore
5. Creates ENRICH jobs for exercises with enrichable issues:
   - missing_fields: missing content arrays (from LLM scan)
   - content_style: style violations or missing content (from heuristic checks 13-14)

Exercises flagged with needs_full_review=true are handled by
the Tier 2 full review (scheduled_review.py with Pro model).

Exercises flagged with needs_enrichment_only=true bypass Pro review
entirely and get enrichment jobs created here (Flash model only).

Usage:
    python -m app.reviewer.scheduled_quality_scan --dry-run
    python -m app.reviewer.scheduled_quality_scan --apply
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.reviewer.quality_scanner import (
    QualityScanner,
    QualityScanResult,
    QualityScanBatchResult,
    save_scan_results,
    SCANNER_VERSION,
)
from app.jobs.models import JobType, JobQueue

logger = logging.getLogger(__name__)

# Configuration
DEFAULT_MAX_EXERCISES = 1000
DEFAULT_BATCH_SIZE = 50
DEFAULT_MAX_JOBS = 200


def _get_firestore_client():
    """Get Firestore client."""
    try:
        from google.cloud import firestore

        emulator_host = os.environ.get("FIRESTORE_EMULATOR_HOST")
        if emulator_host:
            logger.info("Using Firestore emulator at %s", emulator_host)
            return firestore.Client(project="demo-povver")

        return firestore.Client()
    except Exception as e:
        logger.warning("Failed to get Firestore client: %s", e)
        return None


def fetch_exercises_for_scan(
    db,
    max_exercises: int = 1000,
    force_rescan: bool = False,
) -> List[Dict[str, Any]]:
    """
    Fetch exercises that need quality scanning.

    Filters out exercises that were recently scanned with current scanner version
    unless force_rescan is True.
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

            # Skip if recently scanned with current version (unless force)
            if not force_rescan:
                review_meta = data.get("review_metadata", {})
                scanner_version = review_meta.get("scanner_version")
                if scanner_version == SCANNER_VERSION:
                    continue

            exercises.append(data)

        last_doc = docs[-1]

        if len(docs) < batch_size:
            break

    logger.info("Fetched %d exercises for quality scan", len(exercises))
    return exercises


def create_enrich_jobs_from_scan(
    results: List[QualityScanResult],
    exercises: List[Dict[str, Any]],
    dry_run: bool = True,
    max_jobs: int = 100,
) -> Dict[str, Any]:
    """
    Create ENRICH jobs for exercises that need enrichment.

    Covers two issue types:
    - missing_fields: exercises missing content arrays (from LLM scan)
    - content_style: exercises with style violations or missing content (from heuristic)

    Both use Flash model via the enrichment worker — no Pro review needed.
    Deduplicates against pending jobs to avoid double-queuing.
    """
    from app.jobs.queue import create_job, find_pending_jobs_batch

    # Build exercise lookup
    exercise_lookup: Dict[str, Dict[str, Any]] = {}
    for ex in exercises:
        ex_id = ex.get("id") or ex.get("doc_id", "")
        if ex_id:
            exercise_lookup[ex_id] = ex

    # Filter to enrichment-eligible results
    enrichable = [
        r for r in results
        if r.issue_type in ("missing_fields", "content_style")
        or r.needs_enrichment_only
    ]

    if not enrichable:
        return {"total_jobs": 0, "dry_run": dry_run, "skipped_duplicate": 0, "jobs": []}

    # Deduplicate: skip exercises that already have a pending enrichment job
    candidate_ids = [r.exercise_id for r in enrichable if r.exercise_id]
    already_pending = find_pending_jobs_batch(JobType.CATALOG_ENRICH_FIELD, candidate_ids)
    skipped_duplicate = 0

    jobs_created = []
    total_jobs = 0

    for result in enrichable:
        if total_jobs >= max_jobs:
            break

        if result.exercise_id in already_pending:
            skipped_duplicate += 1
            continue

        ex_data = exercise_lookup.get(result.exercise_id, {})
        family_slug = ex_data.get("family_slug", "")

        job_info = {
            "exercise_id": result.exercise_id,
            "exercise_name": result.exercise_name,
            "family_slug": family_slug,
            "quality_score": result.quality_score,
            "issue_type": result.issue_type,
        }

        if not dry_run:
            try:
                job = create_job(
                    job_type=JobType.CATALOG_ENRICH_FIELD,
                    queue=JobQueue.MAINTENANCE,
                    priority=40,
                    mode="apply",
                    exercise_doc_ids=[result.exercise_id],
                    enrichment_spec={
                        "type": "enrich_content",
                        "source": "quality_scanner",
                        "issue_type": result.issue_type,
                        "quality_score": result.quality_score,
                        "details": result.details,
                    },
                )
                job_info["job_id"] = job.id
                total_jobs += 1
            except Exception as e:
                logger.warning("Failed to create job for %s: %s", result.exercise_id, e)
                job_info["error"] = str(e)
        else:
            job_info["job_id"] = f"dry-run-enrich-{result.exercise_id}"
            total_jobs += 1

        jobs_created.append(job_info)

    if skipped_duplicate:
        logger.info("Skipped %d exercises with pending enrichment jobs", skipped_duplicate)

    return {
        "total_jobs": total_jobs,
        "dry_run": dry_run,
        "skipped_duplicate": skipped_duplicate,
        "jobs": jobs_created,
    }


def run_quality_scan(
    max_exercises: int = DEFAULT_MAX_EXERCISES,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_jobs: int = DEFAULT_MAX_JOBS,
    dry_run: bool = True,
    force_rescan: bool = False,
    create_jobs: bool = True,
) -> Dict[str, Any]:
    """
    Run the Tier 1 quality scan.

    Args:
        max_exercises: Maximum exercises to scan
        batch_size: Exercises per LLM batch
        max_jobs: Maximum ENRICH jobs to create
        dry_run: If True, don't save results or create jobs
        force_rescan: If True, rescan all exercises (ignore scanner_version)
        create_jobs: If True, create ENRICH jobs for missing_fields

    Returns:
        Summary of scan results
    """
    start_time = datetime.now(timezone.utc)
    logger.info(
        "Starting quality scan: max_exercises=%d, batch_size=%d, dry_run=%s, force=%s",
        max_exercises, batch_size, dry_run, force_rescan,
    )

    db = _get_firestore_client()

    # Fetch exercises
    exercises = fetch_exercises_for_scan(db, max_exercises, force_rescan)

    if not exercises:
        logger.info("No exercises need scanning")
        return {
            "started_at": start_time.isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": 0,
            "dry_run": dry_run,
            "scanner_version": SCANNER_VERSION,
            "scan": {"total_scanned": 0},
            "jobs": {"total_created": 0},
        }

    # Run quality scan
    scanner = QualityScanner(batch_size=batch_size)
    scan_result = scanner.scan_batch(exercises)

    # Save results to Firestore
    save_result = save_scan_results(db, scan_result.results, dry_run=dry_run)

    # Create ENRICH jobs for enrichable exercises (missing_fields + content_style)
    job_result = {"total_jobs": 0, "dry_run": dry_run, "skipped_duplicate": 0, "jobs": []}
    if create_jobs:
        job_result = create_enrich_jobs_from_scan(
            scan_result.results,
            exercises,
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
        "scanner_version": SCANNER_VERSION,
        "scan": {
            "total_scanned": scan_result.total_scanned,
            "heuristic_passed": scan_result.heuristic_passed,
            "llm_scanned": scan_result.llm_scanned,
            "needs_full_review": scan_result.needs_full_review,
            "needs_enrichment_only": scan_result.needs_enrichment_only,
            "by_issue_type": scan_result._count_by_issue_type(),
        },
        "save": {
            "updated": save_result["updated"],
            "errors": save_result["errors"],
        },
        "jobs": {
            "total_created": job_result["total_jobs"],
            "dry_run": dry_run,
        },
    }

    logger.info(
        "Quality scan complete: %d scanned (%d heuristic, %d LLM), "
        "%d need full review, %d enrichment-only, %d jobs (%d skipped dup) in %.1fs",
        scan_result.total_scanned,
        scan_result.heuristic_passed,
        scan_result.llm_scanned,
        scan_result.needs_full_review,
        scan_result.needs_enrichment_only,
        job_result["total_jobs"],
        job_result.get("skipped_duplicate", 0),
        duration_secs,
    )

    return summary


def main():
    """CLI entrypoint for scheduled quality scan."""
    parser = argparse.ArgumentParser(description="Run Tier 1 quality scan")
    parser.add_argument(
        "--max-exercises", type=int, default=DEFAULT_MAX_EXERCISES,
        help="Maximum exercises to scan"
    )
    parser.add_argument(
        "--batch-size", type=int, default=DEFAULT_BATCH_SIZE,
        help="Exercises per LLM batch"
    )
    parser.add_argument(
        "--max-jobs", type=int, default=DEFAULT_MAX_JOBS,
        help="Maximum ENRICH jobs to create"
    )
    parser.add_argument(
        "--dry-run", action="store_true", default=True,
        help="Dry run mode (default: True)"
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Actually save results and create jobs"
    )
    parser.add_argument(
        "--force-rescan", action="store_true",
        help="Rescan all exercises (ignore scanner_version)"
    )
    parser.add_argument(
        "--skip-jobs", action="store_true",
        help="Don't create ENRICH jobs"
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

    # Run scan
    dry_run = not args.apply
    summary = run_quality_scan(
        max_exercises=args.max_exercises,
        batch_size=args.batch_size,
        max_jobs=args.max_jobs,
        dry_run=dry_run,
        force_rescan=args.force_rescan,
        create_jobs=not args.skip_jobs,
    )

    # Print summary
    print("\n" + "=" * 60)
    print("QUALITY SCAN SUMMARY")
    print("=" * 60)
    print(json.dumps(summary, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
