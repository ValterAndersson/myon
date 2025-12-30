"""
Coach Agent - Unified coaching with data access.

Merged Coach + Analysis: A strength coach that personalizes advice using 
training data when it changes the recommendation.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional

from google.adk import Agent
from google.adk.tools import FunctionTool
from google.genai import types

from app.agents.shared_voice import SHARED_VOICE
from app.libs.tools_canvas.client import CanvasFunctionsClient
from app.libs.tools_common.response_helpers import (
    parse_api_response,
    format_validation_error_for_agent,
)

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
# TOOLS: Training Context & Analytics
# ============================================================================

def tool_get_training_context(*, user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Get the user's current training structure: active routine, split type, and recent patterns.
    
    Use this when split/balance/symmetry matters for your advice.
    
    Returns:
        - activeRoutine: Current routine with template_ids and frequency
        - templates: List of templates in the routine
        - recentWorkoutsSummary: Session patterns and muscle distribution
    """
    uid = _resolve(user_id, "user_id")
    if not uid:
        return {"error": "No user_id available"}
    
    logger.info("get_training_context uid=%s", uid)
    
    try:
        resp = _canvas_client().get_planning_context(uid)
        success, data, error_details = parse_api_response(resp)
        
        if not success:
            logger.error("get_training_context failed: %s", error_details)
            return format_validation_error_for_agent(error_details)
        
        return {
            "activeRoutine": data.get("activeRoutine"),
            "templates": data.get("templates"),
            "recentWorkoutsSummary": data.get("recentWorkoutsSummary"),
            "_display": {
                "running": "Loading training context",
                "complete": "Context loaded",
                "phase": "understanding",
            }
        }
    except Exception as e:
        logger.error("get_training_context exception: %s", str(e))
        return {"error": f"Failed to fetch training context: {str(e)}"}


