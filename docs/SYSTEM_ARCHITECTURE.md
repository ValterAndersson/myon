# POVVER System Architecture

> **AI AGENT CONTEXT DOCUMENT**
> 
> This document is optimized for LLM/AI consumption. It provides explicit file paths, 
> complete data schemas, and decision tables to enable accurate code generation without ambiguity.
>
> **Last Updated**: 2026-01-03
> **Branch**: main
> **Repository Root**: /Users/valterandersson/Documents/Povver

---

## CRITICAL: File Path Reference Table (ABSOLUTE PATHS)

| Component | Absolute Path | Purpose |
|-----------|---------------|---------|
| **iOS App Entry** | `Povver/Povver/PovverApp.swift` | SwiftUI app entry |
| **iOS Canvas Screen** | `Povver/Povver/Views/CanvasScreen.swift` | Main chat/canvas UI |
| **iOS Workout Screen** | `Povver/Povver/UI/FocusMode/FocusModeWorkoutScreen.swift` | Active workout UI |
| **iOS Streaming Service** | `Povver/Povver/Services/DirectStreamingService.swift` | Agent communication |
| **iOS Workout Service** | `Povver/Povver/Services/FocusModeWorkoutService.swift` | Workout API calls |
| **Agent Entry Point** | `adk_agent/canvas_orchestrator/app/agent_engine_app.py` | Vertex AI entry |
| **Agent Router** | `adk_agent/canvas_orchestrator/app/shell/router.py` | 4-Lane routing |
| **Agent Skills** | `adk_agent/canvas_orchestrator/app/skills/` | Pure logic modules |
| **Firebase Index** | `firebase_functions/functions/index.js` | All Cloud Functions |
| **Active Workout APIs** | `firebase_functions/functions/active_workout/` | Workout endpoints |

---

## Quick Reference: Layer Map

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                             POVVER ARCHITECTURE                                 │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │ iOS App (Povver/Povver/)                                                 │   │
│  │  Views → ViewModels → Services/Repositories → Firebase SDK             │   │
│  └───────────────────────────────────┬─────────────────────────────────────┘   │
│                                      │                                          │
│                    HTTP/SSE          │  Firestore Listeners                     │
│                                      │                                          │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │ Firebase Functions (firebase_functions/)                                │   │
│  │  HTTP endpoints → Business logic → Firestore reads/writes              │   │
│  └───────────────────────────────────┬─────────────────────────────────────┘   │
│                                      │                                          │
│                    HTTP              │  Service Account                         │
│                                      │                                          │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │ Agent System (adk_agent/)                                               │   │
│  │  Vertex AI → Orchestrator → Sub-agents → Tools → Firebase Functions    │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │ Firestore (source of truth)                                             │   │
│  │  users/{uid}/canvases, routines, templates, workouts, active_workouts  │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Critical Data Flows

### 1. Canvas Conversation Flow (User → Agent → Cards)

```
User types message in iOS
        │
        ▼
iOS: DirectStreamingService.streamQuery()
        │ POST /streamAgentNormalized
        ▼
Firebase: stream-agent-normalized.js
        │ Opens SSE to Vertex AI
        ▼
Agent: orchestrator.py classifies intent
        │ Routes to Planner/Coach/Copilot
        ▼
Agent: planner_agent.tool_propose_routine()
        │ HTTP POST to Firebase
        ▼
Firebase: propose-cards.js
        │ Writes to Firestore
        ▼
Firestore: canvases/{id}/cards/{cardId} created
        │
        ▼ (listener fires)
iOS: CanvasRepository snapshot listener
        │
        ▼
iOS: CanvasViewModel.cards updated
        │
        ▼
iOS: UI renders new card
```

