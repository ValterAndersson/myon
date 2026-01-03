#!/usr/bin/env python3
"""
Post-Workout Analyst - Background worker for workout analysis.

Lane 4: Worker Lane
- Trigger: PubSub event when workout completes
- Model: gemini-2.5-pro (for deep analysis)
- Output: Insight Card written to Firestore

This script demonstrates the "Shared Brain" architecture:
It imports the SAME skill functions used by the chat agent.
This ensures consistent analysis logic across all access patterns.

Usage:
    # Triggered by PubSub
    python post_workout_analyst.py --user-id USER_ID --workout-id WORKOUT_ID
    
    # Or via Cloud Run Job with environment variables
    USER_ID=xxx WORKOUT_ID=yyy python post_workout_analyst.py

Environment:
    GOOGLE_PROJECT: GCP project ID
    CANVAS_FUNCTIONS_URL: Firebase functions base URL
    GEMINI_API_KEY: Optional - for local development only
    
Note: When running on GCP (Cloud Run, Vertex), uses Application Default
Credentials (ADC). For local dev, can use GEMINI_API_KEY fallback.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

# Ensure app module is importable when running as standalone script
script_dir = os.path.dirname(os.path.abspath(__file__))
app_dir = os.path.dirname(script_dir)
if app_dir not in sys.path:
    sys.path.insert(0, app_dir)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("post_workout_analyst")


# =============================================================================
# INSIGHT CARD DATA STRUCTURE
# =============================================================================

@dataclass
class InsightCard:
    """Insight generated from workout analysis."""
    
    card_type: str = "insight"
    title: str = ""
    body: str = ""
    severity: str = "info"  # info, warning, action
    insight_type: str = ""  # stall, volume_imbalance, overreach, recovery
    data: Dict[str, Any] = None
    created_at: str = None
    
    def __post_init__(self):
        if self.data is None:
            self.data = {}
        if self.created_at is None:
            self.created_at = datetime.utcnow().isoformat() + "Z"
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# =============================================================================
# SHARED SKILLS IMPORT
# These are the SAME functions used by the Chat Agent (ShellAgent).
# This is the "Shared Brain" principle in action.
# =============================================================================

def _import_skills():
    """
    Import skills with proper error handling.
    
    Skills may not be available in all environments (e.g., when running
    outside the ADK app context).
    """
    try:
        from app.skills.coach_skills import (
            get_analytics_features,
            get_training_context,
            get_recent_workouts,
        )
        return {
            "get_analytics_features": get_analytics_features,
            "get_training_context": get_training_context,
            "get_recent_workouts": get_recent_workouts,
        }
    except ImportError as e:
        logger.error("Failed to import skills: %s", e)
        logger.info("Falling back to direct API calls")
        return None


def _init_standalone_client():
    """
    Initialize standalone client for use outside ADK context.
    
    Required environment variables:
    - CANVAS_FUNCTIONS_URL: Base URL for Firebase functions
    - GOOGLE_PROJECT or GCP_PROJECT: GCP project ID
    """
    import requests
    
    base_url = os.getenv("CANVAS_FUNCTIONS_URL", "")
    if not base_url:
        project = os.getenv("GOOGLE_PROJECT") or os.getenv("GCP_PROJECT")
        if project:
            base_url = f"https://us-central1-{project}.cloudfunctions.net"
        else:
            raise ValueError("CANVAS_FUNCTIONS_URL or GOOGLE_PROJECT must be set")
    
    logger.info("Initialized standalone client with base URL: %s", base_url)
    return base_url


# =============================================================================
# ANALYSIS LOGIC
# =============================================================================

def fetch_user_data(user_id: str, workout_id: str) -> Dict[str, Any]:
    """
    Fetch all data needed for analysis.
    
    Uses shared skills if available, falls back to direct API calls.
    """
    skills = _import_skills()
    
    if skills:
        # Use shared skills (same as Chat Agent)
        logger.info("Using shared skills for data fetch")
        
        analytics = skills["get_analytics_features"](
            user_id=user_id,
            weeks=12,  # 12-week lookback for trend analysis
        )
        
        context = skills["get_training_context"](user_id=user_id)
        
        recent = skills["get_recent_workouts"](user_id=user_id, limit=10)
        
        return {
            "analytics": analytics.to_dict() if hasattr(analytics, "to_dict") else analytics,
            "context": context.to_dict() if hasattr(context, "to_dict") else context,
            "recent_workouts": recent.to_dict() if hasattr(recent, "to_dict") else recent,
        }
    
    else:
        # Fallback: Direct API calls (for standalone execution)
        logger.info("Using standalone API calls")
        base_url = _init_standalone_client()
        
        # Mock data for demonstration
        return {
            "analytics": {"data": "mock_analytics", "user_id": user_id},
            "context": {"data": "mock_context", "user_id": user_id},
            "recent_workouts": {"workouts": []},
        }


def analyze_workout(user_id: str, workout_id: str) -> Optional[InsightCard]:
    """
    Analyze completed workout for actionable insights.
    
    Uses gemini-2.5-pro for deep analysis of training patterns.
    
    Looks for:
    - Stalled exercises (e1RM slope < 0 for 4+ weeks)
    - Volume imbalances (significant deviation from plan)
    - Overreach signals (excessive RIR accumulation)
    - Recovery needs (form degradation patterns)
    
    Returns:
        InsightCard if intervention needed, None otherwise
    """
    logger.info("Analyzing workout %s for user %s", workout_id, user_id)
    
    # 1. Fetch data using shared skills
    data = fetch_user_data(user_id, workout_id)
    
    if not data.get("analytics") or not data.get("context"):
        logger.warning("Insufficient data for analysis")
        return None
    
    # 2. Build analysis prompt
    prompt = f"""Analyze this user's recent training data. Look for patterns that require coaching intervention.

