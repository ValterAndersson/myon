#!/usr/bin/env python3
"""
Cleanup script to delete orphaned test jobs from catalog_jobs collection.

These jobs were created during a test run where the job creation succeeded
but the error handling failed, leaving jobs with mode: "dry_run" and 
status: "queued".

Usage:
    python3 scripts/cleanup_test_jobs.py --dry-run   # Preview what would be deleted
    python3 scripts/cleanup_test_jobs.py --apply     # Actually delete
"""

import argparse
from datetime import datetime

from google.cloud import firestore


def cleanup_test_jobs(dry_run: bool = True):
    """Delete orphaned test jobs from catalog_jobs collection."""
    
    db = firestore.Client()
    
    # Query all queued jobs (these are the orphaned ones)
    jobs_ref = db.collection("catalog_jobs")
    query = jobs_ref.where("status", "==", "queued")
    
    docs = list(query.stream())
    
    print(f"Found {len(docs)} queued jobs in catalog_jobs")
    
    if not docs:
        print("No jobs to delete.")
        return
    
    # Show what we're about to delete
    print("\nJobs to delete:")
    print("-" * 80)
    
    for doc in docs[:10]:  # Show first 10
        data = doc.to_dict()
        job_type = data.get("type", "unknown")
        created = data.get("created_at")
        mode = data.get("payload", {}).get("mode", "unknown")
        print(f"  {doc.id}: type={job_type}, mode={mode}, created={created}")
    
    if len(docs) > 10:
        print(f"  ... and {len(docs) - 10} more")
    
    print("-" * 80)
    
    if dry_run:
        print(f"\n⚠️  DRY RUN: Would delete {len(docs)} jobs")
        print("Run with --apply to actually delete")
        return
    
    # Delete in batches of 500 (Firestore limit)
    batch_size = 500
    deleted = 0
    
    for i in range(0, len(docs), batch_size):
        batch = db.batch()
        batch_docs = docs[i:i + batch_size]
        
        for doc in batch_docs:
            batch.delete(doc.reference)
        
        batch.commit()
        deleted += len(batch_docs)
        print(f"Deleted batch: {deleted}/{len(docs)}")
    
    print(f"\n✅ Successfully deleted {deleted} jobs")


def main():
    parser = argparse.ArgumentParser(description="Cleanup orphaned test jobs")
    parser.add_argument(
        "--dry-run", action="store_true", default=True,
        help="Preview what would be deleted (default)"
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Actually delete the jobs"
    )
    
    args = parser.parse_args()
    
    dry_run = not args.apply
    
    print("=" * 60)
    print("CATALOG JOBS CLEANUP")
    print("=" * 60)
    print(f"Mode: {'DRY RUN' if dry_run else 'APPLY (DELETING)'}")
    print()
    
    cleanup_test_jobs(dry_run=dry_run)


if __name__ == "__main__":
    main()