**Files involved** (CURRENT PATHS):
- `Povver/Povver/Services/DirectStreamingService.swift` ← iOS streaming
- `firebase_functions/functions/strengthos/stream-agent-normalized.js`
- `adk_agent/canvas_orchestrator/app/shell/router.py` ← Routes intent
- `adk_agent/canvas_orchestrator/app/skills/planner_skills.py` ← Creates cards
- `firebase_functions/functions/canvas/propose-cards.js`
- `Povver/Povver/Repositories/CanvasRepository.swift`
- `Povver/Povver/ViewModels/CanvasViewModel.swift`

---

### 2. Accept Routine Proposal Flow

```
User taps "Accept" on routine_summary card
        │
        ▼
iOS: applyAction(type: "ACCEPT_PROPOSAL", cardId)
        │ POST /applyAction
        ▼
Firebase: apply-action.js
        │ Calls createRoutineFromDraftCore()
        ▼
Firebase: create-routine-from-draft.js
        │ Creates templates + routine
        ▼
Firestore: templates/{id} created (one per day)
Firestore: routines/{id} created
Firestore: users/{uid}.activeRoutineId set
Firestore: cards marked status='accepted'
        │
        ▼ (listeners fire)
iOS: CanvasRepository emits snapshot
iOS: RoutineRepository listener receives new routine
```

**Files involved** (CURRENT PATHS):
- `Povver/Povver/Services/CanvasActions.swift` → `applyAction()`
- `firebase_functions/functions/canvas/apply-action.js`
- `firebase_functions/functions/routines/create-routine-from-draft.js`
- `firebase_functions/functions/utils/plan-to-template-converter.js`

---

### 3. Start Workout Flow

```
User taps "Start Workout" (from routine or template)
        │
        ▼
iOS: ActiveWorkoutManager.startWorkout(templateId, routineId?)
        │ POST /startActiveWorkout
        ▼
Firebase: start-active-workout.js
        │ Fetches template, creates active_workout
        ▼
Firestore: active_workouts/{id} created
  {
    source_template_id: "...",
    source_routine_id: "...",  ← Required for cursor advancement!
    exercises: [...],
    status: "in_progress"      // in_progress | completed | cancelled
  }
        │
        ▼
iOS: Returns workout_id, iOS navigates to workout view
```

**Files involved** (CURRENT PATHS):
- `Povver/Povver/Services/FocusModeWorkoutService.swift` ← startWorkout()
- `firebase_functions/functions/active_workout/start-active-workout.js`

---

### 4. Complete Workout Flow (with Routine Cursor)

```
User taps "Finish Workout"
        │
        ▼
iOS: FocusModeWorkoutService.finishWorkout()
        │ POST /completeActiveWorkout
        ▼
Firebase: complete-active-workout.js
        │ Archives workout with analytics
        ▼
Firestore: workouts/{newId} created
  {
    source_routine_id: "...",
    source_template_id: "...",
    end_time: ...,
    analytics: {...}
  }
        │
        ▼ (onCreate trigger fires)
Firebase: workout-routine-cursor.js
        │ Updates routine cursor
        ▼
Firestore: routines/{id} updated
  {
    last_completed_template_id: "...",
    last_completed_at: ...
  }
        │
        ▼
Next get-next-workout.js call uses cursor for O(1) lookup
```

**Files involved** (CURRENT PATHS):
- `Povver/Povver/Services/FocusModeWorkoutService.swift` ← finishWorkout()
- `firebase_functions/functions/active_workout/complete-active-workout.js`
- `firebase_functions/functions/triggers/workout-routine-cursor.js`
- `firebase_functions/functions/routines/get-next-workout.js`

---

## Schema Contracts (Cross-Boundary Data Shapes)

### Canvas Card (Agent → Firestore → iOS)

```json
// Firestore: users/{uid}/canvases/{canvasId}/cards/{cardId}
{
  "id": "card_abc123",
  "type": "session_plan",              // Card type
  "status": "proposed",                 // proposed | accepted | dismissed
  "lane": "artifact",                   // artifact | suggestion | system
  "created_at": Timestamp,
  "updated_at": Timestamp,
  "meta": {
    "groupId": "group_xyz",            // Links cards in same proposal
    "draftId": "draft_123",            // For routine_summary only
    "sourceTemplateId": "...",         // If editing existing template
    "sourceRoutineId": "..."           // If editing existing routine
  },
  "content": { ... }                   // Type-specific payload
}
```

