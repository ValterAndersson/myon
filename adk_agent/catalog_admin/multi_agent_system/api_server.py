#!/usr/bin/env python3
"""
API Server for the Multi-Agent Catalog Curation System
Provides HTTP endpoints to trigger pipeline processing on-demand.
"""

import json
import logging
import os
import sys
from datetime import datetime
from flask import Flask, request, jsonify
from threading import Thread
import time
import os

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from orchestrator.orchestrator import CatalogOrchestrator, AgentType

app = Flask(__name__)

# Global orchestrator instance
orchestrator = None

def initialize_orchestrator():
    """Initialize the orchestrator instance"""
    global orchestrator
    
    FIREBASE_BASE_URL = os.getenv("MYON_FUNCTIONS_BASE_URL", "https://us-central1-myon-53d85.cloudfunctions.net")
    FIREBASE_API_KEY = os.getenv("FIREBASE_API_KEY", "myon-agent-key-2024")
    # Initialize orchestrator with Firebase config only (engine id not required here)
    log_dir = os.getenv("LOG_DIR", "/tmp/logs")
    os.makedirs(log_dir, exist_ok=True)
    orchestrator = CatalogOrchestrator(
        firebase_base_url=FIREBASE_BASE_URL,
        firebase_api_key=FIREBASE_API_KEY,
        log_dir=log_dir,
        system_user_id="api_orchestrator"
    )
    
    app.logger.info("Orchestrator initialized")


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "orchestrator_ready": orchestrator is not None
    })


@app.route('/trigger', methods=['POST'])
def trigger_pipeline():
    """
    Trigger the full pipeline to run immediately.
    Useful after bulk imports or scheduled triggers.
    """
    if not orchestrator:
        return jsonify({"error": "Orchestrator not initialized"}), 500
    
    # Run pipeline in background thread
    def run_pipeline():
        orchestrator.run_pipeline()
    
    thread = Thread(target=run_pipeline)
    thread.start()
    
    return jsonify({
        "status": "triggered",
        "timestamp": datetime.now().isoformat(),
        "message": "Pipeline started in background"
    })


