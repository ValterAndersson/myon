# POVVER System Architecture

> **AI AGENT CONTEXT DOCUMENT**
> 
> This document is optimized for LLM/AI consumption. It provides explicit file paths, 
> complete data schemas, and decision tables to enable accurate code generation without ambiguity.
>
> **Last Updated**: 2026-02-16
> **Branch**: main
> **Repository Root**: /Users/valterandersson/Documents/Povver

---

## CRITICAL: File Path Reference Table (ABSOLUTE PATHS)

| Component | Absolute Path | Purpose |
|-----------|---------------|---------|
| **iOS App Entry** | `Povver/Povver/PovverApp.swift` | SwiftUI app entry + Google URL handler |
| **iOS Auth Service** | `Povver/Povver/Services/AuthService.swift` | Multi-provider auth (email, Google, Apple) |
| **iOS Auth Provider** | `Povver/Povver/Models/AuthProvider.swift` | Provider enum mapping |
| **iOS Apple Coordinator** | `Povver/Povver/Services/AppleSignInCoordinator.swift` | ASAuth delegate wrapper |
| **iOS Root Navigation** | `Povver/Povver/Views/RootView.swift` | Reactive auth state navigation |
| **iOS Conversation Screen** | `Povver/Povver/Views/ConversationView.swift` | Main chat UI with inline artifacts |
| **iOS Workout Screen** | `Povver/Povver/UI/FocusMode/FocusModeWorkoutScreen.swift` | Active workout UI |
| **iOS Streaming Service** | `Povver/Povver/Services/DirectStreamingService.swift` | Agent communication |
| **iOS Conversation Service** | `Povver/Povver/Services/ConversationService.swift` | Artifact actions |
| **iOS Workout Service** | `Povver/Povver/Services/FocusModeWorkoutService.swift` | Workout API calls |
| **iOS Session Logger** | `Povver/Povver/Services/WorkoutSessionLogger.swift` | On-device workout event log (JSON) |
| **Agent Entry Point** | `adk_agent/canvas_orchestrator/app/agent_engine_app.py` | Vertex AI entry |
| **Agent Router** | `adk_agent/canvas_orchestrator/app/shell/router.py` | 4-Lane routing |
| **Agent Skills** | `adk_agent/canvas_orchestrator/app/skills/` | Pure logic modules |
| **Agent Workout Skills** | `adk_agent/canvas_orchestrator/app/skills/workout_skills.py` | Workout brief + mutation skills |
| **iOS Workout Coach VM** | `Povver/Povver/ViewModels/WorkoutCoachViewModel.swift` | Workout chat state |
| **iOS Workout Coach View** | `Povver/Povver/UI/FocusMode/WorkoutCoachView.swift` | Compact gym chat UI |
| **iOS Subscription Service** | `Povver/Povver/Services/SubscriptionService.swift` | StoreKit 2 purchase/entitlements |
| **iOS Subscription Models** | `Povver/Povver/Models/SubscriptionStatus.swift` | Tier/status enums, UserSubscriptionState |
| **iOS Paywall** | `Povver/Povver/Views/PaywallView.swift` | Purchase sheet with trial CTA |
| **iOS Subscription Settings** | `Povver/Povver/Views/Settings/SubscriptionView.swift` | Subscription management |
| **Recommendation Triggers** | `firebase_functions/functions/triggers/process-recommendations.js` | Analysis → recommendation pipeline |
| **Review Endpoint** | `firebase_functions/functions/recommendations/review-recommendation.js` | Accept/reject recommendations |
| **iOS Recommendation Model** | `Povver/Povver/Models/AgentRecommendation.swift` | Codable recommendation structs |
| **iOS Recommendation VM** | `Povver/Povver/ViewModels/RecommendationsViewModel.swift` | Recommendation state + actions |
| **Subscription Gate** | `firebase_functions/functions/utils/subscription-gate.js` | `isPremiumUser()` check |
| **App Store Webhook** | `firebase_functions/functions/subscriptions/app-store-webhook.js` | V2 server notifications |
| **Firebase Index** | `firebase_functions/functions/index.js` | All Cloud Functions |
| **Conversation APIs** | `firebase_functions/functions/conversations/` | Artifact actions |
| **Active Workout APIs** | `firebase_functions/functions/active_workout/` | Workout endpoints |
| **Session APIs** | `firebase_functions/functions/sessions/` | Session initialization |

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
│  │  users/{uid}/conversations, routines, templates, workouts, active_wks  │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Critical Data Flows

### 1. Conversation Flow with Inline Artifacts (User → Agent → SSE)

```
User types message in iOS
        │
        ▼
iOS: DirectStreamingService.streamQuery()
        │ POST /streamAgentNormalized (conversationId)
        ▼
Firebase: stream-agent-normalized.js
        │ Writes message to conversations/{id}/messages
        │ Opens SSE to Vertex AI
        │ (At stream end: fire-and-forget title generation via Gemini Flash
        │  → writes `title` to canvases/{id} + conversations/{id})
        ▼
Agent: shell/router.py classifies intent
        │ Routes to Fast/Functional/Slow lane
        ▼
Agent: planner_skills.propose_routine()
        │ Returns artifact data in SkillResult
        ▼
Agent: shell/agent.py emits SSE artifact event
        │ {type: "artifact", data: {...}, artifactId: "..."}
        ▼
iOS: DirectStreamingService receives artifact event
        │ Converts to CanvasCardModel (reuses renderers)
        ▼
iOS: ConversationViewModel appends artifact
        │
        ▼
iOS: UI renders artifact inline with messages
```

