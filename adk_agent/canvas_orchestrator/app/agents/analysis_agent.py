"""
Analysis Agent - Progress analysis and evidence-based insights.

Simplified approach: Fetch data, analyze, respond with text.
Visualization cards can be added later as needed.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional

from google.adk import Agent
from google.adk.tools import FunctionTool

from app.libs.tools_canvas.client import CanvasFunctionsClient

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(levelname)s | %(name)s | %(message)s'))
    logger.addHandler(handler)

# Global context
_context: Dict[str, Any] = {
    "canvas_id": None,
    "user_id": None,
    "correlation_id": None,
}
_client: Optional[CanvasFunctionsClient] = None
_context_parsed_for_message: Optional[str] = None


def _auto_parse_context(message: str) -> None:
    """Auto-parse context from message prefix."""
    global _context_parsed_for_message
    
    if _context_parsed_for_message == message:
        return
    
    match = re.search(r'\(context:\s*canvas_id=(\S+)\s+user_id=(\S+)\s+corr=(\S+)\)', message)
    if match:
        _context["canvas_id"] = match.group(1).strip()
        _context["user_id"] = match.group(2).strip()
        corr = match.group(3).strip()
        _context["correlation_id"] = corr if corr != "none" else None
        _context_parsed_for_message = message
        logger.info("auto_parse_context canvas=%s user=%s corr=%s",
                    _context.get("canvas_id"), _context.get("user_id"), _context.get("correlation_id"))


def _canvas_client() -> CanvasFunctionsClient:
    global _client
    if _client is None:
        base_url = os.getenv("MYON_FUNCTIONS_BASE_URL", "https://us-central1-myon-53d85.cloudfunctions.net")
        api_key = os.getenv("MYON_API_KEY", "myon-agent-key-2024")
        _client = CanvasFunctionsClient(base_url=base_url, api_key=api_key)
    return _client


def _resolve(value: Optional[str], fallback_key: str) -> Optional[str]:
    if isinstance(value, str) and value.strip():
        return value.strip()
    stored = _context.get(fallback_key)
    return stored.strip() if isinstance(stored, str) and stored.strip() else None


# ============================================================================
# TOOLS: Analytics Data Fetching
# ============================================================================

def tool_get_analytics_features(
    *,
    user_id: Optional[str] = None,
    weeks: int = 8,
    exercise_ids: Optional[List[str]] = None,
    muscles: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Fetch analytics features for progress analysis.
    
    Use this as your PRIMARY data source for volume, intensity, and progression analysis.
    
    Args:
        user_id: User ID (auto-resolved from context if not provided)
        weeks: Number of weeks to analyze (1-52, default 8). Use 12-16 for plateau detection.
        exercise_ids: Optional exercise IDs for per-exercise e1RM series. Get IDs from tool_get_user_exercises_by_muscle.
        muscles: Optional muscle names for per-muscle series. Values: "chest", "back", "shoulders", etc.
    
    Returns:
        {
            "weeks_requested": int,
            "weeks_with_data": int,  # Weeks that had at least one workout
            "total_workouts": int,
            "total_sets": int,
            "total_volume_kg": float,
            "avg_workouts_per_week": float,
            "avg_sets_per_week": float,
            
            # Muscle ranking by weekly hard sets (use for exposure analysis)
            "muscle_sets_ranking": [
                {"muscle": "chest", "total_sets": 45.0, "avg_sets_per_week": 5.6}, ...
            ],
            
            # Muscle group ranking by volume in kg
            "muscle_group_volume_kg": [
                {"group": "chest", "total_kg": 12500}, ...
            ],
            
            # Raw weekly rollups (for trend analysis)
            "rollups": [
                {
                    "id": "2024-01-01",  # Week start date
                    "total_sets": int,
                    "total_reps": int, 
                    "total_weight": float,  # Volume in kg
                    "workouts": int,  # Sessions this week
                    "weight_per_muscle_group": {"chest": kg, "back": kg, ...},
                    "intensity": {
                        "hard_sets_total": int,
                        "hard_sets_per_muscle": {"chest": sets, ...},
                        "load_per_muscle": {"chest": load_units, ...}  # Internal metric
                    }
                }, ...
            ],
            
            # Per-muscle weekly series (if muscles param provided)
            "series_muscle": {
                "chest": [{"week": "2024-01-01", "sets": 12, "volume": 5000, "hard_sets": 10}], ...
            },
            
            # Per-exercise series with e1RM trends (if exercise_ids param provided)
            "series_exercise": {
                "exercise_id_123": {
                    "days": ["2024-01-05", "2024-01-12", ...],  # Workout dates
                    "e1rm": [85.0, 87.5, 90.0, ...],  # Estimated 1RM per session
                    "vol": [2500, 2800, ...],  # Volume per session
                    "e1rm_slope": 0.5,  # Positive = getting stronger
                    "vol_slope": 50.0   # Volume trend
                }
            }
        }
    
    Key metrics for agents:
        - Use "muscle_sets_ranking" for exposure/volume distribution
        - Use "series_exercise.e1rm_slope" for strength progress (positive = improving)
        - Use "weeks_with_data" vs "weeks_requested" for consistency assessment
        - Never say "load units" to users - use "hard sets" or "volume (kg)" instead
    """
    uid = _resolve(user_id, "user_id")
    if not uid:
        return {"error": "No user_id available"}
    
    weeks = max(1, min(52, weeks))
    
    logger.info("get_analytics_features uid=%s weeks=%d", uid, weeks)
    
    try:
        resp = _canvas_client().get_analytics_features(
            uid,
            mode="weekly",
            weeks=weeks,
            exercise_ids=exercise_ids,
            muscles=muscles,
        )
    except Exception as e:
        logger.error("get_analytics_features failed: %s", str(e))
        return {"error": f"Failed to fetch analytics: {str(e)}"}
    
    # Firebase returns {"success": true, "data": {...}}
    data = resp.get("data") or resp
    rollups = data.get("rollups") or []
    series_muscle = data.get("series_muscle") or {}
    series_exercise = data.get("series_exercise") or {}
    
    logger.info("get_analytics_features: rollups=%d, muscles=%d, exercises=%d",
                len(rollups), len(series_muscle), len(series_exercise))
    
    # Compute summary stats
    weeks_with_data = len([r for r in rollups if (r.get("workouts") or r.get("cadence", {}).get("sessions") or 0) > 0])
    total_workouts = sum(r.get("workouts") or r.get("cadence", {}).get("sessions") or 0 for r in rollups)
    total_sets = sum(r.get("total_sets") or 0 for r in rollups)
    total_weight = sum(r.get("total_weight") or 0 for r in rollups)
    
    # Aggregate muscle group volume (uses weight_per_muscle_group which is more intuitive)
    muscle_group_weight: Dict[str, float] = {}
    for rollup in rollups:
        for group, weight in (rollup.get("weight_per_muscle_group") or {}).items():
            muscle_group_weight[group] = muscle_group_weight.get(group, 0) + (weight or 0)
    
    # Aggregate muscle sets (more intuitive than load)
    muscle_sets: Dict[str, float] = {}
    for rollup in rollups:
        intensity = rollup.get("intensity") or {}
        for muscle, sets in (intensity.get("hard_sets_per_muscle") or {}).items():
            muscle_sets[muscle] = muscle_sets.get(muscle, 0) + (sets or 0)
    
    # Sort muscles by sets
    sorted_muscles_by_sets = sorted(muscle_sets.items(), key=lambda x: -x[1])
    
    # Sort muscle groups by weight
    sorted_groups_by_weight = sorted(muscle_group_weight.items(), key=lambda x: -x[1])
    
    # Compute avg sets per week per muscle
    muscle_avg_sets = {
        m: round(s / max(weeks_with_data, 1), 1)
        for m, s in muscle_sets.items()
    }
    
    return {
        "weeks_requested": weeks,
        "weeks_with_data": weeks_with_data,
        "total_workouts": total_workouts,
        "total_sets": total_sets,
        "total_volume_kg": round(total_weight, 0),
        "avg_workouts_per_week": round(total_workouts / max(weeks_with_data, 1), 1),
        "avg_sets_per_week": round(total_sets / max(weeks_with_data, 1), 1),
        # Muscle ranking by weekly sets (more intuitive)
        "muscle_sets_ranking": [
            {"muscle": m, "total_sets": round(s, 1), "avg_sets_per_week": muscle_avg_sets.get(m, 0)} 
            for m, s in sorted_muscles_by_sets[:10]
        ],
        # Muscle group ranking by volume in kg
        "muscle_group_volume_kg": [
            {"group": g, "total_kg": round(w, 0)} 
            for g, w in sorted_groups_by_weight[:6]
        ],
        "rollups": rollups,  # Raw data for detailed analysis
        "series_muscle": series_muscle,
        "series_exercise": series_exercise,
    }


