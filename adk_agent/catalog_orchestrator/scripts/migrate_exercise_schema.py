#!/usr/bin/env python3
"""
Phase 1: Exercise Schema Migration Script

This script migrates exercises to the canonical schema:
1. Migrate doc IDs to {family_slug}__{name_slug} format
2. Normalize muscle fields (top-level → nested)
3. Convert string fields to arrays (instructions → execution_notes[])
4. Remove legacy fields (enriched_*, _debug_*, etc.)
5. Update exercise_aliases to point to new IDs

Usage:
    # Dry run (default) - shows what would change
    python scripts/migrate_exercise_schema.py

    # Apply changes
    python scripts/migrate_exercise_schema.py --apply

    # Limit to N exercises (for testing)
    python scripts/migrate_exercise_schema.py --limit 10

    # Process specific exercise
    python scripts/migrate_exercise_schema.py --exercise-id "38pcIFH7DhQq74Nr5WGJ"
"""

import argparse
import logging
import re
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Fields to DELETE entirely
FIELDS_TO_DELETE = {
    'enriched_common_mistakes',
    'enriched_instructions',
    'enriched_tips',
    'enriched_cues',
    'enriched_at',
    'enriched_by',
    '_debug_project_id',
    'delete_candidate',
    'delete_candidate_justification',
    'id',  # Redundant with doc ID
    'created_by',
    'created_at',  # Keep updated_at only
    'version',
    'images',  # Empty/unused
}

# Fields that should be arrays
ARRAY_FIELDS = {
    'execution_notes',
    'common_mistakes',
    'programming_use_cases',
    'stimulus_tags',
    'suitability_notes',
    'coaching_cues',
    'equipment',
}


def slugify(text: str) -> str:
    """Convert text to URL-safe slug."""
    if not text:
        return ''
    # Lowercase and replace spaces/underscores with hyphens
    slug = text.lower().strip()
    slug = re.sub(r'[\s_]+', '-', slug)
    # Remove non-alphanumeric except hyphens
    slug = re.sub(r'[^a-z0-9\-]', '', slug)
    # Remove multiple consecutive hyphens
    slug = re.sub(r'-+', '-', slug)
    # Remove leading/trailing hyphens
    slug = slug.strip('-')
    return slug


def parse_numbered_list(text: str) -> List[str]:
    """Parse a numbered list string into array of steps."""
    if not text or not isinstance(text, str):
        return []
    
    # Split by numbered patterns like "1.", "2.", etc.
    lines = re.split(r'\n?\d+\.\s*', text)
    # Filter empty and strip whitespace
    items = [line.strip() for line in lines if line.strip()]
    return items


