#!/usr/bin/env python3
"""
Catalog Orchestrator CLI.

Command-line interface for catalog operations:
- insert-exercise: Add new exercise to catalog
- enrich-field: Batch enrich exercises with LLM-computed fields
- normalize-catalog: Deterministic normalization (content arrays, muscles,
  equipment, movement, category) — no LLM calls
- dedup-catalog: Merge duplicate exercises with identical names

Usage:
    python cli.py insert-exercise --base-name "Lateral Raise" --equipment cable
    python cli.py enrich-field --spec-id difficulty --field-path metadata.difficulty ...
    python cli.py normalize-catalog --dry-run -v
    python cli.py dedup-catalog --dry-run -v
"""

from __future__ import annotations

import json
import os
import sys
from typing import List, Optional

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import click

from app.jobs.queue import create_job
from app.jobs.models import JobType, JobQueue


@click.group()
def cli():
    """Catalog Orchestrator CLI - Job triggers for catalog curation."""
    pass


# =============================================================================
# INSERT EXERCISE
# =============================================================================

@cli.command("insert-exercise")
@click.option("--base-name", required=True, help="Exercise base name (e.g., 'Lateral Raise')")
@click.option("--equipment", "-e", multiple=True, help="Equipment types (e.g., cable, dumbbell)")
@click.option("--muscles-primary", "-m", multiple=True, help="Primary muscles")
@click.option("--muscles-secondary", multiple=True, help="Secondary muscles")
@click.option("--description", help="Exercise description seed")
@click.option("--family-slug", help="Explicit family slug (auto-derived if not provided)")
@click.option("--mode", default="dry_run", type=click.Choice(["dry_run", "apply"]),
              help="Execution mode (default: dry_run)")
@click.option("--priority", default=100, type=int, help="Job priority (higher = more urgent)")
def insert_exercise(
    base_name: str,
    equipment: tuple,
    muscles_primary: tuple,
    muscles_secondary: tuple,
    description: Optional[str],
    family_slug: Optional[str],
    mode: str,
    priority: int,
):
    """
    Insert a new exercise into the catalog.
    
    Creates an EXERCISE_ADD job in the priority queue. The job will:
    - Derive canonical name with equipment qualifier if needed
    - Create proper slugs and family assignment
    - Set up aliases for the new exercise
    
    Examples:
        python cli.py insert-exercise --base-name "Lateral Raise" --equipment cable
        python cli.py insert-exercise --base-name "Deadlift" -e barbell -m glutes -m hamstrings --mode apply
    """
    intent = {
        "base_name": base_name,
        "equipment": list(equipment) if equipment else [],
        "muscles_primary": list(muscles_primary) if muscles_primary else [],
        "muscles_secondary": list(muscles_secondary) if muscles_secondary else [],
    }
    
    if description:
        intent["description_seed"] = description
    
    try:
        job = create_job(
            job_type=JobType.EXERCISE_ADD,
            queue=JobQueue.PRIORITY,
            priority=priority,
            family_slug=family_slug,
            mode=mode,
            intent=intent,
        )
        
        click.echo(click.style("✓ Exercise add job queued", fg="green"))
        click.echo(f"  Job ID:    {job.id}")
        click.echo(f"  Type:      {job.type.value}")
        click.echo(f"  Queue:     {job.queue.value}")
        click.echo(f"  Priority:  {priority}")
        click.echo(f"  Mode:      {mode}")
        click.echo(f"  Intent:    {json.dumps(intent, indent=2)}")
        
        if mode == "dry_run":
            click.echo(click.style("\n⚠ Dry-run mode: No changes will be applied", fg="yellow"))
            click.echo("  Run with --mode apply to create the exercise")
            
    except Exception as e:
        click.echo(click.style(f"✗ Failed to create job: {e}", fg="red"), err=True)
        sys.exit(1)


# =============================================================================
# ENRICH FIELD (BATCH)
# =============================================================================

@cli.command("enrich-field")
@click.option("--spec-id", required=True, help="Enrichment spec ID (e.g., 'difficulty', 'fatigue_score')")
@click.option("--spec-version", default="v1", help="Spec version for idempotency")
@click.option("--field-path", required=True, help="Target field path (e.g., 'metadata.difficulty')")
@click.option("--instructions", required=True, help="LLM instructions for computing the value")
@click.option("--output-type", default="enum", 
              type=click.Choice(["enum", "string", "number", "boolean", "object"]),
              help="Expected output type")
@click.option("--allowed-values", "-v", multiple=True, 
              help="Allowed values for enum type (e.g., -v beginner -v intermediate -v advanced)")
@click.option("--filter-equipment", help="Filter: only exercises with this equipment")
@click.option("--filter-category", help="Filter: only exercises in this category")
@click.option("--filter-family", help="Filter: only exercises in this family")
@click.option("--exercise-ids", help="Explicit exercise IDs (comma-separated, overrides filters)")
@click.option("--shard-size", default=200, type=int, help="Exercises per shard (default: 200)")
@click.option("--mode", default="dry_run", type=click.Choice(["dry_run", "apply"]),
              help="Execution mode (default: dry_run)")
