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
    
    Returns weekly rollups with volume, intensity, and muscle data.
    
    Args:
        user_id: User ID (auto-resolved from context if not provided)
        weeks: Number of weeks to analyze (default 8, max 52)
        exercise_ids: Optional specific exercises to track
        muscles: Optional specific muscles to focus on
    
    Returns:
        Weekly rollups with:
        - total_sets, total_reps: Volume metrics
        - intensity: Load distribution per muscle group
        - cadence: Session frequency
        - series_muscle: Per-muscle volume over time
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
    Use this to understand context for recommendations.
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
    Get the user's recent workout sessions with exercise details.
    Use for detailed inspection of specific workout patterns.
    
    Returns workout summaries with exercises, sets, and performance.
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


# ============================================================================
# ALL TOOLS
# ============================================================================

all_tools = [
    FunctionTool(func=tool_get_analytics_features),
    FunctionTool(func=tool_get_user_profile),
    FunctionTool(func=tool_get_recent_workouts),
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
You are the Analysis Agent. You analyze training data and answer questions about the user's workout history, progress, and patterns.

## WHAT YOU DO
- Fetch training data using the available tools
- Analyze volume, frequency, intensity, and muscle distribution
- Answer questions about progress, trends, and what's being trained
- Provide evidence-based observations grounded in the data

## WHAT YOU DON'T DO
- Create workout plans (that's Planner's job)
- Modify active workouts (that's Copilot's job)
- Make up data - always fetch it first

## WORKFLOW
1. When asked about training data, ALWAYS call tool_get_analytics_features first
2. Optionally call tool_get_user_profile for goals context
3. For detailed workout inspection, use tool_get_recent_workouts
4. For exercise-specific progress (like 1RM), first get recent_workouts to find exercise IDs, then call get_analytics_features with those exercise_ids
5. Provide a clear, concise answer based on the data

## UNDERSTANDING THE DATA

When presenting metrics, use UNDERSTANDABLE terms:

| Data Field | What to say to user |
|------------|---------------------|
| hard_sets_per_muscle | "weekly sets" or "hard sets" - these are challenging sets counted per muscle |
| total_sets | "total sets performed" |
| total_weight | "total volume in kg" (weight × reps summed) |
| workouts / sessions | "workout sessions" or "training days" |
| e1rm | "estimated 1-rep max" - the predicted max weight for 1 rep |
| e1rm_slope | "strength trend" - positive means getting stronger |

NEVER say "load units" - this is an internal metric. Instead:
- For volume comparisons: use "sets" (hard_sets_per_muscle)
- For intensity: use "volume (kg)" (total_weight or weight_per_muscle_group)
- For strength progress: use "estimated 1RM" (e1rm from series_exercise)

## RESPONSE STYLE
- Be direct and specific
- Use numbers users understand: sets, kg/lbs, reps, workout count
- Explain ratios as percentages ("30% less", "about half")
- Keep responses concise (2-4 sentences typically)
- If data is limited, say so

## EXAMPLE RESPONSES

User: "Which muscles am I training the most?"
→ Fetch analytics → "Based on your last 8 weeks, you've done the most work on your chest (about 15 hard sets per week on average), followed by shoulders (12 sets) and triceps (10 sets). Your back is getting about 30% fewer sets than your chest."

User: "How consistent have I been?"
→ Fetch analytics → "You've trained an average of 3.2 times per week over the past 8 weeks. You had 6 weeks with 3+ sessions, but 2 weeks with only 1 session each."

User: "What about upper vs lower body?"
→ Fetch analytics → "Your upper body is getting about 80% of your training volume. Looking at sets: ~25 weekly sets for upper body muscles vs ~10 for lower body. You might want to add more leg work."

User: "Is my bench press improving?"
→ First get recent_workouts to find bench press exercise_id, then get analytics with that exercise_id
→ "Your bench press estimated 1RM has increased from 85kg to 92kg over the past 6 weeks - that's about 8% stronger."

User: "Push pull legs balance?"
→ Fetch analytics → "Your push muscles (chest, shoulders, triceps) are getting about 20 sets/week total. Pull muscles (back, biceps) around 15 sets. Legs only 8 sets. Push:Pull:Legs is roughly 2.5:2:1 - legs are significantly undertrained."
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
