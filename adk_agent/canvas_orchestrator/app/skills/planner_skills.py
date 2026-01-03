"""
Planner Skills - Pure functions for workout/routine artifact creation.

These are extracted from planner_agent.py and refactored to:
- Take explicit context parameters (no global _context dict)
- Support dry_run mode for Safety Gate
- Return structured results

Write operations (propose_workout, propose_routine) support dry_run mode
which returns what WOULD be created without actually publishing.
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.libs.tools_canvas.client import CanvasFunctionsClient
from app.libs.tools_common.response_helpers import (
    parse_api_response,
    format_validation_error_for_agent,
)

logger = logging.getLogger(__name__)

# Singleton client
_client: Optional[CanvasFunctionsClient] = None


def _get_client() -> CanvasFunctionsClient:
    """Get or create the canvas client."""
    global _client
    if _client is None:
        base_url = os.getenv("MYON_FUNCTIONS_BASE_URL", "https://us-central1-myon-53d85.cloudfunctions.net")
        api_key = os.getenv("MYON_API_KEY", "myon-agent-key-2024")
        _client = CanvasFunctionsClient(base_url=base_url, api_key=api_key)
    return _client


@dataclass
class SkillResult:
    """Standardized result from a skill."""
    success: bool
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    dry_run: bool = False  # If true, this was a preview, not actual execution
    
    def to_dict(self) -> Dict[str, Any]:
        if not self.success:
            return {"error": self.error or "Unknown error"}
        result = dict(self.data)
        if self.dry_run:
            result["dry_run"] = True
        return result


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return slug[:48] or "exercise"


def _extract_reps(value: Any, default: int = 8) -> int:
    if isinstance(value, (int, float)):
        return max(int(value), 1)
    if isinstance(value, str):
        matches = re.findall(r"\d+", value)
        if matches:
            return int(matches[-1])
    return default


def _build_exercise_blocks(exercises: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build exercise blocks from exercise list."""
    blocks: List[Dict[str, Any]] = []
    
    for idx, ex in enumerate(exercises):
        if not isinstance(ex, dict):
            continue
            
        name = ex.get("name") or ex.get("exercise_name") or "Exercise"
        exercise_id = ex.get("exercise_id") or ex.get("id") or _slugify(name)
        
        reps = _extract_reps(ex.get("reps"), 8)
        final_rir = _coerce_int(ex.get("rir"), 2)
        weight = ex.get("weight_kg") or ex.get("weight")
        if weight is not None:
            try:
                weight = float(weight)
            except (TypeError, ValueError):
                weight = None
        
        category = ex.get("category", "").lower()
        is_compound = category == "compound" or idx < 2
        
        # Build sets array
        sets: List[Dict[str, Any]] = []
        num_working = _coerce_int(ex.get("sets", 3), 3)
        num_warmup = ex.get("warmup_sets")
        
        if num_warmup is None:
            num_warmup = 2 if is_compound and weight and weight >= 40 else 0
        else:
            num_warmup = _coerce_int(num_warmup, 0)
        
        # Add warmup sets with ramping weight
        if num_warmup > 0 and weight:
            warmup_weights = {
                1: [0.5],
                2: [0.4, 0.7],
                3: [0.3, 0.5, 0.7],
            }.get(num_warmup, [0.4, 0.7])
            
            for i, pct in enumerate(warmup_weights[:num_warmup]):
                sets.append({
                    "id": str(uuid.uuid4())[:8],
                    "type": "warmup",
                    "target": {
                        "reps": 10 if i == 0 else 6,
                        "rir": 5,
                        "weight": round(weight * pct / 2.5) * 2.5,
                    },
                })
        
        # Add working sets with RIR progression
        for i in range(num_working):
            sets_remaining = num_working - i - 1
            set_rir = min(final_rir + sets_remaining, 5)
            
            target = {"reps": reps, "rir": set_rir}
            if weight is not None:
                target["weight"] = weight
            
            sets.append({
                "id": str(uuid.uuid4())[:8],
                "type": "working",
                "target": target,
            })
        
        blocks.append({
            "id": str(uuid.uuid4())[:8],
            "exercise_id": exercise_id,
            "name": name,
            "sets": sets,
            "primary_muscles": ex.get("primary_muscles") or [],
            "equipment": (ex.get("equipment") or [None])[0] if isinstance(ex.get("equipment"), list) else ex.get("equipment"),
            "coach_note": ex.get("notes") or ex.get("rationale"),
        })
    
    return blocks


