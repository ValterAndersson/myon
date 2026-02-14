# Workouts Domain

Completed workout history management. All endpoints use v2 `onRequest` with `requireFlexibleAuth`.

## File Inventory

| File | Endpoint | Auth | Purpose |
|------|----------|------|---------|
| `get-user-workouts.js` | `getUserWorkouts` | API Key (service lane) | Paginated workout history with analytics. Ordered by `end_time desc`. Supports `startDate`/`endDate` filters |
| `get-workout.js` | `getWorkout` | API Key (service lane) | Single workout with full metrics and optional template context |
| `upsert-workout.js` | `upsertWorkout` | Bearer (flexible) | Create or update workout with inline analytics computation, set_facts generation, and series updates. Idempotent on re-import. Used by `scripts/import_strong_csv.js` |
| `delete-workout.js` | `deleteWorkout` | Bearer (flexible) | Delete completed workout. Firestore trigger `onWorkoutDeleted` in `triggers/weekly-analytics.js` handles weekly_stats rollback automatically |

## Auth Pattern

- `getUserWorkouts` / `getWorkout`: userId from `req.query.userId` or `req.body.userId` (service lane, trusted agent/script calls)
- `upsertWorkout` / `deleteWorkout`: userId from `req.auth.uid` (Bearer lane, iOS app or authenticated service calls)

## Firestore Paths

- Read/write: `users/{uid}/workouts/{workoutId}`
- Side effects (upsert): `users/{uid}/set_facts/{factId}`, `users/{uid}/series_exercises/{key}`, `users/{uid}/series_muscle_groups/{key}`

## Cross-References

- **Triggers**: `triggers/weekly-analytics.js` — `onWorkoutCreated`, `onWorkoutDeleted` handle stats rollback
- **iOS caller**: `WorkoutRepository.swift` — `deleteWorkout()`, workout history fetching
- **Import scripts**: `scripts/import_strong_csv.js` — calls `upsertWorkout`
- **Agent tools**: `app/skills/coach_skills.py` — reads via `getUserWorkouts`