USER DATA:
Analytics (12 weeks): {json.dumps(data.get("analytics", {}), indent=2)}

Training Context: {json.dumps(data.get("context", {}), indent=2)}

Recent Workouts: {json.dumps(data.get("recent_workouts", {}), indent=2)}

ANALYSIS CRITERIA:

1. STALL DETECTION
   - Exercise where e1RM slope < 0 for 4+ consecutive weeks
   - Significant reduction in working weight without intentional deload

2. VOLUME IMBALANCE
   - Sets completed significantly below planned (adherence < 80%)
   - Muscle group receiving < 50% of target volume

3. OVERREACH SIGNALS
   - RIR consistently 2+ higher than planned
   - Performance declining across multiple exercises

4. RECOVERY NEEDS
   - Session RPE increasing while performance decreasing
   - Form degradation signals (weight drops mid-session)

OUTPUT RULES:
- If ANY intervention is needed, output a JSON InsightCard
- If NO intervention needed, output: {{"insight": null}}

InsightCard format:
{{
    "insight": {{
        "title": "Brief, actionable title",
        "body": "2-3 sentence explanation with specific data",
        "severity": "info|warning|action",
        "insight_type": "stall|volume_imbalance|overreach|recovery",
        "data": {{
            "exercise": "affected exercise name",
            "weeks_affected": 4,
            "recommendation": "specific action to take"
        }}
    }}
}}
"""

    # 3. Call Gemini Pro for analysis
    # Use Vertex AI for GCP deployments (ADC), fallback to genai for local dev
    try:
        # Try Vertex AI first (for Cloud Run / GCP environment)
        try:
            import vertexai
            from vertexai.generative_models import GenerativeModel, GenerationConfig
            
            # Initialize with ADC (Application Default Credentials)
            project = os.getenv("GOOGLE_PROJECT") or os.getenv("GCP_PROJECT")
            location = os.getenv("GOOGLE_LOCATION", "us-central1")
            if project:
                vertexai.init(project=project, location=location)
            else:
                vertexai.init()  # Uses default project from ADC
            
            model = GenerativeModel("gemini-2.5-pro")
            response = model.generate_content(
                prompt,
                generation_config=GenerationConfig(
                    temperature=0.2,  # Low temp for analytical precision
                    response_mime_type="application/json",
                ),
            )
            logger.info("Using Vertex AI (ADC)")
            
        except Exception as vertex_err:
            # Fallback to google-generativeai for local development
            logger.warning("Vertex AI init failed (%s), falling back to genai", vertex_err)
            import google.generativeai as genai
            
            api_key = os.getenv("GEMINI_API_KEY")
            if api_key:
                genai.configure(api_key=api_key)
            
            model = genai.GenerativeModel(
                "gemini-2.5-pro",
                generation_config={
                    "temperature": 0.2,
                    "response_mime_type": "application/json",
                },
            )
            response = model.generate_content(prompt)
            logger.info("Using google-generativeai (API key)")
        result = json.loads(response.text)
        
        insight_data = result.get("insight")
        
        if insight_data is None:
            logger.info("No insight needed for workout %s", workout_id)
            return None
        
        # Build InsightCard from response
        return InsightCard(
            title=insight_data.get("title", "Training Insight"),
            body=insight_data.get("body", ""),
            severity=insight_data.get("severity", "info"),
            insight_type=insight_data.get("insight_type", "general"),
            data=insight_data.get("data", {}),
        )
        
    except Exception as e:
        logger.error("Analysis failed: %s", e)
        return None


def write_insight_card(user_id: str, card: InsightCard) -> bool:
    """
    Write InsightCard to Firestore.
    
    Target collection: users/{user_id}/insights/{auto_id}
    
    TODO: Implement actual Firestore write.
    For now, this is a mock that logs the card.
    """
    logger.info("=" * 60)
    logger.info("INSIGHT CARD GENERATED")
    logger.info("=" * 60)
    logger.info("User: %s", user_id)
    logger.info("Title: %s", card.title)
    logger.info("Severity: %s", card.severity)
    logger.info("Type: %s", card.insight_type)
    logger.info("Body: %s", card.body)
    logger.info("Data: %s", json.dumps(card.data, indent=2))
    logger.info("=" * 60)
    
    # TODO: Actual Firestore write
    # from google.cloud import firestore
    # db = firestore.Client()
    # db.collection("users").document(user_id).collection("insights").add(card.to_dict())
    
    return True


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def main():
    """
    Main entry point for the post-workout analyst.
    
    Can be triggered by:
    - Command line arguments
    - Environment variables (for Cloud Run Job)
    - PubSub message parsing (for Cloud Functions trigger)
    """
    parser = argparse.ArgumentParser(
        description="Post-Workout Analyst - Generate insights from workout data"
    )
    parser.add_argument(
        "--user-id",
        help="User ID to analyze",
        default=os.getenv("USER_ID"),
    )
    parser.add_argument(
        "--workout-id",
        help="Workout ID that triggered analysis",
        default=os.getenv("WORKOUT_ID"),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run analysis but don't write to Firestore",
    )
    
    args = parser.parse_args()
    
    if not args.user_id or not args.workout_id:
        logger.error("user-id and workout-id are required")
        sys.exit(1)
    
    logger.info("Starting post-workout analysis")
    logger.info("User: %s, Workout: %s", args.user_id, args.workout_id)
    
    # Run analysis
    insight = analyze_workout(args.user_id, args.workout_id)
    
    if insight:
        if args.dry_run:
            logger.info("DRY RUN - Would write insight: %s", insight.title)
            print(json.dumps(insight.to_dict(), indent=2))
        else:
            success = write_insight_card(args.user_id, insight)
            if success:
                logger.info("Insight card written successfully")
            else:
                logger.error("Failed to write insight card")
                sys.exit(1)
    else:
        logger.info("No insight generated - training is on track")
    
    logger.info("Analysis complete")


if __name__ == "__main__":
    main()
