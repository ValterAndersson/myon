"""
Analysis Agent - Progress analysis and evidence-based recommendations.

Part of the multi-agent architecture. This agent:
- Fetches training data and analytics aggregates
- Transforms data into standardized metrics for progress and lag detection
- Publishes analysis artifacts to the canvas in the analysis lane
- Recommends changes with explicit evidence and tradeoffs

Permission boundary: Can read all data, can write analysis artifacts only.
Cannot: Create workout/routine drafts, modify active workouts.
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from datetime import datetime
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

# Global context for the current request
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
# DATA SUFFICIENCY CONSTANTS
# ============================================================================

MIN_WEEKS_FOR_SLOPE = 4  # Minimum weeks before computing trend slopes
MIN_DATA_POINTS_FOR_RANKING = 3  # Minimum data points to rank muscles/exercises
DEFAULT_ANALYSIS_WEEKS = 8  # Default analysis window


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
    
    Returns weekly rollups, muscle series, and exercise series with computed metrics.
    Use this FIRST to gather data before generating analysis.
    
    Args:
        user_id: User ID (auto-resolved from context if not provided)
        weeks: Number of weeks to analyze (default 8, range 1-52)
        exercise_ids: Optional list of exercise IDs for per-exercise trends
        muscles: Optional list of muscle names for per-muscle volume tracking
    
    Returns:
        {
            "rollups": Weekly aggregates with intensity and fatigue metrics,
            "series_muscle": Per-muscle weekly volume series,
            "series_exercise": Per-exercise daily e1RM and volume with slopes,
            "data_quality": Assessment of data sufficiency,
            "computed_metrics": Derived signals for analysis
        }
    """
    uid = _resolve(user_id, "user_id")
    if not uid:
        return {"error": "No user_id available"}
    
    # Clamp weeks to valid range
    weeks = max(1, min(52, weeks))
    
    logger.info("get_analytics_features uid=%s weeks=%d exercises=%s muscles=%s",
                uid, weeks, len(exercise_ids or []), len(muscles or []))
    
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
    
    # Process response and add computed metrics
    rollups = resp.get("rollups") or []
    series_muscle = resp.get("series_muscle") or {}
    series_exercise = resp.get("series_exercise") or {}
    
    # Compute data quality assessment
    weeks_with_data = len([r for r in rollups if (r.get("workouts") or r.get("cadence", {}).get("sessions") or 0) > 0])
    total_workouts = sum(r.get("workouts") or r.get("cadence", {}).get("sessions") or 0 for r in rollups)
    
    if weeks_with_data >= 8:
        confidence = "high"
    elif weeks_with_data >= 4:
        confidence = "medium"
    else:
        confidence = "low"
    
    # Build caveats for data quality issues
    caveats = []
    if weeks_with_data < MIN_WEEKS_FOR_SLOPE:
        caveats.append(f"Only {weeks_with_data} weeks of data (minimum {MIN_WEEKS_FOR_SLOPE} for trend analysis)")
    elif len(rollups) > 0 and weeks_with_data < len(rollups) * 0.7:
        # More than 30% of weeks have zero workouts
        gap_count = len(rollups) - weeks_with_data
        caveats.append(f"{gap_count} weeks with no workouts in analysis window")
    if total_workouts < 8:
        caveats.append(f"Limited workout history ({total_workouts} workouts)")
    
    data_quality = {
        "weeks_requested": weeks,
        "weeks_with_data": weeks_with_data,
        "total_workouts": total_workouts,
        "confidence": confidence,
        "sufficient_for_slopes": weeks_with_data >= MIN_WEEKS_FOR_SLOPE,
        "caveats": caveats,
    }
    
    # Compute derived metrics from rollups
    computed_metrics = _compute_analysis_metrics(rollups, series_muscle, series_exercise)
    
    return {
        "rollups": rollups,
        "series_muscle": series_muscle,
        "series_exercise": series_exercise,
        "data_quality": data_quality,
        "computed_metrics": computed_metrics,
    }


