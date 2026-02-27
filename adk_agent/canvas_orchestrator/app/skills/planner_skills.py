"""
Planner Skills - Pure functions for workout/routine artifact creation.

These are extracted from planner_agent.py and refactored to:
- Take explicit context parameters (no global _context dict)
- Support dry_run mode for Safety Gate
- Return structured results

Write operations (propose_workout, propose_routine) return artifact data
directly via the tool response. The streaming layer (stream-agent-normalized.js)
detects artifact_type in tool responses and handles SSE emission + Firestore
persistence. The agent never writes cards/artifacts to Firestore directly.
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.libs.tools_canvas.client import CanvasFunctionsClient

logger = logging.getLogger(__name__)

# Singleton client — used by get_planning_context() for read-only calls
_client: Optional[CanvasFunctionsClient] = None


def _get_client() -> CanvasFunctionsClient:
    """Get or create the client for read-only API calls."""
    global _client
    if _client is None:
        base_url = os.getenv("MYON_FUNCTIONS_BASE_URL", "https://us-central1-myon-53d85.cloudfunctions.net")
        api_key = os.getenv("MYON_API_KEY")
        if not api_key:
            raise RuntimeError("MYON_API_KEY env var is required")
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

        if weight is None:
            logger.warning(json.dumps({
                "event": "missing_weight",
                "exercise": name,
                "exercise_id": exercise_id,
            }))
        
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

        # Cache weight_unit for other skills to use
        from app.shell.context import get_current_context
        from app.skills.workout_skills import set_weight_unit

        try:
            ctx = get_current_context()
            wu = data.get("weight_unit", "kg") if isinstance(data, dict) else "kg"
            corr_id = ctx.correlation_id or ctx.conversation_id
            set_weight_unit(user_id, corr_id, wu)
            logger.debug("Cached weight_unit=%s for user=%s", wu, user_id)
        except Exception as e:
            logger.debug("Failed to cache weight_unit: %s", e)

        return SkillResult(success=True, data=data)
    except Exception as e:
        logger.error("get_planning_context exception: %s", e)
        return SkillResult(success=False, error=str(e))


# ============================================================================
# WORKOUT PROPOSAL (WITH SAFETY GATE SUPPORT)
# ============================================================================

def propose_workout(
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
    Create a workout plan artifact.

    Returns artifact data directly. The streaming layer detects artifact_type
    in the tool response and handles SSE emission + Firestore persistence.

    Args:
        user_id: User ID (required)
        title: Workout name
        exercises: List of exercises with name, exercise_id, sets, reps, rir, weight_kg
        focus: Brief goal description
        duration_minutes: Estimated duration
        coach_notes: Rationale for this plan
        correlation_id: Request correlation ID
        dry_run: If True, return preview without publishing (Safety Gate)

    Returns:
        SkillResult with artifact data or preview
    """
    if not user_id:
        return SkillResult(success=False, error="user_id is required")

    # Build exercise blocks
    blocks = _build_exercise_blocks(exercises)

    if not blocks:
        return SkillResult(success=False, error="No valid exercises provided")

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

    # Return artifact data directly — streaming layer handles persistence
    logger.info("PROPOSE_WORKOUT: title='%s' exercises=%d", title, len(blocks))

    return SkillResult(
        success=True,
        data={
            "artifact_type": "session_plan",
            "content": {
                "title": title,
                "blocks": blocks,
                "estimated_duration_minutes": duration_minutes,
                "coach_notes": coach_notes,
            },
            "actions": ["start_workout", "dismiss"],
            "status": "proposed",
            "message": f"'{title}' proposed ({len(blocks)} exercises, ~{duration_minutes} min)",
            "exercises": len(blocks),
            "total_sets": sum(len(b.get("sets", [])) for b in blocks),
        }
    )


# ============================================================================
# ROUTINE PROPOSAL (WITH SAFETY GATE SUPPORT)
# ============================================================================