def enrich_field(
    spec_id: str,
    spec_version: str,
    field_path: str,
    instructions: str,
    output_type: str,
    allowed_values: tuple,
    filter_equipment: Optional[str],
    filter_category: Optional[str],
    filter_family: Optional[str],
    exercise_ids: Optional[str],
    shard_size: int,
    mode: str,
):
    """
    Enqueue a batch field enrichment job.
    
    Creates a CATALOG_ENRICH_FIELD parent job that will:
    1. Query exercises matching filters
    2. Create shard jobs for parallel processing
    3. Each shard uses LLM to compute field values
    4. Apply changes with validation and journaling
    
    Examples:
        # Add difficulty ratings to all barbell exercises
        python cli.py enrich-field \\
            --spec-id difficulty \\
            --field-path metadata.difficulty \\
            --instructions "Rate difficulty based on muscles, complexity, and equipment" \\
            --output-type enum \\
            -v beginner -v intermediate -v advanced \\
            --filter-equipment barbell
        
        # Add joint stress tags (dry-run)
        python cli.py enrich-field \\
            --spec-id joint_stress \\
            --field-path metadata.joint_stress \\
            --instructions "List joints under stress during this movement" \\
            --output-type object
    """
    enrichment_spec = {
        "spec_id": spec_id,
        "spec_version": spec_version,
        "field_path": field_path,
        "instructions": instructions,
        "output_type": output_type,
        "allowed_values": list(allowed_values) if allowed_values else None,
    }
    
    # Build filter criteria
    filter_criteria = {}
    if filter_equipment:
        filter_criteria["equipment"] = filter_equipment
    if filter_category:
        filter_criteria["category"] = filter_category
    if filter_family:
        filter_criteria["family_slug"] = filter_family
    
    # Explicit exercise IDs override filters
    explicit_ids = []
    if exercise_ids:
        explicit_ids = [eid.strip() for eid in exercise_ids.split(",")]
    
    try:
        job = create_job(
            job_type=JobType.CATALOG_ENRICH_FIELD,
            queue=JobQueue.MAINTENANCE,
            mode=mode,
            enrichment_spec=enrichment_spec,
            filter_criteria=filter_criteria if filter_criteria else None,
            exercise_doc_ids=explicit_ids,
            shard_size=shard_size,
        )
        
        click.echo(click.style("✓ Enrichment job queued", fg="green"))
        click.echo(f"  Job ID:      {job.id}")
        click.echo(f"  Type:        {job.type.value}")
        click.echo(f"  Queue:       {job.queue.value}")
        click.echo(f"  Mode:        {mode}")
        click.echo(f"  Shard size:  {shard_size}")
        click.echo(f"  Spec:        {spec_id}:{spec_version}")
        click.echo(f"  Field:       {field_path}")
        
        if filter_criteria:
            click.echo(f"  Filters:     {json.dumps(filter_criteria)}")
        if explicit_ids:
            click.echo(f"  Exercise IDs: {len(explicit_ids)} specified")
        
        if mode == "dry_run":
            click.echo(click.style("\n⚠ Dry-run mode: No changes will be applied", fg="yellow"))
            click.echo("  Run with --mode apply (and CATALOG_APPLY_ENABLED=true) to apply")
            
    except Exception as e:
        click.echo(click.style(f"✗ Failed to create job: {e}", fg="red"), err=True)
        sys.exit(1)


# =============================================================================
# MAINTENANCE SCAN
# =============================================================================

@cli.command("maintenance-scan")
@click.option("--mode", default="dry_run", type=click.Choice(["dry_run", "apply"]),
              help="Execution mode (default: dry_run)")
def maintenance_scan(mode: str):
    """
    Scan all families for issues needing maintenance.
    
    Creates a MAINTENANCE_SCAN job that will:
    - Scan all exercise families
    - Detect naming issues (missing equipment qualifiers)
    - Detect duplicate equipment variants
    - Report families needing audit/normalization
    
    Example:
        python cli.py maintenance-scan
        python cli.py maintenance-scan --mode apply
    """
    try:
        job = create_job(
            job_type=JobType.MAINTENANCE_SCAN,
            queue=JobQueue.MAINTENANCE,
            mode=mode,
        )
        
        click.echo(click.style("✓ Maintenance scan job queued", fg="green"))
        click.echo(f"  Job ID:    {job.id}")
        click.echo(f"  Type:      {job.type.value}")
        click.echo(f"  Queue:     {job.queue.value}")
        click.echo(f"  Mode:      {mode}")
        
        click.echo(click.style("\nRun worker to process:", fg="cyan"))
        click.echo("  FIRESTORE_EMULATOR_HOST=127.0.0.1:8085 python workers/catalog_worker.py")
            
    except Exception as e:
        click.echo(click.style(f"✗ Failed to create job: {e}", fg="red"), err=True)
        sys.exit(1)


# =============================================================================
# DUPLICATE DETECTION SCAN
# =============================================================================

@cli.command("duplicate-scan")
@click.option("--mode", default="dry_run", type=click.Choice(["dry_run", "apply"]),
              help="Execution mode (default: dry_run)")
def duplicate_scan(mode: str):
    """
    Scan for potential duplicate exercises across families.
    
    Creates a DUPLICATE_DETECTION_SCAN job that will:
    - Compare exercise names across all families
    - Detect near-duplicate families
    - Suggest merge candidates
    
    Example:
        python cli.py duplicate-scan
    """
    try:
        job = create_job(
            job_type=JobType.DUPLICATE_DETECTION_SCAN,
            queue=JobQueue.MAINTENANCE,
            mode=mode,
        )
        
        click.echo(click.style("✓ Duplicate detection scan job queued", fg="green"))
        click.echo(f"  Job ID:    {job.id}")
        click.echo(f"  Type:      {job.type.value}")
        click.echo(f"  Queue:     {job.queue.value}")
        click.echo(f"  Mode:      {mode}")
        
        click.echo(click.style("\nRun worker to process:", fg="cyan"))
        click.echo("  FIRESTORE_EMULATOR_HOST=127.0.0.1:8085 python workers/catalog_worker.py")
            
    except Exception as e:
        click.echo(click.style(f"✗ Failed to create job: {e}", fg="red"), err=True)
        sys.exit(1)


# =============================================================================
# FAMILY AUDIT
# =============================================================================

@cli.command("family-audit")
@click.argument("family_slug")
@click.option("--mode", default="dry_run", type=click.Choice(["dry_run", "apply"]),
              help="Execution mode (default: dry_run)")
def family_audit(family_slug: str, mode: str):
    """
    Audit a specific exercise family.
    
    Creates a FAMILY_AUDIT job that will:
    - Check naming conformance
    - Detect equipment variants
    - Find duplicates within family
    - Validate alias integrity
    
    Example:
        python cli.py family-audit lateral-raise
        python cli.py family-audit deadlift
    """
    try:
        job = create_job(
            job_type=JobType.FAMILY_AUDIT,
            queue=JobQueue.PRIORITY,
            family_slug=family_slug,
            mode=mode,
        )
        
        click.echo(click.style("✓ Family audit job queued", fg="green"))
        click.echo(f"  Job ID:    {job.id}")
        click.echo(f"  Type:      {job.type.value}")
        click.echo(f"  Family:    {family_slug}")
        click.echo(f"  Mode:      {mode}")
        
        click.echo(click.style("\nRun worker to process:", fg="cyan"))
        click.echo("  FIRESTORE_EMULATOR_HOST=127.0.0.1:8085 python workers/catalog_worker.py")
            
    except Exception as e:
        click.echo(click.style(f"✗ Failed to create job: {e}", fg="red"), err=True)
        sys.exit(1)


# =============================================================================
# FAMILY NORMALIZE
# =============================================================================

