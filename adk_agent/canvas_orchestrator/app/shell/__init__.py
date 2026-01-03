"""
Shell Agent - Single unified agent with Coach persona.

This module implements the simplified Single Shell Agent architecture:
- Router: Fast lane bypass for copilot commands
- ShellAgent: Unified agent with all tools (Planning + Coaching)
- Skills: Pure Python functions, no globals

The Shell Agent uses gemini-2.5-pro for complex reasoning.
Fast lane requests bypass the LLM entirely for sub-500ms response times.
"""

from app.shell.agent import root_agent, ShellAgent, handle_message
from app.shell.context import SessionContext
from app.shell.router import route_message, Lane

__all__ = [
    "root_agent",
    "ShellAgent",
    "handle_message",
    "SessionContext",
    "route_message",
    "Lane",
]
