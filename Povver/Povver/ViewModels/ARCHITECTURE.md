# ViewModels — Module Architecture

ViewModels manage observable state and business logic for SwiftUI views. They coordinate between Services, Repositories, and Views.

## File Inventory

| File | Primary Views | Responsibilities |
|------|---------------|------------------|
| `CanvasViewModel.swift` | `CanvasScreen`, all card views | Agent streaming, artifact rendering, conversation state, action dispatch |
| `ExercisesViewModel.swift` | Exercise search views | Exercise catalog fetching and search |
| `WorkoutCoachViewModel.swift` | `WorkoutCoachView` | Ephemeral in-memory chat during active workout. Streams agent responses via `DirectStreamingService.streamQuery(workoutId:)` with workout context prefix. Chat is not persisted to Firestore. Mirrors `CanvasViewModel` streaming pattern (message buffer, flush on `.done`) |

## CanvasViewModel (Primary)

The central ViewModel managing the conversation + artifact experience:

**State:**
- `cards: [CanvasCardModel]` — Artifact cards built from SSE `artifact` events
- `streamEvents: [StreamEvent]` — SSE events for workspace timeline display
- `workspaceEvents: [WorkspaceEvent]` — Persisted conversation history
- `thinkingState: ThinkingProcessState` — Collapsible thought process UI
- `canvasId` (used as conversationId), `currentSessionId`, `currentUserId`

**Key Methods:**
- `start(userId:purpose:)` — Create conversation via `openCanvas()`, attach Firestore listeners
- `startSSEStream()` — Begin agent streaming via `DirectStreamingService`
- `handleIncomingStreamEvent(_:)` — Process SSE events including `.artifact` type
- `buildCardFromArtifact(type:content:actions:status:)` — Converts artifact SSE data to `CanvasCardModel` via JSON round-trip decoding. Supports: `session_plan`, `routine_summary`, `analysis_summary`, `visualization`.

**Artifact Flow:**
1. Agent tool returns `artifact_type` in response
2. `stream-agent-normalized.js` detects and emits SSE `artifact` event
3. `handleIncomingStreamEvent()` receives `.artifact` case
4. `buildCardFromArtifact()` converts to `CanvasCardModel`
5. Card appended to `cards` array, rendered by existing card components

**Firestore Listeners:**
- Workspace events (for reload)
- Canvas events (telemetry)

## Cross-References

- Views: `Povver/Povver/Views/CanvasScreen.swift`, `UI/Canvas/`
- Services: `DirectStreamingService.swift`, `AgentsApi.swift`
- Card renderers: `UI/Canvas/Cards/SessionPlanCard.swift`, `RoutineSummaryCard.swift`, etc.
