# Triggers — Module Architecture

Firestore triggers that react to document lifecycle events. All triggers are v2 functions using `onDocumentCreated`, `onDocumentUpdated`, or `onDocumentDeleted`.

## File Inventory

| File | Trigger Events | Purpose |
|------|---------------|---------|
| `workout-routine-cursor.js` | `onDocumentCreated('users/{userId}/workouts/{workoutId}')` | Updates routine cursor (`last_completed_template_id`, `last_completed_at`) when a workout with `source_routine_id` is archived. Enables O(1) next-workout selection. |
| `weekly-analytics.js` | Multiple triggers on `users/{userId}/workouts/{workoutId}` | Maintains `weekly_stats`, `analytics_series_exercise`, `analytics_series_muscle` collections. Handles workout created, completed, deleted events. Also exports scheduled `weeklyStatsRecalculation`. |
| `muscle-volume-calculations.js` | `onTemplateCreated`, `onTemplateUpdated`, `onWorkoutCreated` | Computes template analytics (estimated duration, total sets, muscles) and workout analytics on document creation/update. |

## Trigger → Collection Mapping

| Trigger | Reads From | Writes To |
|---------|-----------|-----------|
| `onWorkoutCreatedUpdateRoutineCursor` | `workouts/{id}`, `routines/{id}` | `routines/{id}` (cursor fields) |
| `onWorkoutCompleted` / `onWorkoutCreatedWeekly` | `workouts/{id}` | `weekly_stats/{weekId}`, `analytics_series_*` |
| `onWorkoutDeleted` | (deleted doc) | `weekly_stats/{weekId}`, `analytics_series_*` (decrements) |
| `onTemplateCreated/Updated` | `templates/{id}` | `templates/{id}` (analytics field) |
| `onWorkoutCreated` | `workouts/{id}` | `workouts/{id}` (analytics field) |

## Key Behaviors

- **Best-effort**: `workout-routine-cursor.js` catches errors and logs rather than failing the trigger
- **Idempotent**: `weekly-analytics.js` uses deterministic set IDs for upserts
- **No auth**: Triggers don't need authentication middleware — they fire from trusted Firestore events

## Cross-References

- Routine cursor consumed by: `routines/get-next-workout.js`
- Workouts created by: `active_workout/complete-active-workout.js`
- Analytics series read by: `analytics/get-features.js`, `training/series-endpoints.js`
