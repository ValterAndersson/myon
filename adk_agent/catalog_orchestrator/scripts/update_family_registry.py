#!/usr/bin/env python3
"""
Phase 2: Family Registry Update Script

This script updates the exercise_families collection:
1. Recalculate exercise_count for each family
2. Add equipment_variants aggregation
3. Add grip_variants if present
4. Clean up inconsistent family IDs

Usage:
    # Dry run (default)
    python scripts/update_family_registry.py

    # Apply changes
    python scripts/update_family_registry.py --apply

    # Process specific family
    python scripts/update_family_registry.py --family-slug "biceps_curl"
"""

import argparse
import logging
import re
import sys
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def normalize_family_slug(slug: str) -> str:
    """Normalize family slug to snake_case format."""
    if not slug:
        return ''
    # Convert kebab-case to snake_case
    normalized = slug.lower().strip()
    normalized = re.sub(r'-+', '_', normalized)
    # Remove any non-alphanumeric except underscores
    normalized = re.sub(r'[^a-z0-9_]', '', normalized)
    # Remove multiple consecutive underscores
    normalized = re.sub(r'_+', '_', normalized)
    return normalized.strip('_')


def extract_equipment_from_name(name: str) -> Optional[str]:
    """Extract equipment from exercise name in parentheses."""
    match = re.search(r'\(([^)]+)\)', name)
    if match:
        return match.group(1).lower().strip()
    return None


