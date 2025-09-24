#!/usr/bin/env python3
"""
CLI for the Multi-Agent Catalog Curation System
Provides commands to add exercises and trigger processing.
"""

import argparse
import json
import os
import sys
import requests
from typing import Optional, Dict, Any

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from orchestrator.orchestrator import CatalogOrchestrator, AgentType


class CatalogCLI:
    """Command-line interface for catalog management"""
    
    def __init__(self):
        self.firebase_base_url = os.getenv("MYON_FUNCTIONS_BASE_URL", 
                                           "https://us-central1-myon-53d85.cloudfunctions.net")
        self.firebase_api_key = os.getenv("FIREBASE_API_KEY", "myon-agent-key-2024")
        self.api_server_url = os.getenv("API_SERVER_URL", "http://localhost:8080")
        
        # Initialize orchestrator for direct operations
        self.orchestrator = CatalogOrchestrator(
            firebase_base_url=self.firebase_base_url,
            firebase_api_key=self.firebase_api_key,
            log_dir="/Users/valterandersson/Documents/myon/adk_agent/catalog_admin/multi_agent_system/logs",
            system_user_id="cli_user"
        )
    
    def add_exercise(self, name: str, equipment: Optional[str] = None, 
                     muscles: Optional[str] = None, auto_process: bool = True) -> Dict[str, Any]:
        """
        Add a new exercise to the catalog and optionally process it.
        """
        print(f"📝 Adding exercise: {name}")
        
        # Prepare exercise data
        exercise_data = {
            "name": name
        }
        
        if equipment:
            exercise_data["equipment"] = equipment.split(",")
        
        if muscles:
            exercise_data["muscles"] = {
                "primary": muscles.split(",")
            }
        
        # Call Firebase function to create exercise
        try:
            result = self.orchestrator.firebase_client.post("ensureExerciseExists", exercise_data)
            
            if not result.get("success"):
                print(f"❌ Failed to add exercise: {result.get('error')}")
                return result
            
            data = result.get("data", {})
            exercise_id = data.get("exercise_id")
            created = data.get("created", False)
            
            if created:
                print(f"✅ Exercise created with ID: {exercise_id}")
            else:
                print(f"ℹ️ Exercise already exists with ID: {exercise_id}")
            
            if auto_process:
                print("🔄 Processing through pipeline...")
                self.process_exercise(exercise_id)
            
            return result
            
        except Exception as e:
            print(f"❌ Error: {e}")
            return {"ok": False, "error": str(e)}
    
    def process_exercise(self, exercise_id: str) -> None:
        """
        Process a single exercise through the pipeline.
        """
        print(f"🔄 Processing exercise {exercise_id}...")
        
        try:
            # Get the exercise
            result = self.orchestrator.firebase_client.post("getExercise", {"exerciseId": exercise_id})
            if not result.get("success"):
                print(f"❌ Failed to fetch exercise: {result.get('error')}")
                return
            
            # The exercise data is directly in data, not nested
            exercise = result.get("data", {})
            print(f"   Exercise: {exercise.get('name')}")
            
            # Determine what processing is needed
            needs_triage = not exercise.get("family_slug")
            needs_enrichment = exercise.get("family_slug")
            
            # Run triage if needed
            if needs_triage:
                print("   📋 Running triage (normalization)...")
                job = self.orchestrator.create_batch_job(AgentType.TRIAGE, [exercise], batch_size=1)
                completed_job = self.orchestrator.execute_batch_job(job, parallel=False)
                
                if completed_job.is_complete:
                    print("   ✅ Triage completed")
                    # Refresh exercise data
                    result = self.orchestrator.firebase_client.post("getExercise", {"exerciseId": exercise_id})
                    if result.get("success"):
                        exercise = result.get("data", {})
                else:
                    print("   ⚠️ Triage failed")
            
            # Run enrichment if the exercise now has a family
            if exercise.get("family_slug"):
                print("   🎨 Running enrichment (aliases)...")
                job = self.orchestrator.create_batch_job(AgentType.ENRICHMENT, [exercise], batch_size=1)
                completed_job = self.orchestrator.execute_batch_job(job, parallel=False)
                
                if completed_job.is_complete:
                    print("   ✅ Enrichment completed")
                else:
                    print("   ⚠️ Enrichment failed")
            
            print(f"✅ Processing complete for {exercise.get('name')}")
            
            # Show final state
            result = self.orchestrator.firebase_client.post("getExercise", {"exerciseId": exercise_id})
            if result.get("success"):
                exercise = result.get("data", {})
                print(f"\n📊 Final state:")
                print(f"   Name: {exercise.get('name')}")
                print(f"   Family: {exercise.get('family_slug', 'none')}")
                print(f"   Variant: {exercise.get('variant_key', 'none')}")
                print(f"   Approved: {exercise.get('approved', False)}")
            
        except Exception as e:
            print(f"❌ Error processing exercise: {e}")
    
    def bulk_add(self, exercises_file: str, auto_process: bool = True) -> None:
        """
        Add multiple exercises from a JSON file.
        
        File format:
        [
            {"name": "Exercise 1", "equipment": ["barbell"], "muscles": {"primary": ["chest"]}},
            {"name": "Exercise 2", "equipment": ["dumbbell"], "muscles": {"primary": ["shoulders"]}}
        ]
        """
        print(f"📂 Loading exercises from {exercises_file}")
        
        try:
            with open(exercises_file, 'r') as f:
                exercises = json.load(f)
            
            print(f"   Found {len(exercises)} exercises to add")
            
            created_ids = []
            for i, exercise_data in enumerate(exercises, 1):
                name = exercise_data.get("name")
                if not name:
                    print(f"   ⚠️ Skipping exercise {i}: no name")
                    continue
                
                print(f"\n[{i}/{len(exercises)}] Adding {name}...")
                
                result = self.orchestrator.firebase_client.post("ensureExerciseExists", exercise_data)
                
                if result.get("success"):
                    data = result.get("data", {})
                    exercise_id = data.get("exercise_id")
                    created_ids.append(exercise_id)
                    print(f"   ✅ Created with ID: {exercise_id}")
                else:
                    print(f"   ❌ Failed: {result.get('error')}")
            
            print(f"\n✅ Added {len(created_ids)} exercises")
            
            if auto_process and created_ids:
                print("\n🔄 Processing all new exercises through pipeline...")
                self.process_multiple(created_ids)
                
        except Exception as e:
            print(f"❌ Error: {e}")
    
    def process_multiple(self, exercise_ids: list) -> None:
        """
        Process multiple exercises through the pipeline.
        """
        print(f"🔄 Processing {len(exercise_ids)} exercises...")
        
        # Fetch all exercises
        exercises = []
        for ex_id in exercise_ids:
            result = self.orchestrator.firebase_client.post("getExercise", {"exerciseId": ex_id})
            if result.get("ok"):
                exercises.append(result.get("data", {}).get("exercise", {}))
        
        # Categorize by needs
        need_triage = [ex for ex in exercises if not ex.get("family_slug")]
        need_enrichment = [ex for ex in exercises if ex.get("family_slug")]
        
        # Process triage batch
        if need_triage:
            print(f"\n📋 Running triage for {len(need_triage)} exercises...")
            job = self.orchestrator.create_batch_job(AgentType.TRIAGE, need_triage, batch_size=5)
            completed_job = self.orchestrator.execute_batch_job(job, parallel=True)
            print(f"   Completed: {completed_job.progress[0]}/{completed_job.progress[1]} tasks")
        
        # Process enrichment batch
        if need_enrichment:
            print(f"\n🎨 Running enrichment for {len(need_enrichment)} exercises...")
            job = self.orchestrator.create_batch_job(AgentType.ENRICHMENT, need_enrichment, batch_size=5)
            completed_job = self.orchestrator.execute_batch_job(job, parallel=True)
            print(f"   Completed: {completed_job.progress[0]}/{completed_job.progress[1]} tasks")
        
        print("\n✅ Batch processing complete")
    
    def trigger_pipeline(self) -> None:
        """
        Trigger the full pipeline to run.
        """
        print("🚀 Triggering full pipeline...")
        
        if self.api_server_url:
            # Try API server first
            try:
                response = requests.post(f"{self.api_server_url}/trigger")
                if response.status_code == 200:
                    print("✅ Pipeline triggered via API server")
                    return
            except:
                pass
        
        # Fallback to direct execution
        print("   Running pipeline directly...")
        self.orchestrator.run_pipeline()
        print("✅ Pipeline execution complete")
    
    def status(self) -> None:
        """
        Show the current status of the catalog and any active jobs.
        """
        print("📊 Catalog Status")
        print("-" * 40)
        
        state = self.orchestrator.assess_catalog_state()
        
        print(f"Total Exercises: {state['exercises']['total']}")
        print(f"Unnormalized: {state['exercises']['unnormalized']}")
        print(f"Unapproved: {state['exercises']['unapproved']}")
        print(f"Total Families: {state['families']['total']}")
        
        if self.orchestrator.active_jobs:
            print(f"\n📋 Active Jobs")
            print("-" * 40)
            
            for job_id, job in self.orchestrator.active_jobs.items():
                status = "✅ Complete" if job.is_complete else "⏳ In Progress"
                print(f"{job_id}: {status} ({job.progress[0]}/{job.progress[1]} tasks)")