@cli.command("family-normalize")
@click.argument("family_slug")
@click.option("--mode", default="dry_run", type=click.Choice(["dry_run", "apply"]),
              help="Execution mode (default: dry_run)")
def family_normalize(family_slug: str, mode: str):
    """
    Normalize exercise naming in a family.
    
    Creates a FAMILY_NORMALIZE job that will:
    - Add equipment qualifiers to multi-equipment families
    - Update slugs and aliases
    - Ensure canonical naming
    
    Example:
        python cli.py family-normalize lateral-raise --mode apply
    """
    try:
        job = create_job(
            job_type=JobType.FAMILY_NORMALIZE,
            queue=JobQueue.PRIORITY,
            family_slug=family_slug,
            mode=mode,
        )
        
        click.echo(click.style("✓ Family normalize job queued", fg="green"))
        click.echo(f"  Job ID:    {job.id}")
        click.echo(f"  Type:      {job.type.value}")
        click.echo(f"  Family:    {family_slug}")
        click.echo(f"  Mode:      {mode}")
        
        if mode == "apply":
            click.echo(click.style("\n⚠ Apply mode: Changes will be written to Firestore", fg="yellow"))
        
        click.echo(click.style("\nRun worker to process:", fg="cyan"))
        click.echo("  FIRESTORE_EMULATOR_HOST=127.0.0.1:8085 CATALOG_APPLY_ENABLED=true python workers/catalog_worker.py")
            
    except Exception as e:
        click.echo(click.style(f"✗ Failed to create job: {e}", fg="red"), err=True)
        sys.exit(1)


# =============================================================================
# JOB STATUS
# =============================================================================

@cli.command("job-status")
@click.argument("job_id")
def job_status(job_id: str):
    """
    Check status of a catalog job.
    
    Example:
        python cli.py job-status job-abc123def456
    """
    from google.cloud import firestore
    
    db = firestore.Client()
    doc = db.collection("catalog_jobs").document(job_id).get()
    
    if not doc.exists:
        click.echo(click.style(f"✗ Job not found: {job_id}", fg="red"), err=True)
        sys.exit(1)
    
    data = doc.to_dict()
    
    status = data.get("status", "unknown")
    status_color = {
        "queued": "yellow",
        "leased": "cyan",
        "running": "cyan",
        "succeeded": "green",
        "succeeded_dry_run": "green",
        "failed": "red",
        "needs_review": "magenta",
        "deadletter": "red",
    }.get(status, "white")
    
    click.echo(f"Job: {job_id}")
    click.echo(f"  Type:    {data.get('type')}")
    click.echo(f"  Status:  {click.style(status, fg=status_color)}")
    click.echo(f"  Queue:   {data.get('queue')}")
    click.echo(f"  Attempts: {data.get('attempts', 0)}/{data.get('max_attempts', 5)}")
    
    if data.get("result_summary"):
        click.echo(f"  Result:  {json.dumps(data['result_summary'], indent=2)}")
    
    if data.get("error"):
        click.echo(click.style(f"  Error:   {json.dumps(data['error'], indent=2)}", fg="red"))


# =============================================================================
# LIST JOBS
# =============================================================================

@cli.command("list-jobs")
@click.option("--status", type=click.Choice([
    "queued", "leased", "running", "succeeded", "failed", "needs_review", "deadletter"
]))
@click.option("--type", "job_type", help="Filter by job type")
@click.option("--limit", default=20, type=int, help="Max jobs to show")
def list_jobs(status: Optional[str], job_type: Optional[str], limit: int):
    """List catalog jobs with optional filters."""
    from google.cloud import firestore
    
    db = firestore.Client()
    query = db.collection("catalog_jobs").order_by("created_at", direction=firestore.Query.DESCENDING)
    
    if status:
        query = query.where("status", "==", status)
    if job_type:
        query = query.where("type", "==", job_type)
    
    query = query.limit(limit)
    
    jobs = list(query.stream())
    
    if not jobs:
        click.echo("No jobs found matching criteria")
        return
    
    click.echo(f"Found {len(jobs)} job(s):\n")
    
    for doc in jobs:
        data = doc.to_dict()
        job_status = data.get("status", "unknown")
        
        status_icon = {
            "queued": "⏳",
            "leased": "🔒",
            "running": "▶️",
            "succeeded": "✅",
            "succeeded_dry_run": "✅",
            "failed": "❌",
            "needs_review": "⚠️",
            "deadletter": "💀",
        }.get(job_status, "❓")
        
        click.echo(f"{status_icon} {data.get('id', doc.id)}")
        click.echo(f"   Type: {data.get('type')} | Status: {job_status}")


# =============================================================================
# RETRY JOB
# =============================================================================

@cli.command("retry-job")
@click.argument("job_id")
@click.option("--delay", default=0, type=int, help="Delay in seconds before retry")
def retry_job_cmd(job_id: str, delay: int):
    """
    Retry a failed/deadlettered job.
    
    Example:
        python cli.py retry-job job-abc123def456
        python cli.py retry-job job-abc123def456 --delay 60
    """
    from app.jobs.queue import retry_job
    
    try:
        success = retry_job(job_id, delay_seconds=delay)
        if success:
            click.echo(click.style(f"✓ Job {job_id} queued for retry", fg="green"))
            if delay > 0:
                click.echo(f"  Run after: {delay} seconds")
        else:
            click.echo(click.style(f"✗ Failed to retry job {job_id}", fg="red"), err=True)
            sys.exit(1)
    except Exception as e:
        click.echo(click.style(f"✗ Error: {e}", fg="red"), err=True)
        sys.exit(1)


# =============================================================================
# RUN WORKER LOCALLY
# =============================================================================

@cli.command("run-worker")
@click.option("--max-jobs", default=0, type=int, help="Max jobs to process (0 = unlimited)")
@click.option("--apply/--no-apply", default=False, help="Enable apply mode (default: dry-run)")
def run_worker_local(max_jobs: int, apply: bool):
    """
    Run the worker locally for testing.
    
    By default runs in dry-run mode (CATALOG_APPLY_ENABLED=false).
    
    Example:
        python cli.py run-worker
        python cli.py run-worker --max-jobs 5
        python cli.py run-worker --apply  # Will write to Firestore
    """
    import os
    
    # Set environment (0 = unlimited)
    os.environ["MAX_JOBS_PER_RUN"] = str(max_jobs)
    os.environ["CATALOG_APPLY_ENABLED"] = "true" if apply else "false"
    
    if apply:
        click.echo(click.style("⚠ Apply mode enabled - will write to Firestore!", fg="yellow"))
    
    click.echo(f"Starting worker (max_jobs={'unlimited' if max_jobs == 0 else max_jobs}, apply={apply})...")
    
    from workers.catalog_worker import run_worker
    run_worker()


