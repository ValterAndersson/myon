# MYON Documentation

> Documentation for the MYON agent-driven training canvas platform.
> Written for LLM/agentic coding agents with maximum context and verbosity.

---

## 🚀 Start Here: AI Coding Agent Entry Point

| Document | Purpose |
|----------|---------|
| **`SYSTEM_ARCHITECTURE.md`** | **START HERE for AI coding agents.** Cross-cutting data flows, schema contracts, common patterns, deprecated code warnings, and checklists for adding features across the stack. Prevents confusion and duplication. |

---

## Core Architecture Documentation

| Document | Purpose |
|----------|---------|
| **`platformvision.md`** | High-level platform vision and implemented functionality. Use as context reference. |
| **`SYSTEM_ARCHITECTURE.md`** | **Data flows and contracts.** How data moves between iOS → Firebase → Agent → Firestore. Schema shapes, auth patterns, error handling. |
| **`IOS_ARCHITECTURE.md`** | Complete iOS application architecture: MVVM structure, services, repositories, canvas components, design system. |
| **`FIREBASE_FUNCTIONS_ARCHITECTURE.md`** | Firebase Functions backend layer: all HTTP endpoints, triggers, scheduled jobs, auth middleware. |
| **`FIRESTORE_SCHEMA.md`** | Detailed Firestore data model with field-level specifications, triggers, and automatic mutations. |
| **`MULTI_AGENT_ARCHITECTURE.md`** | Agent system architecture (Orchestrator → Coach/Planner/Copilot). Permission boundaries, tools, intent taxonomy. |
| **`THINKING_STREAM_ARCHITECTURE.md`** | Tool display text architecture for agent thinking streams. How `_display` metadata flows from Python agents to iOS UI. |

---

## Reference Documents

| Document | Purpose |
|----------|---------|
| `PLANNING_UX_POLISH_IMPLEMENTATION.md` | Implementation checklist for UI polish items |
| `catalog_admin_agent_review.md` | Catalog admin agent robustness patterns and review |

---

## Quick Reference

### Where to Find What

| Topic | Document | Section |
|-------|----------|---------|
| Canvas architecture | platformvision.md | Canvas Architecture |
| Card types | platformvision.md | Card Types |
| Action types | platformvision.md | Action Types |
| Agent tools | MULTI_AGENT_ARCHITECTURE.md | Agent sections |
| iOS services | IOS_ARCHITECTURE.md | Services Layer |
| iOS canvas views | IOS_ARCHITECTURE.md | Canvas System |
| Firebase endpoints | FIREBASE_FUNCTIONS_ARCHITECTURE.md | Function Categories |
| Firestore collections | FIRESTORE_SCHEMA.md | Collection Structure |
| Analytics data model | platformvision.md | Analytics System |
| Routine cursor | platformvision.md | Routine System |
| Caching strategy | platformvision.md | Caching Strategy |

### Key Source Files

| Category | Location |
|----------|----------|
| **iOS** | |
| Canvas ViewModel | `MYON2/MYON2/ViewModels/CanvasViewModel.swift` |
| Canvas Screen | `MYON2/MYON2/Views/CanvasScreen.swift` |
| Card Components | `MYON2/MYON2/UI/Canvas/Cards/` |
| Design Tokens | `MYON2/MYON2/UI/DesignSystem/Tokens.swift` |
| **Firebase Functions** | |
| Canvas reducer | `firebase_functions/functions/canvas/apply-action.js` |
| Card schemas | `firebase_functions/functions/canvas/schemas/card_types/` |
| Index/exports | `firebase_functions/functions/index.js` |
| Firestore triggers | `firebase_functions/functions/triggers/` |
| **Agent System** | |
| Orchestrator | `adk_agent/canvas_orchestrator/app/agents/orchestrator.py` |
| Planner Agent | `adk_agent/canvas_orchestrator/app/agents/planner_agent.py` |
| Coach Agent | `adk_agent/canvas_orchestrator/app/agents/coach_agent.py` |
| Shared Voice | `adk_agent/canvas_orchestrator/app/agents/shared_voice.py` |
