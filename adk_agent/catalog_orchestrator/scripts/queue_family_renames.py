#!/usr/bin/env python3
"""
Queue Family Rename Jobs - V1.1

Scans for malformed family slugs (those with equipment in the slug)
and queues FAMILY_RENAME_SLUG jobs to fix them.

Usage:
    python scripts/queue_family_renames.py --dry-run
    python scripts/queue_family_renames.py --apply
"""

import argparse
import logging
import os
import sys
from collections import defaultdict
from typing import Dict, List, Set

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.family.taxonomy import derive_movement_family
from app.jobs.queue import create_job
from app.jobs.models import JobType, JobQueue

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# Known equipment keywords that should not be in family slugs
EQUIPMENT_KEYWORDS = {
    "barbell", "dumbbell", "kettlebell", "cable", "machine",
    "band", "bodyweight", "weighted", "smith",
    "ez", "hex", "trap", "landmine",
}


def get_firestore_client():
    """Get Firestore client."""
    from google.cloud import firestore
    
    emulator_host = os.environ.get("FIRESTORE_EMULATOR_HOST")
    if emulator_host:
        logger.info("Using Firestore emulator at %s", emulator_host)
        return firestore.Client(project="demo-povver")
    
    return firestore.Client()


def is_malformed_family_slug(slug: str) -> bool:
    """
    Check if a family slug contains equipment keywords.
    
    A properly formed family slug should only contain the movement name,
    not equipment (e.g., "bench_press" not "bench_press_machine").
    """
    slug_lower = slug.lower().replace("-", "_")
    parts = set(slug_lower.split("_"))
    
    # Check if any equipment keyword is in the slug
    return bool(parts & EQUIPMENT_KEYWORDS)


def derive_correct_family_slug(name: str) -> str:
    """
    Derive the correct family slug from an exercise name.
    Uses the derive_movement_family function which strips equipment.
    """
    return derive_movement_family(name)


def scan_malformed_families(db) -> Dict[str, List[Dict]]:
    """
    Scan all exercises and identify malformed family slugs.
    
    Returns a dict mapping malformed_slug -> list of exercises.
    """
    logger.info("Scanning exercises for malformed family slugs...")
    
    malformed_families: Dict[str, List[Dict]] = defaultdict(list)
    total_scanned = 0
    
    # Stream all exercises
    for doc in db.collection("exercises").stream():
        total_scanned += 1
        data = doc.to_dict()
        family_slug = data.get("family_slug", "")
        
        if family_slug and is_malformed_family_slug(family_slug):
            malformed_families[family_slug].append({
                "doc_id": doc.id,
                "name": data.get("name", ""),
                "family_slug": family_slug,
            })
    
    logger.info(
        "Scanned %d exercises, found %d malformed family slugs",
        total_scanned, len(malformed_families)
    )
    
    return dict(malformed_families)


def compute_renames(malformed_families: Dict[str, List[Dict]]) -> List[Dict]:
    """
    Compute the rename plan for each malformed family.
    
    For each malformed family slug, derive the correct slug from
    the first exercise's name.
    """
    renames = []
    
    for old_slug, exercises in malformed_families.items():
        # Use first exercise name to derive correct slug
        if not exercises:
            continue
        
        first_name = exercises[0]["name"]
        new_slug = derive_correct_family_slug(first_name)
        
        # Skip if they're the same (shouldn't happen but safety check)
        if old_slug == new_slug:
            logger.warning("Slug %s unchanged after derivation, skipping", old_slug)
            continue
        
        renames.append({
            "old_family_slug": old_slug,
            "new_family_slug": new_slug,
            "exercise_count": len(exercises),
            "sample_name": first_name,
        })
    
    return renames


def queue_rename_jobs(renames: List[Dict], mode: str = "dry_run") -> Dict:
    """
    Queue FAMILY_RENAME_SLUG jobs for each rename.
    
    Args:
        renames: List of rename specs
        mode: "dry_run" or "apply"
        
    Returns:
        Summary of jobs created
    """
    jobs_created = []
    
    for rename in renames:
        try:
            job = create_job(
                job_type=JobType.FAMILY_RENAME_SLUG,
                queue=JobQueue.MAINTENANCE,
                priority=40,  # Medium priority
                mode=mode,
                family_slug=rename["old_family_slug"],
                enrichment_spec={
                    "rename_config": {
                        "old_family_slug": rename["old_family_slug"],
                        "new_family_slug": rename["new_family_slug"],
                    },
                    "source": "queue_family_renames_v1.1",
                },
            )
            
            jobs_created.append({
                "job_id": job.id,
                "old_slug": rename["old_family_slug"],
                "new_slug": rename["new_family_slug"],
                "exercise_count": rename["exercise_count"],
            })
            
            logger.info(
                "Created job %s: %s → %s (%d exercises)",
                job.id,
                rename["old_family_slug"],
                rename["new_family_slug"],
                rename["exercise_count"],
            )
            
        except Exception as e:
            logger.exception("Failed to create job for %s: %s", rename["old_family_slug"], e)
    
    return {
        "jobs_created": len(jobs_created),
        "mode": mode,
        "jobs": jobs_created,
    }


def main():
    parser = argparse.ArgumentParser(description="Queue family rename jobs")
    parser.add_argument(
        "--dry-run", action="store_true", default=True,
        help="Create jobs in dry-run mode (default)"
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Create jobs in apply mode"
    )
    parser.add_argument(
        "--limit", type=int, default=100,
        help="Maximum jobs to create"
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
    
    # Scan for malformed families
    malformed_families = scan_malformed_families(db)
    
    if not malformed_families:
        print("\n✅ No malformed family slugs found!")
        return 0
    
    # Compute renames
    renames = compute_renames(malformed_families)
    
    print(f"\n📋 Found {len(renames)} families to rename:\n")
    for r in renames[:10]:
        print(f"  • {r['old_family_slug']} → {r['new_family_slug']} ({r['exercise_count']} exercises)")
    if len(renames) > 10:
        print(f"  ... and {len(renames) - 10} more")
    
    # Limit renames
    renames = renames[:args.limit]
    
    print(f"\n🚀 Creating {len(renames)} FAMILY_RENAME_SLUG jobs (mode={mode})...")
    
    # Queue jobs
    result = queue_rename_jobs(renames, mode=mode)
    
    print(f"\n✅ Created {result['jobs_created']} jobs")
    
    if mode == "dry_run":
        print("\nℹ️  Jobs created in dry-run mode. Run worker to process:")
        print("    python cli.py run-worker --apply")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
