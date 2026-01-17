"""
Scheduled Review - Cloud Run Job entrypoint for periodic catalog reviews.

This module provides the scheduled review runner that:
1. Pages through the catalog in batches
2. Reviews exercises for quality issues
3. Creates jobs for exercises needing improvement
4. Reports summary metrics
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.reviewer.catalog_reviewer import CatalogReviewer, BatchReviewResult
from app.reviewer.review_job_creator import create_jobs_from_review

logger = logging.getLogger(__name__)

# Configuration
DEFAULT_BATCH_SIZE = 50
DEFAULT_MAX_EXERCISES = 500
DEFAULT_MAX_JOBS = 100


def _get_firestore_client():
    """Get Firestore client for catalog reads."""
    try:
        from google.cloud import firestore
        return firestore.Client()
    except Exception as e:
        logger.warning("Failed to get Firestore client: %s", e)
        return None


def fetch_exercises_page(
    db,
    limit: int = 50,
    start_after: Optional[str] = None,
    filter_unnormalized: bool = False,
) -> List[Dict[str, Any]]:
    """
    Fetch a page of exercises from Firestore.
    
    Args:
        db: Firestore client
        limit: Maximum exercises per page
        start_after: Document name to start after (for pagination)
        filter_unnormalized: If True, only return exercises without family_slug
    """
    if not db:
        return []
    
    query = db.collection("exercises").order_by("name").limit(limit)
    
    if start_after:
        query = query.start_after({"name": start_after})
    
    docs = query.get()
    exercises = []
    
    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id
        
        # Apply filter if requested
        if filter_unnormalized and data.get("family_slug"):
            continue
        
        exercises.append(data)
    
    return exercises


def run_scheduled_review(
    max_exercises: int = DEFAULT_MAX_EXERCISES,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_jobs: int = DEFAULT_MAX_JOBS,
    dry_run: bool = True,
    filter_unnormalized: bool = False,
) -> Dict[str, Any]:
    """
    Run a scheduled catalog review.
    
    Args:
        max_exercises: Maximum exercises to review
        batch_size: Exercises per batch
        max_jobs: Maximum jobs to create
        dry_run: If True, don't create jobs
        filter_unnormalized: If True, only review unnormalized exercises
        
    Returns:
        Summary of review and jobs created
    """
    start_time = datetime.now(timezone.utc)
    logger.info(
        "Starting scheduled review: max_exercises=%d, batch_size=%d, dry_run=%s",
        max_exercises, batch_size, dry_run
    )
    
    db = _get_firestore_client()
    reviewer = CatalogReviewer(dry_run=dry_run)
    
    # Aggregate results
    all_results = BatchReviewResult()
    last_name = None
    total_fetched = 0
    
    # Page through catalog
    while total_fetched < max_exercises:
        # Fetch batch
        exercises = fetch_exercises_page(
            db,
            limit=batch_size,
            start_after=last_name,
            filter_unnormalized=filter_unnormalized,
        )
        
        if not exercises:
            logger.info("No more exercises to review")
            break
        
        total_fetched += len(exercises)
        last_name = exercises[-1].get("name")
        
        # Review batch
        batch_result = reviewer.review_batch(exercises)
        
        # Aggregate
        all_results.total_reviewed += batch_result.total_reviewed
        all_results.issues_found += batch_result.issues_found
        all_results.exercises_needing_enrichment += batch_result.exercises_needing_enrichment
        all_results.exercises_needing_human_review += batch_result.exercises_needing_human_review
        all_results.results.extend(batch_result.results)
        
        for sev, count in batch_result.issues_by_severity.items():
            all_results.issues_by_severity[sev] = all_results.issues_by_severity.get(sev, 0) + count
        for cat, count in batch_result.issues_by_category.items():
            all_results.issues_by_category[cat] = all_results.issues_by_category.get(cat, 0) + count
        
        logger.info(
            "Reviewed batch: %d exercises, %d issues found",
            len(exercises), batch_result.issues_found
        )
        
        if len(exercises) < batch_size:
            break
    
    # Create jobs
    job_result = create_jobs_from_review(
        all_results,
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
            "total_reviewed": all_results.total_reviewed,
            "issues_found": all_results.issues_found,
            "exercises_needing_enrichment": all_results.exercises_needing_enrichment,
            "exercises_needing_human_review": all_results.exercises_needing_human_review,
            "issues_by_severity": all_results.issues_by_severity,
            "issues_by_category": all_results.issues_by_category,
        },
        "jobs": job_result,
    }
    
    logger.info(
        "Scheduled review complete: reviewed %d exercises, created %d jobs in %.1f seconds",
        all_results.total_reviewed,
        job_result.get("jobs_created", 0),
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
        help="Exercises per batch"
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
        "--unnormalized-only", action="store_true",
        help="Only review unnormalized exercises"
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
        filter_unnormalized=args.unnormalized_only,
    )
    
    # Print summary
    import json
    print("\n" + "=" * 60)
    print("SCHEDULED REVIEW SUMMARY")
    print("=" * 60)
    print(json.dumps(summary, indent=2))
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
