"""
Shell Agent - Single unified agent with consistent persona.

Replaces the Router + Sub-Agents architecture with:
- Fast Lane: Regex patterns → direct skill execution (no LLM)
- Slow Lane: ShellAgent (gemini-2.5-pro) with unified instruction

Modules:
- context: Per-request context (no global state)
- router: Fast/Slow lane routing
- instruction: Unified Coach + Planner instruction
- agent: ShellAgent definition
- safety_gate: Write operation confirmation
- critic: Response validation for complex advice
"""

from app.shell.context import SessionContext
from app.shell.router import (
    Lane,
    RoutingResult,
    route_message,
    execute_fast_lane,
)
from app.shell.agent import ShellAgent, create_shell_agent
from app.shell.safety_gate import (
    WriteOperation,
    SafetyDecision,
    check_safety_gate,
    check_message_for_confirmation,
    format_confirmation_prompt,
)
from app.shell.critic import (
    CriticSeverity,
    CriticFinding,
    CriticResult,
    run_critic,
    should_run_critic,
)

__all__ = [
    # Context
    "SessionContext",
    # Router
    "Lane",
    "RoutingResult",
    "route_message",
    "execute_fast_lane",
    # Agent
    "ShellAgent",
    "create_shell_agent",
    # Safety Gate
    "WriteOperation",
    "SafetyDecision",
    "check_safety_gate",
    "check_message_for_confirmation",
    "format_confirmation_prompt",
    # Critic
    "CriticSeverity",
    "CriticFinding",
    "CriticResult",
    "run_critic",
    "should_run_critic",
]
