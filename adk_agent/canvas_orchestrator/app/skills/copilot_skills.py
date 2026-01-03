"""
Copilot Skills - Fast Lane operations for live workout execution.

These skills are called directly by the Fast Lane router, bypassing the LLM entirely.
Target latency: <500ms end-to-end.

Skills:
- log_set: Log a completed set to the active workout
- log_set_shorthand: Parse and log "8 @ 100" format
- get_next_set: Get the next set target
- acknowledge_rest: Acknowledge rest period

All skills call Firebase functions directly via HTTP.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests

from app.shell.context import SessionContext

logger = logging.getLogger(__name__)

# Firebase function base URL
MYON_FUNCTIONS_BASE_URL = os.getenv(
    "MYON_FUNCTIONS_BASE_URL", 
    "https://us-central1-myon-53d85.cloudfunctions.net"
)
FIREBASE_API_KEY = os.getenv("FIREBASE_API_KEY", "myon-agent-key-2024")

# Request timeout for fast lane (aggressive)
FAST_LANE_TIMEOUT = 2.0  # seconds


@dataclass
class SkillResult:
    """Result from a skill execution."""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "success": self.success,
            "message": self.message,
        }
        if self.data:
            result["data"] = self.data
        if self.error:
            result["error"] = self.error
        return result


def _call_firebase(
    endpoint: str, 
    payload: Dict[str, Any],
    user_id: str,
    timeout: float = FAST_LANE_TIMEOUT
) -> Dict[str, Any]:
    """
    Call a Firebase function.
    
    Args:
        endpoint: Function endpoint (e.g., "logSet")
        payload: Request body
        user_id: User ID for auth
        timeout: Request timeout in seconds
        
    Returns:
        Response data or error dict
    """
    url = f"{MYON_FUNCTIONS_BASE_URL}/{endpoint}"
    headers = {
        "Content-Type": "application/json",
        "x-api-key": FIREBASE_API_KEY,
        "x-user-id": user_id,
    }
    
    try:
        response = requests.post(
            url, 
            json=payload, 
            headers=headers, 
            timeout=timeout
        )
        response.raise_for_status()
        return response.json()
    except requests.Timeout:
        logger.warning("Firebase call timed out: %s", endpoint)
        return {"error": "timeout", "message": "Request timed out"}
    except requests.RequestException as e:
        logger.error("Firebase call failed: %s - %s", endpoint, e)
        return {"error": "request_failed", "message": str(e)}


def log_set(ctx: SessionContext) -> SkillResult:
    """
    Log the current set as completed.
    
    This is the simplest fast lane operation - just marks the current set done.
    The active workout state is managed by Firebase.
    
    Args:
        ctx: Session context with user_id
        
    Returns:
        SkillResult with success/failure
    """
    if not ctx.user_id:
        return SkillResult(
            success=False,
            message="No user context available.",
            error="missing_user_id"
        )
    
    # Call Firebase logSet function
    result = _call_firebase(
        "logSet",
        {"action": "complete_current"},
        ctx.user_id
    )
    
    if "error" in result:
        return SkillResult(
            success=False,
            message="Failed to log set.",
            error=result.get("message", "Unknown error")
        )
    
    # Extract set details from response
    set_data = result.get("set", {})
    reps = set_data.get("reps", "?")
    weight = set_data.get("weight", "?")
    exercise = result.get("exercise", "")
    
    return SkillResult(
        success=True,
        message=f"Set logged: {reps} reps @ {weight}kg",
        data={
            "exercise": exercise,
            "reps": reps,
            "weight": weight,
            "sets_remaining": result.get("sets_remaining", 0),
        }
    )


def log_set_shorthand(ctx: SessionContext, reps: int, weight: float, unit: str = "kg") -> SkillResult:
    """
    Log a set with explicit reps and weight.
    
    Parses shorthand like "8 @ 100" or "8@100kg".
    
    Args:
        ctx: Session context
        reps: Number of reps
        weight: Weight in specified unit
        unit: Weight unit (kg or lbs)
        
    Returns:
        SkillResult with set details
    """
    if not ctx.user_id:
        return SkillResult(
            success=False,
            message="No user context available.",
            error="missing_user_id"
        )
    
    # Convert lbs to kg if needed
    weight_kg = weight
    if unit.lower() in ("lb", "lbs"):
        weight_kg = weight * 0.453592
    
    # Call Firebase logSet with explicit values
    result = _call_firebase(
        "logSet",
        {
            "action": "log_explicit",
            "reps": reps,
            "weight": weight_kg,
        },
        ctx.user_id
    )
    
    if "error" in result:
        return SkillResult(
            success=False,
            message="Failed to log set.",
            error=result.get("message", "Unknown error")
        )
    
    return SkillResult(
        success=True,
        message=f"Set logged: {reps} reps @ {weight}{unit}",
        data={
            "reps": reps,
            "weight": weight,
            "unit": unit,
            "weight_kg": weight_kg,
        }
    )


def get_next_set(ctx: SessionContext) -> SkillResult:
    """
    Get the next set target from the active workout.
    
    Args:
        ctx: Session context
        
    Returns:
        SkillResult with next set details
    """
    if not ctx.user_id:
        return SkillResult(
            success=False,
            message="No user context available.",
            error="missing_user_id"
        )
    
    # Call Firebase getActiveWorkout to get current state
    result = _call_firebase(
        "getActiveWorkout",
        {},
        ctx.user_id
    )
    
    if "error" in result:
        return SkillResult(
            success=False,
            message="No active workout found.",
            error=result.get("message", "Unknown error")
        )
    
    # Extract next set from active workout
    workout = result.get("workout", {})
    current_exercise = workout.get("currentExercise", {})
    next_set = current_exercise.get("nextSet", {})
    
    exercise_name = current_exercise.get("name", "Unknown")
    target_reps = next_set.get("targetReps", "?")
    target_weight = next_set.get("targetWeight", "?")
    set_number = next_set.get("setNumber", 1)
    total_sets = current_exercise.get("totalSets", "?")
    
    return SkillResult(
        success=True,
        message=f"Next: {exercise_name} — {target_reps} reps @ {target_weight}kg (Set {set_number}/{total_sets})",
        data={
            "exercise": exercise_name,
            "target_reps": target_reps,
            "target_weight": target_weight,
            "set_number": set_number,
            "total_sets": total_sets,
        }
    )


def acknowledge_rest(ctx: SessionContext) -> SkillResult:
    """
    Acknowledge rest period and prepare for next set.
    
    This is essentially a no-op that confirms the user is ready.
    
    Args:
        ctx: Session context
        
    Returns:
        SkillResult with ready confirmation
    """
    # Get next set info to return
    next_result = get_next_set(ctx)
    
    if not next_result.success:
        return SkillResult(
            success=True,
            message="Ready. No active workout.",
            data={}
        )
    
    return SkillResult(
        success=True,
        message=f"Ready. {next_result.message}",
        data=next_result.data
    )


def parse_shorthand(message: str) -> Optional[Dict[str, Any]]:
    """
    Parse shorthand set notation.
    
    Formats:
    - "8 @ 100" -> {reps: 8, weight: 100, unit: "kg"}
    - "8@100kg" -> {reps: 8, weight: 100, unit: "kg"}
    - "8@100lbs" -> {reps: 8, weight: 100, unit: "lbs"}
    
    Args:
        message: User message to parse
        
    Returns:
        Parsed values or None if no match
    """
    match = re.match(
        r"^(\d+)\s*@\s*(\d+(?:\.\d+)?)\s*(kg|lbs?)?$", 
        message.strip(), 
        re.I
    )
    if match:
        return {
            "reps": int(match.group(1)),
            "weight": float(match.group(2)),
            "unit": match.group(3) or "kg",
        }
    return None


__all__ = [
    "SkillResult",
    "log_set",
    "log_set_shorthand",
    "get_next_set",
    "acknowledge_rest",
    "parse_shorthand",
]
