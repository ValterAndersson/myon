"""
Progression Skills - Headless progression updates for background agents.

These skills are used by post_workout_analyst and other background agents
to apply training progression changes WITHOUT canvas cards.

Key differences from planner_skills:
- No canvas context required (headless mode)
- Changes are logged to agent_recommendations collection
- Supports auto-pilot (immediate apply) or review mode (pending approval)

All changes are audited regardless of mode for full traceability.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


def _format_weight(kg_value: float, weight_unit: str = "kg") -> str:
    """
    Format a weight value in the user's preferred unit.

    Args:
        kg_value: Weight in kilograms
        weight_unit: Target unit ("kg" or "lbs")

    Returns:
        Formatted weight string (e.g., "80kg", "175lbs")
    """
    if weight_unit == "lbs":
        lbs = kg_value * 2.20462
        # Round to nearest 5 for clean display
        rounded = round(lbs / 5) * 5
        if rounded == int(rounded):
            return f"{int(rounded)}lbs"
        return f"{rounded:.1f}lbs"
    else:
        if kg_value == int(kg_value):
            return f"{int(kg_value)}kg"
        return f"{kg_value:.1f}kg"


def _get_weight_unit() -> str:
    """
    Get cached weight unit for the current request.

    Returns "kg" if not available (headless mode, no context).

    Returns:
        Weight unit string ("kg" or "lbs")
    """
    try:
        from app.skills.workout_skills import get_weight_unit
        return get_weight_unit()
    except Exception:
        return "kg"


@dataclass
class ProgressionResult:
    """Result from a progression skill."""
    success: bool
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        if not self.success:
            return {"error": self.error or "Unknown error"}
        return dict(self.data)


def _get_base_url() -> str:
    """Get the base URL for Firebase functions."""
    return os.getenv(
        "MYON_FUNCTIONS_BASE_URL",
        "https://us-central1-myon-53d85.cloudfunctions.net"
    )


def _get_api_key() -> str:
    """Get the API key for Firebase functions."""
    return os.getenv("MYON_API_KEY", "myon-agent-key-2024")


async def apply_progression(
    user_id: str,
    target_type: str,
    target_id: str,
    changes: List[Dict[str, Any]],
    summary: str,
    rationale: Optional[str] = None,
    trigger: str = "agent",
    trigger_context: Optional[Dict[str, Any]] = None,
    auto_apply: bool = True,
) -> ProgressionResult:
    """
    Apply progression changes to a template or routine (headless mode).
    
    This is the PRIMARY tool for background agents to make training adjustments.
    All changes are logged to agent_recommendations for audit.
    
    MODES:
    - auto_apply=True (default): Changes applied immediately, logged as 'applied'
    - auto_apply=False: Changes queued for user review, logged as 'pending_review'
    
    Args:
        user_id: User ID (required)
        target_type: "template" or "routine"
        target_id: ID of the template or routine to update
        changes: List of changes to apply. Each change:
            - path: Field path (e.g., "exercises[0].sets[0].weight")
            - from: Current value
            - to: New value
            - rationale: Why this change (optional but recommended)
        summary: Human-readable summary of changes (e.g., "Increase Bench Press weight from 80kg to 82.5kg")
        rationale: Full explanation for the change
        trigger: What triggered this change:
            - "post_workout" - After workout completion analysis
            - "scheduled" - Scheduled progression check
            - "plateau_detected" - Auto-detected plateau
            - "user_request" - User asked for adjustment
        trigger_context: Additional context about the trigger
        auto_apply: If True, apply immediately; if False, queue for user review
        
    Returns:
        ProgressionResult with recommendation_id and applied status
        
    Example:
        # Post-workout weight increase
        result = await apply_progression(
            user_id="user123",
            target_type="template",
            target_id="push-template-abc",
            changes=[
                {
                    "path": "exercises[0].sets[0].weight",
                    "from": 80,
                    "to": 82.5,
                    "rationale": "All sets completed at RIR 0-1, ready for 2.5kg increase"
                },
                {
                    "path": "exercises[0].sets[1].weight",
                    "from": 80,
                    "to": 82.5,
                    "rationale": "All sets completed at RIR 0-1, ready for 2.5kg increase"
                },
            ],
            summary="Increase Bench Press from 80kg to 82.5kg",
            rationale="User completed all sets at RIR 0-1 with good form. Based on linear progression protocol, increase weight by 2.5kg.",
            trigger="post_workout",
            trigger_context={"workout_id": "workout-xyz", "completed_at": "2024-01-15T10:30:00Z"},
            auto_apply=True,
        )
    """
    if not user_id:
        return ProgressionResult(success=False, error="user_id is required")
    
    if target_type not in ["template", "routine"]:
        return ProgressionResult(success=False, error="target_type must be 'template' or 'routine'")
    
    if not target_id:
        return ProgressionResult(success=False, error="target_id is required")
    
    if not changes:
        return ProgressionResult(success=False, error="changes list is required")
    
    if not summary:
        return ProgressionResult(success=False, error="summary is required")
    
    base_url = _get_base_url()
    api_key = _get_api_key()
    
    payload = {
        "userId": user_id,
        "targetType": target_type,
        "targetId": target_id,
        "changes": changes,
        "summary": summary,
        "rationale": rationale,
        "trigger": trigger,
        "triggerContext": trigger_context or {},
        "autoApply": auto_apply,
    }
    
    logger.info(
        "apply_progression: target=%s/%s changes=%d auto_apply=%s",
        target_type, target_id, len(changes), auto_apply
    )
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{base_url}/applyProgression",
                json=payload,
                headers={
                    "x-api-key": api_key,
                    "Content-Type": "application/json",
                },
            )
            
            if response.status_code != 200:
                error_data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
                error_msg = error_data.get("message") or error_data.get("error") or f"HTTP {response.status_code}"
                logger.error("apply_progression failed: %s", error_msg)
                return ProgressionResult(success=False, error=error_msg)
            
            data = response.json()
            
            logger.info(
                "apply_progression success: recommendation_id=%s state=%s applied=%s",
                data.get("recommendationId"),
                data.get("state"),
                data.get("applied"),
            )
            
            return ProgressionResult(
                success=True,
                data={
                    "recommendation_id": data.get("recommendationId"),
                    "state": data.get("state"),
                    "applied": data.get("applied", False),
                    "result": data.get("result"),
                    "message": f"Progression {'applied' if data.get('applied') else 'queued for review'}: {summary}",
                }
            )
            
    except httpx.TimeoutException:
        logger.error("apply_progression timeout")
        return ProgressionResult(success=False, error="Request timed out")
    except Exception as e:
        logger.error("apply_progression exception: %s", e)
        return ProgressionResult(success=False, error=str(e))


async def suggest_weight_increase(
    user_id: str,
    template_id: str,
    exercise_index: int,
    current_weight: float,
    new_weight: float,
    rationale: str,
    trigger: str = "post_workout",
    trigger_context: Optional[Dict[str, Any]] = None,
    auto_apply: bool = True,
) -> ProgressionResult:
    """
    Convenience wrapper for suggesting a weight increase.
    
    Builds the proper changes array and calls apply_progression.
    
    Args:
        user_id: User ID
        template_id: Template to update
        exercise_index: Index of the exercise (0-based)
        current_weight: Current weight in kg
        new_weight: Suggested new weight in kg
        rationale: Why this increase is recommended
        trigger: What triggered this (default: "post_workout")
        trigger_context: Additional context
        auto_apply: Apply immediately or queue for review
        
    Returns:
        ProgressionResult
    """
    # Build changes for all working sets of this exercise
    changes = []

    # Typically 3-4 working sets, we'll update all of them
    # In practice, the backend will only update existing sets
    for set_idx in range(4):  # Max 4 sets
        changes.append({
            "path": f"exercises[{exercise_index}].sets[{set_idx}].weight",
            "from": current_weight,
            "to": new_weight,
            "rationale": rationale,
        })

    weight_unit = _get_weight_unit()
    current_str = _format_weight(current_weight, weight_unit)
    new_str = _format_weight(new_weight, weight_unit)
    delta = new_weight - current_weight
    delta_str = _format_weight(delta, weight_unit)
    summary = f"Increase weight from {current_str} to {new_str} (+{delta_str})"
    
    return await apply_progression(
        user_id=user_id,
        target_type="template",
        target_id=template_id,
        changes=changes,
        summary=summary,
        rationale=rationale,
        trigger=trigger,
        trigger_context=trigger_context,
        auto_apply=auto_apply,
    )


async def suggest_deload(
    user_id: str,
    template_id: str,
    exercise_index: int,
    current_weight: float,
    deload_weight: float,
    reason: str,
    trigger: str = "plateau_detected",
    trigger_context: Optional[Dict[str, Any]] = None,
    auto_apply: bool = True,
) -> ProgressionResult:
    """
    Suggest a deload for an exercise.
    
    Used when detecting overreach or plateau.
    
    Args:
        user_id: User ID
        template_id: Template to update
        exercise_index: Index of the exercise (0-based)
        current_weight: Current weight in kg
        deload_weight: Suggested deload weight in kg
        reason: Why the deload is recommended
        trigger: What triggered this
        trigger_context: Additional context
        auto_apply: Apply immediately or queue for review
        
    Returns:
        ProgressionResult
    """
    changes = []

    for set_idx in range(4):
        changes.append({
            "path": f"exercises[{exercise_index}].sets[{set_idx}].weight",
            "from": current_weight,
            "to": deload_weight,
            "rationale": reason,
        })

    weight_unit = _get_weight_unit()
    current_str = _format_weight(current_weight, weight_unit)
    deload_str = _format_weight(deload_weight, weight_unit)
    reduction_pct = round((1 - deload_weight / current_weight) * 100)
    summary = f"Deload: reduce weight from {current_str} to {deload_str} (-{reduction_pct}%)"
    
    return await apply_progression(
        user_id=user_id,
        target_type="template",
        target_id=template_id,
        changes=changes,
        summary=summary,
        rationale=reason,
        trigger=trigger,
        trigger_context=trigger_context,
        auto_apply=auto_apply,
    )


__all__ = [
    "ProgressionResult",
    "apply_progression",
    "suggest_weight_increase",
    "suggest_deload",
]