# =============================================================================
# RUN WATCHDOG LOCALLY
# =============================================================================

@cli.command("run-watchdog")
@click.option("--dry-run/--no-dry-run", default=True, help="Dry-run mode (default: True)")
def run_watchdog_local(dry_run: bool):
    """
    Run the watchdog locally for testing.
    
    Cleans up expired leases and orphaned locks.
    
    Example:
        python cli.py run-watchdog
        python cli.py run-watchdog --no-dry-run  # Actually clean up
    """
    import os
    
    os.environ["WATCHDOG_DRY_RUN"] = "true" if dry_run else "false"
    
    if not dry_run:
        click.echo(click.style("⚠ WARNING: Dry-run disabled - will modify Firestore!", fg="yellow"))
    
    click.echo(f"Starting watchdog (dry_run={dry_run})...")
    
    from workers.catalog_worker import run_watchdog
    run_watchdog()


# =============================================================================
# TRIGGER CLOUD RUN JOB (REQUIRES GCLOUD AUTH)
# =============================================================================

@cli.command("trigger-worker")
@click.option("--region", default="europe-west1", help="Cloud Run region")
@click.option("--project", envvar="PROJECT_ID", help="GCP project ID")
@click.option("--wait/--no-wait", default=False, help="Wait for completion")
def trigger_worker_remote(region: str, project: Optional[str], wait: bool):
    """
    Trigger the Cloud Run Job worker (requires gcloud auth).
    
    Example:
        python cli.py trigger-worker --project my-project
        python cli.py trigger-worker --project my-project --wait
    """
    import subprocess
    
    if not project:
        click.echo(click.style("✗ Project ID required (--project or PROJECT_ID env)", fg="red"), err=True)
        sys.exit(1)
    
    cmd = ["gcloud", "run", "jobs", "execute", "catalog-worker", f"--region={region}"]
    if wait:
        cmd.append("--wait")
    
    click.echo(f"Triggering catalog-worker in {project}/{region}...")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            click.echo(click.style("✓ Worker triggered", fg="green"))
            if result.stdout:
                click.echo(result.stdout)
        else:
            click.echo(click.style(f"✗ Failed to trigger worker", fg="red"), err=True)
            if result.stderr:
                click.echo(result.stderr, err=True)
            sys.exit(1)
    except FileNotFoundError:
        click.echo(click.style("✗ gcloud not found. Install Google Cloud SDK.", fg="red"), err=True)
        sys.exit(1)


# =============================================================================
# LIST CHANGES (AUDIT TRAIL)
# =============================================================================

@cli.command("list-changes")
@click.option("--job-id", help="Filter by job ID")
@click.option("--limit", default=20, type=int, help="Max changes to show")
def list_changes(job_id: Optional[str], limit: int):
    """
    List catalog changes from the audit trail.
    
    Shows all mutations made to the exercise catalog with before/after snapshots.
    
    Example:
        python cli.py list-changes
        python cli.py list-changes --job-id job-abc123
        python cli.py list-changes --limit 50
    """
    from google.cloud import firestore
    
    db = firestore.Client()
    query = db.collection("catalog_changes").order_by(
        "completed_at", direction=firestore.Query.DESCENDING
    )
    
    if job_id:
        query = query.where("job_id", "==", job_id)
    
    query = query.limit(limit)
    changes = list(query.stream())
    
    if not changes:
        click.echo("No changes found")
        return
    
    click.echo(f"Found {len(changes)} change record(s):\n")
    
    for doc in changes:
        data = doc.to_dict()
        
        successful = data.get("successful_count", 0)
        failed = data.get("failed_count", 0)
        total = data.get("operation_count", 0)
        
        status_icon = "✅" if failed == 0 else "⚠️"
        
        click.echo(f"{status_icon} {data.get('change_id', doc.id)}")
        click.echo(f"   Job: {data.get('job_id')} | Ops: {successful}/{total} succeeded")
        
        completed = data.get("completed_at")
        if completed:
            completed_str = completed.isoformat() if hasattr(completed, 'isoformat') else str(completed)
            click.echo(f"   Completed: {completed_str}")
        
        # Show operation summary
        for op in data.get("operations", [])[:3]:  # Show first 3 ops
            op_type = op.get("operation_type", "?")
            targets = op.get("targets", [])
            target_str = ", ".join(targets[:2]) + ("..." if len(targets) > 2 else "")
            click.echo(f"   - {op_type}: {target_str}")
        
        if len(data.get("operations", [])) > 3:
            click.echo(f"   ... and {len(data['operations']) - 3} more operations")
        click.echo()


@cli.command("change-details")
@click.argument("change_id")
def change_details(change_id: str):
    """
    Show detailed information about a specific change.
    
    Includes before/after snapshots for each operation.
    
    Example:
        python cli.py change-details job-abc123_12345678
    """
    from google.cloud import firestore
    import json
    
    db = firestore.Client()
    doc = db.collection("catalog_changes").document(change_id).get()
    
    if not doc.exists:
        click.echo(click.style(f"✗ Change not found: {change_id}", fg="red"), err=True)
        sys.exit(1)
    
    data = doc.to_dict()
    
    click.echo(f"Change: {change_id}")
    click.echo(f"  Job ID:      {data.get('job_id')}")
    click.echo(f"  Attempt ID:  {data.get('attempt_id')}")
    click.echo(f"  Started:     {data.get('started_at')}")
    click.echo(f"  Completed:   {data.get('completed_at')}")
    click.echo(f"  Summary:     {data.get('result_summary')}")
    click.echo(f"  Operations:  {data.get('operation_count', 0)} ({data.get('successful_count', 0)} succeeded)")
    
    click.echo("\nOperations:")
    for i, op in enumerate(data.get("operations", [])):
        success = "✅" if op.get("success") else "❌"
        click.echo(f"\n  {success} Operation {i}: {op.get('operation_type')}")
        click.echo(f"     Targets: {op.get('targets')}")
        
        if op.get("before"):
            click.echo(f"     Before: {json.dumps(op['before'], indent=2, default=str)[:200]}")
        if op.get("after"):
            click.echo(f"     After:  {json.dumps(op['after'], indent=2, default=str)[:200]}")
        if op.get("error"):
            click.echo(click.style(f"     Error: {op['error']}", fg="red"))


