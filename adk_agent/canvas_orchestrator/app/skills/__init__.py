"""
Skills - Pure Python functions for the Shell Agent.

Skills are organized by domain:
- copilot_skills: Fast Lane operations (log set, next set, etc.)
- coach_skills: Analytics and coaching logic (extracted from coach_agent)
- planner_skills: Artifact creation logic (extracted from planner_agent)

Skills are pure functions that:
- Take explicit parameters (no global state access)
- Return structured results (SkillResult)
- Are callable by both Fast Lane (direct) and Slow Lane (via Shell Agent tools)
"""

# Copilot Skills - Fast Lane
from app.skills.copilot_skills import (
    log_set,
    log_set_shorthand,
    get_next_set,
    acknowledge_rest,
    parse_shorthand,
    SkillResult as CopilotSkillResult,
)

# Coach Skills - Analytics & Coaching
from app.skills.coach_skills import (
    get_training_context,
    get_analytics_features,
    get_user_profile,
    get_recent_workouts,
    search_exercises,
    get_exercise_details,
    SkillResult as CoachSkillResult,
)

# Planner Skills - Artifact Creation (with dry_run support)
from app.skills.planner_skills import (
    get_planning_context,
    propose_workout,
    propose_routine,
    SkillResult as PlannerSkillResult,
)

__all__ = [
    # Copilot Skills (Fast Lane)
    "log_set",
    "log_set_shorthand",
    "get_next_set",
    "acknowledge_rest",
    "parse_shorthand",
    "CopilotSkillResult",
    # Coach Skills
    "get_training_context",
    "get_analytics_features",
    "get_user_profile",
    "get_recent_workouts",
    "search_exercises",
    "get_exercise_details",
    "CoachSkillResult",
    # Planner Skills
    "get_planning_context",
    "propose_workout",
    "propose_routine",
    "PlannerSkillResult",
]
