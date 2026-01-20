#!/usr/bin/env python3
"""
Queue Schema Cleanup Jobs - V1.1

Scans for exercises with deprecated fields and queues SCHEMA_CLEANUP
jobs to remove them.

Deprecated fields:
- _debug_project_id (debug artifact)
- delete_candidate (old review system)
- delete_candidate_justification (old review system)
- enriched_description (replaced by description)
- enriched_common_mistakes (replaced by common_mistakes)
- enriched_programming_use_cases (replaced by stimulus_tags)

Usage:
    python scripts/queue_schema_cleanup.py --dry-run
    python scripts/queue_schema_cleanup.py --apply
"""

import argparse
import logging
import os
import sys
from collections import defaultdict
from typing import Dict, List, Set

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.jobs.queue import create_job
from app.jobs.models import JobType, JobQueue

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# Deprecated fields to remove
DEPRECATED_FIELDS = [
    "_debug_project_id",
    "delete_candidate",
    "delete_candidate_justification",
    "enriched_description",
    "enriched_common_mistakes",
    "enriched_programming_use_cases",
]

# Batch size for SCHEMA_CLEANUP jobs
BATCH_SIZE = 50


def get_firestore_client():
    """Get Firestore client."""
    from google.cloud import firestore
    
    emulator_host = os.environ.get("FIRESTORE_EMULATOR_HOST")
    if emulator_host:
        logger.info("Using Firestore emulator at %s", emulator_host)
        return firestore.Client(project="demo-povver")
    
    return firestore.Client()


def scan_deprecated_fields(db) -> Dict[str, List[str]]:
    """
    Scan all exercises for deprecated fields.
    
    Returns a dict mapping doc_id -> list of deprecated fields present.
    """
    logger.info("Scanning exercises for deprecated fields...")
    
    exercises_with_deprecated: Dict[str, List[str]] = {}
    field_counts: Dict[str, int] = defaultdict(int)
    total_scanned = 0
    
    # Stream all exercises
    for doc in db.collection("exercises").stream():
        total_scanned += 1
        data = doc.to_dict()
        
        # Check for deprecated fields
        deprecated_present = [f for f in DEPRECATED_FIELDS if f in data]
        
        if deprecated_present:
            exercises_with_deprecated[doc.id] = deprecated_present
            for field in deprecated_present:
                field_counts[field] += 1
    
    logger.info(
        "Scanned %d exercises, found %d with deprecated fields",
        total_scanned, len(exercises_with_deprecated)
    )
    
    # Log field counts
    for field, count in sorted(field_counts.items(), key=lambda x: -x[1]):
        logger.info("  • %s: %d exercises", field, count)
    
    return exercises_with_deprecated


def create_batches(exercises_with_deprecated: Dict[str, List[str]], batch_size: int) -> List[List[str]]:
    """
    Split exercises into batches for processing.
    
    Args:
        exercises_with_deprecated: Dict mapping doc_id -> deprecated fields
        batch_size: Maximum exercises per batch
        
    Returns:
        List of batches, each batch is a list of doc_ids
    """
    doc_ids = list(exercises_with_deprecated.keys())
    batches = [doc_ids[i:i + batch_size] for i in range(0, len(doc_ids), batch_size)]
    return batches


def queue_cleanup_jobs(batches: List[List[str]], mode: str = "dry_run") -> Dict:
    """
    Queue SCHEMA_CLEANUP jobs for each batch.
    
    Args:
        batches: List of doc_id batches
        mode: "dry_run" or "apply"
        
    Returns:
        Summary of jobs created
    """
    jobs_created = []
    
    for i, batch in enumerate(batches):
        try:
            job = create_job(
                job_type=JobType.SCHEMA_CLEANUP,
                queue=JobQueue.MAINTENANCE,
                priority=30,  # Lower priority (cleanup is background work)
                mode=mode,
                exercise_doc_ids=batch,
                enrichment_spec={
                    "fields_to_remove": DEPRECATED_FIELDS,
                    "source": "queue_schema_cleanup_v1.1",
                    "batch_index": i,
                },
            )
            
            jobs_created.append({
                "job_id": job.id,
                "batch_index": i,
                "exercise_count": len(batch),
            })
            
            logger.info(
                "Created job %s: batch %d with %d exercises",
                job.id, i, len(batch)
            )
            
        except Exception as e:
            logger.exception("Failed to create job for batch %d: %s", i, e)
    
    return {
        "jobs_created": len(jobs_created),
        "total_exercises": sum(j["exercise_count"] for j in jobs_created),
        "mode": mode,
        "jobs": jobs_created,
    }


def main():
    parser = argparse.ArgumentParser(description="Queue schema cleanup jobs")
    parser.add_argument(
        "--dry-run", action="store_true", default=True,
        help="Create jobs in dry-run mode (default)"
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Create jobs in apply mode"
    )
    parser.add_argument(
        "--batch-size", type=int, default=BATCH_SIZE,
        help=f"Exercises per job (default: {BATCH_SIZE})"
    )
    parser.add_argument(
        "--limit", type=int, default=1000,
        help="Maximum exercises to process"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Verbose output"
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    mode = "apply" if args.apply else "dry_run"
    
    # Get Firestore client
    db = get_firestore_client()
    
    # Scan for deprecated fields
    exercises_with_deprecated = scan_deprecated_fields(db)
    
    if not exercises_with_deprecated:
        print("\n✅ No exercises with deprecated fields found!")
        return 0
    
    # Limit exercises
    if len(exercises_with_deprecated) > args.limit:
        doc_ids = list(exercises_with_deprecated.keys())[:args.limit]
        exercises_with_deprecated = {k: exercises_with_deprecated[k] for k in doc_ids}
        logger.info("Limited to %d exercises", args.limit)
    
    # Create batches
    batches = create_batches(exercises_with_deprecated, args.batch_size)
    
    print(f"\n📋 Found {len(exercises_with_deprecated)} exercises with deprecated fields")
    print(f"   Will create {len(batches)} SCHEMA_CLEANUP jobs ({args.batch_size} exercises/job)")
    
    print(f"\n🗑️  Deprecated fields to remove:")
    for field in DEPRECATED_FIELDS:
        print(f"   • {field}")
    
    print(f"\n🚀 Creating {len(batches)} jobs (mode={mode})...")
    
    # Queue jobs
    result = queue_cleanup_jobs(batches, mode=mode)
    
    print(f"\n✅ Created {result['jobs_created']} jobs covering {result['total_exercises']} exercises")
    
    if mode == "dry_run":
        print("\nℹ️  Jobs created in dry-run mode. Run worker to process:")
        print("    python cli.py run-worker --apply")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