def main():
    parser = argparse.ArgumentParser(description="Catalog Curation CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Add exercise command
    add_parser = subparsers.add_parser("add", help="Add a new exercise")
    add_parser.add_argument("name", help="Exercise name")
    add_parser.add_argument("--equipment", help="Equipment (comma-separated)")
    add_parser.add_argument("--muscles", help="Primary muscles (comma-separated)")
    add_parser.add_argument("--no-process", action="store_true", help="Don't process through pipeline")
    
    # Process exercise command
    process_parser = subparsers.add_parser("process", help="Process an exercise")
    process_parser.add_argument("exercise_id", help="Exercise ID to process")
    
    # Bulk add command
    bulk_parser = subparsers.add_parser("bulk-add", help="Add exercises from JSON file")
    bulk_parser.add_argument("file", help="Path to JSON file with exercises")
    bulk_parser.add_argument("--no-process", action="store_true", help="Don't process through pipeline")
    
    # Trigger pipeline command
    trigger_parser = subparsers.add_parser("trigger", help="Trigger full pipeline")
    
    # Status command
    status_parser = subparsers.add_parser("status", help="Show catalog status")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    cli = CatalogCLI()
    
    if args.command == "add":
        cli.add_exercise(
            args.name,
            args.equipment,
            args.muscles,
            auto_process=not args.no_process
        )
    elif args.command == "process":
        cli.process_exercise(args.exercise_id)
    elif args.command == "bulk-add":
        cli.bulk_add(args.file, auto_process=not args.no_process)
    elif args.command == "trigger":
        cli.trigger_pipeline()
    elif args.command == "status":
        cli.status()


if __name__ == "__main__":
    main()