def propose_routine(
    user_id: str,
    name: str,
    frequency: int,
    workouts: List[Dict[str, Any]],
    description: Optional[str] = None,
    correlation_id: Optional[str] = None,
    dry_run: bool = False,
) -> SkillResult:
    """
    Create a routine artifact with embedded workout data.

    Returns a single routine_summary artifact with all workouts and their
    exercises embedded inline. The streaming layer handles persistence.

    Args:
        user_id: User ID (required)
        name: Routine name
        frequency: Times per week
        workouts: List of workouts, each with title and exercises
        description: Routine description
        correlation_id: Request correlation ID
        dry_run: If True, return preview without publishing (Safety Gate)

    Returns:
        SkillResult with artifact data or preview
    """
    if not user_id:
        return SkillResult(success=False, error="user_id is required")

    if not workouts:
        return SkillResult(success=False, error="At least one workout is required")

    # Build workout data with embedded exercises
    workout_summaries = []
    empty_days = []

    for idx, workout in enumerate(workouts):
        title = workout.get("title") or f"Day {idx + 1}"
        exercises = workout.get("exercises") or []

        blocks = _build_exercise_blocks(exercises)

        if not blocks:
            empty_days.append(title)
            continue

        estimated_duration = len(blocks) * 5 + 10

        workout_summaries.append({
            "day": idx + 1,
            "title": title,
            "blocks": blocks,
            "estimated_duration": estimated_duration,
            "exercise_count": len(blocks),
        })

    if not workout_summaries:
        detail = f" (empty: {', '.join(empty_days)})" if empty_days else ""
        return SkillResult(
            success=False,
            error=f"All workouts have empty exercises{detail}. "
                  "Provide exercises for each workout day.",
        )

    if empty_days:
        logger.warning(
            "PROPOSE_ROUTINE: skipped %d empty workout(s): %s",
            len(empty_days), ", ".join(empty_days),
        )

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

    # Return artifact data directly — streaming layer handles persistence
    logger.info("PROPOSE_ROUTINE: name='%s' workouts=%d", name, len(workouts))

    return SkillResult(
        success=True,
        data={
            "artifact_type": "routine_summary",
            "content": {
                "name": name,
                "description": description,
                "frequency": frequency,
                "workouts": workout_summaries,
            },
            "actions": ["save_routine", "dismiss"],
            "status": "proposed",
            "message": f"'{name}' routine proposed ({len(workouts)} workouts)",
            "workout_count": len(workouts),
            "total_exercises": total_exercises,
        }
    )


# ============================================================================
# ROUTINE UPDATE PROPOSAL (Canvas Context - User Confirms)
# ============================================================================

def propose_routine_update(
    user_id: str,
    routine_id: str,
    workouts: List[Dict[str, Any]],
    name: Optional[str] = None,
    description: Optional[str] = None,
    frequency: Optional[int] = None,
    routine_name: Optional[str] = None,
    correlation_id: Optional[str] = None,
    dry_run: bool = False,
) -> SkillResult:
    """
    Propose updates to an existing routine as an artifact.

    Returns artifact data with source metadata so the artifact action endpoint
    can UPDATE the existing routine instead of creating a new one.

    Args:
        user_id: User ID (required)
        routine_id: ID of routine to update (required)
        workouts: List of workouts, each with:
            - title: Day name
            - exercises: List of exercises
            - source_template_id: (optional) Original template ID if updating existing day
        name: New routine name (optional, keeps existing if not provided)
        description: New description (optional)
        frequency: New frequency (optional)
        routine_name: Current routine name for UI display
        correlation_id: Request correlation ID
        dry_run: If True, return preview without publishing

    Returns:
        SkillResult with artifact data or preview
    """
    if not user_id:
        return SkillResult(success=False, error="user_id is required")

    if not routine_id:
        return SkillResult(success=False, error="routine_id is required for updates")

    if not workouts:
        return SkillResult(success=False, error="At least one workout is required")

    # Build workout data with embedded exercises and source metadata
    workout_summaries = []

    for idx, workout in enumerate(workouts):
        title = workout.get("title") or f"Day {idx + 1}"
        exercises = workout.get("exercises") or []
        source_template_id = workout.get("source_template_id")

        blocks = _build_exercise_blocks(exercises)
        estimated_duration = len(blocks) * 5 + 10

        summary = {
            "day": idx + 1,
            "title": title,
            "blocks": blocks,
            "estimated_duration": estimated_duration,
            "exercise_count": len(blocks),
        }
        if source_template_id:
            summary["source_template_id"] = source_template_id

        workout_summaries.append(summary)

    total_exercises = sum(w.get("exercise_count", 0) for w in workout_summaries)

    # SAFETY GATE: If dry_run, return preview without publishing
    if dry_run:
        logger.info("PROPOSE_ROUTINE_UPDATE DRY_RUN: routine_id='%s' workouts=%d", routine_id, len(workouts))
        return SkillResult(
            success=True,
            dry_run=True,
            data={
                "status": "preview",
                "message": f"Ready to update routine ({len(workouts)} workouts)",
                "preview": {
                    "source_routine_id": routine_id,
                    "name": name,
                    "frequency": frequency,
                    "workout_count": len(workouts),
                    "total_exercises": total_exercises,
                    "workouts": workout_summaries,
                    "mode": "update",
                },
                "action_required": "Call propose_routine_update with dry_run=False to publish",
            }
        )

    # Return artifact data directly
    logger.info("PROPOSE_ROUTINE_UPDATE: routine_id='%s' workouts=%d", routine_id, len(workouts))

    return SkillResult(
        success=True,
        data={
            "artifact_type": "routine_summary",
            "content": {
                "name": name,
                "description": description,
                "frequency": frequency or len(workouts),
                "workouts": workout_summaries,
                "mode": "update",
                "source_routine_id": routine_id,
                "source_routine_name": routine_name,
            },
            "actions": ["save_routine", "dismiss", "save_as_new"],
            "status": "proposed",
            "message": f"Routine update proposed ({len(workouts)} workouts)",
            "mode": "update",
            "source_routine_id": routine_id,
            "workout_count": len(workouts),
            "total_exercises": total_exercises,
        }
    )


