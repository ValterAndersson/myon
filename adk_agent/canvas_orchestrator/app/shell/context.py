"""
SessionContext - Per-request context using contextvars.

Thread-safe, async-safe storage for the Vertex AI Agent Engine
concurrent serverless environment.

CRITICAL: Never use module-level globals for request state.
ContextVars provide proper request isolation.

This replaces the global _context dictionaries that were causing
state leakage between requests in coach_agent.py and planner_agent.py.
"""

from __future__ import annotations

import re
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Optional


# =============================================================================
# CONTEXT VARIABLES (Thread-safe, Async-safe)
# =============================================================================

# Session context for the current request
_session_context_var: ContextVar[Optional["SessionContext"]] = ContextVar(
    "session_context", 
    default=None
)

# User message for the current request (for Safety Gate checks)
_message_context_var: ContextVar[str] = ContextVar(
    "message_context", 
    default=""
)


def set_current_context(ctx: "SessionContext", message: str = "") -> None:
    """
    Set the context for the current request.
    
    MUST be called at the start of stream_query in agent_engine_app.py,
    BEFORE any routing or tool execution.
    
    Args:
        ctx: SessionContext parsed from message prefix
        message: Raw user message (for Safety Gate checks)
    """
    _session_context_var.set(ctx)
    _message_context_var.set(message)


def get_current_context() -> "SessionContext":
    """
    Get the context for the current request.
    
    Called by tool wrappers to get user_id, canvas_id.
    
    Returns:
        SessionContext for current request
        
    Raises:
        RuntimeError: If called outside an active request context
    """
    ctx = _session_context_var.get()
    if ctx is None:
        raise RuntimeError(
            "get_current_context() called outside request context. "
            "Ensure set_current_context() is called in stream_query."
        )
    return ctx


def get_current_message() -> str:
    """
    Get the message for the current request.
    
    Used by Safety Gate to check for confirmation keywords.
    
    Returns:
        User message for current request, or empty string if not set
    """
    return _message_context_var.get()


def clear_current_context() -> None:
    """
    Clear the context after request completion.
    
    Optional cleanup - contextvars automatically reset per-task in asyncio.
    """
    _session_context_var.set(None)
    _message_context_var.set("")


@dataclass(frozen=True)  # Immutable
class SessionContext:
    """
    Per-request context extracted from message prefix.

    This is NOT persistent across requests. Each request creates a new
    SessionContext from the message prefix.

    Format: (context: canvas_id=X user_id=Y corr=Z [workout_id=W]) message
    """
    canvas_id: str
    user_id: str
    correlation_id: Optional[str]
    workout_mode: bool = False
    active_workout_id: Optional[str] = None
    
    @classmethod
    def from_message(cls, message: str) -> "SessionContext":
        """
        Parse context from message prefix.

        Expected format: (context: canvas_id=X user_id=Y corr=Z [workout_id=W]) message

        Args:
            message: Raw message with optional context prefix

        Returns:
            SessionContext with parsed values, or empty context if parsing fails
        """
        match = re.search(
            r'\(context:\s*canvas_id=(\S+)\s+user_id=(\S+)\s+corr=(\S+)'
            r'(?:\s+workout_id=(\S+))?\)',
            message
        )
        if match:
            corr = match.group(3).strip()
            workout_id = match.group(4).strip() if match.group(4) else None

            # Parse workout mode
            workout_mode = False
            active_workout_id = None
            if workout_id and workout_id != "none":
                workout_mode = True
                active_workout_id = workout_id

            return cls(
                canvas_id=match.group(1).strip(),
                user_id=match.group(2).strip(),
                correlation_id=corr if corr != "none" else None,
                workout_mode=workout_mode,
                active_workout_id=active_workout_id,
            )
        # Fallback for malformed messages
        return cls(canvas_id="", user_id="", correlation_id=None)
    
    @staticmethod
    def strip_prefix(message: str) -> str:
        """
        Remove context prefix from message for cleaner processing.

        Args:
            message: Raw message with optional context prefix

        Returns:
            Message without the context prefix
        """
        return re.sub(
            r'\(context:\s*canvas_id=\S+\s+user_id=\S+\s+corr=\S+'
            r'(?:\s+workout_id=\S+)?\)\s*',
            '',
            message
        ).strip()
    
    def is_valid(self) -> bool:
        """Check if context has required fields."""
        return bool(self.canvas_id and self.user_id)
    
    def __str__(self) -> str:
        """Format for logging."""
        corr = self.correlation_id or "none"
        if self.workout_mode and self.active_workout_id:
            return f"SessionContext(canvas={self.canvas_id}, user={self.user_id}, corr={corr}, workout={self.active_workout_id})"
        return f"SessionContext(canvas={self.canvas_id}, user={self.user_id}, corr={corr})"


__all__ = [
    "SessionContext",
    "set_current_context",
    "get_current_context",
    "get_current_message",
    "clear_current_context",
]
