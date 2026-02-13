# iOS Application Architecture (Povver)

> **Document Purpose**: Complete documentation of the Povver iOS application architecture. Written for LLM/agentic coding agents.

---

## Table of Contents

1. [Application Overview](#application-overview)
2. [App Entry and Navigation](#app-entry-and-navigation)
3. [Architecture Layers](#architecture-layers)
4. [Services Layer](#services-layer)
5. [Repositories Layer](#repositories-layer)
6. [Models](#models)
7. [ViewModels](#viewmodels)
8. [Views and UI](#views-and-ui)
9. [Canvas System](#canvas-system)
10. [Design System](#design-system)
11. [Directory Structure](#directory-structure)

---

## Application Overview

Povver is a SwiftUI-based iOS fitness coaching application. The app provides:
- AI-powered workout planning via the Canvas system
- Routine and template management
- Active workout tracking
- Real-time agent streaming with thinking/tool visualization

**Key Architectural Patterns:**
- MVVM (Model-View-ViewModel)
- Repository pattern for data access
- Singleton services for shared state
- Protocol-based abstractions for testability
- Async/await for all network operations

**Primary Technologies:**
- SwiftUI for UI
- Firebase Auth for authentication
- Firebase Firestore for data persistence
- Firebase Functions for backend API
- Firebase Crashlytics for crash reporting (tagged with userId)
- Vertex AI Agent Engine for AI agents (via streaming)

---

## App Entry and Navigation

### Entry Point (`PovverApp.swift`)

```swift
@main
struct PovverApp: App {
    init() {
        FirebaseConfig.shared.configure()
    }
    
    var body: some Scene {
        WindowGroup {
            RootView()
        }
    }
}
```

### Navigation Flow (`RootView.swift`)

```
┌─────────────────┐
│    RootView     │
│                 │
│  AppFlow enum:  │
│  - login        │──► LoginView
│  - register     │──► RegisterView
│  - main         │──► MainTabsView
└─────────────────┘
```

### Tab Structure (`MainTabsView.swift`)

| Tab | View | Purpose |
|-----|------|---------|
| Chat | `ChatHomeEntry` | Session-based chat interface |
| Routines | `RoutinesListView` | Manage workout routines |
| Templates | `TemplatesListView` | Manage workout templates |
| Canvas | `CanvasScreen` | AI-powered planning workspace |
| Dev (DEBUG) | `ComponentGallery` | UI component testing |

---

## Architecture Layers

```
┌──────────────────────────────────────────────────────────┐
│                        VIEWS                             │
│   SwiftUI Views (CanvasScreen, RoutinesListView, etc.)   │
├──────────────────────────────────────────────────────────┤
│                      VIEWMODELS                          │
│   Observable state + business logic                      │
│   (CanvasViewModel, RoutinesViewModel, etc.)             │
├──────────────────────────────────────────────────────────┤
│                       SERVICES                           │
│   Singleton managers for cross-cutting concerns          │
│   (AuthService, CanvasService, ChatService, etc.)        │
├──────────────────────────────────────────────────────────┤
│                     REPOSITORIES                         │
│   Data access abstraction over Firestore                 │
│   (UserRepository, TemplateRepository, etc.)             │
├──────────────────────────────────────────────────────────┤
│                       MODELS                             │
│   Codable structs matching Firestore schema              │
│   (User, Workout, Routine, Exercise, etc.)               │
└──────────────────────────────────────────────────────────┘
```

---

## Services Layer

### Core Services

| Service | Type | Purpose |
|---------|------|---------|
| `AuthService` | Singleton | Firebase Auth management |
| `SessionManager` | Singleton | User session state |
| `CanvasService` | Class | Canvas CRUD operations via Cloud Functions |
| `ChatService` | Singleton | Chat session management + streaming |
| `DirectStreamingService` | Singleton | SSE streaming to Agent Engine |
| `CloudFunctionService` | Class | Firebase Functions HTTP client |
| `ApiClient` | Singleton | Generic HTTP client with auth |

### Managers

| Manager | Type | Purpose |
|---------|------|---------|
| `ActiveWorkoutManager` | Singleton | Live workout state management |
| `FocusModeWorkoutService` | ObservableObject | Active workout API: start, logSet, patchField, complete, cancel. Drains pending syncs before completion. |
| `WorkoutSessionLogger` | Singleton | Records every workout event to JSON on disk (`Documents/workout_logs/`). Auto-flushes on app background. Breadcrumbs to Crashlytics for crash correlation. |
| `BackgroundSaveService` | Singleton | Fire-and-forget background saves with observable sync state |
| `TemplateManager` | Singleton | Template editing state |
| `CacheManager` | Actor | Memory + disk caching |
| `DeviceManager` | Singleton | Device registration |
| `TimezoneManager` | Singleton | User timezone handling |

### Key Service Details

#### `AuthService`
- Manages Firebase Auth state
- Publishes `isAuthenticated` and `currentUser`
- Supports email/password, Google, Apple sign-in

#### `DirectStreamingService`
- Streams to Vertex AI Agent Engine via Firebase Function proxy (`streamAgentNormalized`)
- Parses SSE events into `StreamEvent` objects
- Handles markdown sanitization and deduplication
- Returns `AsyncThrowingStream<StreamEvent, Error>`

#### `CanvasService`
- `bootstrapCanvas(userId, purpose)` - Create new canvas
- `openCanvas(userId, purpose)` - Open or resume canvas with session
- `initializeSession(canvasId, purpose)` - Initialize agent session
- `applyAction(request)` - Execute canvas actions
- `purgeCanvas(userId, canvasId)` - Delete canvas

#### `ActiveWorkoutManager`
- Manages live workout state (`ActiveWorkout`)
- Tracks workout duration, exercises, sets
- Converts `ActiveWorkout` to Firestore `Workout` on completion
- Calculates per-exercise and per-muscle analytics

#### `BackgroundSaveService`
- `@MainActor ObservableObject` singleton decoupling UI from slow backend saves
- Edit views submit an operation via `save(entityId:operation:)` and dismiss immediately
- Publishes `pendingSaves: [String: PendingSave]` — keyed by entity ID, value contains `FocusModeSyncState` (`.pending` / `.failed(message)`)
- List rows observe `isSaving(entityId)` to show a spinner instead of a chevron
- Detail view toolbars switch between Edit / Syncing spinner / Retry based on sync state
- Detail views use `.onChange(of: syncState)` to auto-reload fresh data when the save completes
- Guards against duplicate saves for the same entity — second call is ignored while one is in flight
- Used by: `WorkoutEditView`, `TemplateDetailView`, `RoutineDetailView`, `HistoryView`, `TemplatesListView`, `RoutinesListView`

---

## Repositories Layer

All repositories extend data access with type-safe Firestore operations:

| Repository | Collection(s) | Purpose |
|------------|---------------|---------|
| `UserRepository` | `users`, `users/{id}/attributes` | User profile and preferences |
| `WorkoutRepository` | `users/{id}/workouts` | Completed workout history |
| `TemplateRepository` | `users/{id}/templates` | Workout templates |
| `RoutineRepository` | `users/{id}/routines` | Routines (template sequences) |
| `ExerciseRepository` | `exercises` | Global exercise catalog |
| `CanvasRepository` | `users/{id}/canvases`, `.../cards` | Canvas and card state |

### `BaseRepository`

Provides retry logic with exponential backoff via `retry.swift`:
```swift
func withRetry<T>(
    maxAttempts: Int = 3,
    operation: @escaping () async throws -> T
) async throws -> T
```

---

## Models

### Core Domain Models

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `User` | User profile | `id`, `email`, `displayName`, `createdAt` |
| `UserAttributes` | User preferences | `weightFormat`, `heightFormat`, `timezone` |
| `Workout` | Completed workout | `id`, `userId`, `exercises`, `startedAt`, `completedAt`, `analytics` |
| `WorkoutTemplate` | Reusable workout plan | `id`, `name`, `exercises`, `userId` |
| `Routine` | Ordered template sequence | `id`, `name`, `templateIds`, `frequency`, `isActive` |
| `Exercise` | Exercise catalog entry | `id`, `name`, `primaryMuscles`, `equipment`, `instructions` |
| `ActiveWorkout` | In-progress workout | `exercises`, `startTime`, `workoutDuration` |
| `ActiveWorkoutDoc` | Firestore-synced active state | `userId`, `canvasId`, `state` |
| `MuscleGroup` | Muscle group enumeration | Used by Exercise model |

### Canvas Models (`UI/Canvas/Models.swift`)

| Model | Purpose |
|-------|---------|
| `CanvasCardModel` | Universal card container |
| `CardType` | Enum: `session_plan`, `routine_summary`, `visualization`, `clarify_questions`, etc. |
| `CardLane` | Enum: `planning`, `analysis`, `execution` |
| `CardStatus` | Enum: `pending`, `active`, `accepted`, `rejected`, `completed` |
| `CanvasCardData` | Tagged union for card-specific content |

### Streaming Models

| Model | Purpose |
|-------|---------|
| `StreamEvent` | SSE event with type, content, metadata |
| `ChatMessage` | Chat UI message with author, content, timestamp |
| `AgentProgressState` | Tool execution progress tracking |
| `WorkspaceEvent` | Workspace events from agent |

---

## ViewModels

| ViewModel | Views | Responsibilities |
|-----------|-------|------------------|
| `CanvasViewModel` | `CanvasScreen`, card views | Canvas state, Firestore listeners, action handling |
| `RoutinesViewModel` | `RoutinesListView`, detail views | Routine CRUD, active routine management |
| `ExercisesViewModel` | Exercise search | Exercise catalog fetching |

### `CanvasViewModel` (Primary)

**State:**
- `cards: [CanvasCardModel]` - All cards on canvas
- `cardsByLane: [CardLane: [CanvasCardModel]]` - Cards grouped by lane
- `isLoading`, `isAgentProcessing`, `error`
- `canvasId`, `sessionId`, `userId`
- `agentProgress: AgentProgressState`

**Key Methods:**
- `bootstrap()` - Create/resume canvas
- `sendMessage(_:)` - Invoke agent with message
- `applyAction(_:)` - Execute canvas action
- `acceptCard(_:)` / `rejectCard(_:)` - Proposal handling
- `startWorkout(from:)` - Begin active workout

**Firestore Listeners:**
- Cards subcollection (`cards`)
- Workspace events (`workspace_events`)
- Active workout doc (`active_workouts/{canvasId}`)

---

## Views and UI

### Primary Screens

| Screen | File | Purpose |
|--------|------|---------|
| `CanvasScreen` | `Views/CanvasScreen.swift` | Main AI workspace |
| `ChatHomeEntry` | `Views/ChatHomeEntry.swift` | Chat session list |
| `ChatHomeView` | `Views/ChatHomeView.swift` | Chat conversation |
| `RoutinesListView` | `UI/Routines/RoutinesListView.swift` | Routine management |
| `TemplatesListView` | `UI/Templates/TemplatesListView.swift` | Template management |

### Canvas Views

| View | Purpose |
|------|---------|
| `CanvasGridView` | Masonry grid layout for cards |
| `CardContainer` | Universal card wrapper with header/actions |
| `CardHeader` | Title, subtitle, status badge |
| `ThoughtTrackView` | Agent thinking/tool visualization |
| `WorkoutRailView` | Horizontal workout exercise rail |
| `WorkspaceTimelineView` | Workspace events timeline |
| `StreamOverlay` | Streaming state overlay |

### Card Types

| Card View | Card Type | Purpose |
|-----------|-----------|---------|
| `SessionPlanCard` | `session_plan` | Workout plan with exercises |
| `RoutineSummaryCard` | `routine_summary` | Routine overview |
| `VisualizationCard` | `visualization` | Charts and tables |
| `AnalysisSummaryCard` | `analysis_summary` | Progress analysis |
| `ClarifyQuestionsCard` | `clarify_questions` | Agent clarification |
| `AgentStreamCard` | `agent_stream` | Streaming agent output |
| `ChatCard` | `chat` | Chat message |
| `SuggestionCard` | `suggestion` | Quick action suggestions |
| `SmallContentCard` | `text` | Simple text content |
| `RoutineOverviewCard` | `routine_overview` | Routine overview |
| `ListCardWithExpandableOptions` | `list_card` | Generic expandable list |

---

## Canvas System

The Canvas is the primary AI interaction surface. It displays cards organized by lanes and manages agent streaming.

### Canvas Lifecycle

```
1. User opens Canvas tab
2. CanvasScreen.onAppear → CanvasViewModel.bootstrap()
3. bootstrap() calls openCanvas(userId, purpose)
4. Backend returns canvasId + sessionId
5. ViewModel attaches Firestore listeners for cards
6. User sends message → sendMessage()
7. Agent streams response → cards written to Firestore
8. Listeners update local state → UI refreshes
```

### Card Actions

Cards can define actions in their `actions` and `menuItems` arrays:

| Action Type | Purpose |
|-------------|---------|
| `accept` | Accept proposed card |
| `reject` | Reject proposed card |
| `edit` | Open edit interface |
| `start` | Start workout from plan |
| `save_as_template` | Save plan as template |
| `add_to_routine` | Add template to routine |
| `refine` | Open refinement sheet |
| `swap` | Open exercise swap sheet |

### Canvas DTOs

Request/response types for canvas operations:

- `ApplyActionRequestDTO` - Action request with idempotency key
- `ApplyActionResponseDTO` - Action result with changed cards
- `CanvasStateDTO` - Canvas state snapshot
- `CanvasMapper` - Firestore document to model conversion

---

## Design System

### Tokens (`UI/DesignSystem/Tokens.swift`)

Centralized design tokens for consistency:

| Category | Examples |
|----------|----------|
| Spacing | `spacing4`, `spacing8`, `spacing16` |
| Radius | `radiusS`, `radiusM`, `radiusL` |
| Typography | `headlineLarge`, `bodyMedium`, `labelSmall` |
| Colors | `surfacePrimary`, `textPrimary`, `accent` |

### Components (`UI/Components/`)

| Component | Purpose |
|-----------|---------|
| `MyonButton` | Standard button styles |
| `MyonText` | Typography component |
| `SurfaceCard` | Card container with elevation |
| `AgentPromptBar` | Chat input with send button |
| `CardActionBar` | Action buttons for cards |
| `Banner` / `Toast` | Feedback components |
| `Spinner` / `StatusTag` | Auxiliary indicators |
| `DropdownMenu` | Dropdown selection |

---

## Directory Structure

```
Povver/Povver/
├── PovverApp.swift                 # App entry point
├── GoogleService-Info.plist        # Firebase config
├── Config/
│   ├── FirebaseConfig.swift        # Firebase initialization
│   └── StrengthOSConfig.swift      # Environment config
├── Extensions/
│   └── String+Extensions.swift     # String helpers
├── Models/
│   ├── ActiveWorkout.swift
│   ├── ActiveWorkoutDoc.swift
│   ├── ChatMessage.swift
│   ├── Exercise.swift
│   ├── FocusModeModels.swift
│   ├── MuscleGroup.swift
│   ├── Routine.swift
│   ├── StreamEvent.swift
│   ├── User.swift
│   ├── UserAttributes.swift
│   ├── Workout.swift
│   ├── WorkoutTemplate.swift
│   └── WorkspaceEvent.swift
├── Repositories/
│   ├── BaseRepository.swift
│   ├── CanvasRepository.swift
│   ├── ExerciseRepository.swift
│   ├── retry.swift
│   ├── RoutineRepository.swift
│   ├── TemplateRepository.swift
│   ├── UserRepository.swift
│   └── WorkoutRepository.swift
├── Services/
│   ├── ActiveWorkoutManager.swift  # Live workout state
│   ├── AgentProgressState.swift    # Tool progress tracking
│   ├── AgentsApi.swift             # Agent invocation
│   ├── AnyCodable.swift            # Dynamic JSON coding
│   ├── ApiClient.swift             # HTTP client
│   ├── AuthService.swift           # Firebase Auth
│   ├── CacheManager.swift          # Memory/disk cache
│   ├── CanvasActions.swift         # Action builders
│   ├── CanvasDTOs.swift            # Canvas data types
│   ├── CanvasService.swift         # Canvas API
│   ├── ChatService.swift           # Chat management
│   ├── CloudFunctionService.swift  # Firebase Functions
│   ├── DebugLogger.swift           # Logging utilities
│   ├── DeviceManager.swift         # Device registration
│   ├── DirectStreamingService.swift # SSE streaming
│   ├── Errors.swift                # Error types
│   ├── FirebaseService.swift       # Firestore abstraction
│   ├── Idempotency.swift           # Idempotency keys
│   ├── PendingAgentInvoke.swift    # Pending message queue
│   ├── SessionManager.swift        # Session state
│   ├── FocusModeWorkoutService.swift # Active workout API
│   ├── WorkoutSessionLogger.swift  # On-device event log
│   ├── TemplateManager.swift       # Template editing
│   └── TimezoneManager.swift       # Timezone handling
├── ViewModels/
│   ├── CanvasViewModel.swift       # Primary canvas VM
│   ├── ExercisesViewModel.swift
│   └── RoutinesViewModel.swift
├── Views/
│   ├── CanvasScreen.swift          # Main canvas screen
│   ├── ChatHomeEntry.swift         # Chat entry
│   ├── ChatHomeView.swift          # Chat conversation
│   ├── ComponentGallery.swift      # Dev component gallery
│   ├── LoginView.swift
│   ├── MainTabsView.swift          # Tab navigation
│   ├── RegisterView.swift
│   └── RootView.swift              # App root
└── UI/
    ├── Canvas/
    │   ├── Models.swift            # Canvas card models
    │   ├── CanvasGridView.swift    # Masonry layout
    │   ├── CardContainer.swift     # Card wrapper
    │   ├── CardHeader.swift
    │   ├── ThoughtTrackView.swift  # Agent thoughts
    │   ├── WorkoutRailView.swift
    │   ├── WorkspaceTimelineView.swift
    │   ├── Charts/                 # Chart components
    │   │   ├── BarChartView.swift
    │   │   ├── LineChartView.swift
    │   │   ├── RankedTableView.swift
    │   │   └── VisualizationModels.swift
    │   └── Cards/
    │       ├── SessionPlanCard.swift
    │       ├── RoutineSummaryCard.swift
    │       ├── VisualizationCard.swift
    │       ├── AnalysisSummaryCard.swift
    │       ├── ClarifyQuestionsCard.swift
    │       ├── SmallContentCard.swift
    │       ├── RoutineOverviewCard.swift
    │       ├── ListCardWithExpandableOptions.swift
    │       ├── PlanCardSkeleton.swift
    │       ├── SetGridView.swift
    │       ├── ExerciseDetailSheet.swift
    │       └── Shared/
    │           ├── ExerciseActionsRow.swift
    │           ├── ExerciseRowView.swift
    │           ├── ExerciseSwapSheet.swift
    │           └── IterationActionsRow.swift
    ├── FocusMode/
    │   ├── ARCHITECTURE.md            # Module architecture
    │   ├── FocusModeWorkoutScreen.swift # Main workout screen
    │   ├── FocusModeSetGrid.swift      # Set grid + editing dock
    │   ├── FocusModeComponents.swift   # Shared components
    │   └── FocusModeExerciseSearch.swift # Exercise search
    ├── Components/
    │   ├── MyonButton.swift
    │   ├── MyonText.swift
    │   ├── SurfaceCard.swift
    │   ├── DropdownMenu.swift
    │   └── ... (component library)
    ├── DesignSystem/
    │   ├── Tokens.swift            # Design tokens
    │   ├── Theme.swift             # Theme provider
    │   └── Validation.swift        # Input validation
    ├── Routines/
    │   ├── RoutinesListView.swift
    │   ├── RoutineDetailView.swift
    │   └── RoutineEditView.swift
    ├── Templates/
    │   ├── TemplatesListView.swift
    │   └── TemplateDetailView.swift
    └── Schemas/
        └── ... (JSON schemas for card types)
```