def tool_get_user_profile(*, user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Get the user's fitness profile including goals, experience level, and preferences.
    
    Use this ONCE per conversation when you need to understand their training context.
    Call only if goals/experience would change your analysis conclusions.
    
    Args:
        user_id: User ID (auto-resolved from context if not provided)
    
    Returns:
        {
            "name": str | None,
            "fitness_goal": "hypertrophy" | "strength" | "general_fitness" | None,
            "fitness_level": "beginner" | "intermediate" | "advanced" | None,
            "equipment_preference": "full_gym" | "home_gym" | "bodyweight" | None,
            "workouts_per_week_goal": int | None,  # e.g., 3, 4, 5
            "weight": float | None,  # User's bodyweight
            "height": float | None,
            "weight_format": "kilograms" | "pounds"
        }
    
    Use cases:
        - Adjust volume recommendations based on fitness_level
        - Consider equipment_preference when suggesting exercise swaps
        - Compare actual training frequency to workouts_per_week_goal
    """
    uid = _resolve(user_id, "user_id")
    if not uid:
        return {"error": "No user_id available"}
    
    logger.info("get_user_profile uid=%s", uid)
    try:
        resp = _canvas_client().get_user(uid)
        return resp.get("data") or resp.get("context") or {}
    except Exception as e:
        logger.error("get_user_profile failed: %s", str(e))
        return {"error": f"Failed to fetch profile: {str(e)}"}


def tool_get_recent_workouts(*, user_id: Optional[str] = None, limit: int = 10) -> Dict[str, Any]:
    """
    Get the user's recent completed workout sessions with full exercise details.
    
    Use this for:
    - Inferring the user's training split (PPL, Upper/Lower, Full Body)
    - Finding specific exercise IDs for e1RM queries
    - Inspecting rep ranges, loads, and exercise selection patterns
    
    Args:
        user_id: User ID (auto-resolved from context if not provided)
        limit: Number of workouts to fetch (5-30, default 10). Use 10-20 for split detection.
    
    Returns:
        {
            "count": int,
            "workouts": [
                {
                    "id": str,  # Workout document ID
                    "start_time": timestamp,
                    "end_time": timestamp,
                    "notes": str | None,
                    "source_template_id": str | None,  # Template this workout was based on
                    "source_routine_id": str | None,   # Routine this belongs to
                    "exercises": [
                        {
                            "id": str,  # Exercise catalog ID - USE THIS for analytics queries
                            "exercise_id": str,  # Same as id (legacy field)
                            "name": str,  # e.g., "Bench Press (Barbell)"
                            "position": int,  # Order in workout
                            "primaryMuscle": str,  # e.g., "chest"
                            "secondaryMuscles": [str],  # e.g., ["triceps", "shoulders"]
                            "muscleGroup": str,  # e.g., "chest"
                            "sets": [
                                {
                                    "id": str,
                                    "reps": int,
                                    "weight_kg": float,
                                    "rir": int,  # Reps in reserve (0-5)
                                    "type": "working" | "warmup" | "drop" | "failure",
                                    "is_completed": bool
                                }, ...
                            ],
                            "analytics": {  # Per-exercise computed stats
                                "total_sets": int,
                                "total_reps": int,
                                "total_weight": float
                            }
                        }, ...
                    ],
                    "analytics": {  # Workout-level computed stats
                        "total_sets": int,
                        "total_reps": int,
                        "total_weight": float,
                        "weight_per_muscle_group": {"chest": kg, ...}
                    }
                }, ...
            ]
        }
    
    Use cases:
        - Split detection: Look at muscle groups across 10-15 sessions
        - Exercise ID lookup: Find "id" field for specific exercises to pass to analytics
        - Rep range analysis: Inspect "sets" array for reps/weight patterns
    """
    uid = _resolve(user_id, "user_id")
    if not uid:
        return {"error": "No user_id available"}
    
    limit = max(5, min(30, limit))
    
    logger.info("get_recent_workouts uid=%s limit=%s", uid, limit)
    try:
        resp = _canvas_client().get_user_workouts(uid, limit=limit)
        workouts = resp.get("data") or resp.get("workouts") or []
        return {
            "count": len(workouts),
            "workouts": workouts,
        }
    except Exception as e:
        logger.error("get_recent_workouts failed: %s", str(e))
        return {"error": f"Failed to fetch workouts: {str(e)}"}


def tool_get_user_exercises_by_muscle(
    *, 
    user_id: Optional[str] = None, 
    muscle_group: str,
    limit: int = 20,
) -> Dict[str, Any]:
    """
    Discover which exercises the user has performed for a specific muscle group.
    
    REQUIRED STEP before analyzing progress for a muscle group (e.g., "chest 1RM").
    Use the returned exercise IDs in tool_get_analytics_features(exercise_ids=[...]).
    
    Args:
        user_id: User ID (auto-resolved from context)
        muscle_group: Target muscle. Valid values:
            - Upper body: "chest", "back", "shoulders", "biceps", "triceps", "forearms"
            - Lower body: "quadriceps", "hamstrings", "glutes", "calves"
            - Core: "abs", "core", "obliques"
        limit: Max workouts to scan (5-50, default 20). Higher = more complete list.
    
    Returns:
        {
            "muscle_group": str,  # The muscle queried
            "exercises_found": int,  # Count of unique exercises
            "exercises": [
                {
                    "id": str,  # Exercise catalog ID - PASS THIS to tool_get_analytics_features
                    "name": str,  # e.g., "Bench Press (Barbell)"
                    "count": int,  # How many times performed in the scanned workouts
                    "primary_muscle": str  # Primary target muscle
                }, ...
            ]
        }
    
    Workflow example:
        1. User asks: "How's my chest 1RM?"
        2. Call tool_get_user_exercises_by_muscle(muscle_group="chest")
        3. Get top 2-3 exercises by count (most frequently performed)
        4. Call tool_get_analytics_features(exercise_ids=["id1", "id2"], weeks=12)
        5. Check "series_exercise.{id}.e1rm_slope" for strength trends
    """
    uid = _resolve(user_id, "user_id")
    if not uid:
        return {"error": "No user_id available"}
    
    muscle_group = muscle_group.lower().strip()
    limit = max(5, min(50, limit))
    
    logger.info("get_user_exercises_by_muscle uid=%s muscle=%s", uid, muscle_group)
    
    try:
        resp = _canvas_client().get_user_workouts(uid, limit=limit)
        workouts = resp.get("data") or resp.get("workouts") or []
    except Exception as e:
        logger.error("get_user_exercises_by_muscle failed: %s", str(e))
        return {"error": f"Failed to fetch workouts: {str(e)}"}
    
    # Track unique exercises with occurrence count
    exercise_counts: Dict[str, Dict[str, Any]] = {}
    
    for workout in workouts:
        exercises = workout.get("exercises") or []
        for ex in exercises:
            # Check if this exercise targets the requested muscle group
            primary = (ex.get("primaryMuscle") or ex.get("primary_muscle") or "").lower()
            secondary = [m.lower() for m in (ex.get("secondaryMuscles") or ex.get("secondary_muscles") or [])]
            muscle_group_field = (ex.get("muscleGroup") or ex.get("muscle_group") or "").lower()
            
            matches = (
                muscle_group in primary or
                muscle_group in secondary or
                muscle_group in muscle_group_field or
                primary == muscle_group or
                muscle_group_field == muscle_group
            )
            
            if matches:
                ex_id = ex.get("id") or ex.get("exercise_id") or ex.get("exerciseId")
                ex_name = ex.get("name") or ex.get("exerciseName") or "Unknown"
                
                if ex_id:
                    if ex_id not in exercise_counts:
                        exercise_counts[ex_id] = {
                            "id": ex_id,
                            "name": ex_name,
                            "count": 0,
                            "primary_muscle": primary,
                        }
                    exercise_counts[ex_id]["count"] += 1
    
    # Sort by occurrence count (most frequently used first)
    sorted_exercises = sorted(exercise_counts.values(), key=lambda x: -x["count"])
    
    return {
        "muscle_group": muscle_group,
        "exercises_found": len(sorted_exercises),
        "exercises": sorted_exercises,
    }


# ============================================================================
# ALL TOOLS
# ============================================================================

all_tools = [
    FunctionTool(func=tool_get_analytics_features),
    FunctionTool(func=tool_get_user_profile),
    FunctionTool(func=tool_get_recent_workouts),
    FunctionTool(func=tool_get_user_exercises_by_muscle),
]


# ============================================================================
# AGENT CALLBACKS
# ============================================================================

def _before_tool_callback(tool, args, tool_context):
    """Auto-parse context from message before tool execution."""
    try:
        ctx = tool_context.invocation_context
        if ctx and hasattr(ctx, 'user_content'):
            user_msg = str(ctx.user_content.parts[0].text) if ctx.user_content and ctx.user_content.parts else ""
            _auto_parse_context(user_msg)
    except Exception as e:
        logger.debug("before_tool_callback parse error: %s", e)
    return None


def _before_model_callback(callback_context, llm_request):
    """Auto-parse context from message before LLM inference."""
    try:
        contents = llm_request.contents or []
        for content in contents:
            if hasattr(content, 'role') and content.role == 'user':
                for part in (content.parts or []):
                    if hasattr(part, 'text') and part.text:
                        _auto_parse_context(part.text)
                        break
    except Exception as e:
        logger.debug("before_model_callback parse error: %s", e)
    return None


# ============================================================================
# AGENT INSTRUCTION
# ============================================================================

ANALYSIS_INSTRUCTION = """
## ROLE
You are the Analysis Agent. You interpret the user’s logged training data to identify progress, plateaus, balance issues, and anomalies. You produce evidence-led conclusions and minimal actionable deltas.

## CORE DIRECTIVE (SHORT)
Prioritize truth over agreement. If the user’s interpretation conflicts with the data or established training principles, state that clearly and explain why, briefly.

## SCOPE
You do:
- Data-grounded analysis of consistency, exposure (weekly hard sets), distribution, and strength proxies (e1RM trends where available).
- Identify laggards and likely bottlenecks using measurable signals.
- Provide actionable deltas (sets/week, distribution shifts, progression rule adjustments, exercise selection flags).

You do NOT:
- Create or edit workouts/routines.
- Manipulate active workout state.
- Speculate beyond the data. If a metric is not logged (e.g., RIR), do not claim it.

## MIXED QUESTIONS POLICY
Some user prompts mix analysis + coaching (“How can I grow chest faster?”).
You must answer the analysis component first:
- What their current training exposure and progress indicate for that muscle/exercise.
- What change would be most justified by the data.
Keep physiology explanations minimal unless explicitly asked.

## INVESTIGATION POLICY (DIG DEEPER WITHOUT THRASHING)
Default tool-call budget: 1–3 calls.
You MUST take one deeper step when it would materially change the conclusion.
You MUST stop when additional fetching won’t change the recommended deltas.

### Investigation ladder (use in order)
1) Fetch goals/context only if it changes conclusions:
   - tool_get_user_profile (once) when goals/experience matter or are unknown.
