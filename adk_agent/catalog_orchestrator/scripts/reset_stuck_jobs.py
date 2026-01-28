#!/usr/bin/env python3
"""
Reset stuck enrichment jobs from 'running' to 'queued'.

These jobs failed to complete due to the 'invalid nested entity' error
but the actual enrichment writes may have succeeded.
"""

from google.cloud import firestore
from datetime import datetime

db = firestore.Client()

# Find all stuck running jobs
query = db.collection("catalog_jobs").where("status", "==", "running")

reset_count = 0
job_ids = []

for doc in query.stream():
    data = doc.to_dict()
    job_type = data.get("type", "")
    
    # Reset enrichment jobs and any other stuck jobs
    print(f"Found stuck job: {doc.id} (type={job_type})")
    
    # Reset to queued
    doc.reference.update({
        "status": "queued",
        "lease_owner": None,
        "lease_expires_at": None,
        "updated_at": datetime.utcnow(),
    })
    
    reset_count += 1
    job_ids.append(doc.id)

print(f"\n✅ Reset {reset_count} stuck jobs to 'queued'")
print(f"Job IDs: {job_ids[:10]}{'...' if len(job_ids) > 10 else ''}")
