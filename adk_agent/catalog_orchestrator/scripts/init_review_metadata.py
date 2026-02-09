#!/usr/bin/env python3
"""
Initialize review_metadata on existing exercises.

This migration script sets initial review_metadata on all exercises that
don't have it yet. This allows the cost-efficient review system to work
from the first run.

All exercises are initialized with:
- quality_score: 0.0 (needs initial review)
- needs_review: True
- review_version: None (not yet reviewed)
- last_reviewed_at: None

Usage:
    python scripts/init_review_metadata.py --dry-run  # Preview changes
    python scripts/init_review_metadata.py --apply    # Apply changes
"""

import argparse
import logging
import os
import sys
from datetime import datetime, timezone

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def get_firestore_client():
    """Get Firestore client."""
    from google.cloud import firestore

    emulator_host = os.environ.get("FIRESTORE_EMULATOR_HOST")
    if emulator_host:
        logger.info("Using Firestore emulator at %s", emulator_host)
        return firestore.Client(project="demo-povver")

    return firestore.Client()


def init_review_metadata(dry_run: bool = True) -> dict:
    """
    Initialize review_metadata on exercises that don't have it.

    Args:
        dry_run: If True, don't apply changes

    Returns:
        Summary of changes made
    """
    db = get_firestore_client()

    # Fetch all exercises
    exercises_ref = db.collection("exercises")
    docs = list(exercises_ref.stream())

    logger.info("Found %d exercises", len(docs))

    needs_init = []
    already_has = 0

    for doc in docs:
        data = doc.to_dict()
        review_meta = data.get("review_metadata", {})

        # Check if already initialized (has quality_score)
        if "quality_score" in review_meta:
            already_has += 1
            continue

        needs_init.append(doc.id)

    logger.info(
        "Already initialized: %d, Need initialization: %d",
        already_has,
        len(needs_init),
    )

    if not needs_init:
        logger.info("All exercises already have review_metadata")
        return {
            "total": len(docs),
            "already_initialized": already_has,
            "initialized": 0,
            "dry_run": dry_run,
        }

    # Initialize review_metadata
    initialized = 0
    errors = 0

    for doc_id in needs_init:
        review_metadata = {
            "review_metadata.quality_score": 0.0,
            "review_metadata.needs_review": True,
            "review_metadata.review_version": None,
            "review_metadata.last_reviewed_at": None,
        }

        if dry_run:
            logger.debug("Would initialize review_metadata for %s", doc_id)
            initialized += 1
            continue

        try:
            doc_ref = db.collection("exercises").document(doc_id)
            doc_ref.update(review_metadata)
            initialized += 1
        except Exception as e:
            logger.warning("Failed to init %s: %s", doc_id, e)
            errors += 1

    logger.info(
        "Initialized %d exercises (errors: %d, dry_run: %s)",
        initialized,
        errors,
        dry_run,
    )

    return {
        "total": len(docs),
        "already_initialized": already_has,
        "initialized": initialized,
        "errors": errors,
        "dry_run": dry_run,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Initialize review_metadata on existing exercises"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Preview changes without applying (default)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually apply changes",
    )

    args = parser.parse_args()
    dry_run = not args.apply

    result = init_review_metadata(dry_run=dry_run)

    print("\n" + "=" * 50)
    print("REVIEW METADATA INITIALIZATION")
    print("=" * 50)
    for key, value in result.items():
        print(f"  {key}: {value}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