2) Broad evidence:
   - tool_get_analytics_features (default 8w; plateau/slow trends 12–16w).
3) Split discovery (required when discussing symmetry/balance):
   - tool_get_recent_workouts (limit 10–20) to infer the user’s split and day types.
4) Target drilldown (only if needed):
   - Muscle questions: tool_get_user_exercises_by_muscle → then tool_get_analytics_features(exercise_ids=…).
   - Specific exercise: tool_get_recent_workouts to discover exercise_id → tool_get_analytics_features(exercise_ids=[id]).
5) Session inspection (rare):
   - tool_get_recent_workouts to verify rep range drift, exercise churn, or inconsistent exposure.

Never ask the user which exercises they did. Discover it via tools.

## WHAT TO MEASURE (IN PRIORITY ORDER)
A) Consistency (base rate)
- sessions/week, weeks_with_data, gaps.

B) Exposure (stimulus opportunity)
- weekly hard sets per muscle (primary).
- if only volume kg exists, use it as secondary evidence.

C) Progression (outcomes)
- e1RM trend where available (exercise-level).
- otherwise infer from recent workouts (rep/load improvements) and label as inference.

D) Distribution and symmetry (RELATIVE TO THE USER’S SPLIT)
You must infer the user’s split from recent workouts before judging “balance”.
- Detect likely split pattern:
  - Full body: most sessions include upper + lower in same session.
  - Upper/Lower: clear alternation of upper-dominant and lower-dominant days.
  - PPL: recurring push-dominant, pull-dominant, leg-dominant sessions.
  - Other: hybrid; label uncertainty.

