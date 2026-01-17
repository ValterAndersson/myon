#!/usr/bin/env python3
"""
Export production exercise catalog to Firestore emulator.

Usage:
    # 1. Make sure emulator is running:
    firebase emulators:start --only firestore
    
    # 2. Run this script (uses ADC for prod, emulator for writes):
    python scripts/export_catalog_to_emulator.py
    
    # 3. Verify import worked:
    python scripts/export_catalog_to_emulator.py --verify
"""

import argparse
import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, List

# Production project
PROD_PROJECT = "myon-53d85"  # Update if different

# Emulator config
EMULATOR_HOST = "127.0.0.1:8085"

# Collections to export
COLLECTIONS = ["exercises", "exercise_aliases"]


def get_prod_client():
    """Get Firestore client for production (uses ADC)."""
    # Ensure emulator is NOT used for production reads
    if "FIRESTORE_EMULATOR_HOST" in os.environ:
        del os.environ["FIRESTORE_EMULATOR_HOST"]
    
    from google.cloud import firestore
    return firestore.Client(project=PROD_PROJECT)


def get_emulator_client():
    """Get Firestore client for emulator."""
    os.environ["FIRESTORE_EMULATOR_HOST"] = EMULATOR_HOST
    
    from google.cloud import firestore
    # Force new client with emulator host
    return firestore.Client(project="demo-povver")


def export_collection(prod_client, collection_name: str) -> List[Dict[str, Any]]:
    """Export all documents from a production collection."""
    print(f"Reading {collection_name} from production...")
    
    docs = []
    for doc in prod_client.collection(collection_name).stream():
        data = doc.to_dict()
        data["_doc_id"] = doc.id
        docs.append(data)
    
    print(f"  Found {len(docs)} documents")
    return docs


def import_collection(emulator_client, collection_name: str, docs: List[Dict[str, Any]]) -> int:
    """Import documents to emulator collection."""
    print(f"Writing {len(docs)} documents to emulator {collection_name}...")
    
    batch = emulator_client.batch()
    batch_count = 0
    total_written = 0
    
    for doc_data in docs:
        doc_id = doc_data.pop("_doc_id")
        doc_ref = emulator_client.collection(collection_name).document(doc_id)
        batch.set(doc_ref, doc_data)
        batch_count += 1
        
        # Firestore batch limit is 500
        if batch_count >= 400:
            batch.commit()
            total_written += batch_count
            print(f"  Committed batch: {total_written}/{len(docs)}")
            batch = emulator_client.batch()
            batch_count = 0
    
    if batch_count > 0:
        batch.commit()
        total_written += batch_count
    
    print(f"  ✓ Wrote {total_written} documents")
    return total_written


def clear_emulator_collection(emulator_client, collection_name: str) -> int:
    """Delete all documents in emulator collection."""
    print(f"Clearing {collection_name} from emulator...")
    
    deleted = 0
    batch = emulator_client.batch()
    batch_count = 0
    
    for doc in emulator_client.collection(collection_name).stream():
        batch.delete(doc.reference)
        batch_count += 1
        deleted += 1
        
        if batch_count >= 400:
            batch.commit()
            batch = emulator_client.batch()
            batch_count = 0
    
    if batch_count > 0:
        batch.commit()
    
    print(f"  Deleted {deleted} documents")
    return deleted


def clear_catalog_admin_collections(emulator_client):
    """Clear catalog orchestrator collections (jobs, locks, etc)."""
    admin_collections = [
        "catalog_jobs",
        "catalog_locks", 
        "catalog_changes",
        "exercise_families",
    ]
    
    for coll in admin_collections:
        try:
            clear_emulator_collection(emulator_client, coll)
        except Exception as e:
            print(f"  Note: {coll} - {e}")


def verify_import(emulator_client):
    """Verify data was imported correctly."""
    print("\n=== Verification ===")
    
    for collection_name in COLLECTIONS:
        count = sum(1 for _ in emulator_client.collection(collection_name).stream())
        print(f"{collection_name}: {count} documents")
    
    # Show sample
    print("\nSample exercises:")
    for doc in emulator_client.collection("exercises").limit(5).stream():
        d = doc.to_dict()
        print(f"  {doc.id}: {d.get('name')} ({d.get('equipment')})")


def main():
    parser = argparse.ArgumentParser(description="Export production catalog to emulator")
    parser.add_argument("--verify", action="store_true", help="Only verify emulator data")
    parser.add_argument("--clear-only", action="store_true", help="Only clear emulator data")
    parser.add_argument("--no-clear", action="store_true", help="Don't clear existing data first")
    args = parser.parse_args()
    
    print(f"Emulator host: {EMULATOR_HOST}")
    print(f"Production project: {PROD_PROJECT}")
    print()
    
    if args.verify:
        emulator_client = get_emulator_client()
        verify_import(emulator_client)
        return
    
    if args.clear_only:
        emulator_client = get_emulator_client()
        for coll in COLLECTIONS:
            clear_emulator_collection(emulator_client, coll)
        clear_catalog_admin_collections(emulator_client)
        print("\n✓ Emulator cleared")
        return
    
    # Export from production
    print("=" * 50)
    print("STEP 1: Export from production")
    print("=" * 50)
    
    prod_client = get_prod_client()
    exported_data = {}
    
    for coll in COLLECTIONS:
        try:
            exported_data[coll] = export_collection(prod_client, coll)
        except Exception as e:
            print(f"  Warning: {coll} - {e}")
            exported_data[coll] = []
    
    # Clear emulator
    if not args.no_clear:
        print()
        print("=" * 50)
        print("STEP 2: Clear emulator")
        print("=" * 50)
        
        emulator_client = get_emulator_client()
        for coll in COLLECTIONS:
            clear_emulator_collection(emulator_client, coll)
        clear_catalog_admin_collections(emulator_client)
    
    # Import to emulator
    print()
    print("=" * 50)
    print("STEP 3: Import to emulator")
    print("=" * 50)
    
    emulator_client = get_emulator_client()
    
    for coll, docs in exported_data.items():
        if docs:
            import_collection(emulator_client, coll, docs)
    
    # Verify
    print()
    verify_import(emulator_client)
    
    print()
    print("=" * 50)
    print("✓ Export complete!")
    print("=" * 50)
    print()
    print("Next steps:")
    print("  # Run maintenance scan:")
    print("  cd adk_agent/catalog_orchestrator")
    print("  FIRESTORE_EMULATOR_HOST=127.0.0.1:8085 python cli.py maintenance-scan --mode dry_run")
    print()
    print("  # Run worker:")
    print("  FIRESTORE_EMULATOR_HOST=127.0.0.1:8085 python workers/catalog_worker.py")


if __name__ == "__main__":
    main()
