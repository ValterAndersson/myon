# ViewModels — Module Architecture

ViewModels manage observable state and business logic for SwiftUI views. They coordinate between Services, Repositories, and Views.

## File Inventory

| File | Primary Views | Responsibilities |
|------|---------------|------------------|
| `CanvasViewModel.swift` | `CanvasScreen`, all card views | Canvas state, Firestore snapshot listeners, agent streaming, action dispatch, card grouping by lane |
| `ExercisesViewModel.swift` | Exercise search views | Exercise catalog fetching and search |

## CanvasViewModel (Primary)

The central ViewModel managing the Canvas experience:

**State:**
- `cards: [CanvasCardModel]` — All cards on canvas
- `cardsByLane: [CardLane: [CanvasCardModel]]` — Cards grouped by lane
- `isLoading`, `isAgentProcessing`, `error`
- `canvasId`, `sessionId`, `userId`

**Key Methods:**
- `bootstrap()` — Create/resume canvas via `CanvasService.openCanvas()`
- `sendMessage(_:)` — Invoke agent with streaming via `DirectStreamingService`
- `applyAction(_:)` — Execute canvas action via `CanvasService.applyAction()`
- `acceptCard(_:)` / `rejectCard(_:)` — Proposal handling
- `startWorkout(from:)` — Begin active workout and navigate to Focus Mode

**Firestore Listeners (via CanvasRepository):**
- Cards subcollection
- Workspace events
- Active workout doc

## Cross-References

- Views: `Povver/Povver/Views/CanvasScreen.swift`, `UI/Canvas/`
- Services: `Povver/Povver/Services/CanvasService.swift`, `DirectStreamingService.swift`
- Repositories: `Povver/Povver/Repositories/CanvasRepository.swift`
