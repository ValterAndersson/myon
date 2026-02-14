"""
Scheduler - Creates daily and weekly analysis jobs for active users.

Run as a Cloud Scheduler job (daily at 6 AM).
"""

import logging
from datetime import datetime, timedelta

from app.firestore_client import get_db
from app.jobs.models import JobType
from app.jobs.queue import create_job

logger = logging.getLogger(__name__)


def schedule_daily_briefs():
    """Create daily brief jobs for active users."""
    db = get_db()

    # Query users with active routines
    users_ref = db.collection("users")
    query = users_ref.where("activeRoutineId", "!=", None).stream()

    created_count = 0

    for user_doc in query:
        user_id = user_doc.id

        # Check if user has recent workouts (last 14 days)
        two_weeks_ago = datetime.utcnow() - timedelta(days=14)
        recent_workouts = (
            db.collection("users")
            .document(user_id)
            .collection("workouts")
            .where("ended_at", ">=", two_weeks_ago)
            .limit(1)
            .get()
        )

        if not recent_workouts:
            continue

        # Create daily brief job
        try:
            create_job(
                job_type=JobType.DAILY_BRIEF,
                user_id=user_id,
            )
            created_count += 1
            logger.info("Created daily brief job for user %s", user_id)
        except Exception as e:
            logger.error("Failed to create daily brief for user %s: %s", user_id, e)

    logger.info("Created %d daily brief jobs", created_count)
    return {"daily_briefs_created": created_count}


def schedule_weekly_reviews():
    """Create weekly review jobs for active users (run on Sundays)."""
    db = get_db()

    # Only run on Sundays
    today = datetime.utcnow()
    if today.weekday() != 6:
        logger.info("Not Sunday, skipping weekly reviews")
        return {"weekly_reviews_created": 0}

    # Query users with active routines
    users_ref = db.collection("users")
    query = users_ref.where("activeRoutineId", "!=", None).stream()

    created_count = 0
    week_ending = today.strftime("%Y-%m-%d")

    for user_doc in query:
        user_id = user_doc.id

        # Check if user has recent workouts (last 30 days)
        month_ago = datetime.utcnow() - timedelta(days=30)
        recent_workouts = (
            db.collection("users")
            .document(user_id)
            .collection("workouts")
            .where("ended_at", ">=", month_ago)
            .limit(1)
            .get()
        )

        if not recent_workouts:
            continue

        # Create weekly review job
        try:
            create_job(
                job_type=JobType.WEEKLY_REVIEW,
                user_id=user_id,
                window_weeks=12,
                week_ending=week_ending,
            )
            created_count += 1
            logger.info("Created weekly review job for user %s", user_id)
        except Exception as e:
            logger.error("Failed to create weekly review for user %s: %s", user_id, e)

    logger.info("Created %d weekly review jobs", created_count)
    return {"weekly_reviews_created": created_count}


def run_scheduler():
    """Run scheduler - creates daily and weekly jobs."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
    )

    logger.info("Starting scheduler")

    daily_result = schedule_daily_briefs()
    weekly_result = schedule_weekly_reviews()

    results = {
        **daily_result,
        **weekly_result,
    }

    logger.info("Scheduler completed: %s", results)
    return results


if __name__ == "__main__":
    run_scheduler()
