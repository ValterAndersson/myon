"""
Gated Planner Skills - Safety Gate wrappers for write operations.

This module wraps planner_skills.py functions with Safety Gate checks.
Write operations (propose_workout, propose_routine) cannot execute without
explicit user confirmation.

The Safety Gate enforces:
1. First call → dry_run=True (preview)
2. User confirms → dry_run=False (execute)

This is the ONLY module that should expose write operations to the ShellAgent.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.shell.context import SessionContext
from app.shell.safety_gate import (
    WriteOperation,
    check_safety_gate,
    format_confirmation_prompt,
)
from app.skills.planner_skills import (
    SkillResult,
    propose_routine as _propose_routine,
    propose_workout as _propose_workout,
    get_planning_context as _get_planning_context,
)

logger = logging.getLogger(__name__)


def propose_workout(
    ctx: SessionContext,
    message: str,
    title: str,
    exercises: List[Dict[str, Any]],
    focus: Optional[str] = None,
    duration_minutes: int = 45,
    coach_notes: Optional[str] = None,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
) -> SkillResult:
    """
    Create a workout plan with Safety Gate enforcement.
    
    The Safety Gate checks:
    1. Does the message contain explicit confirmation?
    2. Was the previous response a preview?
    
    If neither, returns preview (dry_run=True).
    If confirmed, executes (dry_run=False).
    
    Args:
        ctx: Session context with canvas_id, user_id
        message: User's message (checked for confirmation keywords)
        title: Workout title
        exercises: List of exercises
        focus: Workout focus/goal
        duration_minutes: Estimated duration
        coach_notes: Rationale
        conversation_history: Previous messages for preview→confirm detection
        
    Returns:
        SkillResult with preview (if not confirmed) or published result
    """
    # Check Safety Gate
    decision = check_safety_gate(
        operation=WriteOperation.PROPOSE_WORKOUT,
        message=message,
        conversation_history=conversation_history,
    )
    
    logger.info(
        "GATED_PLANNER propose_workout: allow=%s dry_run=%s reason='%s'",
        decision.allow_execute, decision.dry_run, decision.reason
    )
    
    # Execute with dry_run based on Safety Gate decision
    result = _propose_workout(
        canvas_id=ctx.canvas_id,
        user_id=ctx.user_id,
        title=title,
        exercises=exercises,
        focus=focus,
        duration_minutes=duration_minutes,
        coach_notes=coach_notes,
        correlation_id=ctx.correlation_id,
        dry_run=decision.dry_run,
    )
    
    # If preview, add confirmation prompt to message
    if result.dry_run and result.success:
        prompt = format_confirmation_prompt(
            WriteOperation.PROPOSE_WORKOUT, 
            result.data
        )
        result.data["confirmation_prompt"] = prompt
    
    return result


def propose_routine(
    ctx: SessionContext,
    message: str,
    name: str,
    frequency: int,
    workouts: List[Dict[str, Any]],
    description: Optional[str] = None,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
) -> SkillResult:
    """
    Create a routine with Safety Gate enforcement.
    
    Same Safety Gate logic as propose_workout.
    
    Args:
        ctx: Session context
        message: User's message (checked for confirmation)
        name: Routine name
        frequency: Times per week
        workouts: List of workout days with exercises
        description: Routine description
        conversation_history: Previous messages for preview→confirm detection
        
    Returns:
        SkillResult with preview (if not confirmed) or published result
    """
    # Check Safety Gate
    decision = check_safety_gate(
        operation=WriteOperation.PROPOSE_ROUTINE,
        message=message,
        conversation_history=conversation_history,
    )
    
    logger.info(
        "GATED_PLANNER propose_routine: allow=%s dry_run=%s reason='%s'",
        decision.allow_execute, decision.dry_run, decision.reason
    )
    
    # Execute with dry_run based on Safety Gate decision
    result = _propose_routine(
        canvas_id=ctx.canvas_id,
        user_id=ctx.user_id,
        name=name,
        frequency=frequency,
        workouts=workouts,
        description=description,
        correlation_id=ctx.correlation_id,
        dry_run=decision.dry_run,
    )
    
    # If preview, add confirmation prompt
    if result.dry_run and result.success:
        prompt = format_confirmation_prompt(
            WriteOperation.PROPOSE_ROUTINE,
            result.data
        )
        result.data["confirmation_prompt"] = prompt
    
    return result


def get_planning_context(ctx: SessionContext) -> SkillResult:
    """
    Get planning context (read-only, no Safety Gate needed).
    
    Delegates directly to planner_skills.
    """
    return _get_planning_context(user_id=ctx.user_id)


__all__ = [
    "propose_workout",
    "propose_routine",
    "get_planning_context",
]