**Files involved** (CURRENT PATHS):
- `Povver/Povver/Services/DirectStreamingService.swift` ← iOS streaming
- `firebase_functions/functions/strengthos/stream-agent-normalized.js`
- `adk_agent/canvas_orchestrator/app/shell/router.py` ← Routes intent
- `adk_agent/canvas_orchestrator/app/skills/planner_skills.py` ← Returns artifacts
- `Povver/Povver/ViewModels/ConversationViewModel.swift`
- `Povver/Povver/Views/ConversationView.swift`

---

### 2. Accept Artifact Flow

```
User taps "Accept" on routine_summary artifact
        │
        ▼
iOS: artifactAction(action: "accept", artifactId, conversationId)
        │ POST /artifactAction
        ▼
Firebase: artifact-action.js
        │ Routes based on artifact type
        ▼
Firebase: create-routine-from-draft.js
        │ Creates templates + routine
        ▼
Firestore: templates/{id} created (one per day)
Firestore: routines/{id} created
Firestore: users/{uid}.activeRoutineId set
Firestore: conversations/{id}/artifacts/{artifactId} updated (status='accepted')
        │
        ▼ (listeners fire)
iOS: ConversationRepository listener sees artifact update
iOS: RoutineRepository listener receives new routine
```

**Files involved** (CURRENT PATHS):
- `Povver/Povver/Services/ConversationService.swift` → `artifactAction()`
- `firebase_functions/functions/conversations/artifact-action.js`
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
iOS: FocusModeWorkoutService drains pending syncs
        │ Awaits all in-flight logSet/patchField calls
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

### 5. Workout Coaching Flow (Active Workout + Agent)

```
User taps Coach button during active workout
        │
        ▼
iOS: WorkoutCoachView presents compact chat sheet
        │ User sends message (e.g., "log 8 at 100")
        ▼
iOS: WorkoutCoachViewModel.send()
        │ Calls DirectStreamingService.streamQuery(workoutId: workout.id)
        ▼
Firebase: stream-agent-normalized.js
        │ Builds context prefix: (context: conversation_id=X user_id=Y corr=Z workout_id=W today=YYYY-MM-DD)
        │ Opens SSE to Vertex AI
        ▼
Agent: agent_engine_app.py::stream_query()
        │ 1. Parses workout_id from context → ctx.workout_mode = true
        │ 2. Routes message (Fast/Functional/Slow)
        │ 3. If Slow Lane: front-loads Workout Brief (~1350 tokens)
        │    - Parallel fetch: getActiveWorkout + getAnalysisSummary
        │    - Sequential: getExerciseSummary (current exercise)
        │    - Formats as [WORKOUT BRIEF] text prepended to message
        │ 4. LLM sees: brief + user message + workout instruction overlay
        │ 5. LLM calls workout tools as needed (tool_log_set, etc.)
        ▼
Agent tools (via workout_skills.py):
        │ tool_log_set → client.log_set → Firebase logSet
        │ tool_add_exercise → client.add_exercise → Firebase addExercise
        │ tool_prescribe_set → client.patch_active_workout → Firebase patchActiveWorkout
        │ tool_swap_exercise → search + client.swap_exercise → Firebase swapExercise
        │ tool_complete_workout → client.complete_active_workout → Firebase completeActiveWorkout
        ▼
Firebase: Active workout endpoints mutate Firestore
        │
        ▼ (Firestore listener fires)
iOS: FocusModeWorkoutService receives updated workout state
```

**Files involved** (CURRENT PATHS):
- `Povver/Povver/UI/FocusMode/WorkoutCoachView.swift` ← Compact chat sheet
- `Povver/Povver/ViewModels/WorkoutCoachViewModel.swift` ← Ephemeral chat VM
- `Povver/Povver/Services/DirectStreamingService.swift` ← streamQuery(workoutId:)
- `firebase_functions/functions/strengthos/stream-agent-normalized.js` ← workout_id in context
- `adk_agent/canvas_orchestrator/app/agent_engine_app.py` ← Workout Brief injection
- `adk_agent/canvas_orchestrator/app/shell/context.py` ← SessionContext (workout_mode, today)
- `adk_agent/canvas_orchestrator/app/skills/workout_skills.py` ← Brief builder + mutations
- `adk_agent/canvas_orchestrator/app/shell/tools.py` ← 6 workout tool wrappers
- `adk_agent/canvas_orchestrator/app/shell/instruction.py` ← ACTIVE WORKOUT MODE section

**Design decisions**:
- Same Vertex AI deployment, mode-based switching (no second agent)
- Workout Brief front-loaded once per request (not per LLM turn)
- Fast Lane still works in workout mode (bypasses brief fetch for <500ms)
- Chat is ephemeral (in-memory, not persisted to Firestore)
- Instruction overlay enforces 2-sentence max responses for gym context

---

## Conversation & Artifact Architecture

### Design Principles

The conversation system is a lightweight replacement for the previous canvas architecture. Key differences:

| Aspect | Old Canvas | New Conversations |
|--------|-----------|-------------------|
| **State Management** | Transactional reducer with version checking | Simple message append + optional artifact storage |
| **Artifact Delivery** | Firestore subcollection → listener | SSE events → in-memory |
| **Persistence** | 5 subcollections (cards, workspace, actions, drafts, events) | 2 subcollections (messages, artifacts - optional) |
| **Complexity** | apply-action reducer, undo stack, phase state machine | Direct writes, no state machine |
| **Session Init** | openCanvas → bootstrapCanvas → propose initial cards | initialize-session → returns sessionId |

