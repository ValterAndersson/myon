"""
Catalog Admin Dashboard - Flask Backend

Provides API endpoints for monitoring:
- Cloud Scheduler jobs (next run times)
- Cloud Run Jobs (execution status, manual triggers)
- Firestore job queue (pending/running jobs)
- Cloud Logging (real-time log streaming)

Run locally:
    python app.py

Uses Application Default Credentials for GCP access.
"""

from flask import Flask, jsonify, render_template, Response, request
from flask_cors import CORS
from google.cloud import firestore, scheduler_v1
from google.cloud import run_v2
from google.cloud import logging as cloud_logging
from datetime import datetime, timezone, timedelta
import os
import json
import time

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)

# Configuration
PROJECT_ID = os.environ.get('GOOGLE_CLOUD_PROJECT', 'myon-53d85')
REGION = os.environ.get('CLOUD_RUN_REGION', 'europe-west1')

# Job descriptions for tooltips
JOB_DESCRIPTIONS = {
    'catalog-worker': {
        'description': 'Processes the job queue (enrichment, fixes, additions)',
        'default_params': 'APPLY=true, processes until queue is empty',
        'schedule': 'Every 15 minutes',
    },
    'catalog-review': {
        'description': 'LLM-powered quality review of exercise catalog',
        'default_params': 'Reviews up to 1000 exercises, creates fix/enrich jobs',
        'schedule': 'Daily at 03:00 UTC',
    },
    'catalog-cleanup': {
        'description': 'Archives completed jobs older than 7 days',
        'default_params': 'Moves old jobs to catalog_jobs_archive',
        'schedule': 'Daily at 08:00 UTC',
    },
    'catalog-watchdog': {
        'description': 'Cleans up expired leases and stale locks',
        'default_params': 'Releases jobs stuck >30min',
        'schedule': 'Every 6 hours',
    },
}


def get_firestore_client():
    """Get Firestore client."""
    return firestore.Client(project=PROJECT_ID)


def get_scheduler_client():
    """Get Cloud Scheduler client."""
    return scheduler_v1.CloudSchedulerClient()


def get_run_client():
    """Get Cloud Run Jobs client."""
    return run_v2.JobsClient()


def get_logging_client():
    """Get Cloud Logging client."""
    return cloud_logging.Client(project=PROJECT_ID)


@app.route('/')
def index():
    """Serve the main dashboard."""
    return render_template('index.html')


@app.route('/api/job-descriptions')
def get_job_descriptions():
    """Get job descriptions for tooltips."""
    return jsonify({
        'success': True,
        'descriptions': JOB_DESCRIPTIONS,
    })