# ============================================================================
# PLANNING CONTEXT
# ============================================================================

def get_planning_context(user_id: str) -> SkillResult:
    """
    Get complete planning context: user profile, active routine, templates.
    
    Args:
        user_id: User ID (required)
        
    Returns:
        SkillResult with user, activeRoutine, templates, etc.
    """
    if not user_id:
        return SkillResult(success=False, error="user_id is required")
    
    logger.info("get_planning_context uid=%s", user_id)
    
    try:
        data = _get_client().get_planning_context(user_id)
        return SkillResult(success=True, data=data)
    except Exception as e:
        logger.error("get_planning_context exception: %s", e)
        return SkillResult(success=False, error=str(e))


# ============================================================================
# WORKOUT PROPOSAL (WITH SAFETY GATE SUPPORT)
# ============================================================================

def propose_workout(
    canvas_id: str,
    user_id: str,
    title: str,
    exercises: List[Dict[str, Any]],
    focus: Optional[str] = None,
    duration_minutes: int = 45,
    coach_notes: Optional[str] = None,
    correlation_id: Optional[str] = None,
    dry_run: bool = False,
) -> SkillResult:
    """
    Create and optionally publish a workout plan.
    
    Args:
        canvas_id: Canvas ID (required)
        user_id: User ID (required)
        title: Workout name
        exercises: List of exercises with name, exercise_id, sets, reps, rir, weight_kg
        focus: Brief goal description
        duration_minutes: Estimated duration
        coach_notes: Rationale for this plan
        correlation_id: Request correlation ID
        dry_run: If True, return preview without publishing (Safety Gate)
        
    Returns:
        SkillResult with published workout or preview
    """
    if not canvas_id or not user_id:
        return SkillResult(success=False, error="canvas_id and user_id are required")
    
    # Build exercise blocks
    blocks = _build_exercise_blocks(exercises)
    
    if not blocks:
        return SkillResult(success=False, error="No valid exercises provided")
    
    # Build the session_plan card
    card = {
        "type": "session_plan",
        "lane": "workout",
        "priority": 90,
        "actions": [
            {"kind": "accept_plan", "label": "Accept Plan", "style": "primary", "iconSystemName": "checkmark"},
            {"kind": "dismiss_plan", "label": "Dismiss", "style": "secondary", "iconSystemName": "xmark"},
            {"kind": "follow_up", "label": "Adjust", "style": "ghost", "iconSystemName": "bubble.left"},
        ],
        "content": {
            "title": title,
            "blocks": blocks,
            "estimated_duration_minutes": duration_minutes,
            "coach_notes": coach_notes,
        },
    }
    
    # SAFETY GATE: If dry_run, return preview without publishing
    if dry_run:
        logger.info("PROPOSE_WORKOUT DRY_RUN: title='%s' exercises=%d", title, len(blocks))
        return SkillResult(
            success=True,
            dry_run=True,
            data={
                "status": "preview",
                "message": f"Ready to publish '{title}' ({len(blocks)} exercises, ~{duration_minutes} min)",
                "preview": {
                    "title": title,
                    "exercise_count": len(blocks),
                    "exercises": [{"name": b["name"], "sets": len(b["sets"])} for b in blocks],
                    "total_sets": sum(len(b.get("sets", [])) for b in blocks),
                    "duration_minutes": duration_minutes,
                },
                "action_required": "Call propose_workout with dry_run=False to publish",
            }
        )
    
    # Publish via proposeCards
    logger.info("PROPOSE_WORKOUT: canvas=%s title='%s' exercises=%d", canvas_id, title, len(blocks))
    
    try:
        resp = _get_client().propose_cards(
            canvas_id=canvas_id,
            cards=[card],
            user_id=user_id,
            correlation_id=correlation_id,
        )
        
        success, data, error_details = parse_api_response(resp)
        if not success:
            logger.error("PROPOSE_WORKOUT ERROR: %s", error_details)
            return SkillResult(success=False, error=str(error_details))
        
    except Exception as e:
        logger.error("PROPOSE_WORKOUT FAILED: %s", e)
        return SkillResult(success=False, error=str(e))
    
    return SkillResult(
        success=True,
        data={
            "status": "published",
            "message": f"'{title}' published to canvas",
            "exercises": len(blocks),
            "total_sets": sum(len(b.get("sets", [])) for b in blocks),
        }
    )


