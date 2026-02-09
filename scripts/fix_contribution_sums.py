#!/usr/bin/env python3
"""
Fix muscle contribution sums that don't add up to ~1.0.

Re-normalizes contribution maps where the sum exceeds 1.05 or is below 0.85
by dividing each value by the total sum.

Usage:
    python scripts/fix_contribution_sums.py              # dry-run
    python scripts/fix_contribution_sums.py --apply      # apply changes
"""

import argparse
from datetime import datetime

from google.cloud import firestore

EXERCISES_COLLECTION = "exercises"

# Acceptable range for contribution sums
MIN_SUM = 0.85
MAX_SUM = 1.05


def fix_contribution_sums(apply=False):
    db = firestore.Client()
    exercises_ref = db.collection(EXERCISES_COLLECTION)

    fixes = []
    total = 0
    has_contribution = 0

    print("Scanning exercises collection...")
    for doc in exercises_ref.stream():
        total += 1
        data = doc.to_dict()
        doc_id = doc.id
        name = data.get("name", "")
        muscles = data.get("muscles") or {}
        contribution = muscles.get("contribution")

        if not isinstance(contribution, dict) or not contribution:
            continue

        has_contribution += 1

        # Calculate sum
        values = {k: v for k, v in contribution.items()
                  if isinstance(v, (int, float))}
        total_sum = sum(values.values())

        if total_sum < MIN_SUM or total_sum > MAX_SUM:
            # Re-normalize
            if total_sum > 0:
                normalized = {
                    k: round(v / total_sum, 3)
                    for k, v in values.items()
                }
            else:
                continue  # Can't normalize zero sum

            fixes.append({
                "doc_id": doc_id,
                "name": name,
                "old_sum": round(total_sum, 4),
                "new_sum": round(sum(normalized.values()), 4),
                "old": contribution,
                "new": normalized,
            })

            if apply:
                exercises_ref.document(doc_id).update({
                    "muscles.contribution": normalized,
                    "updated_at": datetime.utcnow(),
                })

    # Report
    print(f"\nScanned {total} exercises ({has_contribution} with contributions)")
    print(f"\n--- Contribution Sum Fixes ({len(fixes)}) ---")
    for f in fixes:
        print(f"  {f['doc_id']} ({f['name']}):")
        print(f"    sum: {f['old_sum']} → {f['new_sum']}")
        print(f"    old: {f['old']}")
        print(f"    new: {f['new']}")

    if apply:
        print(f"\nApplied fixes to {len(fixes)} exercises")
    else:
        print(f"\nDRY RUN — would fix {len(fixes)} exercises")
        print("Run with --apply to execute")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Fix muscle contribution sums in exercises collection"
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Actually apply changes (default: dry-run)"
    )
    args = parser.parse_args()
    fix_contribution_sums(apply=args.apply)