**iOS mapping**: `CanvasMapper.mapCard()` → `CanvasCardModel`

---

### Routine (Firestore → iOS)

```json
// Firestore: users/{uid}/routines/{routineId}
{
  "id": "routine_abc",
  "name": "Push/Pull/Legs",
  "description": "3-day split",
  "template_ids": ["t1", "t2", "t3"],  // Ordered list
  "frequency": 3,
  "created_at": Timestamp,
  "updated_at": Timestamp,
  
  // Cursor fields (updated by trigger)
  "last_completed_template_id": "t2",
  "last_completed_at": Timestamp
}
```

**iOS model**: (legacy - routines handled via CanvasActions now)

---

### Template (Firestore → iOS)

```json
// Firestore: users/{uid}/templates/{templateId}
{
  "id": "template_abc",
  "name": "Push Day",
  "user_id": "uid",
  "exercises": [
    {
      "exercise_id": "ex_bench",
      "name": "Bench Press",           // Denormalized for display
      "sets": [
        { "target_reps": 8, "target_rir": 2 }
      ]
    }
  ],
  "analytics": {
    "estimated_duration_minutes": 45,
    "total_sets": 15,
    "muscles": ["chest", "triceps", "shoulders"]
  },
  "created_at": Timestamp,
  "updated_at": Timestamp
}
```

**iOS model**: `Povver/Povver/Models/WorkoutTemplate.swift`

---

### Active Workout (Firestore → iOS)

```json
// Firestore: users/{uid}/active_workouts/{workoutId}
{
  "id": "active_abc",
  "user_id": "uid",
  "source_template_id": "template_xyz",
  "source_routine_id": "routine_abc",   // Required for cursor advancement
  "status": "in_progress",              // in_progress | completed | cancelled
  "start_time": Timestamp,
  "exercises": [
    {
      "exercise_id": "ex_bench",
      "name": "Bench Press",
      "sets": [
        { 
          "set_index": 0,
          "target_reps": 8,
          "target_rir": 2,
          "weight": 80,                // Actual (null if not logged)
          "reps": 8,                   // Actual (null if not logged)
          "completed_at": Timestamp    // null if not logged
        }
      ]
    }
  ],
  "totals": {
    "sets": 5,
    "reps": 40,
    "volume": 3200
  },
  "created_at": Timestamp,
  "updated_at": Timestamp
}
```

**iOS model**: `Povver/Povver/Models/FocusModeModels.swift` (FocusModeWorkout)

---

## Common Patterns

### Authentication Lanes

Firebase Functions use **two mutually exclusive authentication lanes**. Never mix these in a single endpoint.

**Bearer Lane (Firebase Auth Token)**
- Used by: iOS app, authenticated user requests
- userId: Derived from `req.auth.uid` **only**
- **All client-provided userId parameters are ignored** (security requirement)
- Example: Focus Mode workout operations, user data access

**Service Lane (API Key)**
- Used by: Agent system, service-to-service calls
- userId: From `req.body.userId` or `req.query.userId` (trusted)
- Authenticated via `x-api-key` header
- Example: Agent writing canvas cards, catalog admin operations

```javascript
// BEARER LANE - user-facing endpoints
// userId MUST come from auth token, never from request params
const userId = req.auth.uid;  // ← Only source of truth
// Any req.body.userId or req.query.userId is IGNORED

// SERVICE LANE - agent/service endpoints  
// userId from request body (trusted service-to-service)
const userId = req.body?.userId || req.query?.userId;
```

**Security Rule**: Bearer-authenticated endpoints must never trust client-provided userId. This prevents cross-user data exposure.