### Conversation Schema

```json
// Firestore: users/{uid}/conversations/{conversationId}
{
  "id": "conv_abc",
  "created_at": Timestamp,
  "updated_at": Timestamp,
  "title": "Push/Pull/Legs Routine",  // Optional, set after first message
  "context": {
    "workout_id": "...",              // If in workout mode
    "routine_id": "..."               // If discussing specific routine
  }
}
```

### Message Schema

```json
// Firestore: users/{uid}/conversations/{id}/messages/{msgId}
{
  "id": "msg_abc",
  "role": "user",                     // user | assistant | system
  "content": "Create a PPL routine",
  "created_at": Timestamp,
  "metadata": {
    "model": "gemini-2.5-flash",     // For assistant messages
    "lane": "slow"                   // fast | functional | slow
  }
}
```

### Artifact Lifecycle

1. **Creation**: Agent tool returns artifact data in SkillResult
2. **Delivery**: Agent emits SSE event `{type: "artifact", data: {...}, artifactId: "..."}`
3. **Display**: iOS receives SSE event, converts to CanvasCardModel, renders inline
4. **Persistence** (optional): iOS may write to `conversations/{id}/artifacts/{artifactId}` for later retrieval
5. **Action**: User taps Accept/Dismiss → calls `artifactAction` endpoint → updates artifact status + executes side effects

### SSE Event Types

| Event Type | Data | Purpose |
|------------|------|---------|
| `message_start` | `{messageId}` | Begin new assistant message |
| `text` | `{delta}` | Streaming text chunk |
| `artifact` | `{type, content, meta, artifactId}` | Inline artifact (routine, workout, etc.) |
| `message_end` | `{}` | Complete assistant message |
| `error` | `{code, message}` | Error during streaming |

### Session Management

```
iOS: ConversationViewModel.init()
        │
        ▼
iOS: initializeSession()
        │ POST /initializeSession
        ▼
Firebase: initialize-session.js
        │ Creates conversation doc if needed
        │ Returns sessionId + conversationId
        ▼
iOS: SessionPreWarmer preloads context
        │ Parallel fetch: routines, templates, recent workouts
        ▼
iOS: Ready to stream
```

**Files involved**:
- `firebase_functions/functions/sessions/initialize-session.js`
- `Povver/Povver/Services/SessionPreWarmer.swift`
- `Povver/Povver/ViewModels/ConversationViewModel.swift`

### Migration Notes

The `stream-agent-normalized.js` endpoint accepts both `conversationId` and `canvasId` (backward compatibility during migration). New clients should pass `conversationId`.

Agent context prefix changed from `canvas_id=X` to `conversation_id=X`.

---

## Schema Contracts (Cross-Boundary Data Shapes)

### Artifact (Agent → SSE → iOS, Firestore storage optional)

```json
// SSE Event: {type: "artifact", data: {...}, artifactId: "..."}
// Firestore (optional): users/{uid}/conversations/{convId}/artifacts/{artifactId}
{
  "id": "artifact_abc123",
  "type": "session_plan",              // Artifact type (routine_summary, workout_plan, etc.)
  "status": "proposed",                // proposed | accepted | dismissed
  "created_at": Timestamp,
  "updated_at": Timestamp,
  "meta": {
    "draftId": "draft_123",            // For routine_summary only
    "sourceTemplateId": "...",         // If editing existing template
    "sourceRoutineId": "..."           // If editing existing routine
  },
  "content": { ... }                   // Type-specific payload
}
```

**iOS mapping**: Artifacts received via SSE are converted to `CanvasCardModel` for rendering (reuses existing card renderers)

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
- Authenticated via `X-API-Key` header
- userId source depends on middleware:
  - `withApiKey` endpoints: userId from `req.body.userId` (handler reads body directly)
  - `requireFlexibleAuth` endpoints: userId from `X-User-Id` header (middleware sets `req.auth.uid`)
- Example: Agent writing canvas cards (withApiKey), workout mutations (requireFlexibleAuth)

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

### iOS Authentication Architecture

The iOS app supports three Firebase Auth providers: Email/Password, Google Sign-In, Apple Sign-In.

**Key files**: `AuthService.swift` (service), `AuthProvider.swift` (enum), `AppleSignInCoordinator.swift` (Apple delegate wrapper), `RootView.swift` (reactive navigation)

**SSO flow pattern** (shared by Google and Apple):
1. Provider SDK authenticates → Firebase Auth credential
2. `Auth.auth().signIn(with: credential)` → Firebase creates/links auth account
3. `user.reload()` to refresh stale `providerData` (critical for auto-linking)
4. Check if Firestore `users/{uid}` exists → return `.existingUser` or `.newUser`
5. `.newUser` → confirmation dialog → `createUserDocument()` if confirmed, `signOut()` if cancelled

**Provider data staleness**: After sign-in or linking, `currentUser.providerData` may not reflect auto-linked providers. Always call `user.reload()` + reassign `self.currentUser = Auth.auth().currentUser` after auth state changes.

**Account deletion sequence**: Reauth → Apple token revocation (if applicable) → Firestore subcollection deletion → Firebase Auth deletion → session cleanup → RootView reactively navigates to login.