def _compute_analysis_metrics(
    rollups: List[Dict[str, Any]],
    series_muscle: Dict[str, Any],
    series_exercise: Dict[str, Any],
) -> Dict[str, Any]:
    """Compute derived metrics for analysis."""
    metrics: Dict[str, Any] = {
        "volume_trends": {},
        "muscle_rankings": [],
        "exercise_movers": [],
        "consistency": {},
    }
    
    if not rollups:
        return metrics
    
    # Sort rollups by week (oldest first for trend calculation)
    sorted_rollups = sorted(rollups, key=lambda r: r.get("id") or "")
    
    # Volume trend (total sets over time)
    total_sets_series = [r.get("total_sets") or 0 for r in sorted_rollups]
    if len(total_sets_series) >= MIN_WEEKS_FOR_SLOPE:
        slope = _simple_slope(total_sets_series)
        trend = "improving" if slope > 0.5 else ("declining" if slope < -0.5 else "stable")
        metrics["volume_trends"]["total_sets"] = {
            "slope": round(slope, 2),
            "trend": trend,
            "first": total_sets_series[0],
            "last": total_sets_series[-1],
        }
    
    # Muscle group rankings by total load
    muscle_loads: Dict[str, float] = {}
    for rollup in sorted_rollups:
        intensity = rollup.get("intensity") or {}
        for muscle, load in (intensity.get("load_per_muscle_group") or {}).items():
            muscle_loads[muscle] = muscle_loads.get(muscle, 0) + (load or 0)
    
    if muscle_loads:
        sorted_muscles = sorted(muscle_loads.items(), key=lambda x: (-x[1], x[0]))
        metrics["muscle_rankings"] = [
            {"muscle": m, "total_load": round(l, 1), "rank": i + 1}
            for i, (m, l) in enumerate(sorted_muscles[:10])
        ]
    
    # Exercise movers (from series_exercise slopes)
    movers = []
    for ex_id, data in series_exercise.items():
        if isinstance(data, dict) and "e1rm_slope" in data:
            slope = data.get("e1rm_slope") or 0
            data_points = data.get("data_points") or data.get("count") or 0
            
            # Gate on minimum data points for reliable ranking
            if data_points < MIN_DATA_POINTS_FOR_RANKING:
                continue
                
            if abs(slope) > 0.1:  # Only include meaningful changes
                movers.append({
                    "exercise_id": ex_id,
                    "e1rm_slope": round(slope, 2),
                    "vol_slope": round(data.get("vol_slope") or 0, 2),
                    "direction": "up" if slope > 0 else "down",
                    "data_points": data_points,
                })
    
    # Sort with stable tie-breakers: slope magnitude → data points → alphabetical ID
    movers.sort(key=lambda x: (-abs(x["e1rm_slope"]), -x.get("data_points", 0), x["exercise_id"]))
    metrics["exercise_movers"] = movers[:10]
    
    # Consistency metrics
    workout_counts = [r.get("workouts") or r.get("cadence", {}).get("sessions") or 0 for r in sorted_rollups]
    if workout_counts:
        avg_workouts = sum(workout_counts) / len(workout_counts)
        variance = sum((x - avg_workouts) ** 2 for x in workout_counts) / len(workout_counts)
        metrics["consistency"] = {
            "avg_workouts_per_week": round(avg_workouts, 1),
            "variance": round(variance, 2),
            "is_consistent": variance < 2.0,
        }
    
    return metrics


def _simple_slope(values: List[float]) -> float:
    """Calculate simple linear slope of a series."""
    if len(values) < 2:
        return 0.0
    return (values[-1] - values[0]) / (len(values) - 1)


def _is_visualization_data_empty(chart_type: str, data: Dict[str, Any]) -> bool:
    """Check if visualization data is empty (for graceful iOS empty_state rendering)."""
    if not data:
        return True
    
    if chart_type == "line":
        # Line chart needs series with data points
        series = data.get("series") or []
        return not series or all(
            not (s.get("values") or s.get("data_points") or []) for s in series
        )
    elif chart_type == "bar":
        # Bar chart needs categories and values
        categories = data.get("categories") or data.get("labels") or []
        values = data.get("values") or data.get("series") or []
        return not categories or not values
    elif chart_type == "table":
        # Table needs rows
        rows = data.get("rows") or []
        return not rows
    
    return False


# ============================================================================
# TOOLS: User Context (Read-only)
# ============================================================================