@app.route('/api/scheduler/jobs')
def get_scheduler_jobs():
    """Get Cloud Scheduler job statuses."""
    try:
        client = get_scheduler_client()
        parent = f"projects/{PROJECT_ID}/locations/{REGION}"
        
        jobs = []
        for job in client.list_jobs(parent=parent):
            # Only include catalog-related triggers
            if 'catalog' in job.name.lower():
                schedule_time = job.schedule_time.isoformat() if job.schedule_time else None
                last_attempt = None
                last_status = None
                
                if job.last_attempt_time:
                    last_attempt = job.last_attempt_time.isoformat()
                
                if job.status:
                    last_status = job.status.code
                
                jobs.append({
                    'name': job.name.split('/')[-1],
                    'schedule': job.schedule,
                    'timezone': job.time_zone,
                    'state': job.state.name,
                    'next_run': schedule_time,
                    'last_attempt': last_attempt,
                    'last_status': last_status,
                })
        
        return jsonify({
            'success': True,
            'jobs': sorted(jobs, key=lambda x: x['name']),
            'timestamp': datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@app.route('/api/cloudrun/jobs')
def get_cloudrun_jobs():
    """Get Cloud Run Job statuses and recent executions."""
    try:
        client = get_run_client()
        parent = f"projects/{PROJECT_ID}/locations/{REGION}"
        
        jobs = []
        for job in client.list_jobs(parent=parent):
            # Only include catalog-related jobs
            if 'catalog' in job.name.lower():
                job_name = job.name.split('/')[-1]
                latest_exec = None
                if job.latest_created_execution:
                    exec_name = job.latest_created_execution.name.split('/')[-1]
                    exec_time = job.latest_created_execution.create_time
                    exec_completion = job.latest_created_execution.completion_time
                    
                    # Determine status
                    if exec_completion:
                        status = 'SUCCEEDED'
                    elif exec_time:
                        status = 'RUNNING'
                    else:
                        status = 'PENDING'
                    
                    latest_exec = {
                        'name': exec_name,
                        'create_time': exec_time.isoformat() if exec_time else None,
                        'completion_time': exec_completion.isoformat() if exec_completion else None,
                        'status': status,
                    }
                
                # Get job description
                desc = JOB_DESCRIPTIONS.get(job_name, {})
                
                jobs.append({
                    'name': job_name,
                    'create_time': job.create_time.isoformat() if job.create_time else None,
                    'update_time': job.update_time.isoformat() if job.update_time else None,
                    'execution_count': job.execution_count,
                    'latest_execution': latest_exec,
                    'description': desc.get('description', ''),
                    'default_params': desc.get('default_params', ''),
                    'schedule': desc.get('schedule', ''),
                })
        
        return jsonify({
            'success': True,
            'jobs': sorted(jobs, key=lambda x: x['name']),
            'timestamp': datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@app.route('/api/cloudrun/jobs/<job_name>/trigger', methods=['POST'])
def trigger_job(job_name):
    """Manually trigger a Cloud Run Job."""
    try:
        client = get_run_client()
        job_path = f"projects/{PROJECT_ID}/locations/{REGION}/jobs/{job_name}"
        
        # Run the job
        operation = client.run_job(name=job_path)
        
        return jsonify({
            'success': True,
            'message': f'Job {job_name} triggered successfully',
            'execution_name': operation.metadata.name if hasattr(operation, 'metadata') else None,
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@app.route('/api/firestore/queue')
def get_queue_stats():
    """Get Firestore job queue statistics."""
    try:
        db = get_firestore_client()
        
        # Count jobs by status
        status_counts = {}
        statuses = ['queued', 'leased', 'running', 'succeeded', 'succeeded_dry_run', 
                    'failed', 'needs_review', 'deadletter']
        
        for status in statuses:
            query = db.collection('catalog_jobs').where(
                filter=firestore.FieldFilter('status', '==', status)
            ).limit(1000)
            docs = list(query.stream())
            if docs:
                status_counts[status] = len(docs)
        
        # Get recent jobs
        recent_jobs = []
        query = db.collection('catalog_jobs').order_by(
            'created_at', direction=firestore.Query.DESCENDING
        ).limit(10)
        
        for doc in query.stream():
            data = doc.to_dict()
            recent_jobs.append({
                'id': doc.id,
                'type': data.get('type'),
                'status': data.get('status'),
                'created_at': data.get('created_at').isoformat() if data.get('created_at') else None,
                'family_slug': data.get('family_slug'),
            })
        
        # Calculate summary
        total_pending = status_counts.get('queued', 0) + status_counts.get('leased', 0)
        total_running = status_counts.get('running', 0)
        total_failed = status_counts.get('failed', 0) + status_counts.get('deadletter', 0)
        
        return jsonify({
            'success': True,
            'queue': {
                'pending': total_pending,
                'running': total_running,
                'failed': total_failed,
                'by_status': status_counts,
            },
            'recent_jobs': recent_jobs,
            'timestamp': datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@app.route('/api/firestore/run-history')
def get_run_history():
    """Get recent run history from catalog_run_history."""
    try:
        db = get_firestore_client()
        
        query = db.collection('catalog_run_history').order_by(
            'completed_at', direction=firestore.Query.DESCENDING
        ).limit(50)
        
        history = []
        for doc in query.stream():
            data = doc.to_dict()
            history.append({
                'id': doc.id,
                'job_id': data.get('job_id'),
                'job_type': data.get('job_type'),
                'status': data.get('status'),
                'duration_ms': data.get('duration_ms'),
                'changes_count': data.get('changes_count', 0),
                'completed_at': data.get('completed_at').isoformat() if data.get('completed_at') else None,
                'exercise_id': data.get('exercise_id'),
                'family_slug': data.get('family_slug'),
                'changes': data.get('changes'),  # Include actual changes if stored
                'summary': data.get('summary'),  # Include summary if stored
            })
        
        return jsonify({
            'success': True,
            'history': history,
            'timestamp': datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@app.route('/api/firestore/changes')
def get_catalog_changes():
    """Get catalog change log from catalog_changes collection."""
    try:
        db = get_firestore_client()
        limit = int(request.args.get('limit', 50))
        
        query = db.collection('catalog_changes').order_by(
            'timestamp', direction=firestore.Query.DESCENDING
        ).limit(limit)
        
        changes = []
        for doc in query.stream():
            data = doc.to_dict()
            changes.append({
                'id': doc.id,
                'exercise_id': data.get('exercise_id'),
                'exercise_name': data.get('exercise_name'),
                'change_type': data.get('change_type'),  # e.g., 'create', 'update', 'fix'
                'field_changes': data.get('field_changes', {}),  # {field: {before, after}}
                'job_id': data.get('job_id'),
                'job_type': data.get('job_type'),
                'timestamp': data.get('timestamp').isoformat() if data.get('timestamp') else None,
                'dry_run': data.get('dry_run', False),
            })
        
        return jsonify({
            'success': True,
            'changes': changes,
            'timestamp': datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@app.route('/api/logs/stream')
def stream_logs():
    """Stream logs from Cloud Logging in real-time using SSE."""
    job_filter = request.args.get('job', '')  # Optional filter by job name
    
    def generate():
        try:
            client = get_logging_client()
            
            # Build filter for catalog-related logs
            base_filter = (
                f'resource.type="cloud_run_job" '
                f'resource.labels.project_id="{PROJECT_ID}" '
                f'resource.labels.location="{REGION}" '
                f'resource.labels.job_name=~"catalog.*" '
                f'timestamp>="{(datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()}"'
            )
            
            if job_filter:
                base_filter += f' resource.labels.job_name="{job_filter}"'
            
            # Get initial logs
            entries = client.list_entries(
                filter_=base_filter,
                order_by=cloud_logging.DESCENDING,
                max_results=100,
            )
            
            # Send initial batch
            for entry in entries:
                log_data = {
                    'timestamp': entry.timestamp.isoformat() if entry.timestamp else None,
                    'severity': entry.severity if hasattr(entry, 'severity') else 'DEFAULT',
                    'message': str(entry.payload) if entry.payload else '',
                    'job_name': entry.resource.labels.get('job_name', '') if entry.resource else '',
                    'execution_name': entry.labels.get('execution_name', '') if entry.labels else '',
                }
                yield f"data: {json.dumps(log_data)}\n\n"
            
            # Keep connection alive and poll for new logs
            last_timestamp = datetime.now(timezone.utc)
            while True:
                time.sleep(5)  # Poll every 5 seconds
                
                new_filter = base_filter + f' timestamp>="{last_timestamp.isoformat()}"'
                new_entries = client.list_entries(
                    filter_=new_filter,
                    order_by=cloud_logging.ASCENDING,
                    max_results=50,
                )
                
                for entry in new_entries:
                    if entry.timestamp and entry.timestamp > last_timestamp:
                        last_timestamp = entry.timestamp
                        log_data = {
                            'timestamp': entry.timestamp.isoformat(),
                            'severity': entry.severity if hasattr(entry, 'severity') else 'DEFAULT',
                            'message': str(entry.payload) if entry.payload else '',
                            'job_name': entry.resource.labels.get('job_name', '') if entry.resource else '',
                        }
                        yield f"data: {json.dumps(log_data)}\n\n"
                
                # Send heartbeat
                yield f": heartbeat\n\n"
                
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return Response(generate(), mimetype='text/event-stream')


@app.route('/api/logs/recent')
def get_recent_logs():
    """Get recent logs (non-streaming)."""
    try:
        client = get_logging_client()
        job_filter = request.args.get('job', '')
        hours = int(request.args.get('hours', 1))
        limit = int(request.args.get('limit', 200))
        
        base_filter = (
            f'resource.type="cloud_run_job" '
            f'resource.labels.project_id="{PROJECT_ID}" '
            f'resource.labels.location="{REGION}" '
            f'resource.labels.job_name=~"catalog.*" '
            f'timestamp>="{(datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()}"'
        )
        
        if job_filter:
            base_filter += f' resource.labels.job_name="{job_filter}"'
        
        entries = client.list_entries(
            filter_=base_filter,
            order_by=cloud_logging.DESCENDING,
            max_results=limit,
        )
        
        logs = []
        for entry in entries:
            logs.append({
                'timestamp': entry.timestamp.isoformat() if entry.timestamp else None,
                'severity': entry.severity if hasattr(entry, 'severity') else 'DEFAULT',
                'message': str(entry.payload) if entry.payload else '',
                'job_name': entry.resource.labels.get('job_name', '') if entry.resource else '',
                'execution_name': entry.labels.get('execution_name', '') if entry.labels else '',
            })
        
        return jsonify({
            'success': True,
            'logs': logs,
            'count': len(logs),
            'timestamp': datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@app.route('/api/status')
def get_overall_status():
    """Get overall system status summary."""
    try:
        # Aggregate all status checks
        scheduler_resp = get_scheduler_jobs().get_json()
        cloudrun_resp = get_cloudrun_jobs().get_json()
        queue_resp = get_queue_stats().get_json()
        
        # Determine health
        health = 'healthy'
        issues = []
        
        if queue_resp.get('queue', {}).get('failed', 0) > 0:
            issues.append(f"{queue_resp['queue']['failed']} failed jobs")
            health = 'warning'
        
        if queue_resp.get('queue', {}).get('pending', 0) > 100:
            issues.append(f"{queue_resp['queue']['pending']} jobs in queue")
            health = 'warning'
        
        return jsonify({
            'success': True,
            'health': health,
            'issues': issues,
            'scheduler': scheduler_resp.get('jobs', []),
            'cloudrun': cloudrun_resp.get('jobs', []),
            'queue': queue_resp.get('queue', {}),
            'timestamp': datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'health': 'error',
        }), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    debug = os.environ.get('DEBUG', 'false').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug)
