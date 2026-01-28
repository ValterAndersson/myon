#!/usr/bin/env python3
"""
Export all exercises from Firestore to a JSON file.

Usage:
    python3 scripts/export_exercises.py
    python3 scripts/export_exercises.py --output exercises.json
    python3 scripts/export_exercises.py --limit 10
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from typing import Any, Dict

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


def serialize_value(value: Any) -> Any:
    """Serialize Firestore values to JSON-compatible types."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: serialize_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [serialize_value(v) for v in value]
    # Handle Firestore GeoPoint, DocumentReference, etc.
    if hasattr(value, "__class__") and value.__class__.__name__ == "GeoPoint":
        return {"latitude": value.latitude, "longitude": value.longitude}
    if hasattr(value, "__class__") and value.__class__.__name__ == "DocumentReference":
        return f"ref:{value.path}"
    return value


def export_exercises(
    output_path: str = "exercises_export.json",
    limit: int = None,
    pretty: bool = True,
) -> Dict[str, Any]:
    """
    Export all exercises from Firestore to JSON.

    Args:
        output_path: Path to output JSON file
        limit: Optional limit on number of exercises
        pretty: Whether to pretty-print JSON

    Returns:
        Summary dict with counts
    """
    db = get_firestore_client()

    logger.info("Fetching exercises from Firestore...")

    query = db.collection("exercises")
    if limit:
        query = query.limit(limit)

    exercises = []
    for doc in query.stream():
        data = doc.to_dict()
        # Add doc ID to data
        data["_doc_id"] = doc.id
        # Serialize for JSON
        serialized = serialize_value(data)
        exercises.append(serialized)

    logger.info("Fetched %d exercises", len(exercises))

    # Sort by name for easier review
    exercises.sort(key=lambda x: x.get("name", ""))

    # Build export object with metadata
    export_data = {
        "_export_metadata": {
            "exported_at": datetime.utcnow().isoformat(),
            "total_exercises": len(exercises),
            "limit_applied": limit,
        },
        "exercises": exercises,
    }

    # Write to file
    with open(output_path, "w", encoding="utf-8") as f:
        if pretty:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
        else:
            json.dump(export_data, f, ensure_ascii=False)

    logger.info("Exported to %s", output_path)

    # Print summary
    summary = analyze_exercises(exercises)
    print_summary(summary)

    return summary


def analyze_exercises(exercises: list) -> Dict[str, Any]:
    """Analyze exercises for schema compliance."""
    summary = {
        "total": len(exercises),
        "with_new_schema": 0,
        "with_legacy_only": 0,
        "with_both": 0,
        "missing_muscles_contribution": 0,
        "missing_execution_notes": 0,
        "fields_present": {},
    }

    for ex in exercises:
        muscles = ex.get("muscles", {}) or {}
        has_new_primary = bool(muscles.get("primary"))
        has_legacy_primary = bool(ex.get("primary_muscles"))
        has_contribution = bool(muscles.get("contribution"))
        has_execution_notes = bool(ex.get("execution_notes"))

        if has_new_primary and not has_legacy_primary:
            summary["with_new_schema"] += 1
        elif has_legacy_primary and not has_new_primary:
            summary["with_legacy_only"] += 1
        elif has_new_primary and has_legacy_primary:
            summary["with_both"] += 1

        if has_new_primary and not has_contribution:
            summary["missing_muscles_contribution"] += 1

        if not has_execution_notes:
            summary["missing_execution_notes"] += 1

        # Track field presence
        for key in ex.keys():
            if key.startswith("_"):
                continue
            summary["fields_present"][key] = summary["fields_present"].get(key, 0) + 1

    return summary


def print_summary(summary: Dict[str, Any]):
    """Print analysis summary."""
    print("\n" + "=" * 60)
    print("EXERCISE EXPORT SUMMARY")
    print("=" * 60)
    print(f"Total exercises: {summary['total']}")
    print(f"\nSchema Status:")
    print(f"  New schema only (muscles.primary): {summary['with_new_schema']}")
    print(f"  Legacy only (primary_muscles): {summary['with_legacy_only']}")
    print(f"  Both (needs cleanup): {summary['with_both']}")
    print(f"\nMissing Fields:")
    print(f"  Missing muscles.contribution: {summary['missing_muscles_contribution']}")
    print(f"  Missing execution_notes: {summary['missing_execution_notes']}")
    print(f"\nField Presence (top 20):")
    sorted_fields = sorted(
        summary["fields_present"].items(),
        key=lambda x: -x[1]
    )[:20]
    for field, count in sorted_fields:
        pct = count / summary["total"] * 100
        print(f"  {field}: {count} ({pct:.0f}%)")


def main():
    parser = argparse.ArgumentParser(description="Export exercises to JSON")
    parser.add_argument(
        "--output", "-o",
        type=str,
        default="exercises_export.json",
        help="Output file path (default: exercises_export.json)"
    )
    parser.add_argument(
        "--limit", "-l",
        type=int,
        default=None,
        help="Limit number of exercises to export"
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Output compact JSON (no indentation)"
    )

    args = parser.parse_args()

    export_exercises(
        output_path=args.output,
        limit=args.limit,
        pretty=not args.compact,
    )


if __name__ == "__main__":
    main()