### Error Response Format

```javascript
// Success
return ok(res, { data: {...} });

// Error
return fail(res, 'NOT_FOUND', 'Resource not found', { details }, 404);

// Response shape:
{
  "success": true,
  "data": {...}
}
// or
{
  "success": false,
  "error": {
    "code": "NOT_FOUND",
    "message": "Resource not found",
    "details": {...}
  }
}
```

### Idempotency

```javascript
// Apply-action uses idempotency_key to prevent duplicate writes
{
  "action": {
    "type": "ACCEPT_PROPOSAL",
    "card_id": "...",
    "idempotency_key": "uuid-v4"  // Client-generated
  }
}

// Server checks: if (await Idempotency.check(key)) return cached response
```

### Version Conflict Handling

```javascript
// Canvas uses optimistic concurrency
{
  "expected_version": 5,  // Client's current version
  "action": {...}
}

// If state.version != expected_version:
return fail(res, 'STALE_VERSION', 'Version conflict');

// iOS retries once with fresh version
```

---

## Adding a New Field (Cross-Stack Checklist)

When adding a new field (e.g., `routine.goal`):

1. **Firestore Schema** (`docs/FIRESTORE_SCHEMA.md`)
   - Add field to collection documentation

2. **Firebase Function - Write**
   - `create-routine-from-draft.js` - Add to routineData
   - `patch-routine.js` - Add to allowed update fields

3. **Firebase Function - Read**
   - `get-routine.js` - Already returns full doc
   - `get-planning-context.js` - Check if included

4. **iOS Model**
   - `Povver/Povver/Models/*.swift` - Add property
   - Ensure `Codable` picks it up

5. **iOS Repository**
   - Usually automatic via Firestore SDK

6. **iOS UI**
   - Add to relevant views (RoutineDetailView, etc.)

7. **Agent Schema** (if agent needs to write it)
   - `canvas/schemas/card_types/routine_summary.schema.json`
   - Agent prompt instructions

---

## Deprecated / Legacy Code

### Files to Avoid

| File | Reason | Replacement |
|------|--------|-------------|
| `Povver/Povver/Archived/CloudFunctionProxy.swift` | Old HTTP wrapper | `CanvasService.swift` |
| `Povver/Povver/Archived/StrengthOSClient.swift` | Old API client | `CloudFunctionService.swift` |
| `routines/create-routine.js` | Manual routine creation | `create-routine-from-draft.js` |
| `routines/update-routine.js` | Direct update | `patch-routine.js` |
| `templates/update-template.js` | Direct update | `patch-template.js` |

### Legacy Field Names

| Legacy | Current | Notes |
|--------|---------|-------|
| `templateIds` | `template_ids` | get-next-workout handles both |
| `weight` | `weight_kg` | Normalized on archive |

### Unused Functions to Consider Removing

| Function | Status | Notes |
|----------|--------|-------|
| `canvas/expire-proposals.js` | May be unused | Check if scheduled job uses |
| `aliases/upsert-alias.js` | Low usage | Part of exercise catalog admin |
| `maintenance/*.js` | One-time scripts | Consider archiving |

---

## Agent Architecture: 4-Lane Shell Agent (CURRENT)

> **CRITICAL**: The old multi-agent architecture (CoachAgent, PlannerAgent, Orchestrator) 
> is DEPRECATED and moved to `adk_agent/canvas_orchestrator/_archived/`. 
> DO NOT import from that folder. All new code uses the Shell Agent.

### Architecture Decision Record

| Decision | Rationale |
|----------|-----------|
| Single Shell Agent | Unified persona, no "dead ends" |
| 4-Lane Routing | Fast lane bypasses LLM for <500ms copilot |
| Skills as Modules | Pure functions, not chat agents |
| ContextVars for State | Thread-safe in async serverless |

### Shell Agent File Map