# =============================================================================
# SCHEDULED REVIEW
# =============================================================================

@cli.command("run-review")
@click.option("--max-exercises", default=500, type=int, help="Max exercises to review")
@click.option("--batch-size", default=20, type=int, help="Exercises per LLM batch")
@click.option("--max-jobs", default=100, type=int, help="Max jobs to create")
@click.option("--dry-run/--apply", default=True, help="Dry-run mode (default: True)")
@click.option("--skip-gap-analysis", is_flag=True, help="Skip equipment gap analysis")
@click.option("--force-review", is_flag=True, help="Force review all exercises (ignore quality filter)")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
def run_review_cmd(
    max_exercises: int,
    batch_size: int,
    max_jobs: int,
    dry_run: bool,
    skip_gap_analysis: bool,
    force_review: bool,
    verbose: bool,
):
    """
    Run the unified LLM catalog review agent.
    
    Reviews exercises using LLM to decide:
    - KEEP: Good quality, no action
    - ENRICH: Missing data, needs enrichment
    - FIX_IDENTITY: Name/slug malformed
    - ARCHIVE: Test data, garbage, mistakes
    - MERGE: Duplicate of another exercise
    
    Also detects equipment gaps and suggests new exercises.
    
    Examples:
        python cli.py run-review                    # Dry-run review
        python cli.py run-review --apply            # Create jobs
        python cli.py run-review --max-exercises 50 --batch-size 10 -v
    """
    import logging
    
    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    from app.reviewer.scheduled_review import run_scheduled_review
    
    click.echo(f"Running unified LLM catalog review...")
    click.echo(f"  Max exercises:   {max_exercises}")
    click.echo(f"  Batch size:      {batch_size}")
    click.echo(f"  Max jobs:        {max_jobs}")
    click.echo(f"  Dry-run:         {dry_run}")
    click.echo(f"  Gap analysis:    {not skip_gap_analysis}")
    click.echo(f"  Force review:    {force_review}")
    click.echo()

    summary = run_scheduled_review(
        max_exercises=max_exercises,
        batch_size=batch_size,
        max_jobs=max_jobs,
        dry_run=dry_run,
        run_gap_analysis=not skip_gap_analysis,
        force_review=force_review,
    )
    
    click.echo("\n" + "=" * 60)
    click.echo("REVIEW SUMMARY")
    click.echo("=" * 60)
    
    review = summary.get("review", {})
    click.echo(f"\nReviewed:     {review.get('total_reviewed', 0)} exercises")
    
    decisions = review.get("decisions", {})
    click.echo(f"\nDecisions:")
    click.echo(f"  KEEP:         {decisions.get('keep', 0)}")
    click.echo(f"  ENRICH:       {decisions.get('enrich', 0)}")
    click.echo(f"  FIX_IDENTITY: {decisions.get('fix_identity', 0)}")
    click.echo(f"  ARCHIVE:      {decisions.get('archive', 0)}")
    click.echo(f"  MERGE:        {decisions.get('merge', 0)}")
    
    click.echo(f"\nGaps suggested: {review.get('gaps_suggested', 0)}")
    click.echo(f"Duplicates found: {review.get('duplicates_found', 0)}")
    
    jobs = summary.get("jobs", {})
    click.echo(f"\nJobs created: {jobs.get('total_created', 0)}")
    
    by_type = jobs.get("by_type", {})
    if any(by_type.values()):
        click.echo(f"  Enrich:       {by_type.get('enrich', 0)}")
        click.echo(f"  Fix:          {by_type.get('fix_identity', 0)}")
        click.echo(f"  Archive:      {by_type.get('archive', 0)}")
        click.echo(f"  Merge:        {by_type.get('merge', 0)}")
        click.echo(f"  Add exercise: {by_type.get('add_exercise', 0)}")
    
    if dry_run:
        click.echo(click.style("\n⚠ Dry-run mode: No jobs were actually created", fg="yellow"))
        click.echo("  Run with --apply to create jobs")
    
    click.echo(f"\nDuration: {summary.get('duration_seconds', 0):.1f} seconds")


# =============================================================================
# BACKUP CATALOG
# =============================================================================