Then evaluate symmetry using split-adjusted expectations:
- Compare weekly sets and volume across muscle groups, but interpret through split structure.
- Example logic:
  - In PPL run once/week: legs naturally appear ~33% of session-days. In U/L: legs ~50% of session-days.
  - Push vs pull exposure differs by split; judge undertraining against the split’s intended distribution and user goals.

E) Anomalies
- sudden drops in sessions/week, total sets, or volume.
- large changes in muscle exposure week-to-week.
- exercise churn that can mask trends.

## LANGUAGE RULES (USER LANGUAGE, NOT INTERNAL JARGON)
- Avoid terms like “delta”. Use: “change”, “difference”, “trend”, “shift”.
- Prefer: “hard sets per week”, “training days per week”, “strength trend”, “stalled”, “rising”.
- If you use a technical metric, add a short gloss:
  - e1RM = “estimated max strength trend”.
- Never claim RIR-based conclusions unless RIR is actually logged.

## DATA SUFFICIENCY + CONFIDENCE
Always include a confidence tag:
- High: ≥ 6 sessions in-window AND ≥ 4 weeks with data (or dense exercise series).
- Medium: signal present but gaps exist.
- Low: sparse weeks, few sessions, or missing exercise series.

If confidence is low:
- Say what’s missing in one short clause.
- Provide the next diagnostic step that would change the conclusion.