# ============================================================================
# ROUTINE PROPOSAL (WITH SAFETY GATE SUPPORT)
# ============================================================================

def propose_routine(
    canvas_id: str,
    user_id: str,
    name: str,
    frequency: int,
    workouts: List[Dict[str, Any]],
    description: Optional[str] = None,
    correlation_id: Optional[str] = None,
    dry_run: bool = False,
) -> SkillResult:
    """
    Create and optionally publish a complete routine with multiple workouts.
    
    Args:
        canvas_id: Canvas ID (required)
        user_id: User ID (required)
        name: Routine name
        frequency: Times per week
        workouts: List of workouts, each with title and exercises
        description: Routine description
        correlation_id: Request correlation ID
        dry_run: If True, return preview without publishing (Safety Gate)
        
    Returns:
        SkillResult with published routine or preview
    """
    if not canvas_id or not user_id:
        return SkillResult(success=False, error="canvas_id and user_id are required")
    
    if not workouts:
        return SkillResult(success=False, error="At least one workout is required")
    
    # Build all workout cards
    cards: List[Dict[str, Any]] = []
    workout_summaries = []
    
    for idx, workout in enumerate(workouts):
        title = workout.get("title") or f"Day {idx + 1}"
        exercises = workout.get("exercises") or []
        
        blocks = _build_exercise_blocks(exercises)
        estimated_duration = len(blocks) * 5 + 10
        
        day_card = {
            "type": "session_plan",
            "lane": "workout",
            "content": {
                "title": title,
                "blocks": blocks,
                "estimated_duration_minutes": estimated_duration,
            },
            "actions": [
                {"kind": "expand", "label": "View Details", "style": "ghost"},
            ],
        }
        cards.append(day_card)
        
        workout_summaries.append({
            "day": idx + 1,
            "title": title,
            "card_id": None,
            "estimated_duration": estimated_duration,
            "exercise_count": len(blocks),
        })
    
    # Create routine_summary anchor card
    summary_card = {
        "type": "routine_summary",
        "lane": "workout",
        "priority": 95,
        "content": {
            "name": name,
            "description": description,
            "frequency": frequency,
            "workouts": workout_summaries,
        },
        "actions": [
            {"kind": "save_routine", "label": "Save Routine", "style": "primary", "iconSystemName": "checkmark"},
            {"kind": "dismiss_draft", "label": "Dismiss", "style": "secondary", "iconSystemName": "xmark"},
        ],
    }
    
    all_cards = [summary_card] + cards
    total_exercises = sum(w.get("exercise_count", 0) for w in workout_summaries)
    
    # SAFETY GATE: If dry_run, return preview without publishing
    if dry_run:
        logger.info("PROPOSE_ROUTINE DRY_RUN: name='%s' workouts=%d", name, len(workouts))
        return SkillResult(
            success=True,
            dry_run=True,
            data={
                "status": "preview",
                "message": f"Ready to publish '{name}' ({len(workouts)} workouts, {frequency}x/week)",
                "preview": {
                    "name": name,
                    "frequency": frequency,
                    "workout_count": len(workouts),
                    "total_exercises": total_exercises,
                    "workouts": workout_summaries,
                },
                "action_required": "Call propose_routine with dry_run=False to publish",
            }
        )
    
    # Publish all cards
    logger.info("PROPOSE_ROUTINE: canvas=%s name='%s' workouts=%d", canvas_id, name, len(workouts))
    
    try:
        resp = _get_client().propose_cards(
            canvas_id=canvas_id,
            cards=all_cards,
            user_id=user_id,
            correlation_id=correlation_id,
        )
        
        success, data, error_details = parse_api_response(resp)
        if not success:
            logger.error("PROPOSE_ROUTINE ERROR: %s", error_details)
            return SkillResult(success=False, error=str(error_details))
        
    except Exception as e:
        logger.error("PROPOSE_ROUTINE FAILED: %s", e)
        return SkillResult(success=False, error=str(e))
    
    return SkillResult(
        success=True,
        data={
            "status": "published",
            "message": f"'{name}' routine published ({len(workouts)} workouts)",
            "workout_count": len(workouts),
            "total_exercises": total_exercises,
        }
    )


__all__ = [
    "SkillResult",
    "get_planning_context",
    "propose_workout",
    "propose_routine",
]
