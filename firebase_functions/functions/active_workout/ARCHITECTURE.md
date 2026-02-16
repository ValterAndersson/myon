# Active Workout Domain

HTTP endpoints for managing a user's in-progress workout.

## File Inventory

| File | Endpoint | Purpose |
|------|----------|---------|
| `start-active-workout.js` | `startActiveWorkout` | Create active workout from plan or template |
| `get-active-workout.js` | `getActiveWorkout` | Fetch most recent active workout |
| `propose-session.js` | `proposeSession` | Propose a session plan stub |
| `log-set.js` | `logSet` | Log a completed set (v2, transactional, idempotent) |
| `patch-active-workout.js` | `patchActiveWorkout` | Edit workout values, add/remove sets (v2, transactional) |
| `autofill-exercise.js` | `autofillExercise` | AI bulk prescription for a single exercise (v2, transactional) |
| `add-exercise.js` | `addExercise` | Add exercise to workout (v2, transactional, idempotent) |
| `swap-exercise.js` | `swapExercise` | Swap exercise in workout (v2, transactional, idempotent) |
| `complete-current-set.js` | `completeCurrentSet` | Mark next planned set done (v2, transactional, fast lane) |
| `complete-active-workout.js` | `completeActiveWorkout` | Finish workout, archive to `workouts/` (v2, transactional) |
| `cancel-active-workout.js` | `cancelActiveWorkout` | Cancel workout without archiving (v2) |

## Concurrency Model

All hot-path mutation endpoints (`logSet`, `patchActiveWorkout`, `addExercise`, `autofillExercise`, `completeCurrentSet`, `swapExercise`, `completeActiveWorkout`) use Firestore transactions to prevent lost updates from concurrent requests. The pattern:

1. **Outside transaction**: method check, auth, schema validation, parse fields, pre-generate `workoutRef` + `eventRef` (no Firestore reads).
2. **Inside `db.runTransaction()`**: idempotency check → read workout → validate state → compute mutations → increment `version` → write workout + event + idempotency record.
3. **Outside transaction**: return response or cached idempotency response.

Validation errors inside the transaction are thrown as structured objects `{ httpCode, code, message, details }` and caught by the outer try/catch for HTTP response mapping via `fail()`.

### Version Field

The `version` field is a monotonically incrementing integer on the active workout document. Starts at `1` (set by `startActiveWorkout`), incremented by every mutation. Existing documents without `version` are treated as version `0` via `(workout.version || 0) + 1`. The server always returns `version` in mutation responses. iOS tracks it for debugging. No client-side version enforcement — Firestore transactions handle serialization automatically.

### Shared Helpers

Shared logic extracted to `../utils/active-workout-helpers.js`:
- `computeTotals(exercises)` — recomputes `{ sets, reps, volume }` from exercises array
- `findExercise(exercises, instanceId)` — returns `{ index, exercise }` or null
- `findSet(exercise, setId)` — returns `{ index, set }` or null
- `findExerciseAndSet(exercises, instanceId, setId)` — combined lookup

## Key Endpoints

### startActiveWorkout (HTTPS)
- Auth: flexible
- Request: `{ "plan"?: object }`
- Response: `{ success, data: { workout_id, workout, resumed } }`
- Initializes `version: 1` on new workout documents

### getActiveWorkout (HTTPS)
- Auth: flexible
- Returns the most recent active workout: `{ success, data: { workout } }`

### proposeSession (HTTPS)
- Auth: flexible
- Request: `{ constraints?: object }`
- Response: `{ success, data: { session_plan } }`

### logSet (HTTPS, v2)
- Auth: flexible; idempotency_key supported
- Request: `{ workout_id, exercise_instance_id, set_id, values, is_failure?, idempotency_key }`
- Response: `{ success, data: { event_id, totals, version } }`

### patchActiveWorkout (HTTPS, v2)
- Auth: flexible; idempotency_key supported
- Request: `{ workout_id, ops: [{ op, target, field?, value? }], cause, ui_source, idempotency_key }`
- Response: `{ success, data: { event_id, totals, version } }`

### autofillExercise (HTTPS, v2)
- Auth: flexible; idempotency_key supported
- Request: `{ workout_id, exercise_instance_id, updates?, additions?, idempotency_key }`
- Response: `{ success, data: { event_id, totals, version } }`

### addExercise (HTTPS, v2)
- Auth: flexible; idempotency_key supported
- Request: `{ workout_id, instance_id, exercise_id, name?, position?, sets?, idempotency_key }`
- Response: `{ success, data: { exercise_instance_id, event_id, version } }`

### completeCurrentSet (HTTPS, v2)
- Auth: flexible
- Request: `{ workout_id }`
- Response: `{ success, data: { exercise_name, set_number, total_sets, weight, reps } }`
- Finds the first `planned` working/dropset set (defaults `set_type` to `'working'` when unset), marks it `done`, logs `set_done` event.
- Used by the agent Fast Lane (`copilot_skills.py`) — accepts only `workout_id`, discovers the target set server-side to avoid an extra round-trip.

### swapExercise (HTTPS, v2)
- Auth: flexible; idempotency_key supported
- Request: `{ workout_id, from_exercise_id, to_exercise_id, reason? }`
- Response: `{ success, data: { event_id, version } }`
- `from_exercise_id` matches on `instance_id` (the stable UUID within the workout, not the catalog `exercise_id`). The agent client (`CanvasFunctionsClient.swap_exercise`) sends `exercise_instance_id` as `from_exercise_id`.
- Fetches the new exercise name from the `exercises` catalog collection.

### completeActiveWorkout (HTTPS, v2)
- Auth: flexible
- Request: `{ workout_id }`
- Response: `{ success, data: { workout_id, archived } }`
- Uses transaction with status guard (`status !== 'in_progress'` returns `{ already_completed: true }`) to prevent double-completion.

### cancelActiveWorkout (HTTPS, v2)
- Auth: flexible
- Request: `{ workout_id }`
- Response: `{ success, data: { ... } }`

## Firestore layout
- `users/{uid}/active_workouts/{workoutId}` with `events/{eventId}` appends and `idempotency/{key}` records
- Archived workouts under `users/{uid}/workouts/{workoutId}`