**Firestore fields for auth**:
- `users/{uid}.provider` — provider used at account creation (`"email"`, `"google.com"`, `"apple.com"`)
- `users/{uid}.apple_authorization_code` — required for Apple token revocation on account deletion

See `docs/IOS_ARCHITECTURE.md` [Authentication System] section for exhaustive details.

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
// Artifact actions use idempotency_key to prevent duplicate writes
{
  "action": "accept",
  "artifact_id": "...",
  "conversation_id": "...",
  "idempotency_key": "uuid-v4"  // Client-generated
}

// Server checks: if (await Idempotency.check(key)) return cached response
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

7. **Agent Skills** (if agent needs to write it)
   - Update return data in `app/skills/planner_skills.py`
   - Agent prompt instructions in `app/shell/instruction.py`

---

## Deprecated / Legacy Code

### Files to Avoid

| File | Reason | Replacement |
|------|--------|-------------|
| `Povver/Povver/Archived/CloudFunctionProxy.swift` | Old HTTP wrapper | `ConversationService.swift` |
| `Povver/Povver/Archived/StrengthOSClient.swift` | Old API client | `CloudFunctionService.swift` |
| `Povver/Povver/Repositories/CanvasRepository.swift` | Canvas system removed | `ConversationRepository.swift` |
| `canvas/apply-action.js` | Canvas reducer removed | `conversations/artifact-action.js` |
| `canvas/propose-cards.js` | Canvas cards removed | Artifacts via SSE |
| `canvas/bootstrap-canvas.js` | Canvas bootstrap removed | `sessions/initialize-session.js` |
| `canvas/open-canvas.js` | Canvas open removed | Direct conversation creation |
| `canvas/emit-event.js` | Canvas events removed | SSE from agent |
| `canvas/purge-canvas.js` | Canvas purge removed | N/A |
| `canvas/expire-proposals.js` | Canvas expiry removed | N/A |
| `canvas/reducer-utils.js` | Canvas reducer removed | N/A |
| `canvas/validators.js` | Canvas validators removed | N/A |
| `routines/create-routine.js` | Manual routine creation | `create-routine-from-draft.js` |
| `routines/update-routine.js` | Direct update | `patch-routine.js` |
| `templates/update-template.js` | Direct update | `patch-template.js` |

### Legacy Field Names

| Legacy | Current | Notes |
|--------|---------|-------|
| `templateIds` | `template_ids` | get-next-workout handles both |
| `weight` | `weight_kg` | Normalized on archive |
| `canvasId` | `conversationId` | stream-agent-normalized supports both during migration |

### Removed Collections

| Collection | Status | Replacement |
|------------|--------|-------------|
| `users/{uid}/canvases/{id}/cards` | Removed | `conversations/{id}/artifacts` (optional Firestore storage) |
| `users/{uid}/canvases/{id}/workspace_entries` | Removed | `conversations/{id}/messages` |
| `users/{uid}/canvases/{id}` | Removed | `conversations/{id}` (lightweight metadata) |

---

## Training Analyst: Background Analysis Architecture

The Training Analyst is an **asynchronous background service** that pre-computes training insights, daily briefs, and weekly reviews. It runs as Cloud Run Jobs processing from a Firestore-backed job queue. This allows the chat agent to retrieve analysis instantly instead of computing it during conversations.

### Architecture Flow

```
Workout Completed
        │
        ▼ (Firestore trigger: onWorkoutCompleted)
Firebase: weekly-analytics.js
        │ Writes job to training_analysis_jobs collection
        ▼
Firestore: training_analysis_jobs/{jobId}
        │ status: "queued"
        ▼ (Cloud Run Job polls every 15 min)
Training Analyst Worker: poll_job() → lease → run
        │ Routes to appropriate analyzer
        ▼
PostWorkoutAnalyzer / DailyBriefAnalyzer / WeeklyReviewAnalyzer
        │ Reads aggregated data, calls Gemini LLM
        ▼
Firestore: analysis_insights / daily_briefs / weekly_reviews
        │
        ▼ (Chat agent retrieves)
Chat Agent: tool_get_training_analysis()
        │ Instant response (<100ms)
        ▼
User sees pre-computed insights
```

### Key Design Principles

| Principle | Rationale |
|-----------|-----------|
| **Pre-computation** | Analysis happens in background, not during chat |
| **Firestore queue** | Lease-based concurrency, no PubSub dependency |
| **Bounded responses** | All summaries <2KB for fast agent retrieval |
| **Data budget** | Only pre-aggregated data to LLM (never raw workouts) |
| **Retry with backoff** | Max 3 attempts, exponential backoff (5-30 min) |

### Component Map

```
adk_agent/training_analyst/
├── app/
│   ├── config.py                  ← Models, TTLs, collection names
│   ├── firestore_client.py        ← Firestore SDK singleton
│   ├── analyzers/
│   │   ├── base.py                ← Shared LLM client (google.genai + Vertex AI)
│   │   ├── post_workout.py        ← Post-workout insights
│   │   ├── daily_brief.py         ← Daily readiness
│   │   └── weekly_review.py       ← Weekly progression
│   └── jobs/
│       ├── models.py              ← Job, JobPayload, JobStatus, JobType
│       ├── queue.py               ← Create, poll, lease, complete, fail
│       └── watchdog.py            ← Stuck job recovery
├── workers/
│   ├── analyst_worker.py          ← Main worker (+ watchdog entry point)
│   └── scheduler.py               ← Daily/weekly job creation
├── Makefile                       ← Build, deploy, trigger commands
└── ARCHITECTURE.md                ← Tier 2 module docs
```

