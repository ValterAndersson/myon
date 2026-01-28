#!/usr/bin/env python3
"""
Cleanup Duplicate Jobs - Rejects all needs_review jobs with DUPLICATE_EXERCISE error.

These jobs were created by the reviewer suggesting exercises that already exist.
Since we've now added pre-checks to prevent duplicates at job creation time,
these legacy jobs can be safely rejected.

Usage:
    # Dry run (default) - just count jobs
    python scripts/cleanup_duplicate_jobs.py
    
    # Actually reject the jobs
    python scripts/cleanup_duplicate_jobs.py --apply
"""

import argparse
import logging
import sys
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def cleanup_duplicate_jobs(dry_run: bool = True) -> dict:
    """
    Find and reject all needs_review jobs with DUPLICATE_EXERCISE error.
    
    Args:
        dry_run: If True, just count - don't actually reject
        
    Returns:
        Summary of actions taken
    """
    from google.cloud import firestore
    from google.cloud.firestore_v1 import FieldFilter
    
    db = firestore.Client(project='myon-53d85')
    
    # Find all needs_review jobs
    query = db.collection('catalog_jobs').where(
        filter=FieldFilter('status', '==', 'needs_review')
    )
    
    duplicate_jobs = []
    other_jobs = []
    
    for doc in query.stream():
        data = doc.to_dict()
        error = data.get('error', {})
        
        if error.get('code') == 'DUPLICATE_EXERCISE':
            duplicate_jobs.append({
                'id': doc.id,
                'intent': data.get('payload', {}).get('intent', {}),
                'error_message': error.get('message', ''),
                'existing_doc_id': error.get('existing_doc_id', ''),
                'created_at': data.get('created_at'),
            })
        else:
            other_jobs.append({
                'id': doc.id,
                'type': data.get('type'),
                'error': error,
            })
    
    logger.info("Found %d DUPLICATE_EXERCISE jobs to reject", len(duplicate_jobs))
    logger.info("Found %d other needs_review jobs (not touching)", len(other_jobs))
    
    rejected_count = 0
    errors = []
    
    if not dry_run:
        for job in duplicate_jobs:
            try:
                db.collection('catalog_jobs').document(job['id']).update({
                    'status': 'rejected',
                    'rejected_at': datetime.now(timezone.utc),
                    'rejection_reason': 'Auto-rejected: exercise already exists in catalog',
                    'updated_at': datetime.now(timezone.utc),
                })
                rejected_count += 1
                logger.debug("Rejected job %s", job['id'])
            except Exception as e:
                logger.error("Failed to reject job %s: %s", job['id'], e)
                errors.append({'id': job['id'], 'error': str(e)})
        
        logger.info("Rejected %d duplicate jobs", rejected_count)
    else:
        logger.info("DRY RUN - would reject %d jobs", len(duplicate_jobs))
        
        # Show sample of what would be rejected
        for job in duplicate_jobs[:5]:
            intent = job.get('intent', {})
            logger.info("  Would reject: %s (%s) - %s", 
                       job['id'], 
                       intent.get('base_name', 'unknown'),
                       job.get('error_message', ''))
        
        if len(duplicate_jobs) > 5:
            logger.info("  ... and %d more", len(duplicate_jobs) - 5)
    
    return {
        'dry_run': dry_run,
        'duplicate_jobs_found': len(duplicate_jobs),
        'other_needs_review': len(other_jobs),
        'rejected': rejected_count,
        'errors': len(errors),
        'sample_duplicates': duplicate_jobs[:10],
    }


def main():
    parser = argparse.ArgumentParser(
        description="Reject needs_review jobs with DUPLICATE_EXERCISE error"
    )
    parser.add_argument(
        '--apply', action='store_true',
        help="Actually reject the jobs (default: dry run)"
    )
    parser.add_argument(
        '--verbose', '-v', action='store_true',
        help="Verbose output"
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    result = cleanup_duplicate_jobs(dry_run=not args.apply)
    
    print("\n" + "=" * 50)
    print("CLEANUP SUMMARY")
    print("=" * 50)
    print(f"Mode: {'APPLY' if not result['dry_run'] else 'DRY RUN'}")
    print(f"Duplicate jobs found: {result['duplicate_jobs_found']}")
    print(f"Other needs_review: {result['other_needs_review']}")
    print(f"Jobs rejected: {result['rejected']}")
    print(f"Errors: {result['errors']}")
    
    if result['dry_run']:
        print("\nRun with --apply to actually reject the jobs")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
