"""Agent core primitives for session, memory, tools, and streaming.

This package is intentionally minimal at first. It provides interfaces and
thin utilities that higher-level agent apps can depend on without pulling in
any app-specific logic.
"""

__all__ = [
    "version",
]

version: str = "0.1.0"


