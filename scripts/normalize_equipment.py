#!/usr/bin/env python3
"""
Normalize equipment values in the exercises collection.

Standardizes equipment to hyphenated lowercase format matching
exercise_field_guide.py EQUIPMENT_TYPES.

Examples:
    pull_up_bar → pull-up-bar
    pull-up bar → pull-up-bar
    dip_belt → dip-belt
    Barbell → barbell
    Smith Machine → smith-machine

Usage:
    python scripts/normalize_equipment.py              # dry-run
    python scripts/normalize_equipment.py --apply      # apply changes
"""

import argparse
from collections import Counter
from datetime import datetime

from google.cloud import firestore

EXERCISES_COLLECTION = "exercises"

# Canonical equipment values (from exercise_field_guide.py)
CANONICAL_EQUIPMENT = {
    "barbell", "dumbbell", "kettlebell", "ez-bar", "trap-bar",
    "machine", "cable", "smith-machine",
    "bodyweight", "pull-up-bar", "dip-station", "suspension-trainer",
    "resistance-band", "medicine-ball", "stability-ball",
    "treadmill", "rowing-machine", "bike", "elliptical",
}

# Known mappings for non-canonical formats
EQUIPMENT_MAP = {
    # Underscore variants
    "pull_up_bar": "pull-up-bar",
    "pull_up bar": "pull-up-bar",
    "pullup bar": "pull-up-bar",
    "pullup_bar": "pull-up-bar",
    "pull up bar": "pull-up-bar",
    "chin up bar": "pull-up-bar",
    "chin-up bar": "pull-up-bar",
    "chin_up_bar": "pull-up-bar",
    "dip_station": "dip-station",
    "dip station": "dip-station",
    "ez_bar": "ez-bar",
    "ez bar": "ez-bar",
    "ezbar": "ez-bar",
    "trap_bar": "trap-bar",
    "trap bar": "trap-bar",
    "hex bar": "trap-bar",
    "hex_bar": "trap-bar",
    "smith_machine": "smith-machine",
    "smith machine": "smith-machine",
    "resistance_band": "resistance-band",
    "resistance band": "resistance-band",
    "band": "resistance-band",
    "bands": "resistance-band",
    "medicine_ball": "medicine-ball",
    "medicine ball": "medicine-ball",
    "med ball": "medicine-ball",
    "med_ball": "medicine-ball",
    "stability_ball": "stability-ball",
    "stability ball": "stability-ball",
    "swiss ball": "stability-ball",
    "swiss_ball": "stability-ball",
    "exercise ball": "stability-ball",
    "suspension_trainer": "suspension-trainer",
    "suspension trainer": "suspension-trainer",
    "trx": "suspension-trainer",
    "rowing_machine": "rowing-machine",
    "rowing machine": "rowing-machine",
    "rower": "rowing-machine",
    # Case variants
    "bb": "barbell",
    "db": "dumbbell",
    "kb": "kettlebell",
    "dumbell": "dumbbell",
    "dumbells": "dumbbell",
    "dumbbells": "dumbbell",
    "barbells": "barbell",
    "kettlebells": "kettlebell",
    "cables": "cable",
    "machines": "machine",
    "body weight": "bodyweight",
    "body_weight": "bodyweight",
    "bw": "bodyweight",
    "none": "bodyweight",
}


def normalize_equipment_value(value):
    """Normalize a single equipment value."""
    if not isinstance(value, str):
        return value
    clean = value.lower().strip()
    if clean in CANONICAL_EQUIPMENT:
        return clean
    mapped = EQUIPMENT_MAP.get(clean)
    if mapped:
        return mapped
    # Try hyphenating underscores
    hyphenated = clean.replace("_", "-").replace(" ", "-")
    if hyphenated in CANONICAL_EQUIPMENT:
        return hyphenated
    return clean  # Return cleaned but unmapped


def normalize_equipment(apply=False):
    db = firestore.Client()
    exercises_ref = db.collection(EXERCISES_COLLECTION)

    changes = []
    unmapped = Counter()
    total = 0

    print("Scanning exercises collection...")
    for doc in exercises_ref.stream():
        total += 1
        data = doc.to_dict()
        doc_id = doc.id
        name = data.get("name", "")
        equipment = data.get("equipment") or []

        if not isinstance(equipment, list):
            continue

        normalized = []
        changed = False
        for e in equipment:
            norm = normalize_equipment_value(e)
            if norm != e:
                changed = True
            if norm not in CANONICAL_EQUIPMENT:
                unmapped[norm] += 1
            normalized.append(norm)

        # Deduplicate
        seen = set()
        deduped = []
        for e in normalized:
            if e not in seen:
                deduped.append(e)
                seen.add(e)
        if len(deduped) != len(normalized):
            changed = True

        if changed:
            changes.append({
                "doc_id": doc_id,
                "name": name,
                "old": equipment,
                "new": deduped,
            })

            if apply:
                exercises_ref.document(doc_id).update({
                    "equipment": deduped,
                    "updated_at": datetime.utcnow(),
                })

    # Report
    print(f"\nScanned {total} exercises")
    print(f"\n--- Equipment Changes ({len(changes)}) ---")
    for c in changes:
        print(f"  {c['doc_id']}: {c['old']} → {c['new']}  ({c['name']})")

    if unmapped:
        print(f"\n--- Non-canonical Equipment ({len(unmapped)}) ---")
        for val, count in unmapped.most_common():
            print(f"  {val}: {count} exercises")

    if apply:
        print(f"\nApplied changes to {len(changes)} exercises")
    else:
        print(f"\nDRY RUN — would update {len(changes)} exercises")
        print("Run with --apply to execute")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Normalize equipment values in exercises collection"
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Actually apply changes (default: dry-run)"
    )
    args = parser.parse_args()
    normalize_equipment(apply=args.apply)
