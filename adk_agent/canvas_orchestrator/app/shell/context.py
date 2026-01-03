"""
SessionContext - Per-request context only.

No persistent state. No flow memory. Stateless by design.
The LLM reads conversation history to understand multi-turn context.

This replaces the global _context dictionaries that were causing
state leakage between requests in coach_agent.py and planner_agent.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)  # Immutable
class SessionContext:
    """
    Per-request context extracted from message prefix.
    
    This is NOT persistent across requests. Each request creates a new
    SessionContext from the message prefix.
    
    Format: (context: canvas_id=X user_id=Y corr=Z) message
    """
    canvas_id: str
    user_id: str
    correlation_id: Optional[str]
    
    @classmethod
    def from_message(cls, message: str) -> "SessionContext":
        """
        Parse context from message prefix.
        
        Expected format: (context: canvas_id=X user_id=Y corr=Z) message
        
        Args:
            message: Raw message with optional context prefix
            
        Returns:
            SessionContext with parsed values, or empty context if parsing fails
        """
        match = re.search(
            r'\(context:\s*canvas_id=(\S+)\s+user_id=(\S+)\s+corr=(\S+)\)', 
            message
        )
        if match:
            corr = match.group(3).strip()
            return cls(
                canvas_id=match.group(1).strip(),
                user_id=match.group(2).strip(),
                correlation_id=corr if corr != "none" else None,
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
            r'\(context:\s*canvas_id=\S+\s+user_id=\S+\s+corr=\S+\)\s*', 
            '', 
            message
        ).strip()
    
    def is_valid(self) -> bool:
        """Check if context has required fields."""
        return bool(self.canvas_id and self.user_id)
    
    def __str__(self) -> str:
        """Format for logging."""
        corr = self.correlation_id or "none"
        return f"SessionContext(canvas={self.canvas_id}, user={self.user_id}, corr={corr})"


__all__ = ["SessionContext"]
