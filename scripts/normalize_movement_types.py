#!/usr/bin/env python3
"""
Normalize movement.type values in the exercises collection.

Maps non-canonical movement types to the 11 canonical values defined in
exercise_field_guide.py. Exercises that can't be auto-mapped are queued
for LLM enrichment.

Usage:
    python scripts/normalize_movement_types.py              # dry-run
    python scripts/normalize_movement_types.py --apply      # apply changes
"""

import argparse
from collections import Counter
from datetime import datetime

from google.cloud import firestore

EXERCISES_COLLECTION = "exercises"

# The 11 canonical movement types (from exercise_field_guide.py)
CANONICAL_MOVEMENT_TYPES = {
    "push", "pull", "hinge", "squat", "carry", "rotation",
    "flexion", "extension", "abduction", "adduction", "other",
}

# Known mappings from invalid → canonical
MOVEMENT_TYPE_MAP = {
    # Press variants → push
    "press": "push",
    "pressing": "push",
    "overhead press": "push",
    "bench press": "push",
    "push press": "push",
    # Pull variants
    "row": "pull",
    "rowing": "pull",
    "pulldown": "pull",
    "pull-up": "pull",
    "chin-up": "pull",
    # Hinge variants
    "deadlift": "hinge",
    "hip hinge": "hinge",
    "rdl": "hinge",
    "good morning": "hinge",
    # Squat variants
    "lunge": "squat",
    "leg press": "squat",
    # Curl/flexion variants
    "curl": "flexion",
    "crunch": "flexion",
    "bicep curl": "flexion",
    "leg curl": "flexion",
    # Extension variants
    "kickback": "extension",
    "pushdown": "extension",
    "tricep extension": "extension",
    "leg extension": "extension",
    # Raise/abduction variants
    "raise": "abduction",
    "lateral raise": "abduction",
    "lateral": "abduction",
    # Fly/adduction variants
    "fly": "adduction",
    "flye": "adduction",
    "crossover": "adduction",
    "cable crossover": "adduction",
    # Isolation (ambiguous — map to flexion as most common)
    "isolation": "flexion",
    # Carry variants
    "farmer's walk": "carry",
    "loaded carry": "carry",
    # Rotation variants
    "twist": "rotation",
    "woodchop": "rotation",
    "russian twist": "rotation",
    # Compound (ambiguous — fallback)
    "compound": "other",
    "exercise": "other",
    "dip": "push",
}

# Canonical movement splits
CANONICAL_MOVEMENT_SPLITS = {"upper", "lower", "full_body", "core"}

# Known mappings for movement.split
MOVEMENT_SPLIT_MAP = {
    "full body": "full_body",
    "full": "full_body",
    "upper body": "upper",
    "lower body": "lower",
    "arms": "upper",
    "back": "upper",
    "chest": "upper",
    "shoulders": "upper",
    "legs": "lower",
    "abs": "core",
    "pull": "upper",
    "push": "upper",
}


def normalize_movement_types(apply: bool = False):
    db = firestore.Client()
    exercises_ref = db.collection(EXERCISES_COLLECTION)

    type_changes = []
    split_changes = []
    unmapped_types = Counter()
    unmapped_splits = Counter()
    total = 0

    print("Scanning exercises collection...")
    for doc in exercises_ref.stream():
        total += 1
        data = doc.to_dict()
        doc_id = doc.id
        name = data.get("name", "")
        movement = data.get("movement") or {}
        updates = {}

        # Check movement.type
        mtype = movement.get("type")
        if mtype and mtype not in CANONICAL_MOVEMENT_TYPES:
            mapped = MOVEMENT_TYPE_MAP.get(mtype.lower().strip())
            if mapped:
                updates["movement.type"] = mapped
                type_changes.append({
                    "doc_id": doc_id,
                    "name": name,
                    "old": mtype,
                    "new": mapped,
                })
            else:
                unmapped_types[mtype] += 1

        # Check movement.split
        msplit = movement.get("split")
        if msplit:
            # Handle list values (shouldn't be a list but some are)
            if isinstance(msplit, list):
                # Take first valid value
                resolved = None
                for s in msplit:
                    if isinstance(s, str):
                        sl = s.lower().strip()
                        if sl in CANONICAL_MOVEMENT_SPLITS:
                            resolved = sl
                            break
                        elif sl in MOVEMENT_SPLIT_MAP:
                            resolved = MOVEMENT_SPLIT_MAP[sl]
                            break
                if resolved:
                    updates["movement.split"] = resolved
                    split_changes.append({
                        "doc_id": doc_id,
                        "name": name,
                        "old": msplit,
                        "new": resolved,
                    })
                else:
                    unmapped_splits[str(msplit)] += 1
            elif isinstance(msplit, str) and msplit not in CANONICAL_MOVEMENT_SPLITS:
                mapped = MOVEMENT_SPLIT_MAP.get(msplit.lower().strip())
                if mapped:
                    updates["movement.split"] = mapped
                    split_changes.append({
                        "doc_id": doc_id,
                        "name": name,
                        "old": msplit,
                        "new": mapped,
                    })
                else:
                    unmapped_splits[msplit] += 1

        # Apply updates
        if updates and apply:
            updates["updated_at"] = datetime.utcnow()
            exercises_ref.document(doc_id).update(updates)

    # Report
    print(f"\nScanned {total} exercises")
    print(f"\n--- Movement Type Changes ({len(type_changes)}) ---")
    for c in type_changes:
        print(f"  {c['doc_id']}: {c['old']} → {c['new']}  ({c['name']})")

    print(f"\n--- Movement Split Changes ({len(split_changes)}) ---")
    for c in split_changes:
        print(f"  {c['doc_id']}: {c['old']} → {c['new']}  ({c['name']})")

    if unmapped_types:
        print(f"\n--- Unmapped Movement Types ({len(unmapped_types)}) ---")
        for val, count in unmapped_types.most_common():
            print(f"  {val}: {count} exercises (needs LLM enrichment)")

    if unmapped_splits:
        print(f"\n--- Unmapped Movement Splits ({len(unmapped_splits)}) ---")
        for val, count in unmapped_splits.most_common():
            print(f"  {val}: {count} exercises (needs LLM enrichment)")

    if apply:
        print(f"\nApplied {len(type_changes)} type changes, "
              f"{len(split_changes)} split changes")
    else:
        print(f"\nDRY RUN — would apply {len(type_changes)} type changes, "
              f"{len(split_changes)} split changes")
        print("Run with --apply to execute")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Normalize movement.type and movement.split values"
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Actually apply changes (default: dry-run)"
    )
    args = parser.parse_args()
    normalize_movement_types(apply=args.apply)
