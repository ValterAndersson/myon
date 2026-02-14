"""Configuration for training analyst service."""

import os

# GCP Project
PROJECT_ID = os.getenv("GCP_PROJECT_ID", "myon-53d85")
REGION = os.getenv("GCP_REGION", "europe-west1")

# Firestore collections
JOBS_COLLECTION = "training_analysis_jobs"

# Job queue settings
LEASE_DURATION_SECS = 300  # 5 minutes
LEASE_RENEWAL_MARGIN_SECS = 120  # 2 minutes
MAX_ATTEMPTS = 3

# LLM models
MODEL_PRO = "gemini-2.5-pro"  # Post-workout and weekly review
MODEL_FLASH = "gemini-2.5-flash"  # Daily brief

# TTL for output documents (days)
TTL_INSIGHTS = 7  # analysis_insights
TTL_BRIEFS = 7   # daily_briefs
TTL_REVIEWS = 30  # weekly_reviews
