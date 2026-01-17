#!/usr/bin/env python3
"""
Catalog Orchestrator CLI.

Command-line interface for catalog operations:
- insert-exercise: Add new exercise to catalog
- enrich-field: Batch enrich exercises with LLM-computed fields

Usage:
    python cli.py insert-exercise --base-name "Lateral Raise" --equipment cable
    python cli.py enrich-field --spec-id difficulty --field-path metadata.difficulty ...
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
@click.option("--max-jobs", default=10, type=int, help="Max jobs to process")
@click.option("--apply/--no-apply", default=False, help="Enable apply mode (default: dry-run)")
def run_worker_local(max_jobs: int, apply: bool):
    """
    Run the worker locally for testing.
    
    By default runs in dry-run mode (CATALOG_APPLY_ENABLED=false).
    
    Example:
        python cli.py run-worker
        python cli.py run-worker --max-jobs 5
        python cli.py run-worker --apply  # Warning: will write to Firestore!
    """
    import os
    
    # Set environment
    os.environ["MAX_JOBS_PER_RUN"] = str(max_jobs)
    os.environ["CATALOG_APPLY_ENABLED"] = "true" if apply else "false"
    
    if apply:
        click.echo(click.style("⚠ WARNING: Apply mode enabled - will write to Firestore!", fg="red"))
        if not click.confirm("Continue?"):
            click.echo("Aborted")
            return
    
    click.echo(f"Starting worker (max_jobs={max_jobs}, apply={apply})...")
    
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


if __name__ == "__main__":
    cli()