def normalize_muscles(doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize muscle fields:
    - Move top-level primary_muscles/secondary_muscles into muscles.primary/secondary
    - Ensure muscles.category is an array
    """
    muscles = doc.get('muscles', {}) or {}
    if not isinstance(muscles, dict):
        muscles = {}
    
    # Move top-level fields into muscles
    if 'primary_muscles' in doc:
        if not muscles.get('primary'):
            muscles['primary'] = doc['primary_muscles'] if isinstance(doc['primary_muscles'], list) else []
    
    if 'secondary_muscles' in doc:
        if not muscles.get('secondary'):
            muscles['secondary'] = doc['secondary_muscles'] if isinstance(doc['secondary_muscles'], list) else []
    
    # Ensure arrays exist
    if 'primary' not in muscles:
        muscles['primary'] = []
    if 'secondary' not in muscles:
        muscles['secondary'] = []
    
    # Ensure category is an array
    if 'category' in muscles:
        if isinstance(muscles['category'], str):
            muscles['category'] = [muscles['category']]
    else:
        muscles['category'] = []
    
    return muscles


def normalize_array_field(doc: Dict[str, Any], field: str) -> Optional[List[str]]:
    """Ensure a field is an array of strings."""
    value = doc.get(field)
    if value is None:
        return None
    if isinstance(value, list):
        return [str(v) for v in value if v]
    if isinstance(value, str):
        return parse_numbered_list(value)
    return None


def build_canonical_id(family_slug: str, name_slug: str) -> str:
    """Build canonical document ID: {family_slug}__{name_slug}"""
    return f"{family_slug}__{name_slug}"


def transform_exercise(doc_id: str, data: Dict[str, Any]) -> Tuple[str, Dict[str, Any], List[str]]:
    """
    Transform an exercise document to canonical schema.
    
    Returns:
        (new_doc_id, transformed_data, changes_made)
    """
    changes = []
    transformed = {}
    
    # Required fields
    name = data.get('name', '')
    name_slug = data.get('name_slug') or slugify(name)
    family_slug = data.get('family_slug', '')
    
    if not name_slug:
        name_slug = slugify(name)
        changes.append(f"Generated name_slug: {name_slug}")
    
    if not family_slug:
        # Try to derive from name
        family_slug = slugify(name.split('(')[0].strip())
        changes.append(f"Derived family_slug: {family_slug}")
    
    # Build canonical ID
    new_doc_id = build_canonical_id(family_slug, name_slug)
    if new_doc_id != doc_id:
        changes.append(f"ID: {doc_id} → {new_doc_id}")
    
    # Copy required fields
    transformed['name'] = name
    transformed['name_slug'] = name_slug
    transformed['family_slug'] = family_slug
    transformed['category'] = data.get('category', 'exercise')
    transformed['equipment'] = data.get('equipment', [])
    if not isinstance(transformed['equipment'], list):
        transformed['equipment'] = [transformed['equipment']] if transformed['equipment'] else []
    
    # Optional fields to preserve
    if 'variant_key' in data:
        transformed['variant_key'] = data['variant_key']
    
    # Metadata
    if 'metadata' in data:
        transformed['metadata'] = data['metadata']
    else:
        transformed['metadata'] = {'level': 'intermediate'}
    
    # Movement
    if 'movement' in data:
        transformed['movement'] = data['movement']
    else:
        transformed['movement'] = {'type': 'other', 'split': 'upper'}
    
    # Normalize muscles
    muscles = normalize_muscles(data)
    if 'primary_muscles' in data or 'secondary_muscles' in data:
        changes.append("Moved primary_muscles/secondary_muscles into muscles.*")
    transformed['muscles'] = muscles
    
    # Description
    if 'description' in data and data['description']:
        transformed['description'] = data['description']
    
    # Array fields - normalize
    for field in ARRAY_FIELDS:
        if field == 'equipment':
            continue  # Already handled
        
        # Check for instructions → execution_notes conversion
        if field == 'execution_notes' and 'instructions' in data and data['instructions']:
            if isinstance(data['instructions'], str):
                parsed = parse_numbered_list(data['instructions'])
                if parsed:
                    transformed['execution_notes'] = parsed
                    changes.append(f"Converted instructions string to execution_notes[{len(parsed)}]")
                continue
        
        normalized = normalize_array_field(data, field)
        if normalized is not None:
            transformed[field] = normalized
        elif field in data:
            # Keep empty arrays
            transformed[field] = []
    
    # Always set updated_at
    transformed['updated_at'] = firestore.SERVER_TIMESTAMP
    
    # Track deleted fields
    deleted_fields = []
    for field in FIELDS_TO_DELETE:
        if field in data:
            deleted_fields.append(field)
    
    if deleted_fields:
        changes.append(f"Removing fields: {', '.join(deleted_fields)}")
    
    # Also remove top-level muscle fields (now in muscles.*)
    if 'primary_muscles' in data:
        deleted_fields.append('primary_muscles')
    if 'secondary_muscles' in data:
        deleted_fields.append('secondary_muscles')
    if 'instructions' in data:
        deleted_fields.append('instructions')
    if 'status' in data:
        deleted_fields.append('status')
    
    return new_doc_id, transformed, changes


def needs_enrichment(data: Dict[str, Any]) -> List[str]:
    """Check what LLM enrichment this exercise needs."""
    needs = []
    muscles = data.get('muscles', {})
    
    if not muscles.get('contribution'):
        needs.append('muscles.contribution')
    
    if not muscles.get('primary'):
        needs.append('muscles.primary')
    
    if not muscles.get('secondary'):
        needs.append('muscles.secondary')
    
    if not data.get('description'):
        needs.append('description')
    
    return needs


class ExerciseMigration:
    def __init__(self, project_id: str = 'myon-53d85'):
        self.db = firestore.Client(project=project_id)
        self.stats = {
            'total': 0,
            'migrated': 0,
            'skipped_already_migrated': 0,
            'id_changes': 0,
            'schema_changes': 0,
            'errors': 0,
            'needs_enrichment': 0,
        }
        self.id_mapping = {}  # old_id -> new_id
        self.enrichment_needed = []  # exercises needing LLM enrichment
    
    def run(self, apply: bool = False, limit: Optional[int] = None, exercise_id: Optional[str] = None):
        """Run the migration."""
        logger.info(f"Starting exercise migration (apply={apply}, limit={limit})")
        
        # Get exercises
        if exercise_id:
            exercises = [self.db.collection('exercises').document(exercise_id).get()]
        else:
            query = self.db.collection('exercises')
            if limit:
                query = query.limit(limit)
            exercises = list(query.stream())
        
        logger.info(f"Found {len(exercises)} exercises to process")
        
        for doc in exercises:
            self.stats['total'] += 1
            try:
                self._process_exercise(doc, apply)
            except Exception as e:
                logger.error(f"Error processing {doc.id}: {e}")
                self.stats['errors'] += 1
        
        # Update aliases if applying
        if apply and self.id_mapping:
            self._update_aliases()
        
        # Summary
        self._print_summary(apply)
        
        return self.stats
    
    def _process_exercise(self, doc, apply: bool):
        """Process a single exercise document."""
        doc_id = doc.id
        data = doc.to_dict()
        
        # Check if already in canonical format
        if '__' in doc_id and doc_id.count('__') == 1:
            family, name = doc_id.split('__', 1)
            if family == data.get('family_slug') and name == data.get('name_slug'):
                # Check for legacy fields
                has_legacy = any(f in data for f in FIELDS_TO_DELETE)
                if not has_legacy:
                    logger.debug(f"Skipping {doc_id} - already migrated")
                    self.stats['skipped_already_migrated'] += 1
                    
                    # Still check enrichment needs
                    needs = needs_enrichment(data)
                    if needs:
                        self.enrichment_needed.append({
                            'id': doc_id,
                            'name': data.get('name'),
                            'needs': needs
                        })
                        self.stats['needs_enrichment'] += 1
                    return
        
        # Transform
        new_id, transformed, changes = transform_exercise(doc_id, data)
        
        if not changes:
            logger.debug(f"No changes needed for {doc_id}")
            return
        
        logger.info(f"Processing {doc_id}:")
        for change in changes:
            logger.info(f"  - {change}")
        
        # Track stats
        if new_id != doc_id:
            self.stats['id_changes'] += 1
            self.id_mapping[doc_id] = new_id
        
        self.stats['schema_changes'] += 1
        
        # Check enrichment needs
        needs = needs_enrichment(transformed)
        if needs:
            self.enrichment_needed.append({
                'id': new_id,
                'name': transformed.get('name'),
                'needs': needs
            })
            self.stats['needs_enrichment'] += 1
        
        if apply:
            # If ID changed, create new doc and delete old
            if new_id != doc_id:
                # Create new doc
                self.db.collection('exercises').document(new_id).set(transformed)
                # Delete old doc
                self.db.collection('exercises').document(doc_id).delete()
                logger.info(f"  ✓ Migrated {doc_id} → {new_id}")
            else:
                # Update in place
                self.db.collection('exercises').document(doc_id).set(transformed)
                logger.info(f"  ✓ Updated {doc_id}")
            
            self.stats['migrated'] += 1
    
    def _update_aliases(self):
        """Update exercise_aliases to point to new IDs."""
        if not self.id_mapping:
            return
        
        logger.info(f"Updating {len(self.id_mapping)} alias references...")
        
        for old_id, new_id in self.id_mapping.items():
            # Find aliases pointing to old ID
            aliases = self.db.collection('exercise_aliases').where(
                filter=FieldFilter('exercise_id', '==', old_id)
            ).stream()
            
            for alias_doc in aliases:
                self.db.collection('exercise_aliases').document(alias_doc.id).update({
                    'exercise_id': new_id,
                    'updated_at': firestore.SERVER_TIMESTAMP
                })
                logger.info(f"  Updated alias {alias_doc.id}: {old_id} → {new_id}")
    
    def _print_summary(self, apply: bool):
        """Print migration summary."""
        mode = "APPLIED" if apply else "DRY RUN"
        
        print("\n" + "=" * 60)
        print(f"EXERCISE MIGRATION SUMMARY ({mode})")
        print("=" * 60)
        print(f"Total exercises processed: {self.stats['total']}")
        print(f"Already migrated (skipped): {self.stats['skipped_already_migrated']}")
        print(f"ID changes: {self.stats['id_changes']}")
        print(f"Schema changes: {self.stats['schema_changes']}")
        print(f"{'Migrated' if apply else 'Would migrate'}: {self.stats['migrated'] if apply else self.stats['schema_changes']}")
        print(f"Errors: {self.stats['errors']}")
        print(f"Exercises needing LLM enrichment: {self.stats['needs_enrichment']}")
        
        if self.enrichment_needed and len(self.enrichment_needed) <= 20:
            print("\nExercises needing enrichment:")
            for ex in self.enrichment_needed:
                print(f"  - {ex['name']} ({ex['id']}): {', '.join(ex['needs'])}")
        elif self.enrichment_needed:
            print(f"\n(First 10 exercises needing enrichment:)")
            for ex in self.enrichment_needed[:10]:
                print(f"  - {ex['name']} ({ex['id']}): {', '.join(ex['needs'])}")
        
        if self.id_mapping and len(self.id_mapping) <= 20:
            print("\nID mappings:")
            for old, new in self.id_mapping.items():
                print(f"  {old} → {new}")


def main():
    parser = argparse.ArgumentParser(description='Migrate exercises to canonical schema')
    parser.add_argument('--apply', action='store_true', help='Apply changes (default: dry run)')
    parser.add_argument('--limit', type=int, help='Limit number of exercises to process')
    parser.add_argument('--exercise-id', type=str, help='Process specific exercise by ID')
    parser.add_argument('--project', type=str, default='myon-53d85', help='GCP project ID')
    
    args = parser.parse_args()
    
    migration = ExerciseMigration(project_id=args.project)
    stats = migration.run(
        apply=args.apply,
        limit=args.limit,
        exercise_id=args.exercise_id
    )
    
    # Exit with error code if there were errors
    sys.exit(1 if stats['errors'] > 0 else 0)


if __name__ == '__main__':
    main()