## RESPONSE FORMAT (BRIEF, EVIDENCE-LED, ACTIONABLE)
Default structure (max ~10 lines):
1) Conclusion (1–2 sentences)
2) Evidence (2–4 bullets with numbers)
3) Action (1–3 bullets as measurable deltas or a diagnostic step)
4) Confidence (High/Med/Low + short reason)
5) Analysis Trace (3–6 steps; “what I checked”, no narration)

### Analysis Trace (for user-visible thinking stream)
Only list the checks performed, not internal deliberation.
Example:
- Pulled 12-week rollups
- Ranked hard sets per muscle
- Inferred split from last 12 sessions (likely U/L)
- Checked chest exercise strength trend (e1RM) on top 2 presses
- Compared chest exposure vs goal focus

## RECOMMENDATION HEURISTICS (EVIDENCE → MINIMAL CHANGE)
When recommending change, prefer the smallest lever that plausibly changes outcomes:
1) exposure shift: +/− sets/week or redistribute sets across days
2) frequency distribution: move sets to improve exposure cadence without increasing total workload
3) progression rule: adjust rep targets or load increments when trends are flat
4) exercise selection flag: only when stability/ROM/angle mismatch is evident from patterns

If the user’s claim conflicts with the data, say so plainly and propose a better interpretation.

"""

# ============================================================================
# AGENT DEFINITION
# ============================================================================

AnalysisAgent = Agent(
    name="AnalysisAgent",
    model=os.getenv("CANVAS_ANALYSIS_MODEL", "gemini-2.5-flash"),
    instruction=ANALYSIS_INSTRUCTION,
    tools=all_tools,
    before_tool_callback=_before_tool_callback,
    before_model_callback=_before_model_callback,
)

root_agent = AnalysisAgent

__all__ = ["root_agent", "AnalysisAgent"]
