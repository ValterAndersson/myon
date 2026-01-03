# Archived: Legacy Multi-Agent Architecture

This folder contains the **deprecated** "Router + Sub-Agents" architecture that was replaced by the unified Shell Agent.

## Why Archived?

The old architecture had several issues:

1. **Fragmented UX** - Transferring control between CoachAgent and PlannerAgent caused persona drift
2. **Dead Ends** - One agent couldn't help with another's domain
3. **Global State Leakage** - Session context was scattered across multiple agent instances
4. **Latency** - Every request went through the LLM, even simple copilot commands

## What's Here?

```
_archived/
├── agents/
│   ├── coach_agent.py      # Old coaching chat agent
│   ├── copilot_agent.py    # Old copilot chat agent  
│   ├── orchestrator.py     # Old router (LangGraph style)
│   ├── planner_agent.py    # Old planning chat agent
│   ├── shared_voice.py     # Shared prompt fragments
│   └── tools/              # Old tool definitions
├── agent.py                # Old single agent wrapper
└── agent_multi.py          # Old multi-agent with fallback
```

## New Architecture

See `app/shell/` for the unified Shell Agent with:

- **4-Lane Pipeline** (Fast → Functional → Slow → Critic)
- **Single Persona** with consistent voice
- **Skills as Modules** instead of chat agents
- **Explicit State Management** via SessionContext

Documentation: `docs/SHELL_AGENT_ARCHITECTURE.md`

## Can I Delete This?

Yes, once you're confident the new system works. This is kept for reference and rollback capability.
