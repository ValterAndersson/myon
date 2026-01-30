#!/usr/bin/env python3
"""
Batch Enrich Catalog - Queue enrichment jobs for all exercises.

This script:
1. Queues SCHEMA_CLEANUP jobs for exercises with legacy fields
2. Queues CATALOG_ENRICH_FIELD jobs for holistic enrichment (Flash by default)

Usage:
    # Dry run - see what would be queued
    python scripts/batch_enrich_catalog.py --dry-run

    # Queue schema cleanup jobs only
    python scripts/batch_enrich_catalog.py --apply --cleanup-only

    # Queue enrichment jobs only (skip cleanup)
    python scripts/batch_enrich_catalog.py --apply --enrich-only

    # Queue both cleanup and enrichment
    python scripts/batch_enrich_catalog.py --apply

    # Use Pro model instead of Flash
    python scripts/batch_enrich_catalog.py --apply --use-pro
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Set

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Legacy fields that should be cleaned up
LEGACY_FIELDS = {
    "instructions", "status", "deprecated_at", "created_by", "version",
    "coaching_cues",  # Deprecated - redundant with execution_notes
    "tips",  # Deprecated - redundant with suitability_notes
    "variant_key",  # Deprecated - family_slug + equipment in name is sufficient
}

# Fields that indicate an exercise needs enrichment
ENRICHABLE_FIELDS = {
    "muscles.contribution",
    "programming_use_cases",
    "stimulus_tags",
    # "coaching_cues",  # Deprecated - redundant with execution_notes
    "suitability_notes",
    "execution_notes",
    "common_mistakes",
}


def get_firestore_client():
    """Get Firestore client."""
    from google.cloud import firestore

    emulator_host = os.environ.get("FIRESTORE_EMULATOR_HOST")
    if emulator_host:
        logger.info("Using Firestore emulator at %s", emulator_host)
        return firestore.Client(project="demo-povver")

    return firestore.Client()


def fetch_all_exercises(db, max_exercises: int = 2000) -> List[Dict[str, Any]]:
    """Fetch all exercises from Firestore."""
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

    logger.info("Fetched %d exercises", len(exercises))
    return exercises


def find_exercises_with_legacy_fields(exercises: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """
    Find exercises that have legacy fields.

    Returns:
        Dict mapping exercise_id to list of legacy fields present
    """
    results = {}

    for ex in exercises:
        ex_id = ex.get("id") or ex.get("doc_id", "")
        legacy_present = []

        for field in LEGACY_FIELDS:
            if field in ex and ex[field] is not None:
                legacy_present.append(field)

        if legacy_present:
            results[ex_id] = legacy_present

    return results


def find_exercises_needing_enrichment(exercises: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """
    Find exercises that are missing enrichable fields.

    Returns:
        Dict mapping exercise_id to list of missing fields
    """
    results = {}

    for ex in exercises:
        ex_id = ex.get("id") or ex.get("doc_id", "")
        missing_fields = []

        # Check muscles.contribution
        muscles = ex.get("muscles") or {}
        if not muscles.get("contribution"):
            missing_fields.append("muscles.contribution")

        # Check other enrichable fields (coaching_cues removed - deprecated)
        for field in ["programming_use_cases", "stimulus_tags", "suitability_notes"]:
            val = ex.get(field)
            if not val or (isinstance(val, list) and len(val) == 0):
                missing_fields.append(field)

        # Check execution_notes and common_mistakes
        execution_notes = ex.get("execution_notes") or []
        if len(execution_notes) < 2:
            missing_fields.append("execution_notes")

        common_mistakes = ex.get("common_mistakes") or []
        if len(common_mistakes) < 1:
            missing_fields.append("common_mistakes")

        if missing_fields:
            results[ex_id] = missing_fields

    return results


def queue_schema_cleanup_jobs(
    exercises_with_legacy: Dict[str, List[str]],
    dry_run: bool = True,
    batch_size: int = 50,
) -> Dict[str, Any]:
    """
    Queue SCHEMA_CLEANUP jobs for exercises with legacy fields.
    """
    from app.jobs.queue import create_job
    from app.jobs.models import JobType, JobQueue

    if not exercises_with_legacy:
        logger.info("No exercises need schema cleanup")
        return {"jobs_created": 0, "exercises": 0}

    exercise_ids = list(exercises_with_legacy.keys())
    jobs_created = 0

    # Create jobs in batches
    for i in range(0, len(exercise_ids), batch_size):
        batch_ids = exercise_ids[i:i + batch_size]

        if dry_run:
            logger.info(
                "Would create SCHEMA_CLEANUP job for %d exercises: %s...",
                len(batch_ids),
                batch_ids[:3],
            )
            jobs_created += 1
        else:
            try:
                job = create_job(
                    job_type=JobType.SCHEMA_CLEANUP,
                    queue=JobQueue.MAINTENANCE,
                    priority=60,
                    mode="apply",
                    exercise_doc_ids=batch_ids,
                    enrichment_spec={
                        "type": "schema_cleanup",
                        "legacy_fields": list(LEGACY_FIELDS),
                        "source": "batch_enrich_catalog",
                    },
                )
                logger.info("Created SCHEMA_CLEANUP job %s for %d exercises", job.id, len(batch_ids))
                jobs_created += 1
            except Exception as e:
                logger.error("Failed to create SCHEMA_CLEANUP job: %s", e)

    return {
        "jobs_created": jobs_created,
        "exercises": len(exercise_ids),
        "dry_run": dry_run,
    }


def queue_enrichment_jobs(
    exercises_needing_enrichment: Dict[str, List[str]],
    dry_run: bool = True,
    batch_size: int = 10,  # Smaller batches for LLM work
    use_pro_model: bool = False,
) -> Dict[str, Any]:
    """
    Queue CATALOG_ENRICH_FIELD jobs for holistic enrichment.
    """
    from app.jobs.queue import create_job
    from app.jobs.models import JobType, JobQueue

    if not exercises_needing_enrichment:
        logger.info("No exercises need enrichment")
        return {"jobs_created": 0, "exercises": 0}

    exercise_ids = list(exercises_needing_enrichment.keys())
    jobs_created = 0
    model_name = "gemini-2.5-pro" if use_pro_model else "gemini-2.5-flash"

    # Create jobs in batches
    for i in range(0, len(exercise_ids), batch_size):
        batch_ids = exercise_ids[i:i + batch_size]

        if dry_run:
            logger.info(
                "Would create CATALOG_ENRICH_FIELD job (%s) for %d exercises: %s...",
                model_name,
                len(batch_ids),
                batch_ids[:3],
            )
            jobs_created += 1
        else:
            try:
                job = create_job(
                    job_type=JobType.CATALOG_ENRICH_FIELD,
                    queue=JobQueue.MAINTENANCE,
                    priority=40,
                    mode="apply",
                    exercise_doc_ids=batch_ids,
                    enrichment_spec={
                        "type": "holistic",
                        "use_pro_model": use_pro_model,
                        "source": "batch_enrich_catalog",
                        "fields_to_enrich": list(ENRICHABLE_FIELDS),
                    },
                )
                logger.info(
                    "Created CATALOG_ENRICH_FIELD job %s (%s) for %d exercises",
                    job.id, model_name, len(batch_ids),
                )
                jobs_created += 1
            except Exception as e:
                logger.error("Failed to create CATALOG_ENRICH_FIELD job: %s", e)

    return {
        "jobs_created": jobs_created,
        "exercises": len(exercise_ids),
        "model": model_name,
        "dry_run": dry_run,
    }


def main():
    parser = argparse.ArgumentParser(description="Batch enrich catalog exercises")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Preview what would be queued (default)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually create jobs",
    )
    parser.add_argument(
        "--cleanup-only",
        action="store_true",
        help="Only queue SCHEMA_CLEANUP jobs",
    )
    parser.add_argument(
        "--enrich-only",
        action="store_true",
        help="Only queue enrichment jobs (skip cleanup)",
    )
    parser.add_argument(
        "--use-pro",
        action="store_true",
        help="Use gemini-2.5-pro instead of flash for enrichment",
    )
    parser.add_argument(
        "--max-exercises",
        type=int,
        default=2000,
        help="Maximum exercises to process",
    )
    parser.add_argument(
        "--enrich-batch-size",
        type=int,
        default=10,
        help="Exercises per enrichment job (smaller = more jobs, better error isolation)",
    )

    args = parser.parse_args()
    dry_run = not args.apply

    # Fetch exercises
    db = get_firestore_client()
    exercises = fetch_all_exercises(db, args.max_exercises)

    if not exercises:
        logger.error("No exercises found")
        return 1

    # Analyze
    legacy_map = find_exercises_with_legacy_fields(exercises)
    enrichment_map = find_exercises_needing_enrichment(exercises)

    print("\n" + "=" * 60)
    print("CATALOG ANALYSIS")
    print("=" * 60)
    print(f"Total exercises: {len(exercises)}")
    print(f"With legacy fields: {len(legacy_map)}")
    print(f"Needing enrichment: {len(enrichment_map)}")
    print()

    # Show legacy field breakdown
    if legacy_map:
        field_counts: Dict[str, int] = {}
        for fields in legacy_map.values():
            for f in fields:
                field_counts[f] = field_counts.get(f, 0) + 1
        print("Legacy fields to clean:")
        for field, count in sorted(field_counts.items(), key=lambda x: -x[1]):
            print(f"  {field}: {count}")
        print()

    # Show enrichment field breakdown
    if enrichment_map:
        field_counts = {}
        for fields in enrichment_map.values():
            for f in fields:
                field_counts[f] = field_counts.get(f, 0) + 1
        print("Fields needing enrichment:")
        for field, count in sorted(field_counts.items(), key=lambda x: -x[1]):
            print(f"  {field}: {count}")
        print()

    # Queue jobs
    cleanup_result = {"jobs_created": 0}
    enrich_result = {"jobs_created": 0}

    if not args.enrich_only:
        print("=" * 60)
        print("SCHEMA CLEANUP")
        print("=" * 60)
        cleanup_result = queue_schema_cleanup_jobs(legacy_map, dry_run=dry_run)
        print(f"Jobs created: {cleanup_result['jobs_created']}")
        print()

    if not args.cleanup_only:
        print("=" * 60)
        print("ENRICHMENT")
        print("=" * 60)
        enrich_result = queue_enrichment_jobs(
            enrichment_map,
            dry_run=dry_run,
            batch_size=args.enrich_batch_size,
            use_pro_model=args.use_pro,
        )
        print(f"Jobs created: {enrich_result['jobs_created']}")
        print(f"Model: {enrich_result.get('model', 'flash')}")
        print()

    # Summary
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Dry run: {dry_run}")
    print(f"Cleanup jobs: {cleanup_result['jobs_created']}")
    print(f"Enrichment jobs: {enrich_result['jobs_created']}")

    if dry_run:
        print()
        print("To actually create jobs, run with --apply")

    return 0


if __name__ == "__main__":
    sys.exit(main())
