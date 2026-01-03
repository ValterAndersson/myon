"""
Skills - Pure Python functions for the Shell Agent.

Skills are organized by domain:
- copilot_skills: Fast Lane operations (log set, next set, etc.)
- coach_skills: Analytics and coaching logic (extracted from coach_agent)
- planner_skills: Artifact creation logic (extracted from planner_agent)

Skills are pure functions that:
- Take explicit parameters (no global state access)
- Return structured results
- Are callable by both Fast Lane (direct) and Slow Lane (via Shell Agent tools)
"""

from app.skills.copilot_skills import (
    log_set,
    log_set_shorthand,
    get_next_set,
    acknowledge_rest,
)

__all__ = [
    "log_set",
    "log_set_shorthand",
    "get_next_set",
    "acknowledge_rest",
]
