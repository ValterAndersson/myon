# Active Workout Domain

HTTP tools for managing a user's in-progress workout. These are legacy-compatible and also reused by the Canvas reducer via shared cores.

## File Inventory

| File | Endpoint | Purpose |
|------|----------|---------|
| `start-active-workout.js` | `startActiveWorkout` | Create active workout from plan or template |
| `get-active-workout.js` | `getActiveWorkout` | Fetch most recent active workout |
| `propose-session.js` | `proposeSession` | Propose a session plan stub |
| `log-set.js` | `logSet` | Log a completed set (v2, idempotent) |
| `patch-active-workout.js` | `patchActiveWorkout` | Edit workout values, add/remove sets (v2) |
| `autofill-exercise.js` | `autofillExercise` | AI bulk prescription for a single exercise (v2) |
| `add-exercise.js` | `addExercise` | Add exercise to workout (v2, idempotent) |
| `swap-exercise.js` | `swapExercise` | Swap exercise in workout (v2, idempotent) |
| `complete-active-workout.js` | `completeActiveWorkout` | Finish workout, archive to `workouts/` (v2) |
| `cancel-active-workout.js` | `cancelActiveWorkout` | Cancel workout without archiving (v2) |

## Key Endpoints

### startActiveWorkout (HTTPS)
- Auth: flexible
- Request: `{ "plan"?: object }`
- Response: `{ success, data: { workout_id, active_workout_doc } }`

### getActiveWorkout (HTTPS)
- Auth: flexible
- Returns the most recent active workout: `{ success, data: { workout } }`

### proposeSession (HTTPS)
- Auth: flexible
- Request: `{ constraints?: object }`
- Response: `{ success, data: { session_plan } }`

### logSet (HTTPS, v2)
- Auth: flexible; idempotency_key supported
- Request: `{ workout_id, exercise_id, set_index, actual }`
- Response: `{ success, data: { event_id } }`

### patchActiveWorkout (HTTPS, v2)
- Auth: flexible; idempotency_key supported
- Request: `{ workout_id, ops: [{ type, ... }] }`
- Response: `{ success, data: { event_id } }`

### autofillExercise (HTTPS, v2)
- Auth: flexible; idempotency_key supported
- Request: `{ workout_id, exercise_id, sets: [...] }`
- Response: `{ success, data: { event_id } }`

### addExercise / swapExercise (HTTPS, v2)
- Auth: flexible; idempotency_key supported for `addExercise`
- Requests: standard IDs
- Response: `{ success, data: { event_id } }`

### completeActiveWorkout / cancelActiveWorkout (HTTPS, v2)
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
