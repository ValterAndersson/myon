#!/usr/bin/env python3
"""
Identify duplicate exercises in the catalog for manual review.

Groups exercises by normalized name (ignoring equipment, case, whitespace)
and outputs a JSON report of groups with 2+ exercises.

Automated merge is risky — duplicates may be legitimate variants
(same movement with different equipment). This report is for human decision.

Usage:
    python scripts/identify_duplicates.py                    # print report
    python scripts/identify_duplicates.py --output report.json  # save to file
    python scripts/identify_duplicates.py --archive-test     # also archive test exercises
    python scripts/identify_duplicates.py --archive-test --apply  # apply test archival
"""

import argparse
import json
import re
from collections import defaultdict
from datetime import datetime

from google.cloud import firestore

EXERCISES_COLLECTION = "exercises"

# Known test exercise doc IDs to archive
TEST_EXERCISES = [
    "test__test-cli-exercise",
    "test__test-exercise-demo",
    "up__test-push-up",
]


def normalize_for_grouping(name):
    """Normalize exercise name for duplicate grouping.

    Strips equipment parenthetical, lowercases, removes non-alphanumeric.
    """
    if not isinstance(name, str):
        return ""
    # Remove equipment in parentheses
    clean = re.sub(r'\s*\([^)]*\)\s*$', '', name)
    # Lowercase, strip non-alphanumeric
    clean = re.sub(r'[^a-z0-9]', '', clean.lower())
    return clean


def identify_duplicates(output_file=None, archive_test=False, apply=False):
    db = firestore.Client()
    exercises_ref = db.collection(EXERCISES_COLLECTION)

    # Group exercises by normalized name
    groups = defaultdict(list)
    total = 0
    archived_test = []

    print("Scanning exercises collection...")
    for doc in exercises_ref.stream():
        total += 1
        data = doc.to_dict()
        doc_id = doc.id
        name = data.get("name", "")
        status = data.get("status", "active")

        # Archive test exercises if requested
        if archive_test and doc_id in TEST_EXERCISES:
            archived_test.append({
                "doc_id": doc_id,
                "name": name,
                "old_status": status,
            })
            if apply:
                exercises_ref.document(doc_id).update({
                    "status": "deprecated",
                    "updated_at": datetime.utcnow(),
                })
            continue

        # Skip already deprecated
        if status in ("deprecated", "archived", "deleted"):
            continue

        group_key = normalize_for_grouping(name)
        if group_key:
            groups[group_key].append({
                "doc_id": doc_id,
                "name": name,
                "family_slug": data.get("family_slug", ""),
                "equipment": data.get("equipment", []),
                "category": data.get("category", ""),
                "status": status,
                "has_description": bool(data.get("description")),
                "has_muscles": bool((data.get("muscles") or {}).get("primary")),
                "has_execution_notes": bool(data.get("execution_notes")),
            })

    # Filter to groups with duplicates
    duplicate_groups = {
        key: exercises
        for key, exercises in groups.items()
        if len(exercises) > 1
    }

    # Sort by group size (largest first)
    sorted_groups = sorted(
        duplicate_groups.items(),
        key=lambda x: len(x[1]),
        reverse=True,
    )

    # Build report
    report = {
        "generated_at": datetime.utcnow().isoformat(),
        "total_exercises": total,
        "duplicate_groups": len(sorted_groups),
        "total_duplicates": sum(len(g) for _, g in sorted_groups),
        "groups": [],
    }

    for group_key, exercises in sorted_groups:
        # Determine if these are real duplicates or equipment variants
        equipment_sets = [
            tuple(sorted(e.get("equipment", []))) for e in exercises
        ]
        unique_equipment = len(set(equipment_sets))
        all_same_equipment = unique_equipment == 1

        group_info = {
            "normalized_name": group_key,
            "count": len(exercises),
            "likely_type": (
                "true_duplicate" if all_same_equipment
                else "equipment_variants"
            ),
            "exercises": exercises,
        }
        report["groups"].append(group_info)

    # Output
    print(f"\nScanned {total} exercises")
    print(f"Found {len(sorted_groups)} duplicate groups "
          f"({report['total_duplicates']} total exercises)")

    true_dupes = sum(
        1 for g in report["groups"] if g["likely_type"] == "true_duplicate"
    )
    variants = len(sorted_groups) - true_dupes
    print(f"  Likely true duplicates: {true_dupes} groups")
    print(f"  Likely equipment variants: {variants} groups")

    print(f"\n--- Top 10 Duplicate Groups ---")
    for group in report["groups"][:10]:
        print(f"\n  [{group['likely_type']}] {group['normalized_name']} "
              f"({group['count']} exercises):")
        for ex in group["exercises"]:
            equip = ", ".join(ex["equipment"]) if ex["equipment"] else "none"
            print(f"    {ex['doc_id']}: {ex['name']} [{equip}]")

    if archived_test:
        print(f"\n--- Test Exercises {'Archived' if apply else 'To Archive'} ---")
        for t in archived_test:
            action = "archived" if apply else "would archive"
            print(f"  {action}: {t['doc_id']} ({t['name']})")

    if output_file:
        with open(output_file, "w") as f:
            json.dump(report, f, indent=2, default=str)
        print(f"\nFull report written to: {output_file}")
    else:
        print("\nUse --output report.json to save full report")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Identify duplicate exercises for manual review"
    )
    parser.add_argument(
        "--output", type=str,
        help="Output file path for JSON report"
    )
    parser.add_argument(
        "--archive-test", action="store_true",
        help="Also archive known test exercises"
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Apply test exercise archival (requires --archive-test)"
    )
    args = parser.parse_args()
    identify_duplicates(
        output_file=args.output,
        archive_test=args.archive_test,
        apply=args.apply,
    )
