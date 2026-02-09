#!/usr/bin/env python3
"""
Re-queue failed import enrichment jobs with correct payload structure.

The original import script (import_strong_csv.js) had a payload nesting bug
where mode, exercise_doc_ids, and enrichment_spec were placed at the top level
instead of inside a payload: {} object. This script finds those failed jobs
and creates new ones with the correct structure.

Usage:
    python scripts/requeue_failed_import_jobs.py              # dry-run
    python scripts/requeue_failed_import_jobs.py --apply      # apply changes
"""

import argparse
import uuid
from datetime import datetime

from google.cloud import firestore

JOBS_COLLECTION = "catalog_jobs"


def requeue_failed_import_jobs(apply=False):
    db = firestore.Client()
    jobs_ref = db.collection(JOBS_COLLECTION)

    # Find failed import enrichment jobs
    # These have type=CATALOG_ENRICH_FIELD and status in failed/needs_review
    # and source=strong_csv_import (either in enrichment_spec or payload)
    failed_statuses = ["failed", "needs_review", "error"]

    candidates = []
    for status in failed_statuses:
        query = (
            jobs_ref
            .where("type", "==", "CATALOG_ENRICH_FIELD")
            .where("status", "==", status)
        )
        for doc in query.stream():
            data = doc.to_dict()
            # Check if this is from the import script
            # Bug: enrichment_spec was at top level instead of in payload
            enrichment_spec = data.get("enrichment_spec") or {}
            payload_spec = (data.get("payload") or {}).get("enrichment_spec") or {}

            source = (
                enrichment_spec.get("source", "")
                or payload_spec.get("source", "")
            )

            if source == "strong_csv_import" or data.get("id", "").startswith("import-enrich-"):
                candidates.append({
                    "doc_id": doc.id,
                    "data": data,
                })

    print(f"Found {len(candidates)} failed import enrichment jobs")

    requeued = []
    for candidate in candidates:
        old_data = candidate["data"]
        old_id = candidate["doc_id"]

        # Extract exercise info from the broken job
        # Fields were at top level due to the bug
        exercise_doc_ids = (
            old_data.get("exercise_doc_ids")
            or (old_data.get("payload") or {}).get("exercise_doc_ids")
            or []
        )
        enrichment_spec = (
            old_data.get("enrichment_spec")
            or (old_data.get("payload") or {}).get("enrichment_spec")
            or {}
        )
        mode = (
            old_data.get("mode")
            or (old_data.get("payload") or {}).get("mode")
            or "apply"
        )

        if not exercise_doc_ids:
            print(f"  Skipping {old_id}: no exercise_doc_ids found")
            continue

        # Create new job with correct payload structure
        new_job_id = f"requeue-{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        new_job = {
            "id": new_job_id,
            "type": "CATALOG_ENRICH_FIELD",
            "queue": "priority",
            "status": "queued",
            "priority": 200,
            "payload": {
                "mode": mode,
                "exercise_doc_ids": exercise_doc_ids,
                "enrichment_spec": enrichment_spec,
            },
            "created_at": now,
            "updated_at": now,
            "run_after": now,
            "attempts": 0,
            "max_attempts": 3,
            "result_summary": None,
            "error": None,
            "supersedes": old_id,
        }

        requeued.append({
            "old_id": old_id,
            "new_id": new_job_id,
            "exercise_doc_ids": exercise_doc_ids,
            "exercise_name": enrichment_spec.get("exercise_name", "unknown"),
        })

        if apply:
            # Create the new job
            jobs_ref.document(new_job_id).set(new_job)
            # Mark old job as superseded
            jobs_ref.document(old_id).update({
                "status": "superseded",
                "superseded_by": new_job_id,
                "updated_at": now,
            })

    # Report
    print(f"\n--- Re-queued Jobs ({len(requeued)}) ---")
    for r in requeued:
        print(f"  {r['old_id']} → {r['new_id']}")
        print(f"    exercises: {r['exercise_doc_ids']}")
        print(f"    name: {r['exercise_name']}")

    if apply:
        print(f"\nCreated {len(requeued)} new jobs, marked old ones as superseded")
    else:
        print(f"\nDRY RUN — would create {len(requeued)} new jobs")
        print("Run with --apply to execute")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Re-queue failed import enrichment jobs with correct payload"
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Actually apply changes (default: dry-run)"
    )
    args = parser.parse_args()
    requeue_failed_import_jobs(apply=args.apply)