def tool_get_user_profile(*, user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Get the user's fitness profile including goals, experience level, and preferences.
    Use this to understand context for recommendations.
    """
    uid = _resolve(user_id, "user_id")
    if not uid:
        return {"error": "No user_id available"}
    
    logger.info("get_user_profile uid=%s", uid)
    resp = _canvas_client().get_user(uid)
    return resp.get("data") or resp.get("context") or {}


def tool_get_recent_workouts(*, user_id: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Get the user's recent workout sessions with exercise details.
    Use for detailed inspection of specific workout patterns.
    """
    uid = _resolve(user_id, "user_id")
    if not uid:
        return []
    
    # Analysis agent gets extended limit
    limit = max(5, min(50, limit))
    
    logger.info("get_recent_workouts uid=%s limit=%s", uid, limit)
    resp = _canvas_client().get_user_workouts(uid, limit=limit)
    return resp.get("data") or resp.get("workouts") or []


# ============================================================================
# TOOLS: Analysis Artifact Publishing
# ============================================================================

def tool_propose_analysis_group(
    *,
    headline: str,
    insights: List[Dict[str, Any]],
    recommendations: List[Dict[str, Any]],
    data_quality: Dict[str, Any],
    period_weeks: int = 8,
    visualizations: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Publish a complete analysis to the canvas: summary card + optional visualizations.
    
    This is the primary output tool. Use after gathering data with tool_get_analytics_features.
    
    Args:
        headline: Primary summary statement (e.g., "Strong upper body progress, back lagging")
        insights: List of insight objects, each with:
            - category: "progressive_overload" | "volume" | "frequency" | "laggard" | "consistency" | "goal_alignment"
            - signal: Human-readable insight text
            - trend: "improving" | "stable" | "declining" | "insufficient_data"
            - metric_key: Optional reference to the metric
            - value: Optional numeric value
            - confidence: Optional "high" | "medium" | "low"
        recommendations: List of recommendation objects, each with:
            - priority: 1-5 (1 = highest)
            - action: Actionable change description
            - rationale: Evidence-based reason
            - category: Optional "volume" | "frequency" | "exercise_selection" | "progression" | "recovery"
        data_quality: Data quality assessment from tool_get_analytics_features
        period_weeks: Analysis period in weeks
        visualizations: Optional list of visualization specs (max 3), each with:
            - chart_type: "line" | "bar" | "table"
            - title: Chart title
            - data: Chart data payload (see visualization schema)
    
    Returns:
        Confirmation that analysis was published to canvas.
    """
    cid = _context.get("canvas_id")
    uid = _context.get("user_id")
    corr = _context.get("correlation_id")
    
    if not cid or not uid:
        return {"error": "Missing canvas_id or user_id - context not set"}
    
    if not insights:
        return {"error": "At least one insight is required"}
    
    if not recommendations:
        return {"error": "At least one recommendation is required"}
    
    # Build analysis_summary card
    now = datetime.utcnow()
    summary_card = {
        "type": "analysis_summary",
        "lane": "analysis",
        "priority": 95,
        "content": {
            "headline": headline,
            "period": {
                "weeks": period_weeks,
                "end": now.strftime("%Y-%m-%d"),
            },
            "insights": insights[:10],  # Max 10 insights
            "recommendations": recommendations[:5],  # Max 5 recommendations
            "data_quality": {
                "weeks_with_data": data_quality.get("weeks_with_data", 0),
                "workouts_analyzed": data_quality.get("total_workouts", 0),
                "confidence": data_quality.get("confidence", "low"),
                "caveats": data_quality.get("caveats", []),
            },
        },
        "actions": [
            {"kind": "apply_recommendations", "label": "Apply to Plan", "style": "primary", "iconSystemName": "wand.and.stars"},
            {"kind": "dismiss", "label": "Dismiss", "style": "ghost", "iconSystemName": "xmark"},
        ],
    }
    
    # Build visualization cards (max 3)
    cards = [summary_card]
    vis_cards = (visualizations or [])[:3]
    
    for vis in vis_cards:
        if not isinstance(vis, dict):
            continue
        
        chart_type = vis.get("chart_type")
        title = vis.get("title")
        
        if not chart_type or not title:
            continue
        
        vis_data = vis.get("data", {})
        
        # Check if data is empty and add empty_state for graceful iOS rendering
        is_empty = _is_visualization_data_empty(chart_type, vis_data)
        
        vis_card = {
            "type": "visualization",
            "lane": "analysis",
            "priority": 80,
            "content": {
                "chart_type": chart_type,
                "title": title,
                "subtitle": vis.get("subtitle"),
                "data": vis_data,
                "annotations": vis.get("annotations", []),
                "metric_key": vis.get("metric_key"),
            },
        }
        
        # Add empty_state when data is insufficient
        if is_empty:
            vis_card["content"]["empty_state"] = {
                "message": vis.get("empty_message", "Insufficient data to display this chart")
            }
        
        cards.append(vis_card)
    
    logger.info("🎯 PROPOSE_ANALYSIS_GROUP: canvas=%s insights=%d recs=%d vis=%d",
                cid, len(insights), len(recommendations), len(vis_cards))
    
    try:
        resp = _canvas_client().propose_cards(
            canvas_id=cid,
            cards=cards,
            user_id=uid,
            correlation_id=corr,
        )
        
        is_success = resp.get("success", False)
        created_ids = resp.get("data", {}).get("created_card_ids") or resp.get("created_card_ids") or []
        
        if not is_success:
            error_msg = resp.get("error", {}).get("message") if isinstance(resp.get("error"), dict) else str(resp.get("error", "Unknown error"))
            logger.error("❌ PROPOSE_ANALYSIS_GROUP REJECTED: %s", error_msg)
            return {"error": f"Backend rejected analysis: {error_msg}"}
        
        logger.info("✅ PROPOSE_ANALYSIS_GROUP SUCCESS: cards=%d", len(cards))
        
    except Exception as e:
        logger.error("❌ PROPOSE_ANALYSIS_GROUP FAILED: %s", str(e))
        return {"error": f"Failed to publish analysis: {str(e)}"}
    
    # Emit telemetry
    try:
        _canvas_client().emit_event(
            user_id=uid,
            canvas_id=cid,
            event_type="analyze_progress",
            payload={
                "task": "analyze_progress",
                "status": "published",
                "insight_count": len(insights),
                "recommendation_count": len(recommendations),
                "visualization_count": len(vis_cards),
            },
            correlation_id=corr,
        )
    except Exception as e:
        logger.warning("⚠️ PROPOSE_ANALYSIS_GROUP telemetry failed: %s", str(e))
    
    return {
        "status": "published",
        "message": f"Analysis published with {len(insights)} insights, {len(recommendations)} recommendations, {len(vis_cards)} charts",
        "card_ids": created_ids,
    }


# ============================================================================
# ALL TOOLS
# ============================================================================

all_tools = [
    # Analytics data
    FunctionTool(func=tool_get_analytics_features),
    # User context (read-only)
    FunctionTool(func=tool_get_user_profile),
    FunctionTool(func=tool_get_recent_workouts),
    # Analysis publishing
    FunctionTool(func=tool_propose_analysis_group),
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
You are the Analysis Agent. You analyze training data and produce evidence-based progress diagnostics and recommendations. Your output is canvas artifacts, not chat.

## CANVAS PRINCIPLE
- The analysis card is your output. Chat text is only a control surface.
- Publish structured insights and recommendations as artifacts.
- No chatty narration, no speculative physiology, no tool failure prose.

## PERMISSION BOUNDARIES (ENFORCED)
- You CAN read workout history, progression data, templates, routines
- You CAN write analysis artifacts (analysis_summary, visualization cards)
- You CANNOT create workout or routine drafts (that's Planner's job)
- You CANNOT modify active workouts (that's Copilot's job)

## ANALYSIS FOCUS AREAS
Prioritize these signals in order:
1. **Progressive overload quality**: Are loads, reps, or e1RM proxies improving at similar volume?
2. **Laggards**: Muscles and exercises with flat or negative trends given sufficient exposure
3. **Goal alignment**: Volume and effort distribution vs stated goals (hypertrophy emphasis by muscle group)
4. **Consistency**: Adherence and training frequency trends that explain stalled progress
5. **Smallest effective intervention**: Minimal changes likely to unlock progress before major rewrites

## WORKFLOW
1. ALWAYS start by calling tool_get_analytics_features to fetch data
2. Optionally call tool_get_user_profile for goal context
3. Analyze the data: identify what's improving, stalling, undertrained
4. Generate 2-5 recommendations, each tied to specific signals
5. Call tool_propose_analysis_group with your findings
6. Output one short control sentence confirming publication

## DATA SUFFICIENCY RULES
- Use fixed default window (8 weeks) unless user specifies otherwise
- Require minimum 4 weeks of data before computing trend slopes
- If data is insufficient, explicitly state this in data_quality.caveats
- Rank with stable tie-breakers: magnitude, then exposure, then recency, then alphabetical

## INSIGHT CATEGORIES
Each insight must have one of these categories:
- progressive_overload: Load/rep/e1RM improvement signals
- volume: Weekly set volume patterns
- frequency: Training frequency and session distribution
- laggard: Muscles/exercises with flat or negative trends
- consistency: Adherence patterns
- goal_alignment: Volume distribution vs stated goals

## RECOMMENDATION FORMAT
Each recommendation must be actionable:
- Increase or reallocate weekly sets for a muscle group
- Adjust frequency distribution across days
- Change a progression rule for a stalled lift
- Swap an exercise variant when evidence suggests mismatch

## VISUALIZATION SELECTION
You may include up to 3 visualizations. Select based on data shape:
- **Line chart**: Time series (e1RM trends, weekly volume, workout frequency)
- **Bar chart**: Comparisons (current vs baseline, muscle group distribution)
- **Table**: Ranked lists (movers and laggards by slope)

Default is 1-2 visuals per request. Do not spam charts.

## OUTPUT RULES
1. ALWAYS call tool_get_analytics_features first
2. ALWAYS call tool_propose_analysis_group to publish results
3. After publishing, output at most 1 short sentence (e.g., "Published progress analysis with 4 insights and 2 recommendations.")
4. Never dump analysis details as chat prose - publish as artifacts
5. If data is insufficient, still publish an analysis_summary explaining the limitation
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
