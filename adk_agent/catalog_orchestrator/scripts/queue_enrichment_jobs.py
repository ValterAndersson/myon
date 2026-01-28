#!/usr/bin/env python3
"""
Phase 3: Queue LLM Enrichment Jobs

This script queues catalog jobs for exercises missing required fields:
1. Missing muscles.contribution → CATALOG_ENRICH_FIELD job
2. Missing muscles.primary/secondary → TARGETED_FIX job
3. Missing description → CATALOG_ENRICH_FIELD job

Usage:
    # Dry run (default) - shows what jobs would be created
    python scripts/queue_enrichment_jobs.py

    # Apply - create the jobs
    python scripts/queue_enrichment_jobs.py --apply

    # Limit to N exercises
    python scripts/queue_enrichment_jobs.py --limit 50

    # Only queue specific field types
    python scripts/queue_enrichment_jobs.py --fields "muscles.contribution,description"
"""

import argparse
import logging
import sys
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from google.cloud import firestore

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Fields that trigger enrichment jobs
ENRICHMENT_FIELDS = {
    'muscles.contribution': {
        'job_type': 'CATALOG_ENRICH_FIELD',
        'priority': 50,
        'queue': 'maintenance',
    },
    'muscles.primary': {
        'job_type': 'TARGETED_FIX',
        'priority': 60,
        'queue': 'priority',
    },
    'muscles.secondary': {
        'job_type': 'TARGETED_FIX', 
        'priority': 60,
        'queue': 'priority',
    },
    'description': {
        'job_type': 'CATALOG_ENRICH_FIELD',
        'priority': 40,
        'queue': 'maintenance',
    },
}


def generate_job_id() -> str:
    """Generate a unique job ID."""
    return f"job-{uuid.uuid4().hex[:12]}"


def check_missing_fields(data: Dict[str, Any]) -> List[str]:
    """Check which enrichment fields are missing."""
    missing = []
    muscles = data.get('muscles', {}) or {}
    
    if not muscles.get('contribution'):
        missing.append('muscles.contribution')
    
    if not muscles.get('primary'):
        missing.append('muscles.primary')
    
    if not muscles.get('secondary'):
        missing.append('muscles.secondary')
    
    if not data.get('description'):
        missing.append('description')
    
    return missing


