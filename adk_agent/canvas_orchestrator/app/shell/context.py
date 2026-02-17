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
import threading
import time
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

# =============================================================================
# SEARCH CALL COUNTER — module-level dict keyed by correlation_id
#
# ContextVars don't work for this because ADK's _before_tool_callback creates
# a fresh context for each tool invocation. A module-level dict keyed by
# (user_id, correlation_id) provides proper per-request isolation while being
# visible across all tool calls in the same request.
# =============================================================================
_search_counts: dict = {}  # (user_id, corr_id) -> {"count": int, "ts": float}
_search_counts_lock = threading.Lock()
_SEARCH_COUNTS_MAX_SIZE = 200  # Evict oldest entries above this size

MAX_SEARCH_CALLS = 6


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
    
    Called by tool wrappers to get user_id, conversation_id.

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


def _search_count_key() -> Optional[tuple]:
    """Build a dict key from the current request context."""
    ctx = _session_context_var.get()
    if ctx is None or not ctx.user_id:
        return None
    return (ctx.user_id, ctx.correlation_id or ctx.conversation_id)


def increment_search_count() -> int:
    """
    Increment and return the search call count for the current request.

    Uses a module-level dict keyed by (user_id, correlation_id) because
    ADK's before_tool_callback creates a fresh ContextVar scope per tool call,
    making ContextVar-based counters ineffective.

    Returns:
        Updated count after increment
    """
    key = _search_count_key()
    if key is None:
        return 1
    with _search_counts_lock:
        entry = _search_counts.get(key)
        if entry is None:
            entry = {"count": 0, "ts": time.monotonic()}
            _search_counts[key] = entry
        entry["count"] += 1
        entry["ts"] = time.monotonic()
        # Evict oldest entries if dict grows too large
        if len(_search_counts) > _SEARCH_COUNTS_MAX_SIZE:
            oldest = sorted(_search_counts, key=lambda k: _search_counts[k]["ts"])
            for old_key in oldest[: len(_search_counts) - _SEARCH_COUNTS_MAX_SIZE]:
                del _search_counts[old_key]
        return entry["count"]


def get_search_count() -> int:
    """Get current search call count for this request."""
    key = _search_count_key()
    if key is None:
        return 0
    with _search_counts_lock:
        entry = _search_counts.get(key)
        return entry["count"] if entry else 0


def clear_current_context() -> None:
    """
    Clear the context after request completion.

    Optional cleanup - contextvars automatically reset per-task in asyncio.
    """
    key = _search_count_key()
    _session_context_var.set(None)
    _message_context_var.set("")
    # Clean up search counter for this request
    if key:
        with _search_counts_lock:
            _search_counts.pop(key, None)


@dataclass(frozen=True)  # Immutable
class SessionContext:
    """
    Per-request context extracted from message prefix.

    This is NOT persistent across requests. Each request creates a new
    SessionContext from the message prefix.

    Format: (context: conversation_id=X user_id=Y corr=Z [workout_id=W] [today=YYYY-MM-DD]) message

    Note: Also accepts legacy canvas_id= prefix for backward compatibility
    during the canvas-to-conversations migration.
    """
    conversation_id: str
    user_id: str
    correlation_id: Optional[str]
    workout_mode: bool = False
    active_workout_id: Optional[str] = None
    today: Optional[str] = None  # YYYY-MM-DD, injected by streamAgentNormalized

    @classmethod
    def from_message(cls, message: str) -> "SessionContext":
        """
        Parse context from message prefix.

        Expected format:
            (context: conversation_id=X user_id=Y corr=Z [workout_id=W] [today=YYYY-MM-DD]) message

        Also accepts legacy format for backward compatibility:
            (context: canvas_id=X user_id=Y corr=Z [workout_id=W] [today=YYYY-MM-DD]) message

        Args:
            message: Raw message with optional context prefix

        Returns:
            SessionContext with parsed values, or empty context if parsing fails
        """
        # Accept both conversation_id= and canvas_id= (backward compat)
        match = re.search(
            r'\(context:\s*(?:conversation_id|canvas_id)=(\S+)\s+user_id=(\S+)\s+corr=(\S+)'
            r'(?:\s+workout_id=(\S+))?'
            r'(?:\s+today=(\S+))?\)',
            message
        )
        if match:
            corr = match.group(3).strip()
            workout_id = match.group(4).strip() if match.group(4) else None
            today = match.group(5).strip() if match.group(5) else None

            # Parse workout mode
            workout_mode = False
            active_workout_id = None
            if workout_id and workout_id != "none":
                workout_mode = True
                active_workout_id = workout_id

            return cls(
                conversation_id=match.group(1).strip(),
                user_id=match.group(2).strip(),
                correlation_id=corr if corr != "none" else None,
                workout_mode=workout_mode,
                active_workout_id=active_workout_id,
                today=today if today and today != "none" else None,
            )
        # Fallback for malformed messages
        return cls(conversation_id="", user_id="", correlation_id=None)
    
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
            r'\(context:\s*(?:conversation_id|canvas_id)=\S+\s+user_id=\S+\s+corr=\S+'
            r'(?:\s+workout_id=\S+)?(?:\s+today=\S+)?\)\s*',
            '',
            message
        ).strip()
    
    def is_valid(self) -> bool:
        """Check if context has required fields."""
        return bool(self.conversation_id and self.user_id)
    
    def __str__(self) -> str:
        """Format for logging."""
        corr = self.correlation_id or "none"
        if self.workout_mode and self.active_workout_id:
            return f"SessionContext(conv={self.conversation_id}, user={self.user_id}, corr={corr}, workout={self.active_workout_id})"
        return f"SessionContext(conv={self.conversation_id}, user={self.user_id}, corr={corr})"


__all__ = [
    "SessionContext",
    "set_current_context",
    "get_current_context",
    "get_current_message",
    "clear_current_context",
    "increment_search_count",
    "get_search_count",
    "MAX_SEARCH_CALLS",
]