@cli.command("backup-catalog")
@click.option("--target", default="exercises-v2-backup", help="Target collection name")
@click.option("--incremental", is_flag=True, help="Only copy docs newer than last backup")
def backup_catalog_cmd(target: str, incremental: bool):
    """
    Create a backup of the exercises catalog.
    
    Uses the duplicateCatalog Firebase function to create a full copy.
    
    Examples:
        python cli.py backup-catalog
        python cli.py backup-catalog --target exercises-backup-2025-01-17
        python cli.py backup-catalog --incremental
    """
    import requests
    import subprocess
    
    # Get Firebase Functions URL
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT", "myon-53d85")
    function_url = f"https://us-central1-{project_id}.cloudfunctions.net/duplicateCatalog"
    
    click.echo(f"Creating backup to: {target}")
    click.echo(f"Incremental: {incremental}")
    click.echo(f"Function URL: {function_url}")
    
    # Get ID token for auth
    try:
        result = subprocess.run(
            ["gcloud", "auth", "print-identity-token"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            click.echo(click.style("✗ Failed to get auth token. Run: gcloud auth login", fg="red"), err=True)
            sys.exit(1)
        token = result.stdout.strip()
    except FileNotFoundError:
        click.echo(click.style("✗ gcloud not found. Install Google Cloud SDK.", fg="red"), err=True)
        sys.exit(1)
    
    # Call the function
    try:
        response = requests.post(
            function_url,
            json={"target": target, "incremental": incremental},
            headers={"Authorization": f"Bearer {token}"},
            timeout=300,  # 5 minutes timeout for large catalogs
        )
        
        if response.status_code == 200:
            data = response.json().get("data", {})
            click.echo(click.style("✓ Backup completed", fg="green"))
            click.echo(f"  Copied: {data.get('copied', '?')} exercises")
            click.echo(f"  Skipped: {data.get('skipped', 0)}")
            click.echo(f"  Target: {data.get('target_collection', target)}")
            click.echo(f"  Migration tag: {data.get('migration_tag', '?')}")
        else:
            click.echo(click.style(f"✗ Backup failed: {response.status_code}", fg="red"), err=True)
            click.echo(response.text, err=True)
            sys.exit(1)
            
    except Exception as e:
        click.echo(click.style(f"✗ Request failed: {e}", fg="red"), err=True)
        sys.exit(1)


# =============================================================================
# QUEUE STATS
# =============================================================================

@cli.command("queue-stats")
def queue_stats():
    """Show job queue statistics."""
    from google.cloud import firestore
    
    db = firestore.Client()
    
    # Count by status
    status_counts = {}
    for status in ["queued", "leased", "running", "succeeded", "succeeded_dry_run", 
                   "failed", "needs_review", "deadletter"]:
        query = db.collection("catalog_jobs").where("status", "==", status)
        count = len(list(query.limit(1000).stream()))
        if count > 0:
            status_counts[status] = count
    
    click.echo("Job Queue Stats")
    click.echo("===============")
    
    if not status_counts:
        click.echo("No jobs found")
        return
    
    for status, count in sorted(status_counts.items()):
        icon = {
            "queued": "⏳",
            "leased": "🔒",
            "running": "▶️",
            "succeeded": "✅",
            "succeeded_dry_run": "✅",
            "failed": "❌",
            "needs_review": "⚠️",
            "deadletter": "💀",
        }.get(status, "❓")
        click.echo(f"  {icon} {status}: {count}")
    
    total = sum(status_counts.values())
    click.echo(f"\nTotal: {total} jobs")


# =============================================================================
# JOB CLEANUP
# =============================================================================

@cli.command("cleanup-jobs")
@click.option("--completed-days", default=7, type=int, 
              help="Delete completed jobs older than N days (default: 7)")
@click.option("--failed-days", default=30, type=int,
              help="Delete failed jobs older than N days (default: 30)")
@click.option("--dry-run/--apply", default=True, help="Dry-run mode (default: True)")
def cleanup_jobs_cmd(completed_days: int, failed_days: int, dry_run: bool):
    """
    Clean up old completed jobs from catalog_jobs.
    
    Archives jobs to run_history before deleting.
    
    Examples:
        python cli.py cleanup-jobs                # Preview what would be deleted
        python cli.py cleanup-jobs --apply        # Actually delete
        python cli.py cleanup-jobs --completed-days 3 --apply
    """
    from app.jobs.run_history import cleanup_completed_jobs
    
    click.echo(f"Cleaning up jobs...")
    click.echo(f"  Completed retention: {completed_days} days")
    click.echo(f"  Failed retention:    {failed_days} days")
    click.echo(f"  Dry-run:             {dry_run}")
    click.echo()
    
    result = cleanup_completed_jobs(
        dry_run=dry_run,
        completed_retention_days=completed_days,
        failed_retention_days=failed_days,
    )
    
    if dry_run:
        click.echo(f"Would delete: {result.get('would_delete', 0)} jobs")
        if result.get('sample_jobs'):
            click.echo("\nSample jobs:")
            for job in result['sample_jobs']:
                click.echo(f"  - {job['id']}: {job['type']} ({job['status']})")
        click.echo(click.style("\n⚠ Dry-run mode: No jobs deleted", fg="yellow"))
        click.echo("  Run with --apply to delete jobs")
    else:
        click.echo(click.style("✓ Cleanup complete", fg="green"))
        click.echo(f"  Archived: {result.get('archived', 0)}")
        click.echo(f"  Deleted:  {result.get('deleted', 0)}")


# =============================================================================
# RUN HISTORY
# =============================================================================

@cli.command("run-history")
@click.option("--job-type", help="Filter by job type")
@click.option("--status", help="Filter by status")
@click.option("--family", help="Filter by family_slug")
@click.option("--limit", default=20, type=int, help="Max records (default: 20)")
def run_history_cmd(job_type: Optional[str], status: Optional[str], 
                    family: Optional[str], limit: int):
    """
    View catalog job run history.
    
    Shows audit trail of all job executions.
    
    Examples:
        python cli.py run-history
        python cli.py run-history --job-type EXERCISE_ADD
        python cli.py run-history --status succeeded --limit 50
    """
    from app.jobs.run_history import get_run_history
    from app.jobs.models import JobType, JobStatus
    
    # Parse job type if provided
    jt = None
    if job_type:
        try:
            jt = JobType(job_type)
        except ValueError:
            click.echo(click.style(f"Invalid job type: {job_type}", fg="red"), err=True)
            return
    
    # Parse status if provided
    st = None
    if status:
        try:
            st = JobStatus(status)
        except ValueError:
            click.echo(click.style(f"Invalid status: {status}", fg="red"), err=True)
            return
    
    records = get_run_history(
        job_type=jt,
        status=st,
        family_slug=family,
        limit=limit,
    )
    
    if not records:
        click.echo("No run history found")
        return
    
    click.echo(f"Found {len(records)} run history records:\n")
    
    for rec in records:
        status_icon = {
            "succeeded": "✅",
            "succeeded_dry_run": "✅",
            "failed": "❌",
            "needs_review": "⚠️",
        }.get(rec.get("status", ""), "❓")
        
        click.echo(f"{status_icon} {rec.get('job_id', '?')}")
        click.echo(f"   Type: {rec.get('job_type')} | Status: {rec.get('status')}")
        click.echo(f"   Duration: {rec.get('duration_ms', 0)}ms | Changes: {rec.get('changes_count', 0)}")
        
        if rec.get('family_slug'):
            click.echo(f"   Family: {rec['family_slug']}")
        if rec.get('completed_at'):
            click.echo(f"   Completed: {rec['completed_at']}")
        click.echo()


# =============================================================================
# DAILY SUMMARY
# =============================================================================

@cli.command("daily-summary")
@click.option("--date", help="Date in YYYY-MM-DD format (default: today)")
def daily_summary_cmd(date: Optional[str]):
    """
    View daily job summary statistics.
    
    Shows aggregated stats for a specific day.
    
    Examples:
        python cli.py daily-summary
        python cli.py daily-summary --date 2026-01-17
    """
    from app.jobs.run_history import get_daily_summary
    
    summary = get_daily_summary(date)
    
    if not summary:
        click.echo(f"No summary found for {date or 'today'}")
        return
    
    click.echo(f"Daily Summary: {date or 'today'}")
    click.echo("=" * 40)
    
    click.echo(f"\nTotal Jobs: {summary.get('total_jobs', 0)}")
    click.echo(f"Total Duration: {summary.get('total_duration_ms', 0) / 1000:.1f}s")
    click.echo(f"Total Changes: {summary.get('total_changes', 0)}")
    
    by_type = summary.get('jobs_by_type', {})
    if by_type:
        click.echo("\nBy Type:")
        for jt, count in sorted(by_type.items()):
            click.echo(f"  {jt}: {count}")
    
    by_status = summary.get('jobs_by_status', {})
    if by_status:
        click.echo("\nBy Status:")
        for st, count in sorted(by_status.items()):
            icon = "✅" if "succeeded" in st else "❌" if st == "failed" else "⚠️"
            click.echo(f"  {icon} {st}: {count}")
    
    by_mode = summary.get('jobs_by_mode', {})
    if by_mode:
        click.echo("\nBy Mode:")
        for mode, count in sorted(by_mode.items()):
            click.echo(f"  {mode}: {count}")


# =============================================================================
# NORMALIZE CATALOG (One-Time Deterministic Fix)
# =============================================================================

@cli.command("normalize-catalog")
@click.option("--dry-run/--apply", default=True, help="Dry-run mode (default: True)")
@click.option("--field", help="Normalize only this field type (e.g., execution_notes)")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
def normalize_catalog_cmd(dry_run: bool, field: Optional[str], verbose: bool):
    """
    Apply deterministic normalization across all exercises — no LLM calls.

    Fixes:
    - Content arrays: strips markdown prefixes, numbered prefixes, bullet markers
    - Muscle names: resolves aliases (lats->latissimus dorsi, etc.)
    - Muscle contribution keys: resolves aliases

    Examples:
        python cli.py normalize-catalog --dry-run -v    # Preview all changes
        python cli.py normalize-catalog --apply          # Apply to Firestore
        python cli.py normalize-catalog --field execution_notes --dry-run -v
    """
    import logging

    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

    from google.cloud import firestore
    from app.enrichment.engine import (
        _normalize_content_array,
        _normalize_equipment,
        _normalize_muscle_names,
        _resolve_muscle_aliases,
        _normalize_contribution_map,
        _normalize_movement_type,
        _normalize_movement_split,
        _normalize_category,
    )

    db = firestore.Client()

    click.echo(f"Fetching all exercises from Firestore...")
    exercises = list(db.collection("exercises").stream())
    click.echo(f"  Found {len(exercises)} exercises")

    content_fields = ["execution_notes", "common_mistakes",
                      "suitability_notes", "programming_use_cases"]
    muscle_array_fields = ["primary", "secondary"]

    normalize_movement = True
    normalize_category = True
    normalize_equip = True

    # If --field is specified, restrict to that field
    if field:
        normalize_movement = False
        normalize_category = False
        normalize_equip = False
        if field in content_fields:
            content_fields = [field]
            muscle_array_fields = []
        elif field in ("muscles.primary", "muscles.secondary"):
            content_fields = []
            muscle_array_fields = [field.split(".")[-1]]
        elif field == "muscles.contribution":
            content_fields = []
            muscle_array_fields = []
        elif field == "movement.type":
            content_fields = []
            muscle_array_fields = []
            normalize_movement = True
        elif field == "category":
            content_fields = []
            muscle_array_fields = []
            normalize_category = True
        elif field == "equipment":
            content_fields = []
            muscle_array_fields = []
            normalize_equip = True
        else:
            click.echo(click.style(
                f"Unknown field: {field}. Valid: execution_notes, "
                "common_mistakes, suitability_notes, "
                "programming_use_cases, muscles.primary, "
                "muscles.secondary, muscles.contribution, "
                "movement.type, category, equipment", fg="red"
            ), err=True)
            sys.exit(1)

    total_changed = 0
    total_fields_changed = 0
    batch = db.batch() if not dry_run else None
    batch_count = 0

    for doc in exercises:
        data = doc.to_dict()
        exercise_name = data.get("name", doc.id)
        updates = {}

        # Normalize content arrays (accept both list and string)
        for cf in content_fields:
            original = data.get(cf)
            if original and isinstance(original, (list, str)):
                normalized = _normalize_content_array(original)
                if normalized != original:
                    updates[cf] = normalized

        # Normalize muscle arrays
        muscles = data.get("muscles") or {}
        for mf in muscle_array_fields:
            original = muscles.get(mf)
            if isinstance(original, list) and original:
                normalized = _resolve_muscle_aliases(
                    _normalize_muscle_names(original)
                )
                if normalized != original:
                    updates[f"muscles.{mf}"] = normalized

        # Normalize contribution map (always if not restricted to a different field)
        if not field or field == "muscles.contribution":
            contribution = muscles.get("contribution")
            if isinstance(contribution, dict) and contribution:
                normalized = _normalize_contribution_map(contribution)
                if normalized != contribution:
                    updates["muscles.contribution"] = normalized

        # Normalize movement type and split
        if normalize_movement:
            movement = data.get("movement") or {}
            mt = movement.get("type")
            if mt:
                normalized_mt = _normalize_movement_type(mt)
                if normalized_mt and normalized_mt != mt:
                    updates["movement.type"] = normalized_mt
            ms = movement.get("split")
            if ms:
                normalized_ms = _normalize_movement_split(ms)
                if normalized_ms and normalized_ms != ms:
                    updates["movement.split"] = normalized_ms

        # Normalize category
        if normalize_category:
            cat = data.get("category")
            if cat:
                normalized_cat = _normalize_category(cat)
                if normalized_cat != cat:
                    updates["category"] = normalized_cat

        # Normalize equipment
        if normalize_equip:
            equip = data.get("equipment")
            if isinstance(equip, list) and equip:
                normalized_equip = _normalize_equipment(equip)
                if normalized_equip != equip:
                    updates["equipment"] = normalized_equip

        if updates:
            total_changed += 1
            total_fields_changed += len(updates)

            if verbose:
                click.echo(f"\n  {exercise_name}:")
                for fp, new_val in updates.items():
                    old_val = data.get(fp) if "." not in fp else (
                        (data.get(fp.split(".")[0]) or {}).get(fp.split(".")[1])
                    )
                    click.echo(f"    {fp}:")
                    click.echo(f"      old: {old_val}")
                    click.echo(f"      new: {new_val}")

            if not dry_run:
                doc_ref = db.collection("exercises").document(doc.id)
                batch.update(doc_ref, updates)
                batch_count += 1

                # Commit every 400 operations
                if batch_count >= 400:
                    batch.commit()
                    click.echo(f"  Committed batch of {batch_count} updates")
                    batch = db.batch()
                    batch_count = 0

    # Final batch commit
    if not dry_run and batch_count > 0:
        batch.commit()
        click.echo(f"  Committed final batch of {batch_count} updates")

    click.echo(f"\n{'=' * 50}")
    click.echo(f"NORMALIZATION SUMMARY")
    click.echo(f"{'=' * 50}")
    click.echo(f"  Total exercises:      {len(exercises)}")
    click.echo(f"  Exercises changed:    {total_changed}")
    click.echo(f"  Total field changes:  {total_fields_changed}")

    if dry_run:
        click.echo(click.style(
            "\nDry-run mode: No changes applied", fg="yellow"
        ))
        click.echo("  Run with --apply to write changes to Firestore")
    else:
        click.echo(click.style(
            f"\nApplied {total_fields_changed} changes to {total_changed} exercises",
            fg="green",
        ))


# =============================================================================
# DEDUP CATALOG (Deterministic Name-Matching Merge)
# =============================================================================

@cli.command("dedup-catalog")
@click.option("--dry-run/--apply", default=True, help="Dry-run mode (default: True)")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
def dedup_catalog_cmd(dry_run: bool, verbose: bool):
    """
    Merge duplicate exercises with identical names.

    Deterministic: groups exercises by normalized name, picks the richest
    as canonical, marks the rest as merged. Safe because identical names
    are true duplicates (the LLM already made semantic judgments).

    Canonical selection: most execution_notes -> longest description
    -> first alphabetically by doc ID.

    Examples:
        python cli.py dedup-catalog --dry-run -v   # Preview duplicate groups
        python cli.py dedup-catalog --apply         # Execute merges
    """
    import logging
    from collections import defaultdict

    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    from google.cloud import firestore

    db = firestore.Client()

    click.echo("Fetching exercises from Firestore...")
    all_docs = list(db.collection("exercises").stream())
    click.echo(f"  Found {len(all_docs)} exercises")

    # Group by normalized name, excluding merged/deprecated
    groups = defaultdict(list)
    for doc in all_docs:
        data = doc.to_dict()
        status = data.get("status", "approved")
        if status in ("merged", "deprecated"):
            continue
        name = (data.get("name") or "").strip().lower()
        if name:
            groups[name].append((doc.id, data))

    # Filter to groups with 2+ exercises
    dup_groups = {name: members for name, members in groups.items()
                  if len(members) >= 2}

    if not dup_groups:
        click.echo("\nNo duplicate groups found.")
        return

    # Safeguard: skip groups where members have different family_slugs.
    # Different families with the same name = bad rename, not true duplicate.
    safe_groups = {}
    skipped_mixed_family = 0
    for name, members in dup_groups.items():
        slugs = {
            d.get("family_slug", "")
            for _, d in members
            if d.get("family_slug")
        }
        if len(slugs) > 1:
            skipped_mixed_family += 1
            if verbose:
                click.echo(click.style(
                    f"\n  SKIP (mixed families): \"{members[0][1].get('name', name)}\"",
                    fg="yellow",
                ))
                for doc_id, data in members:
                    click.echo(
                        f"    {doc_id}  family={data.get('family_slug')}"
                    )
        else:
            safe_groups[name] = members

    if skipped_mixed_family:
        click.echo(click.style(
            f"\nSkipped {skipped_mixed_family} groups with mixed family_slugs "
            "(likely bad renames, not true duplicates)",
            fg="yellow",
        ))

    click.echo(f"\nMergeable duplicate groups: {len(safe_groups)} "
               f"({sum(len(m) for m in safe_groups.values())} total exercises)")

    total_merged = 0
    batch = db.batch() if not dry_run else None
    batch_count = 0

    for name, members in sorted(safe_groups.items()):
        # Pick canonical: penalize "unknown" doc IDs, then most
        # execution_notes -> longest description -> first alphabetical ID
        def score(item):
            doc_id, data = item
            notes = data.get("execution_notes") or []
            notes_count = len(notes) if isinstance(notes, list) else 0
            desc_len = len(data.get("description") or "")
            # Penalize doc_ids that contain "unknown"
            id_penalty = 0 if "unknown" not in doc_id else -1000
            return (id_penalty, notes_count, desc_len, doc_id)

        ranked = sorted(members, key=score, reverse=True)
        canonical_id, canonical_data = ranked[0]
        duplicates = ranked[1:]

        if verbose:
            click.echo(f"\n  Group: \"{canonical_data.get('name', name)}\"")
            click.echo(f"    Canonical: {canonical_id} "
                       f"(notes={len(canonical_data.get('execution_notes') or [])}, "
                       f"desc={len(canonical_data.get('description') or '')} chars)")
            for dup_id, dup_data in duplicates:
                click.echo(f"    Duplicate: {dup_id} -> merge into {canonical_id}")

        for dup_id, _dup_data in duplicates:
            total_merged += 1
            if not dry_run:
                doc_ref = db.collection("exercises").document(dup_id)
                batch.update(doc_ref, {
                    "status": "merged",
                    "merged_into": canonical_id,
                })
                batch_count += 1

                if batch_count >= 400:
                    batch.commit()
                    click.echo(f"  Committed batch of {batch_count} merges")
                    batch = db.batch()
                    batch_count = 0

    # Final commit
    if not dry_run and batch_count > 0:
        batch.commit()
        click.echo(f"  Committed final batch of {batch_count} merges")

    active_remaining = sum(
        1 for doc in all_docs
        if (doc.to_dict().get("status", "approved") not in ("merged", "deprecated"))
    ) - total_merged

    click.echo(f"\n{'=' * 50}")
    click.echo("DEDUP SUMMARY")
    click.echo(f"{'=' * 50}")
    click.echo(f"  Total name collisions: {len(dup_groups)}")
    click.echo(f"  Skipped (mixed family): {skipped_mixed_family}")
    click.echo(f"  Safe duplicate groups:   {len(safe_groups)}")
    click.echo(f"  Exercises merged:        {total_merged}")
    click.echo(f"  Active remaining:        ~{active_remaining}")

    if dry_run:
        click.echo(click.style(
            "\nDry-run mode: No changes applied", fg="yellow",
        ))
        click.echo("  Run with --apply to merge duplicates")
    else:
        click.echo(click.style(
            f"\nMerged {total_merged} exercises across {len(safe_groups)} groups",
            fg="green",
        ))


if __name__ == "__main__":
    cli()
