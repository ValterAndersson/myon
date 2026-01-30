#!/usr/bin/env python3
"""
Direct cleanup of legacy fields from exercises.

Bypasses the job queue and directly updates Firestore.

Usage:
    # Dry run first
    python scripts/direct_cleanup.py --dry-run

    # Apply changes
    python scripts/direct_cleanup.py --apply
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

# Fields to delete
LEGACY_FIELDS = {
    "instructions",
    "status",
    "deprecated_at",
    "coaching_cues",
    "tips",  # Redundant with suitability_notes
    "variant_key",  # family_slug + equipment in name is sufficient
    "created_by",
    "version",
    "id",
    "_debug_project_id",
    "delete_candidate",
    "delete_candidate_justification",
    "images",
    "primary_muscles",
    "secondary_muscles",
    "enriched_description",
    "enriched_common_mistakes",
    "enriched_programming_use_cases",
    "enriched_instructions",
    "enriched_tips",
    "enriched_cues",
    "enriched_at",
    "enriched_by",
}


def load_export() -> List[Dict[str, Any]]:
    """Load exercises from export file."""
    export_path = os.path.join(os.path.dirname(__file__), "exercises_export.json")
    with open(export_path) as f:
        data = json.load(f)
    return data.get("exercises", [])


def find_exercises_with_legacy_fields(exercises: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """
    Find exercises that have legacy fields.

    Returns:
        Dict mapping doc_id to list of legacy fields present
    """
    results = {}

    for ex in exercises:
        doc_id = ex.get("_doc_id", "")
        legacy_present = []

        for field in LEGACY_FIELDS:
            if field in ex and ex[field] is not None:
                legacy_present.append(field)

        if legacy_present:
            results[doc_id] = legacy_present

    return results


def cleanup_exercises(
    exercises_with_legacy: Dict[str, List[str]],
    dry_run: bool = True,
) -> Dict[str, Any]:
    """
    Delete legacy fields from exercises in Firestore.
    """
    from google.cloud import firestore

    if not exercises_with_legacy:
        logger.info("No exercises need cleanup")
        return {"updated": 0, "errors": 0}

    db = firestore.Client()
    updated = 0
    errors = 0

    # Process in batches of 400 (Firestore limit is 500)
    doc_ids = list(exercises_with_legacy.keys())
    batch_size = 400

    for i in range(0, len(doc_ids), batch_size):
        batch_ids = doc_ids[i:i + batch_size]

        if dry_run:
            for doc_id in batch_ids:
                fields = exercises_with_legacy[doc_id]
                logger.info("Would delete from %s: %s", doc_id, fields)
            updated += len(batch_ids)
        else:
            batch = db.batch()

            for doc_id in batch_ids:
                fields = exercises_with_legacy[doc_id]
                doc_ref = db.collection("exercises").document(doc_id)

                # Build update dict with DELETE_FIELD for each legacy field
                update_dict = {}
                for field in fields:
                    update_dict[field] = firestore.DELETE_FIELD

                batch.update(doc_ref, update_dict)
                logger.info("Deleting from %s: %s", doc_id, fields)

            try:
                batch.commit()
                updated += len(batch_ids)
                logger.info("Committed batch of %d updates", len(batch_ids))
            except Exception as e:
                logger.error("Batch commit failed: %s", e)
                errors += len(batch_ids)

    return {"updated": updated, "errors": errors}


def main():
    parser = argparse.ArgumentParser(description="Direct cleanup of legacy fields")
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--project", type=str, default="myon-53d85", help="GCP project ID")

    args = parser.parse_args()
    dry_run = not args.apply

    # Set project for Firestore
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", args.project)

    # Load and analyze
    exercises = load_export()
    legacy_map = find_exercises_with_legacy_fields(exercises)

    print("\n" + "=" * 60)
    print("LEGACY FIELD CLEANUP")
    print("=" * 60)
    print(f"Total exercises: {len(exercises)}")
    print(f"With legacy fields: {len(legacy_map)}")
    print()

    # Show field breakdown
    if legacy_map:
        field_counts: Dict[str, int] = {}
        for fields in legacy_map.values():
            for f in fields:
                field_counts[f] = field_counts.get(f, 0) + 1
        print("Fields to remove:")
        for field, count in sorted(field_counts.items(), key=lambda x: -x[1]):
            print(f"  {field}: {count}")
        print()

    # Perform cleanup
    result = cleanup_exercises(legacy_map, dry_run=dry_run)

    print("=" * 60)
    print("RESULT")
    print("=" * 60)
    print(f"Dry run: {dry_run}")
    print(f"Updated: {result['updated']}")
    print(f"Errors: {result['errors']}")

    if dry_run:
        print()
        print("To apply, run with --apply")

    return 0


if __name__ == "__main__":
    sys.exit(main())