### Job Types

| Job Type | Trigger | Model | Output Collection | TTL |
|----------|---------|-------|-------------------|-----|
| `POST_WORKOUT` | `onWorkoutCompleted` Firestore trigger | gemini-2.5-pro | `users/{uid}/analysis_insights/{autoId}` | 7 days |
| `DAILY_BRIEF` | Scheduler (daily 6 AM UTC) | gemini-2.5-flash | `users/{uid}/daily_briefs/{YYYY-MM-DD}` | 7 days |
| `WEEKLY_REVIEW` | Scheduler (Sundays) | gemini-2.5-pro | `users/{uid}/weekly_reviews/{YYYY-WNN}` | 30 days |

### Data Budget Strategy

All analyzers read from **pre-aggregated collections only** (never raw workout docs):

| Analyzer | Data Budget | Sources |
|----------|------------|---------|
| Post-Workout | ~8KB | Trimmed workout (~1.5KB) + 4wk rollups (~2KB) + exercise series (~4KB) |
| Daily Brief | ~4KB | Next template (~1KB) + 4wk rollups (~2KB) + recent insight (~1KB) |
| Weekly Review | ~35KB | 12wk rollups (~6KB) + top 10 exercise series (~18KB) + 8 muscle group series (~10KB) + routine context (~1KB) |

### Backfill

Historical analysis can be generated via the backfill script:

```bash
# 1. Rebuild analytics foundation (set_facts, series, rollups)
FIREBASE_SERVICE_ACCOUNT_PATH=$FIREBASE_SA_KEY \
  node scripts/backfill_set_facts.js --user <userId> --rebuild-series

# 2. Enqueue analysis jobs (idempotent — safe to re-run)
FIREBASE_SERVICE_ACCOUNT_PATH=$FIREBASE_SA_KEY \
  node scripts/backfill_analysis_jobs.js --user <userId> --months 3

# 3. Process the jobs
GOOGLE_APPLICATION_CREDENTIALS=$GCP_SA_KEY \
  PYTHONPATH=adk_agent/training_analyst \
  python3 adk_agent/training_analyst/workers/analyst_worker.py
```

The backfill script uses deterministic job IDs (`bf-pw-{hash}`, `bf-wr-{hash}`, `bf-db-{hash}`) so re-runs overwrite existing jobs instead of creating duplicates.

**Required Firestore index**: `training_analysis_jobs` composite index on `status` (ASC) + `created_at` (ASC).

### Chat Agent Integration

The chat agent retrieves all pre-computed analysis through a single consolidated tool:

```python
# In app/shell/tools.py
tool_get_training_analysis(sections=None)  # All sections, or filter: ["insights", "daily_brief", "weekly_review"]
```

This calls the `getAnalysisSummary` Firebase Function, which reads from Firestore and returns all requested sections in a single HTTP call (~6KB total).

### Firebase Function: getAnalysisSummary

```javascript
// firebase_functions/functions/training/get-analysis-summary.js
// Auth: requireFlexibleAuth (Bearer + API key)
// Params: userId, sections? (array), date? (YYYY-MM-DD), limit? (number)
// Default: returns all 3 sections for today
```

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
│   │   ├── agent.py             ← ShellAgent (gemini-2.5-flash)
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
│   │   ├── workout_skills.py    ← Workout Brief + active workout mutations
│   │   └── gated_planner.py     ← Safety-gated writes
│   └── libs/                    ← Utilities
├── workers/                     ← BACKGROUND JOBS
│   └── post_workout_analyst.py  ← Post-workout insights
└── _archived/                   ← DEPRECATED (do not use)
```

### 4-Lane Routing Decision Table

| Input Pattern | Lane | Model | Latency | Handler |
|---------------|------|-------|---------|---------|
| `"done"`, `"8 @ 100"`, `"next set"` | FAST | None | <500ms | `copilot_skills.*` → `completeCurrentSet` |
| `{"intent": "SWAP_EXERCISE", ...}` | FUNCTIONAL | Flash | <1s | `functional_handler.py` |
| `"create a PPL routine"` | SLOW | Flash | 2-5s | `shell/agent.py` |
| PubSub `workout_completed` | WORKER | Flash | N/A | `post_workout_analyst.py` |

### Tool Permission Matrix (Shell Agent)

| Skill Function | Read | Write | Returns Artifact | Safety Gate |
|----------------|------|-------|------------------|-------------|
| `get_training_context()` | ✅ | - | No | No |
| `get_training_analysis()` | ✅ | - | No | No |
| `get_user_profile()` | ✅ | - | No | No |
| `search_exercises()` | ✅ | - | No | No |
| `get_exercise_details()` | ✅ | - | No | No |
| `get_exercise_progress()` | ✅ | - | No | No |
| `get_muscle_group_progress()` | ✅ | - | No | No |
| `get_muscle_progress()` | ✅ | - | No | No |
| `query_training_sets()` | ✅ | - | No | No |
| `get_planning_context()` | ✅ | - | No | No |
| `propose_workout()` | - | - | **Yes** | **Yes** |
| `propose_routine()` | - | - | **Yes** | **Yes** |
| `update_routine()` | - | - | **Yes** | **Yes** |
| `update_template()` | - | - | **Yes** | **Yes** |
| `log_set()` | - | ✅ | No | No (Fast Lane) |
| `tool_log_set()` | - | ✅ | No | No (workout mode gated) |
| `tool_swap_exercise()` | - | ✅ | No | No (workout mode gated) |
| `tool_complete_workout()` | - | ✅ | No | No (workout mode gated) |
| `tool_get_workout_state()` | ✅ | - | No | No (workout mode gated) |

Note: "Returns Artifact" means the tool returns artifact data in SkillResult, which the agent emits as an SSE artifact event. These tools no longer write directly to Firestore (canvas cards removed).

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
- `messages` ordered by `created_at` (for conversation history)
- `artifacts` filtered by `status` (for pending proposals)

---

## Auto-Pilot System

Connects the training analyst pipeline to user-facing recommendations and automated template mutations. The analyst (Python) identifies what needs to change; Firebase Functions translate analysis into specific template changes; the iOS app surfaces recommendations or shows auto-applied changes.

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 1. ANALYSIS (Python — Training Analyst, Cloud Run Jobs)               │
│    Writes: analysis_insights, weekly_reviews (already implemented)     │
└──────────────────┬──────────────────────────────────────────────────────┘
                   │ Firestore trigger (onDocumentCreated)
                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 2. RESOLUTION + APPLICATION (Node.js — Firebase Functions)             │
│    triggers/process-recommendations.js                                 │
│    Reads: user prefs (auto_pilot_enabled), active routine, templates   │
│    Writes: agent_recommendations (+ template if auto-pilot ON)         │
│    Reuses: applyChangesToTarget from agents/apply-progression.js       │
└──────────────────┬──────────────────────────────────────────────────────┘
                   │ Firestore listener (iOS)
                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 3. USER REVIEW (Swift — iOS App)                                       │
│    RecommendationRepository → RecommendationsViewModel → bell + feed   │
│    Calls: reviewRecommendation endpoint (accept/reject)                │
└─────────────────────────────────────────────────────────────────────────┘
```

