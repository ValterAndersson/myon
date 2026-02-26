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
from app.utils.weight_formatting import format_weight, get_weight_unit

logger = logging.getLogger(__name__)

# Firebase function base URL
MYON_FUNCTIONS_BASE_URL = os.getenv(
    "MYON_FUNCTIONS_BASE_URL", "https://us-central1-myon-53d85.cloudfunctions.net"
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
    endpoint: str, payload: Dict[str, Any], user_id: str, timeout: float = FAST_LANE_TIMEOUT
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
        response = requests.post(url, json=payload, headers=headers, timeout=timeout)
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
        ctx: Session context with user_id and optionally active_workout_id

    Returns:
        SkillResult with success/failure
    """
    if not ctx.user_id:
        return SkillResult(
            success=False, message="No user context available.", error="missing_user_id"
        )

    # Call Firebase completeCurrentSet function
    payload = {}
    if ctx.active_workout_id:
        payload["workout_id"] = ctx.active_workout_id

    result = _call_firebase("completeCurrentSet", payload, ctx.user_id)

    if "error" in result:
        error_detail = result.get("error", {})
        if isinstance(error_detail, dict):
            msg = error_detail.get("message", "Unknown error")
        else:
            msg = str(error_detail)
        return SkillResult(
            success=False,
            message="Failed to log set.",
            error=msg,
        )

    # ok() wraps response as {success: true, data: {...}}
    data = result.get("data", {})
    reps = data.get("reps", "?")
    weight = data.get("weight", "?")
    exercise = data.get("exercise_name", "")
    set_number = data.get("set_number", 0)
    total_sets = data.get("total_sets", 0)

    return SkillResult(
        success=True,
        message=f"Set logged: {exercise} — set {set_number}/{total_sets}",
        data={
            "exercise": exercise,
            "reps": reps,
            "weight": weight,
            "set_number": set_number,
            "total_sets": total_sets,
        },
    )


def log_set_shorthand(
    ctx: SessionContext, reps: int, weight: float, unit: str = "kg"
) -> SkillResult:
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
            success=False, message="No user context available.", error="missing_user_id"
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
        ctx.user_id,
    )

    if "error" in result:
        return SkillResult(
            success=False,
            message="Failed to log set.",
            error=result.get("message", "Unknown error"),
        )

    # Format confirmation in user's preferred unit
    user_unit = get_weight_unit()
    weight_str = format_weight(weight_kg, user_unit)

    return SkillResult(
        success=True,
        message=f"Set logged: {reps} reps @ {weight_str}",
        data={
            "reps": reps,
            "weight": weight,
            "unit": unit,
            "weight_kg": weight_kg,
        },
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
            success=False, message="No user context available.", error="missing_user_id"
        )

    # Call Firebase getActiveWorkout to get current state
    result = _call_firebase("getActiveWorkout", {}, ctx.user_id)

    if "error" in result:
        return SkillResult(
            success=False,
            message="No active workout found.",
            error=result.get("message", "Unknown error"),
        )

    # ok() wraps as {success, data: {success, workout: {...}}}
    resp_data = result.get("data", {})
    workout = resp_data.get("workout", {})
    exercises = workout.get("exercises", [])
    for ex in exercises:
        for s in ex.get("sets") or []:
            if s.get("status") == "planned":
                weight_val = s.get("weight")
                weight_str = format_weight(weight_val, get_weight_unit()) if weight_val else "?"
                return SkillResult(
                    success=True,
                    message=(
                        f"Next: {ex.get('name','?')} — "
                        f"{s.get('reps','?')} reps @ {weight_str}"
                    ),
                    data={
                        "exercise": ex.get("name", "Unknown"),
                        "target_reps": s.get("reps", "?"),
                        "target_weight": s.get("weight", "?"),
                        "set_number": (ex.get("sets") or []).index(s) + 1,
                        "total_sets": len(ex.get("sets") or []),
                    },
                )
    return SkillResult(success=True, message="All sets completed!", data={})


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
        return SkillResult(success=True, message="Ready. No active workout.", data={})

    return SkillResult(success=True, message=f"Ready. {next_result.message}", data=next_result.data)


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
    match = re.match(r"^(\d+)\s*@\s*(\d+(?:\.\d+)?)\s*(kg|lbs?)?$", message.strip(), re.I)
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
