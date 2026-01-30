#!/usr/bin/env python3
"""
Fix remaining issues from batch enrichment.

Reads exercises_export.json and creates targeted jobs for:
1. Exercises still with legacy fields (instructions, status, deprecated_at)
2. Exercises missing muscles.contribution

Usage:
    python scripts/fix_remaining_issues.py --dry-run
    python scripts/fix_remaining_issues.py --apply
"""

import argparse
import json
import logging
import os
import sys
from typing import Any, Dict, List, Set

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

LEGACY_FIELDS = {
    "instructions", "status", "deprecated_at", "created_by", "version",
    "coaching_cues",  # Deprecated - redundant with execution_notes
    "tips",  # Deprecated - redundant with suitability_notes
    "variant_key",  # Deprecated - family_slug + equipment in name is sufficient
}


def load_export() -> List[Dict[str, Any]]:
    """Load exercises from export file."""
    export_path = os.path.join(os.path.dirname(__file__), "exercises_export.json")
    with open(export_path) as f:
        data = json.load(f)
    return data.get("exercises", [])


def find_issues(exercises: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """Find exercises with issues."""
    legacy_field_exercises: Set[str] = set()
    missing_contribution: Set[str] = set()
    missing_execution_notes: Set[str] = set()
    needs_enrichment: Set[str] = set()  # Any enrichable field missing

    for ex in exercises:
        doc_id = ex.get("_doc_id", "")

        # Check for legacy fields (includes coaching_cues now)
        for field in LEGACY_FIELDS:
            if field in ex and ex[field] is not None:
                legacy_field_exercises.add(doc_id)
                break

        # Check for missing muscles.contribution
        muscles = ex.get("muscles") or {}
        if not muscles.get("contribution"):
            missing_contribution.add(doc_id)
            needs_enrichment.add(doc_id)

        # Check for missing execution_notes
        execution_notes = ex.get("execution_notes") or []
        if len(execution_notes) < 2:
            missing_execution_notes.add(doc_id)
            needs_enrichment.add(doc_id)

    return {
        "legacy_fields": list(legacy_field_exercises),
        "missing_contribution": list(missing_contribution),
        "missing_execution_notes": list(missing_execution_notes),
        "needs_enrichment": list(needs_enrichment),
    }


def queue_cleanup_jobs(exercise_ids: List[str], dry_run: bool = True) -> int:
    """Queue SCHEMA_CLEANUP jobs for exercises with legacy fields."""
    from app.jobs.queue import create_job
    from app.jobs.models import JobType, JobQueue

    if not exercise_ids:
        logger.info("No exercises need legacy field cleanup")
        return 0

    batch_size = 50
    jobs_created = 0

    for i in range(0, len(exercise_ids), batch_size):
        batch = exercise_ids[i:i + batch_size]

        if dry_run:
            logger.info("Would create SCHEMA_CLEANUP job for %d exercises", len(batch))
            jobs_created += 1
        else:
            try:
                job = create_job(
                    job_type=JobType.SCHEMA_CLEANUP,
                    queue=JobQueue.PRIORITY,  # Higher priority
                    priority=70,
                    mode="apply",
                    exercise_doc_ids=batch,
                )
                logger.info("Created SCHEMA_CLEANUP job %s for %d exercises", job.id, len(batch))
                jobs_created += 1
            except Exception as e:
                logger.error("Failed to create job: %s", e)

    return jobs_created


def queue_enrichment_jobs(exercise_ids: List[str], dry_run: bool = True, use_pro: bool = False) -> int:
    """Queue CATALOG_ENRICH_FIELD jobs for exercises missing contribution."""
    from app.jobs.queue import create_job
    from app.jobs.models import JobType, JobQueue

    if not exercise_ids:
        logger.info("No exercises need enrichment")
        return 0

    batch_size = 5  # Smaller batches for targeted enrichment
    jobs_created = 0
    model = "pro" if use_pro else "flash"

    for i in range(0, len(exercise_ids), batch_size):
        batch = exercise_ids[i:i + batch_size]

        if dry_run:
            logger.info("Would create ENRICH job (%s) for %d exercises", model, len(batch))
            jobs_created += 1
        else:
            try:
                job = create_job(
                    job_type=JobType.CATALOG_ENRICH_FIELD,
                    queue=JobQueue.PRIORITY,
                    priority=60,
                    mode="apply",
                    exercise_doc_ids=batch,
                    enrichment_spec={
                        "type": "holistic",
                        "use_pro_model": use_pro,
                        "source": "fix_remaining_issues",
                        "instructions": "Focus on: 1) muscles.contribution with percentages summing to 1.0, 2) execution_notes if missing, 3) common_mistakes",
                        "fields_to_enrich": ["muscles.contribution", "execution_notes", "common_mistakes"],
                    },
                )
                logger.info("Created ENRICH job %s (%s) for %d exercises", job.id, model, len(batch))
                jobs_created += 1
            except Exception as e:
                logger.error("Failed to create job: %s", e)

    return jobs_created


def main():
    parser = argparse.ArgumentParser(description="Fix remaining enrichment issues")
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--use-pro", action="store_true", help="Use Pro model for enrichment")
    parser.add_argument("--cleanup-only", action="store_true", help="Only run schema cleanup")
    parser.add_argument("--enrich-only", action="store_true", help="Only run enrichment")

    args = parser.parse_args()
    dry_run = not args.apply

    # Load and analyze
    exercises = load_export()
    issues = find_issues(exercises)

    print("\n" + "=" * 60)
    print("REMAINING ISSUES")
    print("=" * 60)
    print(f"Exercises with legacy fields (incl. coaching_cues): {len(issues['legacy_fields'])}")
    print(f"Exercises missing muscles.contribution: {len(issues['missing_contribution'])}")
    print(f"Exercises missing execution_notes: {len(issues['missing_execution_notes'])}")
    print(f"Total needing enrichment (deduplicated): {len(issues['needs_enrichment'])}")
    print()

    cleanup_jobs = 0
    enrich_jobs = 0

    if not args.enrich_only:
        print("=" * 60)
        print("SCHEMA CLEANUP")
        print("=" * 60)
        cleanup_jobs = queue_cleanup_jobs(issues["legacy_fields"], dry_run=dry_run)
        print(f"Jobs created: {cleanup_jobs}")
        print()

    if not args.cleanup_only:
        print("=" * 60)
        print("ENRICHMENT (contribution + execution_notes + common_mistakes)")
        print("=" * 60)
        # Use the deduplicated needs_enrichment list
        enrich_jobs = queue_enrichment_jobs(
            issues["needs_enrichment"],
            dry_run=dry_run,
            use_pro=args.use_pro,
        )
        print(f"Jobs created: {enrich_jobs}")
        print()

    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Dry run: {dry_run}")
    print(f"Cleanup jobs: {cleanup_jobs}")
    print(f"Enrichment jobs: {enrich_jobs}")

    if dry_run:
        print()
        print("To apply, run with --apply")

    return 0


if __name__ == "__main__":
    sys.exit(main())