### Key Components

| Component | File | Purpose |
|-----------|------|---------|
| Analysis triggers | `triggers/process-recommendations.js` | `onAnalysisInsightCreated`, `onWeeklyReviewCreated` — translate analysis into recommendations |
| Review endpoint | `recommendations/review-recommendation.js` | Accept/reject — template-scoped: freshness check + apply; exercise-scoped: acknowledge only |
| Expiry sweep | `triggers/process-recommendations.js` | `expireStaleRecommendations` — daily, 7-day TTL |
| Shared mutations | `agents/apply-progression.js` | `applyChangesToTarget`, `resolvePathValue` — reused by triggers and review endpoint |
| iOS model | `Models/AgentRecommendation.swift` | Codable struct matching `agent_recommendations` schema |
| iOS listener | `Repositories/RecommendationRepository.swift` | Firestore snapshot listener on `agent_recommendations` |
| iOS service | `Services/RecommendationService.swift` | HTTP calls to `reviewRecommendation` via `ApiClient` |
| iOS ViewModel | `ViewModels/RecommendationsViewModel.swift` | Pending/recent state, optimistic UI, premium gate |
| iOS bell | `UI/Components/NotificationBell.swift` | Badge overlay in `MainTabsView` |
| iOS feed | `Views/Recommendations/RecommendationsFeedView.swift` | Sheet with pending + recent cards |
| User preference | `auto_pilot_enabled` on `users/{uid}` | Toggle in Profile → Preferences (premium-only) |

### Recommendation Scopes

| | Template-scoped | Exercise-scoped |
|---|---|---|
| **Trigger condition** | User has `activeRoutineId` | No `activeRoutineId` |
| **Baseline weight** | Template set weights | Max working set weight from workout |
| **`scope` field** | `"template"` | `"exercise"` |
| **`target` field** | `{ template_id }` | `{ exercise_name, exercise_id }` |
| **Auto-apply** | Yes (if `auto_pilot_enabled`) | No (always `pending_review`) |
| **Accept action** | Apply weight delta to template sets | Acknowledge (no mutation) |

Exercise-scoped recommendations ensure users who log workouts directly (without routines/templates) still receive actionable progression suggestions from analysis insights and weekly reviews.

### Progression Rules (Deterministic)

- Weight progression (>40kg): +2.5% rounded to nearest 2.5kg, capped at +5kg/step
- Weight progression (≤40kg): +5% rounded to nearest 1.25kg, capped at +5kg/step
- Deload: -10% weight, same rounding rules
- Safety: min 0kg, no LLM involved in weight computation

### Premium Gates (3 Layers)

1. **Trigger** (`process-recommendations.js`): `isPremiumUser()` prevents template reads and recommendation writes for free users
2. **Review endpoint** (`review-recommendation.js`): `isPremiumUser()` prevents downgraded users from applying stale recommendations
3. **iOS UI** (`RecommendationsViewModel`): Only starts Firestore listener for premium users

---

## Subscription System

Povver uses Apple StoreKit 2 for in-app purchases with server-side state management via App Store Server Notifications V2. The client syncs positive entitlements to Firestore; the webhook is authoritative for downgrades (expiration, refund, revocation).

### Architecture

