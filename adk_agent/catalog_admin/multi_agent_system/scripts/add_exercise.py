#!/usr/bin/env python3
"""
Add a single exercise and process it through the pipeline
Simple script for adding exercises ad-hoc.
"""

import json
import logging
import os
import sys
from datetime import datetime

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from orchestrator.orchestrator import CatalogOrchestrator, AgentType


def add_and_process_exercise(name, equipment=None, muscles=None, category=None):
    """
    Add a new exercise and immediately process it through the pipeline.
    
    Args:
        name: Exercise name
        equipment: List of equipment or comma-separated string
        muscles: List of primary muscles or comma-separated string
        category: Exercise category (compound/isolation)
    """
    print("\n" + "=" * 60)
    print("📝 ADD & PROCESS EXERCISE")
    print("=" * 60)
    
    # Configuration
    FIREBASE_BASE_URL = os.getenv("MYON_FUNCTIONS_BASE_URL", 
                                  "https://us-central1-myon-53d85.cloudfunctions.net")
    FIREBASE_API_KEY = os.getenv("FIREBASE_API_KEY", "myon-agent-key-2024")
    CATALOG_ADMIN_ENGINE_ID = "projects/919326069447/locations/us-central1/reasoningEngines/5176575510360096768"
    
    # Initialize orchestrator
    orchestrator = CatalogOrchestrator(
        firebase_base_url=FIREBASE_BASE_URL,
        firebase_api_key=FIREBASE_API_KEY,
        log_dir=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs"),
        system_user_id="exercise_adder"
    )
    
    # Prepare exercise data
    exercise_data = {"name": name}
    
    if equipment:
        if isinstance(equipment, str):
            equipment = [e.strip() for e in equipment.split(",")]
        exercise_data["equipment"] = equipment
        
    if muscles:
        if isinstance(muscles, str):
            muscles = [m.strip() for m in muscles.split(",")]
        exercise_data["muscles"] = {"primary": muscles}
        
    if category:
        exercise_data["category"] = category
    
    print(f"\nAdding exercise: {name}")
    if equipment:
        print(f"  Equipment: {', '.join(equipment)}")
    if muscles:
        print(f"  Muscles: {', '.join(muscles)}")
    if category:
        print(f"  Category: {category}")
    
    # Step 1: Create the exercise
    print("\n📌 Creating exercise...")
    result = orchestrator.firebase_client.post("ensureExerciseExists", exercise_data)
    
    if not result.get("success"):
        print(f"❌ Failed to create exercise: {result.get('error')}")
        return False
    
    data = result.get("data", {})
    exercise_id = data.get("exercise_id")
    created = data.get("created", False)
    
    if created:
        print(f"✅ Exercise created with ID: {exercise_id}")
    else:
        print(f"ℹ️ Exercise already exists with ID: {exercise_id}")
    
    # Step 2: Get the full exercise data
    print("\n🔍 Fetching exercise details...")
    result = orchestrator.firebase_client.post("getExercise", {"exerciseId": exercise_id})
    
    if not result.get("success"):
        print(f"❌ Failed to fetch exercise: {result.get('error')}")
        return False
    
    exercise = result.get("data", {})
    
    # Step 3: Determine what processing is needed
    needs_triage = not exercise.get("family_slug")
    needs_enrichment = bool(exercise.get("family_slug"))
    needs_analysis = True  # Always analyze new exercises
    
    print("\n📋 Processing needed:")
    print(f"  Normalization: {'Yes' if needs_triage else 'No (already has family)'}")
    print(f"  Enrichment: {'Yes' if needs_enrichment else 'No'}")
    print(f"  Quality Analysis: Yes")
    
    # Step 4: Run Triage if needed
    if needs_triage:
        print("\n🏷️ Running normalization...")
        job = orchestrator.create_batch_job(AgentType.TRIAGE, [exercise], batch_size=1)
        result = orchestrator.execute_batch_job(job, parallel=False)
        
        if result.is_complete:
            print("✅ Normalization complete")
            
            # Refresh exercise data
            result = orchestrator.firebase_client.post("getExercise", {"exerciseId": exercise_id})
            if result.get("success"):
                exercise = result.get("data", {})
        else:
            print("⚠️ Normalization failed")
    
    # Step 5: Run Enrichment if the exercise has a family
    if exercise.get("family_slug"):
        print("\n🎨 Running enrichment...")
        job = orchestrator.create_batch_job(AgentType.ENRICHMENT, [exercise], batch_size=1)
        result = orchestrator.execute_batch_job(job, parallel=False)
        
        if result.is_complete:
            task_result = result.tasks[0].result
            aliases_added = task_result.get("aliases_added", 0) if task_result else 0
            print(f"✅ Enrichment complete ({aliases_added} aliases added)")
        else:
            print("⚠️ Enrichment failed")
    
    # Step 6: Run Quality Analysis
    print("\n📊 Running quality analysis...")
    job = orchestrator.create_batch_job(AgentType.ANALYST, [{"items": [exercise]}], batch_size=1)
    result = orchestrator.execute_batch_job(job, parallel=False)
    
    if result.is_complete and result.tasks[0].result:
        analysis = result.tasks[0].result
        
        if analysis.get("detailed_reports"):
            report = analysis["detailed_reports"][0]
            print(f"✅ Analysis complete")
            print(f"  Quality Score: {report['quality_score']}")
            print(f"  Issues Found: {report['issue_count']}")
            print(f"  Ready for Approval: {'Yes' if report['ready_for_approval'] else 'No'}")
            
            if report.get('strengths'):
                print(f"  Strengths: {', '.join(report['strengths'])}")
    else:
        print("⚠️ Analysis failed")
    
    # Step 7: Show final state
    print("\n" + "=" * 60)
    print("📄 FINAL STATE")
    print("=" * 60)
    
    # Get final exercise data
    result = orchestrator.firebase_client.post("getExercise", {"exerciseId": exercise_id})
    if result.get("success"):
        exercise = result.get("data", {})
        print(f"Name: {exercise.get('name')}")
        print(f"ID: {exercise_id}")
        print(f"Family: {exercise.get('family_slug', 'none')}")
        print(f"Variant: {exercise.get('variant_key', 'none')}")
        print(f"Equipment: {', '.join(exercise.get('equipment', []))}")
        print(f"Category: {exercise.get('category', 'none')}")
        print(f"Approved: {'Yes' if exercise.get('approved') else 'No'}")
        
        # Show aliases if any
        aliases = exercise.get('aliases', [])
        if aliases:
            print(f"Aliases: {', '.join(aliases[:5])}")
    
    print("\n✅ Processing complete!")
    return True


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Add an exercise and process it")
    parser.add_argument("name", help="Exercise name")
    parser.add_argument("-e", "--equipment", help="Equipment (comma-separated)")
    parser.add_argument("-m", "--muscles", help="Primary muscles (comma-separated)")
    parser.add_argument("-c", "--category", choices=["compound", "isolation"], 
                       help="Exercise category")
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Add and process the exercise
    success = add_and_process_exercise(
        name=args.name,
        equipment=args.equipment,
        muscles=args.muscles,
        category=args.category
    )
    
    sys.exit(0 if success else 1)
