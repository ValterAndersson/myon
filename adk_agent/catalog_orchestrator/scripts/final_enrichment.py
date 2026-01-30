#!/usr/bin/env python3
"""
Final Enrichment - Queue enrichment jobs for exercises missing key fields.

This script targets exercises missing:
- description (859 exercises)
- muscles.contribution (1 exercise)
- execution_notes (1 exercise)

Usage:
    # Dry run
    python scripts/final_enrichment.py --dry-run

    # Apply (queue jobs)
    python scripts/final_enrichment.py --apply
"""

import argparse
import json
import logging
import os
import sys
from typing import Any, Dict, List, Set

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Fields to check for missing values
REQUIRED_FIELDS = {
    "description",
    "muscles.contribution",
    "execution_notes",
    "common_mistakes",
}


def load_export() -> List[Dict[str, Any]]:
    """Load exercises from export file."""
    export_path = os.path.join(os.path.dirname(__file__), "exercises_export.json")
    with open(export_path) as f:
        data = json.load(f)
    return data.get("exercises", [])


def find_exercises_needing_enrichment(exercises: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """
    Find exercises missing required fields.

    Returns:
        Dict mapping doc_id to list of missing fields
    """
    results = {}

    for ex in exercises:
        doc_id = ex.get("_doc_id", "")
        missing = []

        # Check description
        if not ex.get("description"):
            missing.append("description")

        # Check muscles.contribution
        muscles = ex.get("muscles") or {}
        if not muscles.get("contribution"):
            missing.append("muscles.contribution")

        # Check execution_notes
        execution_notes = ex.get("execution_notes") or []
        if len(execution_notes) < 2:
            missing.append("execution_notes")

        # Check common_mistakes
        common_mistakes = ex.get("common_mistakes") or []
        if len(common_mistakes) < 1:
            missing.append("common_mistakes")

        if missing:
            results[doc_id] = missing

    return results


def queue_enrichment_jobs(
    exercises_needing_enrichment: Dict[str, List[str]],
    dry_run: bool = True,
    batch_size: int = 10,
) -> Dict[str, Any]:
    """Queue CATALOG_ENRICH_FIELD jobs for holistic enrichment."""
    from app.jobs.queue import create_job
    from app.jobs.models import JobType, JobQueue

    if not exercises_needing_enrichment:
        logger.info("No exercises need enrichment")
        return {"jobs_created": 0, "exercises": 0}

    exercise_ids = list(exercises_needing_enrichment.keys())
    jobs_created = 0

    for i in range(0, len(exercise_ids), batch_size):
        batch_ids = exercise_ids[i:i + batch_size]

        if dry_run:
            logger.info(
                "Would create CATALOG_ENRICH_FIELD job for %d exercises: %s...",
                len(batch_ids),
                batch_ids[:3],
            )
            jobs_created += 1
        else:
            try:
                job = create_job(
                    job_type=JobType.CATALOG_ENRICH_FIELD,
                    queue=JobQueue.MAINTENANCE,
                    priority=50,
                    mode="apply",
                    exercise_doc_ids=batch_ids,
                    enrichment_spec={
                        "type": "holistic",
                        "use_pro_model": False,  # Use Flash
                        "source": "final_enrichment",
                        "instructions": "Focus on adding description field if missing. Also check muscles.contribution and execution_notes.",
                    },
                )
                logger.info(
                    "Created CATALOG_ENRICH_FIELD job %s for %d exercises",
                    job.id, len(batch_ids),
                )
                jobs_created += 1
            except Exception as e:
                logger.error("Failed to create job: %s", e)

    return {
        "jobs_created": jobs_created,
        "exercises": len(exercise_ids),
        "dry_run": dry_run,
    }


def main():
    parser = argparse.ArgumentParser(description="Final enrichment for missing fields")
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--batch-size", type=int, default=10, help="Exercises per job")

    args = parser.parse_args()
    dry_run = not args.apply

    # Load and analyze
    exercises = load_export()
    enrichment_map = find_exercises_needing_enrichment(exercises)

    print("\n" + "=" * 60)
    print("FINAL ENRICHMENT ANALYSIS")
    print("=" * 60)
    print(f"Total exercises: {len(exercises)}")
    print(f"Needing enrichment: {len(enrichment_map)}")
    print()

    # Show field breakdown
    if enrichment_map:
        field_counts: Dict[str, int] = {}
        for fields in enrichment_map.values():
            for f in fields:
                field_counts[f] = field_counts.get(f, 0) + 1
        print("Missing fields:")
        for field, count in sorted(field_counts.items(), key=lambda x: -x[1]):
            print(f"  {field}: {count}")
        print()

    # Queue jobs
    print("=" * 60)
    print("ENRICHMENT JOBS")
    print("=" * 60)
    result = queue_enrichment_jobs(
        enrichment_map,
        dry_run=dry_run,
        batch_size=args.batch_size,
    )
    print(f"Jobs created: {result['jobs_created']}")
    print(f"Exercises covered: {result['exercises']}")
    print()

    # Summary
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Dry run: {dry_run}")
    print(f"Model: gemini-2.5-flash")
    print(f"Batch size: {args.batch_size}")

    if dry_run:
        print()
        print("To queue jobs, run with --apply")

    return 0


if __name__ == "__main__":
    sys.exit(main())
