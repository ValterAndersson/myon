# Firebase Functions Architecture

> **Document Purpose**: Complete documentation of the Firebase Functions backend layer. Written for LLM/agentic coding agents.

---

## Table of Contents

1. [Overview](#overview)
2. [Function Categories](#function-categories)
3. [Authentication & Middleware](#authentication--middleware)
4. [Canvas Operations](#canvas-operations)
5. [Agent Operations](#agent-operations)
6. [Active Workout Operations](#active-workout-operations)
7. [CRUD Operations](#crud-operations)
8. [Firestore Triggers](#firestore-triggers)
9. [Analytics Functions](#analytics-functions)
10. [Exercise Catalog Operations](#exercise-catalog-operations)
11. [Directory Structure](#directory-structure)

---

## Overview

Firebase Functions serve as the backend API layer for the MYON fitness platform. Functions are deployed to Google Cloud and provide:

- RESTful HTTP endpoints for CRUD operations
- Canvas system state management
- Agent streaming proxy to Vertex AI Agent Engine
- Firestore triggers for real-time data processing
- Scheduled jobs for analytics and maintenance

**Runtime**: Node.js 18+
**Region**: us-central1
**Framework**: Firebase Functions (Gen 1 and Gen 2)

---

## Function Categories

### HTTP Functions by Domain

| Domain | Functions | Auth Type |
|--------|-----------|-----------|
| **User** | `getUser`, `updateUser`, `getUserPreferences`, `updateUserPreferences`, `upsertUserAttributes` | API Key |
| **Workouts** | `getUserWorkouts`, `getWorkout` | API Key |
| **Templates** | `getUserTemplates`, `getTemplate`, `createTemplate`, `updateTemplate`, `deleteTemplate`, `createTemplateFromPlan`, `patchTemplate` | API Key / Flexible |
| **Routines** | `getUserRoutines`, `getRoutine`, `createRoutine`, `updateRoutine`, `deleteRoutine`, `getActiveRoutine`, `setActiveRoutine`, `getNextWorkout`, `patchRoutine` | API Key / Flexible |
| **Exercises** | `getExercises`, `getExercise`, `searchExercises`, `upsertExercise`, `approveExercise`, `ensureExerciseExists`, `resolveExercise`, `mergeExercises` | API Key |
| **Canvas** | `bootstrapCanvas`, `openCanvas`, `initializeSession`, `applyAction`, `proposeCards`, `purgeCanvas`, `emitEvent`, `expireProposals` | Flexible Auth |
| **Active Workout** | `startActiveWorkout`, `getActiveWorkout`, `logSet`, `addExercise`, `swapExercise`, `completeActiveWorkout`, `cancelActiveWorkout`, `proposeSession` | Flexible Auth |
| **Agents** | `invokeCanvasOrchestrator`, `getPlanningContext`, `streamAgentNormalized` | Flexible Auth |
| **Analytics** | `runAnalyticsForUser`, `compactAnalyticsForUser`, `getAnalyticsFeatures`, `recalculateWeeklyForUser` | Flexible Auth |

---

## Authentication & Middleware

### Auth Types

**`withApiKey`** - Legacy API key validation via `x-api-key` header:
```javascript
const { withApiKey } = require('./auth/middleware');
exports.getUser = functions.https.onRequest((req, res) => withApiKey(getUser)(req, res));
```

**`requireFlexibleAuth`** - Firebase Auth token or service-to-service:
```javascript
const { requireFlexibleAuth } = require('./auth/middleware');
exports.applyAction = functions.https.onRequest((req, res) => requireFlexibleAuth(applyAction)(req, res));
```

### Service Token Exchange

`getServiceToken` provides service-to-service authentication for agent-to-function calls:
- Validates service credentials
- Returns short-lived tokens for internal API calls

---

## Canvas Operations

The Canvas is the central AI workspace where agents publish cards and users interact with proposals.

### Core Endpoints

| Function | Purpose | Input | Output |
|----------|---------|-------|--------|
| `openCanvas` | Get or create canvas + session (optimized) | `userId`, `purpose` | `{canvasId, sessionId}` |
| `bootstrapCanvas` | Create or resume canvas | `userId`, `purpose` | `{canvasId}` |
| `initializeSession` | Create agent session for canvas | `canvasId`, `purpose` | `{sessionId}` |
| `applyAction` | Execute canvas action (reducer) | `ApplyActionRequest` | `{changedCards}` |
| `proposeCards` | Agent publishes cards | `ProposeCardsRequest` | `{cards}` |
| `purgeCanvas` | Delete canvas and all cards | `userId`, `canvasId` | `{success}` |
| `emitEvent` | Publish workspace event | `canvasId`, `event` | `{success}` |
| `expireProposals` | Mark old proposals expired | - | `{expired}` |

### Canvas State Flow

```
1. Client calls openCanvas(userId, purpose)
2. Backend finds/creates canvas document
3. Backend initializes agent session (Vertex AI)
4. Returns canvasId + sessionId
5. Client attaches Firestore listeners to /cards
6. Agent invocations → proposeCards → cards written to Firestore
7. User actions → applyAction → card state changes
```

### Action Reducer (`apply-action.js`)

The action reducer handles all canvas state transitions:

| Action | Description |
|--------|-------------|
| `accept` | Accept proposal, update card status |
| `reject` | Reject proposal, archive card |
| `edit` | Modify card content |
| `start` | Start workout from session plan |
| `save_as_template` | Convert plan to user template |
| `add_to_routine` | Add template to routine |
| `refine` | Request agent refinement |
| `swap_exercise` | Swap exercise in plan |
| `reorder_exercises` | Reorder plan exercises |

### Card Types (JSON Schemas)

| Schema File | Card Type |
|-------------|-----------|
| `session_plan.schema.json` | Workout session plan |
| `routine_summary.schema.json` | Routine overview |
| `routine_overview.schema.json` | Routine details with schedule |
| `visualization.schema.json` | Charts and tables |
| `analysis_summary.schema.json` | Progress analysis |
| `clarify_questions.schema.json` | Agent clarification questions |
| `agent_stream.schema.json` | Streaming agent output |
| `inline_info.schema.json` | Inline informational text |
| `list.schema.json` | Generic list card |
| `proposal_group.schema.json` | Group of related proposals |
| `set_target.schema.json` | Set target for exercise |

---

## Agent Operations

### Streaming Architecture

`streamAgentNormalized` proxies SSE streams from Vertex AI Agent Engine:

```
iOS App → Firebase Function → Vertex AI Agent Engine
           (SSE proxy)         (ADK agent)
```

**Stream Event Types:**
- `thinking` - Agent processing indicator
- `thought` - Agent reasoning content
- `tool_start` / `tool_end` - Tool execution lifecycle
- `message` - Agent text response
- `card` - Card publication event
- `error` - Error notification

### Agent Invocation

`invokeCanvasOrchestrator` triggers agent execution:
- Forwards user message to agent
- Agent streams responses via `streamAgentNormalized`
- Agent tools write cards via `proposeCards`

### Planning Context

`getPlanningContext` provides agent with user context:
- User preferences and goals
- Workout history
- Active routine information
- Exercise catalog access

---

## Active Workout Operations

### Workout Lifecycle

| Function | Description |
|----------|-------------|
| `proposeSession` | Generate workout proposal from template/routine |
| `startActiveWorkout` | Create active workout document |
| `getActiveWorkout` | Retrieve current workout state |
| `logSet` | Log completed set |
| `addExercise` | Add exercise to workout |
| `swapExercise` | Replace exercise in workout |
| `completeActiveWorkout` | Finalize and persist workout |
| `cancelActiveWorkout` | Discard active workout |

### Active Workout Document

```javascript
{
  userId: string,
  canvasId: string,
  templateId: string,
  startedAt: Timestamp,
  exercises: [
    {
      exerciseId: string,
      name: string,
      sets: [{ reps: number, weight: number, completed: boolean }]
    }
  ],
  state: 'active' | 'completed' | 'cancelled'
}
```

---

## CRUD Operations

### User Operations

| Function | Path | Method |
|----------|------|--------|
| `getUser` | `/getUser?userId={id}` | GET |
| `updateUser` | `/updateUser` | POST |
| `getUserPreferences` | `/getUserPreferences?userId={id}` | GET |
| `updateUserPreferences` | `/updateUserPreferences` | POST |
| `upsertUserAttributes` | `/upsertUserAttributes` | POST |

### Template Operations

| Function | Path | Method |
|----------|------|--------|
| `getUserTemplates` | `/getUserTemplates?userId={id}` | GET |
| `getTemplate` | `/getTemplate?id={id}&userId={userId}` | GET |
| `createTemplate` | `/createTemplate` | POST |
| `updateTemplate` | `/updateTemplate` | PUT |
| `deleteTemplate` | `/deleteTemplate` | DELETE |
| `createTemplateFromPlan` | `/createTemplateFromPlan` | POST |
| `patchTemplate` | `/patchTemplate` | PATCH |

### Routine Operations

| Function | Path | Method |
|----------|------|--------|
| `getUserRoutines` | `/getUserRoutines?userId={id}` | GET |
| `getRoutine` | `/getRoutine?id={id}&userId={userId}` | GET |
| `createRoutine` | `/createRoutine` | POST |
| `updateRoutine` | `/updateRoutine` | PUT |
| `deleteRoutine` | `/deleteRoutine` | DELETE |
| `getActiveRoutine` | `/getActiveRoutine?userId={id}` | GET |
| `setActiveRoutine` | `/setActiveRoutine` | POST |
| `getNextWorkout` | `/getNextWorkout` | POST |
| `patchRoutine` | `/patchRoutine` | PATCH |

---

## Firestore Triggers

### Muscle Volume Calculations

| Trigger | Event | Purpose |
|---------|-------|---------|
| `onTemplateCreated` | Template create | Calculate muscle volume targets |
| `onTemplateUpdated` | Template update | Recalculate muscle volumes |
| `onWorkoutCreated` | Workout create | Calculate actual muscle volumes |

### Weekly Analytics

| Trigger | Event | Purpose |
|---------|-------|---------|
| `onWorkoutCompleted` | Workout complete | Update weekly stats |
| `onWorkoutCreatedWithEnd` | Workout with endTime | Finalize workout analytics |
| `onWorkoutDeleted` | Workout delete | Adjust weekly totals |
| `onWorkoutCreatedWeekly` | Workout create | Increment weekly counters |
| `onWorkoutFinalizedForUser` | Workout finalized | User-level analytics |

### Routine Cursor

| Trigger | Event | Purpose |
|---------|-------|---------|
| `onWorkoutCreatedUpdateRoutineCursor` | Workout create | Advance routine cursor |

---

## Analytics Functions

### Weekly Stats Recalculation

- `weeklyStatsRecalculation` - Scheduled weekly recalculation
- `manualWeeklyStatsRecalculation` - Callable manual trigger
- `recalculateWeeklyForUser` - Per-user recalculation

### Analytics Compaction

- `analyticsCompactionScheduled` - Scheduled compaction job
- `compactAnalyticsForUser` - Per-user compaction

### Analytics Features

- `runAnalyticsForUser` - Run analytics pipeline for user
- `getAnalyticsFeatures` - Get computed analytics features
- `publishWeeklyJob` - Publish weekly analytics job to queue

---

## Exercise Catalog Operations

### Core CRUD

| Function | Purpose |
|----------|---------|
| `getExercises` | List all exercises |
| `getExercise` | Get single exercise by ID |
| `searchExercises` | Full-text search with filters |
| `upsertExercise` | Create or update exercise |
| `approveExercise` | Mark exercise as approved |

### Resolution & Aliases

| Function | Purpose |
|----------|---------|
| `ensureExerciseExists` | Create if not exists |
| `resolveExercise` | Resolve alias to canonical exercise |
| `upsertAlias` | Create exercise alias |
| `deleteAlias` | Remove exercise alias |
| `searchAliases` | Search alias database |
| `suggestAliases` | AI-powered alias suggestions |

### Catalog Maintenance

| Function | Purpose |
|----------|---------|
| `mergeExercises` | Merge duplicate exercises |
| `normalizeCatalog` | Normalize exercise names |
| `normalizeCatalogPage` | Paginated normalization |
| `backfillNormalizeFamily` | Backfill family normalization |
| `listFamilies` | List exercise families |
| `repointAlias` | Update alias target |
| `repointShorthandAliases` | Batch update shorthand aliases |
| `backupExercises` | Create exercise catalog backup |

### AI-Powered

| Function | Purpose |
|----------|---------|
| `suggestFamilyVariant` | Suggest family classification |
| `refineExercise` | AI refinement of exercise metadata |

---

## Directory Structure

```
firebase_functions/functions/
├── index.js                    # All exports and routing
├── package.json                # Dependencies
├── README.md                   # Basic readme
├── active_workout/             # Active workout endpoints
│   ├── add-exercise.js
│   ├── cancel-active-workout.js
│   ├── complete-active-workout.js
│   ├── get-active-workout.js
│   ├── log-set.js
│   ├── propose-session.js
│   ├── start-active-workout.js
│   └── swap-exercise.js
├── agents/                     # Agent invocation
│   ├── get-planning-context.js
│   └── invoke-canvas-orchestrator.js
├── aliases/                    # Exercise alias management
│   ├── delete-alias.js
│   └── upsert-alias.js
├── analytics/                  # Analytics pipeline
│   ├── compaction.js
│   ├── controller.js
│   ├── get-features.js
│   ├── publish-weekly-job.js
│   └── recalculate-weekly-for-user.js
├── auth/                       # Authentication middleware
│   ├── exchange-token.js
│   └── middleware.js
├── canvas/                     # Canvas operations
│   ├── apply-action.js         # Action reducer
│   ├── bootstrap-canvas.js
│   ├── emit-event.js
│   ├── expire-proposals-scheduled.js
│   ├── expire-proposals.js
│   ├── initialize-session.js
│   ├── open-canvas.js          # Optimized open
│   ├── propose-cards-core.js   # Card proposal logic
│   ├── propose-cards.js
│   ├── purge-canvas.js
│   ├── reducer-utils.js        # Reducer helpers
│   ├── validators.js           # Schema validation
│   └── schemas/                # JSON schemas
│       ├── action.schema.json
│       ├── apply_action_request.schema.json
│       ├── card_input.schema.json
│       ├── propose_cards_request.schema.json
│       └── card_types/         # Card type schemas
├── exercises/                  # Exercise catalog
│   ├── approve-exercise.js
│   ├── backfill-normalize-family.js
│   ├── ensure-exercise-exists.js
│   ├── get-exercise.js
│   ├── get-exercises.js
│   ├── list-families.js
│   ├── merge-exercises.js
│   ├── normalize-catalog-page.js
│   ├── normalize-catalog.js
│   ├── refine-exercise.js
│   ├── resolve-exercise.js
│   ├── search-aliases.js
│   ├── search-exercises.js
│   ├── suggest-aliases.js
│   ├── suggest-family-variant.js
│   └── upsert-exercise.js
├── health/                     # Health check
│   └── health.js
├── maintenance/                # Maintenance scripts
│   ├── backup-exercises.js
│   ├── repoint-alias.js
│   └── repoint-shorthand-aliases.js
├── routines/                   # Routine operations
│   ├── create-routine-from-draft.js
│   ├── create-routine.js
│   ├── delete-routine.js
│   ├── get-active-routine.js
│   ├── get-next-workout.js
│   ├── get-routine.js
│   ├── get-user-routines.js
│   ├── patch-routine.js
│   ├── set-active-routine.js
│   └── update-routine.js
├── scripts/                    # Dev scripts
│   ├── seed_canvas.js
│   └── weekly_publisher.js
├── shared/                     # Shared utilities
│   └── active_workout/
│       └── reorder_sets_core.js
├── strengthos/                 # Agent streaming
│   ├── progress-reports.js
│   └── stream-agent-normalized.js
├── templates/                  # Template operations
│   ├── create-template-from-plan.js
│   ├── create-template.js
│   ├── delete-template.js
│   ├── get-template.js
│   ├── get-user-templates.js
│   ├── patch-template.js
│   └── update-template.js
├── tests/                      # Test files
│   ├── reducer.invariants.test.js
│   └── reducer.utils.test.js
├── triggers/                   # Firestore triggers
│   ├── muscle-volume-calculations.js
│   ├── weekly-analytics.js
│   └── workout-routine-cursor.js
├── user/                       # User operations
│   ├── get-preferences.js
│   ├── get-user.js
│   ├── update-preferences.js
│   ├── update-user.js
│   └── upsert-attributes.js
├── utils/                      # Shared utilities
│   ├── plan-to-template-converter.js
│   ├── validation-response.js
│   └── validators.js
└── workouts/                   # Workout operations
    ├── get-user-workouts.js
    └── get-workout.js
```
