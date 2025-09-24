# Active Workout Domain

HTTP tools for managing a user's in-progress workout. These are legacy-compatible and also reused by the Canvas reducer via shared cores.

## Key endpoints

### startActiveWorkout (HTTPS)
- Auth: flexible
- Request: `{ "plan"?: object }`
- Response: `{ success, data: { workout_id, active_workout_doc } }`

### getActiveWorkout (HTTPS)
- Auth: flexible
- Returns the most recent active workout: `{ success, data: { workout } }`

### prescribeSet (HTTPS)
- Auth: flexible; idempotency_key supported
- Request: `{ workout_id, exercise_id, set_index, context? }`
- Response: `{ success, data: { event_id, prescription } }`

### logSet (HTTPS)
- Auth: flexible; idempotency_key supported
- Request: `{ workout_id, exercise_id, set_index, actual }`
- Response: `{ success, data: { event_id } }`

### addExercise / swapExercise (HTTPS)
- Auth: flexible; idempotency_key supported for `addExercise`
- Requests: standard IDs
- Response: `{ success, data: { event_id } }`

### completeActiveWorkout / cancelActiveWorkout (HTTPS)
- Auth: flexible
- Requests: `{ workout_id }`
- Response: `{ success, data: { ... } }`

## Shared cores (used by Canvas reducer)
- `shared/active_workout/log_set_core.js` → appends `set_performed` event and updates timestamps
- `shared/active_workout/swap_core.js` → appends `exercise_swapped` event
- `shared/active_workout/adjust_load_core.js` → appends `load_adjusted` event
- `shared/active_workout/reorder_sets_core.js` → appends `sets_reordered` event

## Firestore layout
- `users/{uid}/active_workouts/{workoutId}` with `events/{eventId}` appends
- Archived workouts under `users/{uid}/workouts/{workoutId}`