class EnrichmentJobQueue:
    def __init__(self, project_id: str = 'myon-53d85'):
        self.db = firestore.Client(project=project_id)
        self.stats = {
            'exercises_scanned': 0,
            'exercises_needing_enrichment': 0,
            'jobs_created': 0,
            'jobs_by_type': {},
            'jobs_by_field': {},
            'errors': 0,
        }
        self.jobs_to_create: List[Dict[str, Any]] = []
    
    def run(
        self,
        apply: bool = False,
        limit: Optional[int] = None,
        fields_filter: Optional[Set[str]] = None
    ):
        """Run the enrichment job queue process."""
        logger.info(f"Starting enrichment job queue (apply={apply}, limit={limit})")
        
        # Step 1: Scan exercises for missing fields
        self._scan_exercises(limit, fields_filter)
        
        # Step 2: Create jobs if applying
        if apply:
            self._create_jobs()
        
        # Summary
        self._print_summary(apply)
        
        return self.stats
    
    def _scan_exercises(self, limit: Optional[int], fields_filter: Optional[Set[str]]):
        """Scan exercises and identify those needing enrichment."""
        logger.info("Scanning exercises for missing fields...")
        
        query = self.db.collection('exercises')
        if limit:
            query = query.limit(limit)
        
        exercises_by_family: Dict[str, List[Dict]] = {}
        
        for doc in query.stream():
            self.stats['exercises_scanned'] += 1
            data = doc.to_dict()
            
            missing = check_missing_fields(data)
            
            # Apply field filter if provided
            if fields_filter:
                missing = [f for f in missing if f in fields_filter]
            
            if not missing:
                continue
            
            self.stats['exercises_needing_enrichment'] += 1
            
            # Track by field
            for field in missing:
                self.stats['jobs_by_field'][field] = self.stats['jobs_by_field'].get(field, 0) + 1
            
            # Group by family for batch jobs
            family_slug = data.get('family_slug', 'unknown')
            if family_slug not in exercises_by_family:
                exercises_by_family[family_slug] = []
            
            exercises_by_family[family_slug].append({
                'id': doc.id,
                'name': data.get('name'),
                'name_slug': data.get('name_slug'),
                'missing_fields': missing,
            })
        
        logger.info(f"Scanned {self.stats['exercises_scanned']} exercises")
        logger.info(f"Found {self.stats['exercises_needing_enrichment']} needing enrichment")
        
        # Build jobs - group by family and primary missing field
        self._build_jobs(exercises_by_family, fields_filter)
    
    def _build_jobs(self, exercises_by_family: Dict[str, List[Dict]], fields_filter: Optional[Set[str]]):
        """Build job definitions from grouped exercises."""
        for family_slug, exercises in exercises_by_family.items():
            # Determine primary missing field type for the job
            all_missing = set()
            for ex in exercises:
                all_missing.update(ex['missing_fields'])
            
            # Create one job per primary field type
            for field in all_missing:
                if fields_filter and field not in fields_filter:
                    continue
                
                config = ENRICHMENT_FIELDS.get(field)
                if not config:
                    continue
                
                # Get exercises missing this specific field
                relevant_exercises = [
                    ex for ex in exercises 
                    if field in ex['missing_fields']
                ]
                
                if not relevant_exercises:
                    continue
                
                job_type = config['job_type']
                
                job = {
                    'id': generate_job_id(),
                    'type': job_type,
                    'queue': config['queue'],
                    'priority': config['priority'],
                    'status': 'queued',
                    'payload': {
                        'family_slug': family_slug,
                        'exercise_doc_ids': [ex['id'] for ex in relevant_exercises],
                        'target_field': field,
                        'mode': 'apply',
                    },
                    'attempts': 0,
                    'max_attempts': 3,
                    'created_at': firestore.SERVER_TIMESTAMP,
                    'updated_at': firestore.SERVER_TIMESTAMP,
                }
                
                self.jobs_to_create.append(job)
                self.stats['jobs_by_type'][job_type] = self.stats['jobs_by_type'].get(job_type, 0) + 1
                
                logger.info(f"Queuing {job_type} for {family_slug}: {len(relevant_exercises)} exercises missing {field}")
    
    def _create_jobs(self):
        """Create jobs in Firestore."""
        logger.info(f"Creating {len(self.jobs_to_create)} jobs...")
        
        batch = self.db.batch()
        batch_count = 0
        
        for job in self.jobs_to_create:
            job_id = job['id']
            ref = self.db.collection('catalog_jobs').document(job_id)
            batch.set(ref, job)
            batch_count += 1
            
            # Commit in batches of 400
            if batch_count >= 400:
                batch.commit()
                logger.info(f"  Committed {batch_count} jobs")
                batch = self.db.batch()
                batch_count = 0
        
        # Commit remaining
        if batch_count > 0:
            batch.commit()
            logger.info(f"  Committed {batch_count} jobs")
        
        self.stats['jobs_created'] = len(self.jobs_to_create)
    
    def _print_summary(self, apply: bool):
        """Print summary."""
        mode = "APPLIED" if apply else "DRY RUN"
        
        print("\n" + "=" * 60)
        print(f"ENRICHMENT JOB QUEUE SUMMARY ({mode})")
        print("=" * 60)
        print(f"Exercises scanned: {self.stats['exercises_scanned']}")
        print(f"Exercises needing enrichment: {self.stats['exercises_needing_enrichment']}")
        print(f"{'Jobs created' if apply else 'Jobs to create'}: {len(self.jobs_to_create)}")
        
        if self.stats['jobs_by_field']:
            print("\nBreakdown by missing field:")
            for field, count in sorted(self.stats['jobs_by_field'].items()):
                print(f"  {field}: {count} exercises")
        
        if self.stats['jobs_by_type']:
            print("\nBreakdown by job type:")
            for job_type, count in sorted(self.stats['jobs_by_type'].items()):
                print(f"  {job_type}: {count} jobs")
        
        if self.jobs_to_create and len(self.jobs_to_create) <= 20:
            print("\nJobs to create:")
            for job in self.jobs_to_create:
                exercises = job['payload']['exercise_doc_ids']
                print(f"  {job['id']}: {job['type']} for {job['payload']['family_slug']} ({len(exercises)} exercises)")


def main():
    parser = argparse.ArgumentParser(description='Queue LLM enrichment jobs for exercises')
    parser.add_argument('--apply', action='store_true', help='Apply changes (default: dry run)')
    parser.add_argument('--limit', type=int, help='Limit number of exercises to scan')
    parser.add_argument('--fields', type=str, help='Comma-separated list of fields to check (default: all)')
    parser.add_argument('--project', type=str, default='myon-53d85', help='GCP project ID')
    
    args = parser.parse_args()
    
    fields_filter = None
    if args.fields:
        fields_filter = set(f.strip() for f in args.fields.split(','))
    
    queue = EnrichmentJobQueue(project_id=args.project)
    stats = queue.run(
        apply=args.apply,
        limit=args.limit,
        fields_filter=fields_filter
    )
    
    sys.exit(1 if stats['errors'] > 0 else 0)


if __name__ == '__main__':
    main()
