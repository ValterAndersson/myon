# Focus Mode — Module Architecture

Focus Mode is the active workout UI. It provides a distraction-free interface for logging sets, swapping exercises, and completing workouts.

## File Inventory

| File | Purpose |
|------|---------|
| `FocusModeWorkoutScreen.swift` | Main workout screen: exercise list, set logging, finish button |
| `FocusModeSetGrid.swift` | Set grid for logging reps, weight, and RIR per exercise |
| `FocusModeComponents.swift` | Shared UI components for Focus Mode (exercise headers, progress indicators) |
| `FocusModeExerciseSearch.swift` | Exercise search for adding/swapping exercises mid-workout |

## Entry Point

Navigation enters Focus Mode from `CanvasViewModel.startWorkout(from:)` or the Routines tab. The screen is presented modally over the Canvas.

## Key Relationships

- **ActiveWorkoutManager** (`Services/ActiveWorkoutManager.swift`): Manages live workout state, set logging, and analytics. Focus Mode views observe this manager.
- **FocusModeWorkoutService** (`Services/FocusModeWorkoutService.swift`): API calls for `startActiveWorkout`, `completeActiveWorkout`, `logSet`, `swapExercise`.
- **FocusModeModels** (`Models/FocusModeModels.swift`): `FocusModeWorkout` struct matching the `active_workouts` Firestore schema.

## Data Flow

```
User taps "Start Workout"
    → FocusModeWorkoutService.startWorkout(templateId, routineId?)
    → POST /startActiveWorkout
    → Firestore: active_workouts/{id} created
    → FocusModeWorkoutScreen displayed

User logs set
    → ActiveWorkoutManager.logSet()
    → POST /logSet
    → Firestore: active_workouts/{id}/events/{eventId}

User finishes
    → FocusModeWorkoutService.finishWorkout()
    → POST /completeActiveWorkout
    → Firestore: workouts/{id} created, active_workouts/{id} archived
    → Trigger: workout-routine-cursor.js advances routine cursor
```
