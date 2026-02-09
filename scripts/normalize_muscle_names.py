#!/usr/bin/env python3
"""
Normalize muscle names in the exercises collection.

Applies to muscles.primary, muscles.secondary, and muscles.contribution keys:
- lowercase
- underscores → spaces
- deduplicate
- resolve aliases (e.g., "lats" → "latissimus dorsi")

Usage:
    python scripts/normalize_muscle_names.py              # dry-run
    python scripts/normalize_muscle_names.py --apply      # apply changes
"""

import argparse
from collections import Counter
from datetime import datetime

from google.cloud import firestore

EXERCISES_COLLECTION = "exercises"

# Aliases from exercise_field_guide.py
MUSCLE_ALIASES = {
    "lats": "latissimus dorsi",
    "traps": "trapezius",
    "delts": "deltoid",
    "front delt": "anterior deltoid",
    "front deltoid": "anterior deltoid",
    "side delt": "lateral deltoid",
    "side deltoid": "lateral deltoid",
    "rear delt": "posterior deltoid",
    "rear deltoid": "posterior deltoid",
    "abs": "rectus abdominis",
    "quads": "quadriceps",
    "hams": "hamstrings",
    "glute": "glutes",
    "pecs": "pectoralis major",
    "chest": "pectoralis major",
    "lower back": "erector spinae",
    "upper back": "trapezius",
    "mid back": "rhomboids",
    "middle back": "rhomboids",
    "hip flexor": "hip flexors",
    "calf": "calves",
    "forearm": "forearms",
    "gluteus": "glutes",
    "abdominals": "rectus abdominis",
    "abdominal": "rectus abdominis",
    "core": "rectus abdominis",
    "deltoids": "deltoid",
    "bicep": "biceps",
    "tricep": "triceps",
    "hamstring": "hamstrings",
    "quad": "quadriceps",
    "glute max": "gluteus maximus",
    "glute med": "gluteus medius",
}


def normalize_muscle_name(name):
    """Normalize a single muscle name."""
    if not isinstance(name, str):
        return name
    clean = name.replace("_", " ").lower().strip()
    # Resolve alias
    return MUSCLE_ALIASES.get(clean, clean)


def normalize_muscle_list(muscles):
    """Normalize a list of muscle names, deduplicating."""
    if not isinstance(muscles, list):
        return muscles, False

    normalized = []
    seen = set()
    changed = False

    for m in muscles:
        norm = normalize_muscle_name(m)
        if norm != m:
            changed = True
        if norm not in seen:
            normalized.append(norm)
            seen.add(norm)
        else:
            changed = True  # duplicate removed

    return normalized, changed


def normalize_contribution_map(contribution):
    """Normalize contribution map keys (muscle names)."""
    if not isinstance(contribution, dict):
        return contribution, False

    normalized = {}
    changed = False

    for muscle, pct in contribution.items():
        norm = normalize_muscle_name(muscle)
        if norm != muscle:
            changed = True
        if isinstance(pct, (int, float)):
            normalized[norm] = round(float(pct), 3)

    return normalized, changed


def normalize_muscle_names(apply=False):
    db = firestore.Client()
    exercises_ref = db.collection(EXERCISES_COLLECTION)

    changes = []
    total = 0

    print("Scanning exercises collection...")
    for doc in exercises_ref.stream():
        total += 1
        data = doc.to_dict()
        doc_id = doc.id
        name = data.get("name", "")
        muscles = data.get("muscles") or {}
        updates = {}
        change_details = []

        # Normalize muscles.primary
        primary = muscles.get("primary")
        if primary:
            norm, did_change = normalize_muscle_list(primary)
            if did_change:
                updates["muscles.primary"] = norm
                change_details.append(f"primary: {primary} → {norm}")

        # Normalize muscles.secondary
        secondary = muscles.get("secondary")
        if secondary:
            norm, did_change = normalize_muscle_list(secondary)
            if did_change:
                updates["muscles.secondary"] = norm
                change_details.append(f"secondary: {secondary} → {norm}")

        # Normalize muscles.contribution keys
        contribution = muscles.get("contribution")
        if contribution:
            norm, did_change = normalize_contribution_map(contribution)
            if did_change:
                updates["muscles.contribution"] = norm
                change_details.append(
                    f"contribution keys: {list(contribution.keys())} → {list(norm.keys())}"
                )

        if updates:
            changes.append({
                "doc_id": doc_id,
                "name": name,
                "details": change_details,
            })

            if apply:
                updates["updated_at"] = datetime.utcnow()
                exercises_ref.document(doc_id).update(updates)

    # Report
    print(f"\nScanned {total} exercises")
    print(f"\n--- Muscle Name Changes ({len(changes)}) ---")
    for c in changes:
        print(f"  {c['doc_id']} ({c['name']}):")
        for d in c["details"]:
            print(f"    {d}")

    if apply:
        print(f"\nApplied changes to {len(changes)} exercises")
    else:
        print(f"\nDRY RUN — would update {len(changes)} exercises")
        print("Run with --apply to execute")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Normalize muscle names in exercises collection"
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Actually apply changes (default: dry-run)"
    )
    args = parser.parse_args()
    normalize_muscle_names(apply=args.apply)