class FamilyRegistryUpdate:
    def __init__(self, project_id: str = 'myon-53d85'):
        self.db = firestore.Client(project=project_id)
        self.stats = {
            'total_families': 0,
            'updated': 0,
            'created': 0,
            'orphaned_families': 0,
            'exercises_scanned': 0,
            'errors': 0,
        }
        # family_slug -> {count, equipment_variants, exercises}
        self.family_data: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            'count': 0,
            'equipment_variants': set(),
            'exercises': [],
            'variant_keys': set(),
        })
    
    def run(self, apply: bool = False, family_slug: Optional[str] = None):
        """Run the family registry update."""
        logger.info(f"Starting family registry update (apply={apply})")
        
        # Step 1: Scan all exercises to build family data
        self._scan_exercises(family_slug)
        
        # Step 2: Update family registry
        self._update_families(apply, family_slug)
        
        # Step 3: Find orphaned families (no exercises)
        self._find_orphaned_families(apply)
        
        # Summary
        self._print_summary(apply)
        
        return self.stats
    
    def _scan_exercises(self, family_filter: Optional[str] = None):
        """Scan exercises to build family aggregation data."""
        logger.info("Scanning exercises...")
        
        query = self.db.collection('exercises')
        if family_filter:
            query = query.where(filter=FieldFilter('family_slug', '==', family_filter))
        
        for doc in query.stream():
            self.stats['exercises_scanned'] += 1
            data = doc.to_dict()
            
            family_slug = data.get('family_slug')
            if not family_slug:
                continue
            
            # Normalize family slug
            normalized_slug = normalize_family_slug(family_slug)
            
            # Aggregate data
            family = self.family_data[normalized_slug]
            family['count'] += 1
            
            # Extract equipment
            equipment = data.get('equipment', [])
            if isinstance(equipment, list):
                for eq in equipment:
                    if eq:
                        family['equipment_variants'].add(eq.lower())
            
            # Extract from name if not in equipment field
            name = data.get('name', '')
            name_equipment = extract_equipment_from_name(name)
            if name_equipment:
                family['equipment_variants'].add(name_equipment)
            
            # Track variant keys
            variant_key = data.get('variant_key')
            if variant_key:
                family['variant_keys'].add(variant_key)
            
            # Track exercises
            family['exercises'].append({
                'id': doc.id,
                'name': data.get('name'),
                'name_slug': data.get('name_slug'),
            })
        
        logger.info(f"Scanned {self.stats['exercises_scanned']} exercises across {len(self.family_data)} families")
    
    def _update_families(self, apply: bool, family_filter: Optional[str] = None):
        """Update family registry documents."""
        logger.info("Updating family registry...")
        
        families_ref = self.db.collection('exercise_families')
        
        for family_slug, data in self.family_data.items():
            if family_filter and family_slug != family_filter:
                continue
            
            self.stats['total_families'] += 1
            
            # Build update data
            update_data = {
                'exercise_count': data['count'],
                'equipment_variants': sorted(list(data['equipment_variants'])),
                'updated_at': firestore.SERVER_TIMESTAMP,
            }
            
            # Add variant_keys if present
            if data['variant_keys']:
                update_data['known_variant_keys'] = sorted(list(data['variant_keys']))
            
            # Check if family doc exists
            family_doc = families_ref.document(family_slug).get()
            
            if family_doc.exists:
                existing = family_doc.to_dict()
                changes = []
                
                if existing.get('exercise_count') != data['count']:
                    changes.append(f"exercise_count: {existing.get('exercise_count', 0)} → {data['count']}")
                
                existing_eq = set(existing.get('equipment_variants', []))
                new_eq = data['equipment_variants']
                if existing_eq != new_eq:
                    added = new_eq - existing_eq
                    if added:
                        changes.append(f"equipment_variants: +{list(added)}")
                
                if changes:
                    logger.info(f"Updating {family_slug}:")
                    for change in changes:
                        logger.info(f"  - {change}")
                    
                    if apply:
                        families_ref.document(family_slug).update(update_data)
                        logger.info(f"  ✓ Updated")
                    
                    self.stats['updated'] += 1
            else:
                # Create new family doc
                logger.info(f"Creating new family: {family_slug} (count={data['count']}, equipment={list(data['equipment_variants'])})")
                
                create_data = {
                    **update_data,
                    'family_slug': family_slug,
                    'base_name': family_slug.replace('_', ' ').title(),
                    'status': 'active',
                    'allowed_equipments': sorted(list(data['equipment_variants'])),
                    'primary_equipment_set': [],
                    'notes': '',
                    'known_collisions': [],
                    'merged_into': None,
                    'created_at': firestore.SERVER_TIMESTAMP,
                }
                
                if apply:
                    families_ref.document(family_slug).set(create_data)
                    logger.info(f"  ✓ Created")
                
                self.stats['created'] += 1
    
    def _find_orphaned_families(self, apply: bool):
        """Find and optionally mark orphaned families (no exercises)."""
        logger.info("Checking for orphaned families...")
        
        active_families = set(self.family_data.keys())
        
        for doc in self.db.collection('exercise_families').stream():
            family_slug = doc.id
            normalized = normalize_family_slug(family_slug)
            
            if normalized not in active_families:
                data = doc.to_dict()
                # Skip if already marked as merged
                if data.get('merged_into') or data.get('status') == 'deprecated':
                    continue
                
                logger.warning(f"Orphaned family: {family_slug} (no exercises found)")
                self.stats['orphaned_families'] += 1
                
                if apply:
                    # Mark as deprecated rather than delete
                    self.db.collection('exercise_families').document(family_slug).update({
                        'status': 'deprecated',
                        'exercise_count': 0,
                        'updated_at': firestore.SERVER_TIMESTAMP,
                    })
                    logger.info(f"  ✓ Marked as deprecated")
    
    def _print_summary(self, apply: bool):
        """Print update summary."""
        mode = "APPLIED" if apply else "DRY RUN"
        
        print("\n" + "=" * 60)
        print(f"FAMILY REGISTRY UPDATE SUMMARY ({mode})")
        print("=" * 60)
        print(f"Exercises scanned: {self.stats['exercises_scanned']}")
        print(f"Total families: {self.stats['total_families']}")
        print(f"{'Updated' if apply else 'Would update'}: {self.stats['updated']}")
        print(f"{'Created' if apply else 'Would create'}: {self.stats['created']}")
        print(f"Orphaned families: {self.stats['orphaned_families']}")
        print(f"Errors: {self.stats['errors']}")
        
        # Show top families by count
        top_families = sorted(
            self.family_data.items(),
            key=lambda x: x[1]['count'],
            reverse=True
        )[:15]
        
        print("\nTop 15 families by exercise count:")
        for slug, data in top_families:
            eq = ', '.join(sorted(data['equipment_variants'])[:5])
            if len(data['equipment_variants']) > 5:
                eq += f" (+{len(data['equipment_variants']) - 5} more)"
            print(f"  {slug}: {data['count']} exercises, equipment: [{eq}]")


def main():
    parser = argparse.ArgumentParser(description='Update exercise family registry')
    parser.add_argument('--apply', action='store_true', help='Apply changes (default: dry run)')
    parser.add_argument('--family-slug', type=str, help='Process specific family')
    parser.add_argument('--project', type=str, default='myon-53d85', help='GCP project ID')
    
    args = parser.parse_args()
    
    updater = FamilyRegistryUpdate(project_id=args.project)
    stats = updater.run(
        apply=args.apply,
        family_slug=args.family_slug
    )
    
    sys.exit(1 if stats['errors'] > 0 else 0)


if __name__ == '__main__':
    main()
