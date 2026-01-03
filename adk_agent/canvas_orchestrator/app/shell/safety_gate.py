"""
Safety Gate - Enforces confirmation for write operations.

Write operations (propose_workout, propose_routine) require explicit permission
or confirmation before executing. This prevents accidental artifact creation.

Modes:
- dry_run=True: Return preview without executing
- explicit_confirm=True: User explicitly confirmed, execute immediately
- Default: Return preview and require confirmation
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class WriteOperation(str, Enum):
    """Tracked write operations that require safety gate."""
    PROPOSE_WORKOUT = "propose_workout"
    PROPOSE_ROUTINE = "propose_routine"
    CREATE_TEMPLATE = "create_template"
    UPDATE_ROUTINE = "update_routine"


# Keywords that indicate explicit permission
CONFIRM_KEYWORDS = frozenset([
    "confirm", "yes", "do it", "go ahead", "publish", "save",
    "create it", "make it", "build it", "looks good", "approved",
])


@dataclass
class SafetyDecision:
    """Result of safety gate check."""
    allow_execute: bool
    dry_run: bool
    reason: str
    requires_confirmation: bool = False
    
    @property
    def should_preview(self) -> bool:
        """True if we should show preview instead of executing."""
        return self.dry_run or self.requires_confirmation


def check_message_for_confirmation(message: str) -> bool:
    """
    Check if user message contains explicit confirmation.
    
    Args:
        message: User's message
        
    Returns:
        True if message contains confirmation keywords
    """
    lower = message.lower().strip()
    
    # Check for exact match or starts with
    for keyword in CONFIRM_KEYWORDS:
        if lower == keyword or lower.startswith(f"{keyword} ") or lower.endswith(f" {keyword}"):
            return True
    
    return False


def check_safety_gate(
    operation: WriteOperation,
    message: str,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    force_dry_run: bool = False,
) -> SafetyDecision:
    """
    Check if a write operation should execute or require confirmation.
    
    Logic:
    1. If force_dry_run=True, always preview
    2. If message contains explicit confirmation, allow execute
    3. If previous message was a preview, and this is confirmation, allow execute
    4. Otherwise, return preview and require confirmation
    
    Args:
        operation: The write operation being attempted
        message: Current user message
        conversation_history: Previous messages (to detect preview→confirm flow)
        force_dry_run: Force preview mode regardless of confirmation
        
    Returns:
        SafetyDecision with allow_execute, dry_run, and reason
    """
    # Force dry run always returns preview
    if force_dry_run:
        return SafetyDecision(
            allow_execute=False,
            dry_run=True,
            reason="Forced dry run mode",
        )
    
    # Check for explicit confirmation in current message
    if check_message_for_confirmation(message):
        logger.info("SAFETY_GATE: Explicit confirmation detected: %s", message[:30])
        return SafetyDecision(
            allow_execute=True,
            dry_run=False,
            reason="Explicit confirmation in message",
        )
    
    # Check if previous message was a preview (confirmation flow)
    if conversation_history:
        # Look for preview in last assistant response
        for msg in reversed(conversation_history[-3:]):
            if msg.get("role") == "assistant":
                content = msg.get("content", "")
                if "Ready to publish" in content or "preview" in content.lower():
                    # Previous response was preview, check if this is confirmation
                    if any(kw in message.lower() for kw in ["yes", "ok", "confirm", "go"]):
                        logger.info("SAFETY_GATE: Preview→confirm flow detected")
                        return SafetyDecision(
                            allow_execute=True,
                            dry_run=False,
                            reason="Confirmation after preview",
                        )
    
    # Default: require confirmation via preview
    logger.info("SAFETY_GATE: Requiring confirmation for %s", operation)
    return SafetyDecision(
        allow_execute=False,
        dry_run=True,
        requires_confirmation=True,
        reason=f"Write operation '{operation}' requires confirmation",
    )


def format_confirmation_prompt(operation: WriteOperation, preview_data: Dict[str, Any]) -> str:
    """
    Format a confirmation prompt based on the preview data.
    
    Args:
        operation: The write operation
        preview_data: Preview data from dry_run
        
    Returns:
        Formatted confirmation prompt
    """
    if operation == WriteOperation.PROPOSE_WORKOUT:
        title = preview_data.get("preview", {}).get("title", "workout")
        exercise_count = preview_data.get("preview", {}).get("exercise_count", 0)
        return f"Ready to publish '{title}' ({exercise_count} exercises). Say 'confirm' to publish."
    
    elif operation == WriteOperation.PROPOSE_ROUTINE:
        name = preview_data.get("preview", {}).get("name", "routine")
        workout_count = preview_data.get("preview", {}).get("workout_count", 0)
        return f"Ready to publish '{name}' ({workout_count} workouts). Say 'confirm' to publish."
    
    return "Ready to publish. Say 'confirm' to proceed."


__all__ = [
    "WriteOperation",
    "SafetyDecision",
    "check_safety_gate",
    "check_message_for_confirmation",
    "format_confirmation_prompt",
]