```
iOS StoreKit 2 (SubscriptionService.swift)
        │ Purchase with appAccountToken (UUID v5 from Firebase UID)
        │ Client-side gate in DirectStreamingService
        ▼
App Store
        │ Completes purchase
        │ Sends V2 Server Notification to webhook
        ▼
Firebase: subscriptions/app-store-webhook.js
        │ Decodes JWS payload (base64; JWS signature verification pending Apple root certs)
        │ Looks up user by subscription_app_account_token (fallback: original_transaction_id)
        │ Updates user subscription fields on users/{uid}
        │ Invalidates profile cache, logs event to subscription_events
        ▼
Firestore: users/{uid}
  {
    subscription_status: "active",
    subscription_tier: "premium",
    subscription_expires_at: ...,
    subscription_override: null        // admin override for test/beta users
  }
        │
        ▼ (Premium feature requests)
Firebase: utils/subscription-gate.js
        │ isPremiumUser(userId): override === 'premium' OR tier === 'premium'
        ▼
Premium features granted or denied
```

### Premium-Gated Features

| Feature | Gate Point | Error Format |
|---------|------------|--------------|
| AI coaching chat (all streaming) | `stream-agent-normalized.js` (server) + `DirectStreamingService` (client) | SSE `{ type: 'error', error: { code: 'PREMIUM_REQUIRED' } }` |
| Post-workout LLM analysis | `triggers/weekly-analytics.js` (job not enqueued) | Silent — free analytics still run |

**Not gated** (free for all users): exercise catalog, manual workout logging, workout history, templates/routines (read-only), weekly_stats, analytics rollups, set_facts.

**Client-side gate**: `DirectStreamingService.streamQuery()` checks `SubscriptionService.shared.isPremium` before opening the SSE connection. If `false`, throws `StreamingError.premiumRequired` which `CanvasViewModel` catches to show the paywall.

**Server-side gate (defense-in-depth)**: `stream-agent-normalized.js` calls `isPremiumUser(userId)` after auth. If `false`, emits an SSE error event with code `PREMIUM_REQUIRED` then closes the stream. `CanvasViewModel` also detects this code in the `.error` event handler.

### Subscription States

| Status | Tier | Description |
|--------|------|-------------|
| `"trial"` | `"premium"` | Introductory offer (7-day free trial) |
| `"active"` | `"premium"` | Paid subscription active |
| `"grace_period"` | `"premium"` | Payment failed, still has access during billing retry |
| `"expired"` | `"free"` | Subscription expired, cancelled, refunded, or revoked |
| `"free"` | `"free"` | Never had subscription or trial ended |

### Override System

The `subscription_override` field allows manual premium access grants for test/beta users:
- Set to `"premium"`: Grants premium access regardless of App Store state
- Set to `null` or absent: Respect App Store subscription state
- Set manually via Firestore console or admin script — never by the app or webhook

**Admin scripts**:
- `scripts/set_subscription_override.js` - Set/remove override for single user

### App Store Server Notifications V2

Webhook at `subscriptions/app-store-webhook.js` (v2 `onRequest`, no auth middleware — Apple calls directly):

| Notification Type | Subtype | subscription_status | subscription_tier |
|-------------------|---------|---------------------|-------------------|
| `SUBSCRIBED` | (offerType=1) | `trial` | `premium` |
| `SUBSCRIBED` | (else) | `active` | `premium` |
| `DID_RENEW` | — | `active` | `premium` |
| `DID_FAIL_TO_RENEW` | `GRACE_PERIOD` | `grace_period` | `premium` |
| `DID_FAIL_TO_RENEW` | (else) | `expired` | `free` |
| `EXPIRED` | any | `expired` | `free` |
| `GRACE_PERIOD_EXPIRED` | — | `expired` | `free` |
| `REFUND` | — | `expired` | `free` |
| `REVOKE` | — | `expired` | `free` |
| `DID_CHANGE_RENEWAL_STATUS` | — | *(unchanged)* | *(unchanged)* |

`DID_CHANGE_RENEWAL_STATUS` only updates `subscription_auto_renew_enabled`. All events logged to `users/{uid}/subscription_events/{auto-id}` for audit trail.

### User Lookup (Webhook)

`appAccountToken` is a deterministic UUID v5 derived from the Firebase UID using the DNS namespace (RFC 4122). Same algorithm on iOS (`SubscriptionService.generateAppAccountToken`) and server. Apple preserves this token across all transactions and webhook notifications.

1. Query `users` where `subscription_app_account_token == token` (lowercased)
2. Fallback: query where `subscription_original_transaction_id == txnId`

### Gate Check Logic

See `utils/subscription-gate.js`:

```javascript
// Premium access = ANY of:
// 1. subscription_override === 'premium' (admin override)
// 2. subscription_tier === 'premium' (set by webhook based on status transitions)
```

The gate checks the denormalized `subscription_tier` field, not `status + expires_at`. The webhook is responsible for setting tier correctly based on status transitions.

### iOS Subscription Components

| File | Purpose |
|------|---------|
| `Models/SubscriptionStatus.swift` | `SubscriptionTier`, `SubscriptionStatusValue`, `UserSubscriptionState` |
| `Services/SubscriptionService.swift` | StoreKit 2 singleton: products, purchase, entitlements, Firestore sync |
| `Views/PaywallView.swift` | Full-screen purchase sheet with trial CTA and restore |
| `Views/Settings/SubscriptionView.swift` | Subscription management in profile settings |

### Authority Model

- **Client writes to Firestore** only when StoreKit reports a **positive entitlement** (trial, active, grace period). This prevents the client from overwriting server-set `subscription_tier: "premium"` with stale `"free"` state (e.g., new device, delayed StoreKit sync).
- **Webhook is authoritative for downgrades** (expiration, cancellation, refund, revocation).
- **Client is authoritative for initial purchase** (syncs tier, token, transaction ID to Firestore so webhook can find the user).

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