# ============================================================================
# TEMPLATE UPDATE PROPOSAL (Canvas Context - User Confirms)
# ============================================================================

def propose_template_update(
    user_id: str,
    template_id: str,
    exercises: List[Dict[str, Any]],
    name: Optional[str] = None,
    coach_notes: Optional[str] = None,
    correlation_id: Optional[str] = None,
    dry_run: bool = False,
) -> SkillResult:
    """
    Propose updates to an existing workout template as an artifact.

    Returns artifact data with source metadata so the artifact action endpoint
    can UPDATE the existing template instead of creating a new one.

    Args:
        user_id: User ID (required)
        template_id: ID of template to update (required)
        exercises: List of exercises with name, exercise_id, sets, reps, rir, weight_kg
        name: New template name (optional)
        coach_notes: Rationale for changes
        correlation_id: Request correlation ID
        dry_run: If True, return preview without publishing

    Returns:
        SkillResult with artifact data or preview
    """
    if not user_id:
        return SkillResult(success=False, error="user_id is required")

    if not template_id:
        return SkillResult(success=False, error="template_id is required for updates")

    # Build exercise blocks
    blocks = _build_exercise_blocks(exercises)

    if not blocks:
        return SkillResult(success=False, error="No valid exercises provided")

    estimated_duration = len(blocks) * 5 + 10

    # SAFETY GATE: If dry_run, return preview without publishing
    if dry_run:
        logger.info("PROPOSE_TEMPLATE_UPDATE DRY_RUN: template_id='%s' exercises=%d", template_id, len(blocks))
        return SkillResult(
            success=True,
            dry_run=True,
            data={
                "status": "preview",
                "message": f"Ready to update template ({len(blocks)} exercises)",
                "preview": {
                    "source_template_id": template_id,
                    "name": name,
                    "exercise_count": len(blocks),
                    "exercises": [{"name": b["name"], "sets": len(b["sets"])} for b in blocks],
                    "total_sets": sum(len(b.get("sets", [])) for b in blocks),
                    "mode": "update",
                },
                "action_required": "Call propose_template_update with dry_run=False to publish",
            }
        )

    # Return artifact data directly
    logger.info("PROPOSE_TEMPLATE_UPDATE: template_id='%s' exercises=%d", template_id, len(blocks))

    return SkillResult(
        success=True,
        data={
            "artifact_type": "session_plan",
            "content": {
                "title": name,
                "blocks": blocks,
                "estimated_duration_minutes": estimated_duration,
                "coach_notes": coach_notes,
                "mode": "update",
                "source_template_id": template_id,
            },
            "actions": ["save_template", "dismiss", "save_as_new"],
            "status": "proposed",
            "message": "Template update proposed",
            "mode": "update",
            "source_template_id": template_id,
            "exercises": len(blocks),
            "total_sets": sum(len(b.get("sets", [])) for b in blocks),
        }
    )


__all__ = [
    "SkillResult",
    "get_planning_context",
    "propose_workout",
    "propose_routine",
    "propose_routine_update",
    "propose_template_update",
]
