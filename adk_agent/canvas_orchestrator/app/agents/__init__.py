"""
Multi-Agent Architecture for Canvas Orchestrator.

This module implements a scalable multi-agent system with:
- Orchestrator: Intent classification and routing
- Planner: Workout/routine draft creation (the workhorse)
- Coach: Education and explanation
- Analysis: Progress analysis artifacts with evidence-based recommendations
- Copilot: Live workout execution

Permission boundaries are enforced at the code level, not prompts.
"""

from app.agents.orchestrator import initialize_root_agent

# Initialize the orchestrator with all sub-agents
root_agent = initialize_root_agent()

__all__ = ["root_agent"]
