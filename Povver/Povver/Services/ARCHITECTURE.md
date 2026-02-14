# Services — Module Architecture

Services are singleton managers and API clients that provide cross-cutting concerns to ViewModels and other services. They sit between the ViewModel layer and Firebase SDK / Cloud Functions.

## File Inventory

| File | Purpose |
|------|---------|
| `AuthService.swift` | Multi-provider Firebase Auth (email, Google, Apple). Handles sign-in/sign-up, SSO credential linking, provider refresh after auto-linking, account deletion with Apple token revocation (App Store 5.1.1(v)), and reauthentication flows |
| `AppleSignInCoordinator.swift` | `ASAuthorizationController` delegate wrapper. Bridges Apple's delegate callbacks to async/await via `CheckedContinuation`. Manages nonce generation (sha256 to Apple, raw to Firebase) |
| `WorkoutSessionLogger.swift` | On-device workout event recorder. Writes timestamped JSON to `Documents/workout_logs/`. Auto-flushes on app background. Writes breadcrumbs to Crashlytics for crash correlation |
| `SessionManager.swift` | User session lifecycle and state |
| `ApiClient.swift` | Generic HTTP client with auth token injection |
| `CloudFunctionService.swift` | Firebase Functions HTTP client (base URL, request building) |
| `CanvasService.swift` | Canvas CRUD: `bootstrapCanvas`, `openCanvas`, `initializeSession`, `applyAction`, `purgeCanvas` |
| `CanvasActions.swift` | Action builder helpers for canvas mutations (accept, reject, log set, swap) |
| `CanvasDTOs.swift` | Canvas request/response DTOs (`ApplyActionRequestDTO`, `ApplyActionResponseDTO`, `CanvasMapper`) |
| `DirectStreamingService.swift` | SSE streaming to Vertex AI via `streamAgentNormalized`. Parses `StreamEvent` objects |
| `ChatService.swift` | Chat session management and message streaming |
| `FocusModeWorkoutService.swift` | Workout API calls: `startWorkout`, `finishWorkout`, `logSet`, `swapExercise`, `patchTemplate`, `getRoutine`, `patchRoutine`, `upsertWorkout` |
| `ActiveWorkoutManager.swift` | Live workout state: exercise tracking, set logging, analytics calculation |
| `TemplateManager.swift` | Template editing state management. Uses `patchTemplate` for updates (not deprecated `CloudFunctionService.updateTemplate`) |
| `CacheManager.swift` | Memory + disk caching (Actor-based) |
| `DeviceManager.swift` | Device registration for push notifications |
| `TimezoneManager.swift` | User timezone detection and sync |
| `SessionPreWarmer.swift` | Pre-warms agent sessions on app launch |
| `AgentsApi.swift` | Agent invocation helpers |
| `AgentPipelineLogger.swift` | Structured logging for agent streaming pipeline |
| `ThinkingProcessState.swift` | Agent thinking/tool execution progress tracking |
| `BackgroundSaveService.swift` | Singleton managing fire-and-forget background saves for library editing (workouts, templates, routines). Views dismiss immediately; the service runs the operation async and publishes sync state per entity ID for UI indicators |
| `MutationCoordinator.swift` | Serial queue for Focus Mode workout operations to prevent race conditions and TARGET_NOT_FOUND errors |
| `PendingAgentInvoke.swift` | Queue for pending agent messages during session initialization |
| `Idempotency.swift` | Client-side idempotency key generation |
| `FirebaseService.swift` | Firestore abstraction layer |
| `Errors.swift` | App error types and handling |
| `DebugLogger.swift` | Debug logging utilities |
| `AnyCodable.swift` | Dynamic JSON encoding/decoding helper |

## Key Patterns

- **Singletons**: `AuthService`, `SessionManager`, `DirectStreamingService`, `ActiveWorkoutManager` are shared instances
- **Cloud Function calls**: Go through `CloudFunctionService` → `ApiClient` with auth token from `AuthService`
- **Streaming**: `DirectStreamingService` opens SSE via `streamAgentNormalized` Cloud Function, returns `AsyncThrowingStream<StreamEvent, Error>`
- **Canvas mutations**: All writes go through `CanvasService.applyAction()` with `idempotency_key` and `expected_version`
- **Background saves**: `BackgroundSaveService` decouples UI from slow backend calls. Edit views submit operations and dismiss immediately. List rows and detail views observe `pendingSaves` to show syncing spinners and retry buttons on failure

## Cross-References

- Services are consumed by ViewModels (`Povver/Povver/ViewModels/`)
- `CanvasService` calls Firebase Functions defined in `firebase_functions/functions/canvas/`
- `FocusModeWorkoutService` calls endpoints in `firebase_functions/functions/active_workout/`, `templates/`, `routines/`, and `workouts/`
- `DirectStreamingService` calls `firebase_functions/functions/strengthos/stream-agent-normalized.js`
