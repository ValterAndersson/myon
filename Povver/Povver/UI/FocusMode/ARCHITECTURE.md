# Focus Mode — Module Architecture

Focus Mode is the active workout UI. It provides a distraction-free interface for logging sets, swapping exercises, and completing workouts. Designed for gym use: large tap targets, sweat-proof gestures, single-hand operation.

## File Inventory

| File | Purpose |
|------|---------|
| `FocusModeWorkoutScreen.swift` | Main workout screen: exercise list, hero header, scroll tracking, finish/discard flow, exercise reordering. Contains `FocusModeExerciseSection`, `FocusModeExerciseSectionNew`, `WorkoutAlertsModifier`, `WorkoutCompletionSummary`. |
| `FocusModeSetGrid.swift` | Set grid for logging reps, weight, and RIR per exercise. Contains `FocusModeEditingDock` (inline editor with stepper/keyboard/RIR pills), `FocusModeEditScope` enum (this/remaining/all). |
| `FocusModeComponents.swift` | Shared UI components: `WorkoutHero`, `TimerPill`, `SwipeToDeleteRow`, `WarmupDivider`, `ExerciseCardContainer`, `CoachButton`, `ReorderModeBanner`, `ActionRail`. |
| `FocusModeExerciseSearch.swift` | Exercise search for adding/swapping exercises mid-workout. |

## Entry Point

Navigation enters Focus Mode from `CanvasViewModel.startWorkout(from:)` or the Routines tab. The screen is presented modally. Tab bar is hidden while a workout is active to prevent accidental navigation.

## Key Relationships

- **FocusModeWorkoutService** (`Services/FocusModeWorkoutService.swift`): `@MainActor ObservableObject`. API calls for `startActiveWorkout`, `completeActiveWorkout`, `logSet`, `patchField`, `swapExercise`, `removeExercise`. Drains all pending sync operations before sending completion request (prevents race conditions). Exposes `workout` as published property.
- **WorkoutSessionLogger** (`Services/WorkoutSessionLogger.swift`): Records every workout event (start, log_set, complete, error) to timestamped JSON files in `Documents/workout_logs/`. Auto-flushes on app background. Writes breadcrumbs to Crashlytics for crash correlation.
- **FocusModeModels** (`Models/FocusModeModels.swift`): `FocusModeWorkout`, `FocusModeExercise`, `FocusModeSet` structs matching the `active_workouts` Firestore schema.

## Data Flow

```
User taps "Start Workout"
    → FocusModeWorkoutService.startWorkout(templateId, routineId?)
    → POST /startActiveWorkout
    → Firestore: active_workouts/{id} created
    → FocusModeWorkoutScreen displayed (screen auto-lock disabled)

User logs set (tap checkmark)
    → Immediate haptic feedback (single, in doneCell)
    → FocusModeWorkoutService.logSet() (async, fire-and-forget)
    → POST /logSet
    → WorkoutSessionLogger records event
    → On failure: warning banner auto-dismisses ("Set sync pending")

User finishes
    → FocusModeWorkoutService drains all in-flight logSet/patchField calls
    → POST /completeActiveWorkout
    → Firestore: workouts/{id} created, active_workouts/{id} archived
    → Trigger: workout-routine-cursor.js advances routine cursor
    → completedWorkoutId set → fullScreenCover presents WorkoutCompletionSummary
    → Screen auto-lock re-enabled
```

## Screen Mode State Machine

`FocusModeWorkoutScreen` uses a `screenMode` enum to manage UI state:

| Mode | Description |
|------|-------------|
| `.normal` | Default scrollable exercise list |
| `.editingSet(exerciseId, setId, cellType)` | Inline editing dock open for a specific cell |
| `.reordering` | List edit mode for drag-to-reorder exercises |

`screenMode` changes drive: editing dock visibility, `ScrollViewReader` scroll-to-dock, list edit mode sync.

## Key UI Patterns

### SwipeToDeleteRow (FocusModeComponents.swift)

Uses `@GestureState` (not `@State`) for the live drag offset so it auto-resets to zero when the gesture is cancelled (e.g., when ScrollView steals the touch). This prevents the "stuck at 30%" bug where `onEnded` never fires.

- `DragGesture(minimumDistance: 20)` — higher threshold to avoid capturing vertical scrolls
- Horizontal-only guard: `abs(width) > abs(height)` in the `updating` block
- `baseOffset` (`@State`) persists revealed/closed state between gestures
- `visibleOffset = baseOffset + dragOffset` — clean separation of concerns
- `.onTapGesture` (not `simultaneousGesture`) closes revealed state without interfering with child buttons

### FocusModeEditingDock (FocusModeSetGrid.swift)

Inline editor that appears below the selected set row. Attached to the set grid via `.id(selectedCell)` for `ScrollViewReader` targeting.

- **Type-to-replace**: Text field starts empty; current value shown as placeholder. Typing replaces the value entirely (no "4060" concatenation).
- **Stepper buttons (+/-)**: Do NOT dismiss keyboard. Clear partial text input so placeholder reflects the new value.
- **Scope selector**: "This" / "Remaining" / "All" — defaults to "Remaining" when subsequent sets have the same value, "This" otherwise.
- **RIR layout**: Uses `VStack` (pills on top, Done button below) instead of `HStack` to prevent 6-pill overflow on narrow screens. Weight/reps editors use `HStack`.

### Scroll-to-Dock (FocusModeWorkoutScreen.swift)

`ScrollViewReader` wraps the `LazyVStack` inside the `ScrollView`. An `.onChange(of: screenMode)` handler detects when editing starts and scrolls to the dock's `.id(cell)` with `.bottom` anchor after a 0.35s delay (to let the keyboard animation begin).

### Mark All Done (Column Header)

The "checkmark" column header in `FocusModeSetGrid` is a tappable button when `onToggleAllDone` is provided. Logic: if all working sets are done, undo all (patch to "planned"); otherwise, log all undone working sets.

### Done State Visibility

Completed sets have:
- Subtle success-tinted row background (`Color.success.opacity(0.06)`)
- Filled circle indicator (`Color.success.opacity(0.15)` fill + green stroke)
- Green checkmark and text color

### WorkoutAlertsModifier

Alert/confirmation dialogs (finish, name edit, discard, resume gate) are extracted into a `ViewModifier` to reduce type-checker load on the main `body` computed property.