```
adk_agent/canvas_orchestrator/
├── app/
│   ├── agent_engine_app.py     ← ENTRY POINT (Vertex AI)
│   ├── shell/                   ← 4-LANE PIPELINE
│   │   ├── router.py            ← Determines lane
│   │   ├── context.py           ← Per-request SessionContext
│   │   ├── agent.py             ← ShellAgent (gemini-2.5-pro)
│   │   ├── tools.py             ← Tool wrappers
│   │   ├── planner.py           ← Intent-based planning
│   │   ├── critic.py            ← Response validation
│   │   ├── safety_gate.py       ← Write confirmation
│   │   ├── functional_handler.py ← JSON/Flash lane
│   │   └── instruction.py       ← System prompt
│   ├── skills/                  ← PURE LOGIC (Shared Brain)
│   │   ├── coach_skills.py      ← Analytics, user data
│   │   ├── planner_skills.py    ← Artifact creation
│   │   ├── copilot_skills.py    ← Set logging, workout
│   │   └── gated_planner.py     ← Safety-gated writes
│   └── libs/                    ← Utilities
├── workers/                     ← BACKGROUND JOBS
│   └── post_workout_analyst.py  ← Post-workout insights
└── _archived/                   ← DEPRECATED (do not use)
```

### 4-Lane Routing Decision Table

| Input Pattern | Lane | Model | Latency | Handler |
|---------------|------|-------|---------|---------|
| `"done"`, `"8 @ 100"`, `"next set"` | FAST | None | <500ms | `copilot_skills.*` |
| `{"intent": "SWAP_EXERCISE", ...}` | FUNCTIONAL | Flash | <1s | `functional_handler.py` |
| `"create a PPL routine"` | SLOW | Pro | 2-5s | `shell/agent.py` |
| PubSub `workout_completed` | WORKER | Pro | N/A | `post_workout_analyst.py` |

### Tool Permission Matrix (Shell Agent)

| Skill Function | Read | Write | Safety Gate |
|----------------|------|-------|-------------|
| `get_training_context()` | ✅ | - | No |
| `get_analytics_features()` | ✅ | - | No |
| `search_exercises()` | ✅ | - | No |
| `get_recent_workouts()` | ✅ | - | No |
| `propose_workout()` | - | ✅ | **Yes** |
| `propose_routine()` | - | ✅ | **Yes** |
| `log_set()` | - | ✅ | No (Fast Lane) |

### Context Flow (SECURITY CRITICAL)

```
agent_engine_app.py::stream_query()
    │
    ├─→ 1. Parse context: ctx = SessionContext.from_message(message)
    │
    ├─→ 2. Set context: set_current_context(ctx, message)  ← MUST BE FIRST
    │
    ├─→ 3. Route: routing = route_request(message)
    │
    └─→ 4. Execute lane with ctx in ContextVar
```

**Security**: `user_id` comes from authenticated request, NOT from LLM.
Tool functions call `get_current_context()` to retrieve verified user_id.

See `docs/SHELL_AGENT_ARCHITECTURE.md` for exhaustive details.

---

## Key Firestore Indexes

See `firebase_functions/firestore.indexes.json` for composite indexes.

**Critical queries requiring indexes**:
- `workouts` ordered by `end_time desc` (for get-recent-workouts)
- `cards` filtered by `type` and `status` (for accept-all-in-group)
- `workspace_entries` ordered by `created_at` (for conversation history)

---

## Summary for AI Coding Agents

**When working on this codebase**:

1. **Check this doc first** for data flow understanding
2. **Look at related files** listed in flow diagrams
3. **Follow schema contracts** for field names/types
4. **Use common patterns** for auth, errors, idempotency
5. **Avoid deprecated files** listed above
6. **Respect agent boundaries** for tool permissions

**When adding features**:
1. Trace the full data flow (all layers)
2. Update schemas if needed
3. Add to FIRESTORE_SCHEMA.md if new collection/field
4. Consider which agent(s) need tool access