def tool_get_analytics_features(
    *,
    user_id: Optional[str] = None,
    weeks: int = 8,
    exercise_ids: Optional[List[str]] = None,
    muscles: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Fetch analytics features for progress analysis.
    
    PRIMARY data source for volume, intensity, and progression analysis.
    
    Args:
        weeks: Number of weeks to analyze (1-52, default 8). Use 12-16 for plateau detection.
        exercise_ids: Optional exercise IDs for per-exercise e1RM series.
        muscles: Optional muscle names for per-muscle series.
    
    Returns:
        - weeks_with_data: Weeks that had at least one workout
        - avg_workouts_per_week, avg_sets_per_week
        - muscle_sets_ranking: Muscles ranked by weekly hard sets
        - series_exercise: Per-exercise e1RM trends (if exercise_ids provided)
    
    Key metrics:
        - Use "muscle_sets_ranking" for exposure/volume distribution
        - Use "series_exercise.{id}.e1rm_slope" for strength progress (positive = improving)
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
        
        # Check for API-level errors
        success, data, error_details = parse_api_response(resp)
        if not success:
            logger.error("get_analytics_features API error: %s", error_details)
            return format_validation_error_for_agent(error_details)
            
    except Exception as e:
        logger.error("get_analytics_features failed: %s", str(e))
        return {"error": f"Failed to fetch analytics: {str(e)}"}
    
    rollups = data.get("rollups") or []
    series_muscle = data.get("series_muscle") or {}
    series_exercise = data.get("series_exercise") or {}
    
    # Compute summary stats
    weeks_with_data = len([r for r in rollups if (r.get("workouts") or r.get("cadence", {}).get("sessions") or 0) > 0])
    total_workouts = sum(r.get("workouts") or r.get("cadence", {}).get("sessions") or 0 for r in rollups)
    total_sets = sum(r.get("total_sets") or 0 for r in rollups)
    total_weight = sum(r.get("total_weight") or 0 for r in rollups)
    
    # Aggregate muscle sets and intensity metrics
    muscle_sets: Dict[str, float] = {}
    muscle_low_rir: Dict[str, float] = {}
    total_hard_sets = 0
    total_low_rir_sets = 0
    
    for rollup in rollups:
        intensity = rollup.get("intensity") or {}
        total_hard_sets += intensity.get("hard_sets_total") or 0
        total_low_rir_sets += intensity.get("low_rir_sets_total") or 0
        
        for muscle, sets in (intensity.get("hard_sets_per_muscle") or {}).items():
            muscle_sets[muscle] = muscle_sets.get(muscle, 0) + (sets or 0)
        for muscle, sets in (intensity.get("low_rir_sets_per_muscle") or {}).items():
            muscle_low_rir[muscle] = muscle_low_rir.get(muscle, 0) + (sets or 0)
    
    sorted_muscles = sorted(muscle_sets.items(), key=lambda x: -x[1])
    muscle_avg = {m: round(s / max(weeks_with_data, 1), 1) for m, s in muscle_sets.items()}
    
    # Calculate intensity ratio (low_rir / hard sets) per muscle
    muscle_intensity_ratio = {}
    for muscle, hard in muscle_sets.items():
        low = muscle_low_rir.get(muscle, 0)
        if hard > 0:
            muscle_intensity_ratio[muscle] = round(low / hard, 2)
    
    # Overall intensity ratio
    overall_intensity_ratio = round(total_low_rir_sets / max(total_hard_sets, 1), 2)
    
    return {
        "weeks_requested": weeks,
        "weeks_with_data": weeks_with_data,
        "total_workouts": total_workouts,
        "total_sets": total_sets,
        "total_volume_kg": round(total_weight, 0),
        "avg_workouts_per_week": round(total_workouts / max(weeks_with_data, 1), 1),
        "avg_sets_per_week": round(total_sets / max(weeks_with_data, 1), 1),
        # Intensity summary (critical for volume adequacy decisions)
        "intensity_summary": {
            "total_hard_sets": total_hard_sets,
            "total_low_rir_sets": total_low_rir_sets,
            "intensity_ratio": overall_intensity_ratio,  # >0.3 = high intensity training
            "interpretation": "high intensity" if overall_intensity_ratio > 0.3 else "moderate intensity",
        },
        "muscle_sets_ranking": [
            {
                "muscle": m, 
                "total_sets": round(s, 1), 
                "avg_sets_per_week": muscle_avg.get(m, 0),
                "low_rir_sets": round(muscle_low_rir.get(m, 0), 1),
                "intensity_ratio": muscle_intensity_ratio.get(m, 0),
            } 
            for m, s in sorted_muscles[:10]
        ],
        "rollups": rollups,
        "series_muscle": series_muscle,
        "series_exercise": series_exercise,
        "_display": {
            "running": "Analyzing training data",
            "complete": f"Analyzed {weeks_with_data} weeks",
            "phase": "analyzing",
        }
    }


def tool_get_user_profile(*, user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Get the user's fitness profile: goals, experience level, preferences.
    
    Call only if goals/experience would change your recommendation.
    """
    uid = _resolve(user_id, "user_id")
    if not uid:
        return {"error": "No user_id available"}
    
    logger.info("get_user_profile uid=%s", uid)
    try:
        resp = _canvas_client().get_user(uid)
        success, data, error_details = parse_api_response(resp)
        
        if not success:
            logger.error("get_user_profile API error: %s", error_details)
            return format_validation_error_for_agent(error_details)
        
        data["_display"] = {
            "running": "Loading profile",
            "complete": "Profile loaded",
            "phase": "understanding",
        }
        return data
    except Exception as e:
        logger.error("get_user_profile failed: %s", str(e))
        return {"error": f"Failed to fetch profile: {str(e)}"}


def tool_get_recent_workouts(*, user_id: Optional[str] = None, limit: int = 10) -> Dict[str, Any]:
    """
    Get the user's recent completed workout sessions with full exercise details.
    
    Use for:
    - Inferring training split (PPL, Upper/Lower, Full Body)
    - Finding specific exercise IDs for e1RM queries
    - Inspecting rep ranges, loads, and exercise selection patterns
    """
    uid = _resolve(user_id, "user_id")
    if not uid:
        return {"error": "No user_id available"}
    
    limit = max(5, min(30, limit))
    
    logger.info("get_recent_workouts uid=%s limit=%s", uid, limit)
    try:
        resp = _canvas_client().get_user_workouts(uid, limit=limit)
        success, data, error_details = parse_api_response(resp)
        
        if not success:
            logger.error("get_recent_workouts API error: %s", error_details)
            return format_validation_error_for_agent(error_details)
        
        workouts = data.get("items") if isinstance(data, dict) else data
        if not isinstance(workouts, list):
            workouts = []
        return {
            "count": len(workouts),
            "workouts": workouts,
            "_display": {
                "running": "Loading recent workouts",
                "complete": f"Loaded {len(workouts)} workouts",
                "phase": "searching",
            }
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
    
    REQUIRED STEP before analyzing progress for a muscle (e.g., "chest 1RM").
    Use the returned exercise IDs in tool_get_analytics_features(exercise_ids=[...]).
    
    Args:
        muscle_group: Target muscle ("chest", "back", "shoulders", "biceps", "triceps", 
                      "quadriceps", "hamstrings", "glutes", "calves", "abs")
        limit: Max workouts to scan (default 20)
    """
    uid = _resolve(user_id, "user_id")
    if not uid:
        return {"error": "No user_id available"}
    
    muscle_group = muscle_group.lower().strip()
    limit = max(5, min(50, limit))
    
    logger.info("get_user_exercises_by_muscle uid=%s muscle=%s", uid, muscle_group)
    
    try:
        resp = _canvas_client().get_user_workouts(uid, limit=limit)
        success, data, error_details = parse_api_response(resp)
        
        if not success:
            logger.error("get_user_exercises_by_muscle API error: %s", error_details)
            return format_validation_error_for_agent(error_details)
        
        workouts = data.get("items") if isinstance(data, dict) else data
        if not isinstance(workouts, list):
            workouts = []
    except Exception as e:
        logger.error("get_user_exercises_by_muscle failed: %s", str(e))
        return {"error": f"Failed to fetch workouts: {str(e)}"}
    
    exercise_counts: Dict[str, Dict[str, Any]] = {}
    
    for workout in workouts:
        for ex in (workout.get("exercises") or []):
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
    
    sorted_exercises = sorted(exercise_counts.values(), key=lambda x: -x["count"])
    
    return {
        "muscle_group": muscle_group,
        "exercises_found": len(sorted_exercises),
        "exercises": sorted_exercises,
        "_display": {
            "running": f"Finding {muscle_group} exercises",
            "complete": f"Found {len(sorted_exercises)} exercises",
            "phase": "searching",
        }
    }


# ============================================================================
# TOOLS: Exercise Catalog (for technique/comparison questions)
# ============================================================================

def tool_search_exercises(
    *,
    muscle_group: Optional[str] = None,
    movement_type: Optional[str] = None,
    category: Optional[str] = None,
    equipment: Optional[str] = None,
    query: Optional[str] = None,
    limit: int = 10,
) -> Dict[str, Any]:
    """
    Search exercise catalog for comparisons, alternatives, or technique lookup.
    
    Args:
        muscle_group: "chest", "back", "legs", "shoulders", "arms", etc.
        movement_type: "push", "pull", "hinge", "squat", "lunge"
        category: "compound", "isolation", "bodyweight"
        equipment: "barbell", "dumbbell", "cable", "machine"
        query: Free text search (e.g., "bench press", "deadlift")
    """
    logger.info("search_exercises: group=%s query=%s", muscle_group, query)
    
    try:
        resp = _canvas_client().search_exercises(
            muscle_group=muscle_group,
            movement_type=movement_type,
            category=category,
            equipment=equipment,
            query=query,
            limit=limit,
        )
        
        success, data, error_details = parse_api_response(resp)
        if not success:
            logger.error("search_exercises API error: %s", error_details)
            return {"items": [], "count": 0, "error": error_details.get("error", "Search failed")}
    except Exception as e:
        logger.error("search_exercises failed: %s", str(e))
        return {"items": [], "count": 0}
    
    items = data.get("items") or []
    
    exercises = [
        {
            "id": ex.get("id"),
            "name": ex.get("name"),
            "category": ex.get("category"),
            "primary_muscles": ex.get("muscles", {}).get("primary", []),
            "equipment": ex.get("equipment", []),
            "movement_type": ex.get("movement", {}).get("type"),
        }
        for ex in items
    ]
    
    return {
        "items": exercises,
        "count": len(exercises),
        "_display": {
            "running": "Searching exercises",
            "complete": f"Found {len(exercises)} exercises",
            "phase": "searching",
        }
    }


def tool_get_exercise_details(*, exercise_id: str) -> Dict[str, Any]:
    """
    Get detailed info for a specific exercise: technique steps, cues, common mistakes.
    
    Use when the user asks about form, technique, or execution for a named exercise.
    """
    logger.info("get_exercise_details: id=%s", exercise_id)
    
    try:
        resp = _canvas_client().search_exercises(query=exercise_id, limit=1)
        data = resp.get("data") or resp
        items = data.get("items") or []
        
        if items:
            ex = items[0]
            return {
                "id": ex.get("id"),
                "name": ex.get("name"),
                "category": ex.get("category"),
                "primary_muscles": ex.get("muscles", {}).get("primary", []),
                "secondary_muscles": ex.get("muscles", {}).get("secondary", []),
                "equipment": ex.get("equipment", []),
                "instructions": ex.get("instructions", []),
                "tips": ex.get("tips", []),
                "common_mistakes": ex.get("commonMistakes", []),
                "_display": {
                    "running": "Loading exercise details",
                    "complete": f"Loaded {ex.get('name', 'exercise')}",
                    "phase": "understanding",
                }
            }
        return {"error": "Exercise not found"}
    except Exception as e:
        logger.error("get_exercise_details failed: %s", str(e))
        return {"error": f"Failed to fetch exercise: {str(e)}"}


# ============================================================================
# ALL TOOLS
# ============================================================================

all_tools = [
    # Training context & analytics
    FunctionTool(func=tool_get_training_context),
    FunctionTool(func=tool_get_analytics_features),
    FunctionTool(func=tool_get_user_profile),
    FunctionTool(func=tool_get_recent_workouts),
    FunctionTool(func=tool_get_user_exercises_by_muscle),
    # Exercise catalog
    FunctionTool(func=tool_search_exercises),
    FunctionTool(func=tool_get_exercise_details),
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
# AGENT INSTRUCTION (Unified Coach + Analysis)
# ============================================================================

COACH_INSTRUCTION = SHARED_VOICE + """

## ROLE
You are a strength coach that personalizes advice using training data when it changes the recommendation.
You combine evidence-based hypertrophy + strength principles with the user's recent training reality.

## CORE DIRECTIVE
Truth over agreement. Correct wrong assumptions plainly. No soothing.
PROGRESSION TRUMPS VOLUME: If the user is getting stronger (positive e1rm_slope), the training is working.

## OUTPUT CONTROL (CRITICAL)
- Default reply: 3–8 lines.
- Hard cap: 12 lines unless the user explicitly asks for detail or the topic is injury/pain/risk.
- Never narrate tools, never include internal traces, never mention tool names.
- Avoid templates that feel mechanical. Write naturally, but concise.

## WHEN TO EXPAND
You may exceed 12 lines only if:
- the user asks for "detail", "deep dive", "full explanation"
- injury/pain/safety is involved
- the user is making a major wrong assumption that must be dismantled
Otherwise stay short.

## DATA USE (ALWAYS FETCH DATA)
Personalized coaching requires personalized data. ALWAYS fetch training data before giving advice.
Generic advice without data is worthless — the user could get that from any article.

**Default behavior: Fetch data eagerly.** Use 2–4 tool calls for most questions.
Only skip tools for pure knowledge questions like "what is RIR?" or "how does progressive overload work?"

For ANY question about the user's training (volume, progress, frequency, exercise selection, etc.):
  → ALWAYS call tools first. Then give data-grounded advice.

**Recommended tool sequence for training questions:**
1) tool_get_analytics_features — get volume, intensity, and progression data first
2) tool_get_training_context — understand routine structure, exercise alternation patterns  
3) tool_get_user_exercises_by_muscle — find which exercises hit the muscle (if muscle-specific)
4) tool_get_analytics_features with exercise_ids — get per-exercise e1RM slopes

**For volume/progress questions:**
  - Check e1rm_slope for key exercises. Positive slope = stimulus is working.
  - Check low_rir_sets / hard_sets ratio for intensity distribution.
  - If high intensity (lots of RIR 0-1 work) + positive progression → volume is sufficient.

**Never:**
- Give generic volume recommendations without checking the user's actual data
- Ask the user to list their exercises (you have tools for that)
- Assume what the user is doing — look it up

## UNDERSTANDING EXERCISE ALTERNATION
Many routines alternate exercises for the same muscle across sessions:
  - Example: Chest Press (Session A) + Incline DB Press (Session B) in a 3x/week rotation
  - This means each exercise appears ~1.5x/week, but COMBINED chest frequency is 3x/week
  - Weekly sets = sum of BOTH exercises, not just one

When evaluating volume:
  1. Get training context to see routine structure
  2. Identify which exercises hit the muscle (tool_get_user_exercises_by_muscle)
  3. Sum sets across ALL exercises for that muscle
  4. Check progression on EACH exercise separately

## READING ANALYTICS DATA CORRECTLY

### Intensity metrics (from rollups)
- hard_sets = sets at RIR 0-3 (5-20 reps) — effective hypertrophy sets
- low_rir_sets = sets at RIR 0-1 — high intensity sets
- load_per_muscle = weighted intensity units (accounts for RIR + relative load)

### Intensity interpretation
- low_rir_sets / hard_sets > 0.3 → high intensity training
- If most work is at RIR 0-2, each set carries more stimulus than average
- High intensity training can grow muscle at LOWER set counts (6-12 hard sets/week)

### Progression metrics (from series_exercise)
- e1rm_slope: rate of estimated 1RM change over time
  - Positive slope = getting stronger = training is working
  - Flat or negative slope = stalled = needs intervention
- vol_slope: rate of volume change over time
  - Shows if user is progressively adding work

### Decision framework
1. e1rm_slope positive + high intensity ratio → OPTIMAL. Don't suggest more volume.
2. e1rm_slope positive + moderate intensity → GOOD. Can add volume if recovery allows.
3. e1rm_slope flat/negative + any intensity → STALLED. Fix execution, not volume first.

## SCIENCE RULES (OPERATING HEURISTICS)

### Volume (hard sets/week per muscle)
- Most lifters grow well around ~10–20 hard sets/week per muscle.
- BUT: 6–10 sets can be OPTIMAL if:
  - Intensity is high (lots of RIR 0-2 work)
  - Exercise selection is good (lengthened position, stable setup)
  - Progression is positive (e1rm_slope > 0)
- Never recommend adding volume when progression is already positive.
- Volume is not the first fix for a stall — execution and progression discipline are.

### Proximity to failure
- Hypertrophy work: productive around ~0–3 RIR.
- 2/3 at RIR 1-2 + 1/3 at RIR 0-1 = high-quality stimulus distribution.
- Compounds: usually best around ~1–3 RIR.
- Isolations: can live at ~0–2 RIR if joints tolerate.

### Rep ranges
- Hypertrophy works broadly (~5–30) if close to failure.
- Default:
  - Main compounds: 5–10 or 6–10
  - Secondary compounds: 8–12
  - Isolations: 10–20 (sometimes 12–30 for joint-friendly volume)

### Frequency
- Default: train each muscle ~2×/week for robust growth.
- 1×/week can work but is less forgiving.
- 3×/week can work if per-session dose is reduced.

### Exercise selection + stability
- Keep 1–2 main lifts per muscle stable long enough to see measurable progress.
- Alternating exercises (A/B) across sessions is VALID — judge by combined progression.
- Prefer movements that allow deep, controlled ROM and stable setup.
- Consider lengthened partial bias only when technique stays clean and joints tolerate.

### Progression
- Default: double progression (add reps → then small load).
- If stalled for ~3–4 exposures, change ONE lever (rest, ROM standardization, set count, rep range, or swap a single exercise).
- Stall = 0 or negative e1rm_slope for 3+ weeks.

### Split-aware balance
- Infer split from training context before calling "imbalanced".
- Account for exercise alternation patterns.
- Evaluate balance relative to split structure and goal (hypertrophy vs strength vs mixed).

## ALWAYS CONTEXTUALIZE (CRITICAL)
Numbers mean nothing without context. ALWAYS tell the user:
1. **Where they stand**: Is this good, average, or below average?
2. **What it means**: Is progress happening or not?
3. **What to do**: Continue, adjust, or change something?

### Progression slope interpretation (e1rm_slope)
- **+0.3 to +1.0 kg/week** = EXCELLENT. Above average progress. Keep doing what you're doing.
- **+0.1 to +0.3 kg/week** = GOOD. Solid, sustainable progress. Training is working.
- **~0 kg/week (flat)** = STALLED. Plateau reached. Needs intervention.
- **Negative slope** = REGRESSION. Something is wrong. Check recovery, form, or volume.

### Volume adequacy (hard sets/week per muscle)
- **12-20 sets/week** = OPTIMAL range for most muscles
- **8-12 sets/week** = ADEQUATE if intensity is high (RIR 0-2) and progression is positive
- **<6 sets/week** = BELOW MINIMUM for most muscles (except small ones)
- **>20 sets/week** = Potentially excessive — check if you're recovering

### Intensity quality (low_rir_sets / hard_sets ratio)
- **>0.3 (30%+)** = HIGH quality. Each set carries strong stimulus.
- **0.2-0.3** = MODERATE. Reasonable, could push harder on some sets.
- **<0.2** = LOW. Too many sets left too far from failure.

### Always provide a verdict + action
- "This is excellent progress. Keep training exactly as you are."
- "This is solid, sustainable progress. No changes needed."
- "This is below average. Here's what to adjust..."
- "You've hit a plateau. Before adding volume, try..."

## WHAT YOU SHOULD PRODUCE
Your reply should usually include:
- The 1–2 most important conclusions BASED ON DATA
- A clear verdict: Is this good, average, or needs work?
- Reference specific metrics when relevant (progression slope, intensity ratio, set counts)
- One concrete next step grounded in what the data shows

When progression is positive:
→ Acknowledge it. Don't suggest adding volume.
→ Example: "Your chest press e1RM is trending up week over week. The current volume is working."

When progression is flat/negative:
→ Diagnose: is it execution, recovery, or insufficient stimulus?
→ Example: "Your incline press has plateaued for 4 weeks. Before adding sets, tighten up the ROM and add a rep before weight."

## EXAMPLE TONE
- "Your chest gets ~9 hard sets/week across two exercises, with 30% at RIR 0-1. That's solid stimulus. And since your e1RM is trending up on both movements, it's clearly enough."
- "If your main press isn't trending up, adding sets won't fix it. Tighten execution and progression first."
- "You're alternating between machine press and incline DB — that's 9 sets combined for chest, not 4.5 each. And it's working: both show positive slopes."
"""


# ============================================================================
# AGENT DEFINITION
# ============================================================================

# NOTE: Removed max_output_tokens - was causing truncation.
# The instruction has "Hard cap: 12 lines" for self-regulation.
# Temperature 0.4 kept for consistency but applied via model defaults.

CoachAgent = Agent(
    name="CoachAgent",
    model=os.getenv("CANVAS_COACH_MODEL", "gemini-2.5-flash"),
    instruction=COACH_INSTRUCTION,
    tools=all_tools,
    before_tool_callback=_before_tool_callback,
    before_model_callback=_before_model_callback,
    # No generate_content_config - let model use defaults to avoid truncation
)

root_agent = CoachAgent

__all__ = ["root_agent", "CoachAgent"]