---

## Monitoring & Analytics

### iOS — Firebase Analytics (GA4)

Firebase Analytics is enabled via `IS_ANALYTICS_ENABLED` in `GoogleService-Info.plist`. All events are fired through `AnalyticsService.swift`, a singleton wrapper around `Analytics.logEvent()` that provides typed methods to prevent typos.

**Debug verification**: Enable Analytics debug mode in Xcode scheme → Arguments → `-FIRAnalyticsDebugEnabled`. Events print to console in DEBUG builds (`[Analytics]` prefix).

**Event Taxonomy**:

| GA4 Event | Parameters | Call Site |
|-----------|-----------|-----------|
| `app_opened` | — | `PovverApp.swift` on launch |
| `signup_completed` | `provider` | `AuthService.signUp`, `confirmSSOAccountCreation` |
| `tab_viewed` | `tab` | `MainTabsView` on tab switch |
| `screen_viewed` | `screen` | `RootView` on flow change (login/register/main) |
| `conversation_started` | `entry_point` | `CanvasViewModel.start()` |
| `message_sent` | `message_length` | `CanvasViewModel.startSSEStream()` |
| `artifact_received` | `artifact_type` | `CanvasViewModel.handleIncomingStreamEvent` (.artifact) |
| `artifact_action` | `action`, `artifact_type` | `CanvasViewModel.applyAction()` |
| `workout_started` | `source`, `workout_id` | `FocusModeWorkoutService.startWorkout()` |
| `workout_completed` | `duration_min`, `exercise_count`, `set_count`, `workout_id` | `FocusModeWorkoutService.completeWorkout()` |
| `workout_cancelled` | `duration_min`, `workout_id` | `FocusModeWorkoutService.cancelWorkout()` |
| `workout_coach_opened` | — | `WorkoutCoachViewModel.send()` (first message) |
| `paywall_shown` | `trigger` | `CanvasViewModel` (premium gate catch / SSE error) |
| `trial_started` | — | `SubscriptionService.purchase()` |
| `subscription_purchased` | `product_id` | `SubscriptionService.purchase()` |
| `recommendation_action` | `action`, `type` | `RecommendationsViewModel.accept/reject()` (after server confirmation) |
| `streaming_error` | `error_code` | `CanvasViewModel.startSSEStream()` (error catch) |

**Workout event correlation**: All workout lifecycle events (`workout_started`, `workout_completed`, `workout_cancelled`) share a `workout_id` parameter so you can join start → completion rates by source (routine vs. template vs. freeform).

**Milestone events** (fire once per install via UserDefaults guard): `first_message_sent`, `first_artifact_received`, `first_workout_completed`. These fire automatically inside `messageSent()`, `artifactReceived()`, and `workoutCompleted()`.

**Funnel tracking**: `screen_viewed` tracks auth flow transitions (login → register → main). `tab_viewed` tracks which tabs users visit and in what order. Combined with `conversation_started`, `message_sent`, `artifact_received`, and `artifact_action`, this gives a full activation funnel: app open → signup → first conversation → first artifact → first accepted plan.

**User identity**: `Analytics.setUserID()` is called in `AuthService`'s auth state listener alongside Crashlytics.

### Server-Side — Structured Cloud Logging

All server-side logs use structured JSON with an `event` field for Cloud Logging filter queries.

**Firebase Functions**:

| Event | File | Filter | Key Fields |
|-------|------|--------|------------|
| `stream_completed` | `stream-agent-normalized.js` | `jsonPayload.event="stream_completed"` | `success`, `latency_ms`, `user_id`, `conversation_id`, `artifact_count`, `data_chunks` |
| `subscription_event_received` | `app-store-webhook.js` | `jsonPayload.event="subscription_event_received"` | `notification_type`, `subtype` |
| `subscription_updated` | `app-store-webhook.js` | `jsonPayload.event="subscription_updated"` | `user_id`, `status`, `tier` |

**Python Agent** (`adk_agent/canvas_orchestrator/`):

| Event | File | Filter | Key Fields |
|-------|------|--------|------------|
| `agent_request_completed` | `agent_engine_app.py` | `jsonPayload.event="agent_request_completed"` | `lane`, `intent`, `workout_mode`, `latency_ms`, `user_id` |
| `tool_called` | `shell/tools.py` | `jsonPayload.event="tool_called"` | `tool`, `success`, `latency_ms`, `error` |

The `@timed_tool` decorator on all tool functions in `tools.py` provides per-tool latency tracking.

### Cloud Monitoring (Manual Setup)

**Log-based metrics** (configure in Cloud Console):
- `stream_latency_ms`: Distribution on `jsonPayload.latency_ms` from `stream_completed` events (filter `jsonPayload.success=true` to exclude failed streams)
- `tool_latency_ms`: Distribution on `jsonPayload.latency_ms` from `tool_called` events, grouped by `jsonPayload.tool`
- `agent_request_latency_ms`: Distribution from `agent_request_completed` events, grouped by `jsonPayload.lane`

**Dashboards**:
- **Product Health** (Firebase Console / GA4): Activation funnel, WAU, subscription funnel, retention cohorts
- **System Health** (Cloud Monitoring): Stream latency by lane, tool latency, error rates, function invocations