@app.route('/process_exercise', methods=['POST'])
def process_exercise():
    """
    Process a single exercise through the pipeline immediately.
    This is perfect for when you add one new exercise.
    
    Expected payload:
    {
        "exercise_id": "abc123",
        "name": "New Exercise Name",
        "force_reprocess": false
    }
    """
    if not orchestrator:
        return jsonify({"error": "Orchestrator not initialized"}), 500
    
    data = request.json
    exercise_id = data.get('exercise_id')
    exercise_name = data.get('name')
    force_reprocess = data.get('force_reprocess', False)
    
    if not exercise_id and not exercise_name:
        return jsonify({"error": "Either exercise_id or name is required"}), 400
    
    try:
        # Fetch the exercise if only name provided
        if not exercise_id:
            result = orchestrator.firebase_client.post("resolveExercise", {"name": exercise_name})
            if result.get("ok") and result.get("data"):
                exercise_id = result["data"].get("exercise", {}).get("id")
            else:
                return jsonify({"error": f"Exercise '{exercise_name}' not found"}), 404
        
        # Get the exercise details
        result = orchestrator.firebase_client.post("getExercise", {"exerciseId": exercise_id})
        if not result.get("ok"):
            return jsonify({"error": "Failed to fetch exercise"}), 404
        
        exercise = result.get("data", {}).get("exercise", {})
        
        # Determine what processing is needed
        needs_triage = not exercise.get("family_slug") or force_reprocess
        needs_enrichment = exercise.get("family_slug") and (force_reprocess or not exercise.get("approved"))
        needs_approval = exercise.get("family_slug") and not exercise.get("approved")
        
        jobs_created = []
        
        # Create and execute jobs as needed
        if needs_triage:
            app.logger.info(f"Creating triage job for {exercise.get('name')}")
            job = orchestrator.create_batch_job(AgentType.TRIAGE, [exercise], batch_size=1)
            orchestrator.execute_batch_job(job, parallel=False)
            jobs_created.append({
                "type": "triage",
                "job_id": job.id,
                "status": "completed" if job.is_complete else "in_progress"
            })
        
        if needs_enrichment:
            app.logger.info(f"Creating enrichment job for {exercise.get('name')}")
            job = orchestrator.create_batch_job(AgentType.ENRICHMENT, [exercise], batch_size=1)
            orchestrator.execute_batch_job(job, parallel=False)
            jobs_created.append({
                "type": "enrichment",
                "job_id": job.id,
                "status": "completed" if job.is_complete else "in_progress"
            })
        
        # TODO: Add approval job when agent is ready
        # if needs_approval:
        #     job = orchestrator.create_batch_job(AgentType.APPROVAL, [exercise], batch_size=1)
        #     orchestrator.execute_batch_job(job, parallel=False)
        #     jobs_created.append({"type": "approval", "job_id": job.id})
        
        return jsonify({
            "status": "processed",
            "exercise_id": exercise_id,
            "exercise_name": exercise.get("name"),
            "jobs_created": jobs_created,
            "processing_summary": {
                "needed_triage": needs_triage,
                "needed_enrichment": needs_enrichment,
                "needed_approval": needs_approval
            }
        })
        
    except Exception as e:
        app.logger.error(f"Error processing exercise: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/process_new_exercises', methods=['POST'])
def process_new_exercises():
    """
    Process multiple new exercises that were just added.
    Automatically detects what processing each needs.
    
    Expected payload:
    {
        "exercise_ids": ["id1", "id2", "id3"],
        "or_names": ["Exercise 1", "Exercise 2"]
    }
    """
    if not orchestrator:
        return jsonify({"error": "Orchestrator not initialized"}), 500
    
    data = request.json
    exercise_ids = data.get('exercise_ids', [])
    exercise_names = data.get('or_names', [])
    
    if not exercise_ids and not exercise_names:
        return jsonify({"error": "Either exercise_ids or or_names is required"}), 400
    
    try:
        exercises_to_process = []
        
        # Fetch exercises by IDs
        for ex_id in exercise_ids:
            result = orchestrator.firebase_client.post("getExercise", {"exerciseId": ex_id})
            if result.get("ok") and result.get("data"):
                exercises_to_process.append(result["data"]["exercise"])
        
        # Fetch exercises by names
        for name in exercise_names:
            result = orchestrator.firebase_client.post("resolveExercise", {"name": name})
            if result.get("ok") and result.get("data"):
                exercise = result["data"].get("exercise")
                if exercise and exercise not in exercises_to_process:
                    exercises_to_process.append(exercise)
        
        # Categorize exercises by what they need
        need_triage = []
        need_enrichment = []
        need_approval = []
        
        for ex in exercises_to_process:
            if not ex.get("family_slug"):
                need_triage.append(ex)
            elif not ex.get("approved"):
                need_enrichment.append(ex)
                need_approval.append(ex)
            else:
                # Even approved exercises might benefit from more aliases
                need_enrichment.append(ex)
        
        jobs_created = []
        
        # Create batch jobs for each category
        if need_triage:
            app.logger.info(f"Creating triage job for {len(need_triage)} exercises")
            job = orchestrator.create_batch_job(AgentType.TRIAGE, need_triage, batch_size=5)
            
            # Run in background
            def run_triage():
                orchestrator.execute_batch_job(job, parallel=True)
            Thread(target=run_triage).start()
            
            jobs_created.append({
                "type": "triage",
                "job_id": job.id,
                "exercise_count": len(need_triage)
            })
        
        if need_enrichment:
            app.logger.info(f"Creating enrichment job for {len(need_enrichment)} exercises")
            job = orchestrator.create_batch_job(AgentType.ENRICHMENT, need_enrichment, batch_size=5)
            
            # Run in background
            def run_enrichment():
                # Wait a bit if triage is running
                if need_triage:
                    time.sleep(5)
                orchestrator.execute_batch_job(job, parallel=True)
            Thread(target=run_enrichment).start()
            
            jobs_created.append({
                "type": "enrichment",
                "job_id": job.id,
                "exercise_count": len(need_enrichment)
            })
        
        return jsonify({
            "status": "processing",
            "total_exercises": len(exercises_to_process),
            "jobs_created": jobs_created,
            "processing_summary": {
                "need_triage": len(need_triage),
                "need_enrichment": len(need_enrichment),
                "need_approval": len(need_approval)
            },
            "message": "Processing in background. Check /status endpoint for progress."
        })
        
    except Exception as e:
        app.logger.error(f"Error processing exercises: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/status', methods=['GET'])
def get_status():
    """Get the current status of all jobs"""
    if not orchestrator:
        return jsonify({"error": "Orchestrator not initialized"}), 500
    
    jobs_summary = []
    for job_id, job in orchestrator.active_jobs.items():
        jobs_summary.append({
            "job_id": job_id,
            "created_at": job.created_at.isoformat(),
            "is_complete": job.is_complete,
            "progress": {
                "completed": job.progress[0],
                "total": job.progress[1]
            },
            "tasks": [
                {
                    "task_id": task.id,
                    "status": task.status.value,
                    "agent_type": task.agent_type.value
                }
                for task in job.tasks
            ]
        })
    
    # Get catalog state
    state = orchestrator.assess_catalog_state()
    
    return jsonify({
        "timestamp": datetime.now().isoformat(),
        "catalog_state": state,
        "active_jobs": len(orchestrator.active_jobs),
        "jobs": jobs_summary
    })


@app.route('/webhook/exercise_created', methods=['POST'])
def webhook_exercise_created():
    """
    Webhook endpoint to be called when a new exercise is created.
    This enables real-time processing of new exercises.
    
    Expected payload (from Firebase function):
    {
        "event": "exercise.created",
        "data": {
            "exercise_id": "abc123",
            "name": "New Exercise",
            "created_by": "user123"
        }
    }
    """
    if not orchestrator:
        return jsonify({"error": "Orchestrator not initialized"}), 500
    
    data = request.json
    if data.get("event") != "exercise.created":
        return jsonify({"error": "Invalid event type"}), 400
    
    exercise_data = data.get("data", {})
    exercise_id = exercise_data.get("exercise_id")
    
    if not exercise_id:
        return jsonify({"error": "exercise_id required"}), 400
    
    app.logger.info(f"Webhook received for new exercise: {exercise_id}")
    
    # Process the exercise asynchronously
    def process_async():
        time.sleep(2)  # Small delay to ensure exercise is fully saved
        
        # Fetch and process the exercise
        result = orchestrator.firebase_client.post("getExercise", {"exerciseId": exercise_id})
        if result.get("ok") and result.get("data"):
            exercise = result["data"]["exercise"]
            
            # Run through triage immediately
            job = orchestrator.create_batch_job(AgentType.TRIAGE, [exercise], batch_size=1)
            orchestrator.execute_batch_job(job, parallel=False)
            
            app.logger.info(f"Processed new exercise {exercise.get('name')} through pipeline")
    
    Thread(target=process_async).start()
    
    return jsonify({
        "status": "accepted",
        "message": "Exercise will be processed shortly"
    }), 202


if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Initialize orchestrator
    initialize_orchestrator()
    
    # Run the server
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
