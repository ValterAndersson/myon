/**
 * =============================================================================
 * workout-routine-cursor.js - Routine Cursor Advancement Trigger
 * =============================================================================
 *
 * PURPOSE:
 * Firestore trigger that updates the routine cursor when a workout is completed.
 * This enables O(1) next-workout selection in get-next-workout.js.
 *
 * ARCHITECTURE CONTEXT:
 * ┌────────────────────────────────────────────────────────────────────────────┐
 * │ ROUTINE CURSOR FLOW                                                        │
 * │                                                                            │
 * │ complete-active-workout.js                                                 │
 * │   │                                                                        │
 * │   ▼ (creates document)                                                     │
 * │ users/{uid}/workouts/{workoutId}                                          │
 * │   {                                                                        │
 * │     source_routine_id: "routine_abc",                                     │
 * │     source_template_id: "template_push",                                  │
 * │     end_time: 2024-01-15T10:00:00Z                                        │
 * │   }                                                                        │
 * │   │                                                                        │
 * │   ▼ (Firestore onCreate trigger - THIS FILE)                              │
 * │ workout-routine-cursor.js                                                  │
 * │   │                                                                        │
 * │   ▼ (updates routine)                                                      │
 * │ users/{uid}/routines/{routineId}                                          │
 * │   {                                                                        │
 * │     last_completed_template_id: "template_push",  ← UPDATED               │
 * │     last_completed_at: 2024-01-15T10:00:00Z       ← UPDATED               │
 * │   }                                                                        │
 * │                                                                            │
 * │ Next call to get-next-workout.js uses last_completed_template_id          │
 * │ for O(1) cursor lookup instead of scanning workout history                 │
 * └────────────────────────────────────────────────────────────────────────────┘
 *
 * TRIGGER DETAILS:
 * - Event: onDocumentCreated('users/{userId}/workouts/{workoutId}')
 * - Condition: Only fires when source_routine_id AND source_template_id exist
 * - Updates: routines/{source_routine_id}.last_completed_template_id
 * - Best-effort: Errors are logged but don't fail the trigger
 *
 * KEY BEHAVIORS:
 * - Uses source_routine_id from workout (not user.activeRoutineId)
 *   → Handles case where user changes routine mid-workout
 * - Only updates if template is still in routine.template_ids
 *   → Handles case where routine was edited after workout started
 * - Non-blocking: Doesn't throw on error (best-effort update)
 *
 * TRIGGERED BY:
 * - complete-active-workout.js when workout is archived to workouts collection
 *
 * RELATED FILES:
 * - ../routines/get-next-workout.js: Reads cursor for O(1) template selection
 * - ../active_workout/complete-active-workout.js: Creates the workout doc
 * - ../active_workout/start-active-workout.js: Captures source_routine_id
 *
 * UNUSED CODE CHECK: ✅ No unused code in this file
 *
 * =============================================================================
 */

const { onDocumentCreated } = require('firebase-functions/v2/firestore');
const admin = require('firebase-admin');

const firestore = admin.firestore();
exports.onWorkoutCreatedUpdateRoutineCursor = onDocumentCreated(
  'users/{userId}/workouts/{workoutId}',
  async (event) => {
    const { userId, workoutId } = event.params;
    const workout = event.data.data();

    // Only process if this workout has routine and template attribution
    if (!workout.source_routine_id || !workout.source_template_id) {
      console.log(`Workout ${workoutId}: No source_routine_id or source_template_id, skipping cursor update`);
      return null;
    }

    // Only process completed workouts (has end_time)
    if (!workout.end_time) {
      console.log(`Workout ${workoutId}: No end_time, skipping cursor update`);
      return null;
    }

    try {
      // Get the source routine
      const routineRef = firestore
        .collection('users')
        .doc(userId)
        .collection('routines')
        .doc(workout.source_routine_id);
      
      const routineDoc = await routineRef.get();
      
      if (!routineDoc.exists) {
        console.log(`Workout ${workoutId}: Source routine ${workout.source_routine_id} not found, skipping cursor update`);
        return null;
      }

      const routine = routineDoc.data();
      const templateIds = routine.template_ids || routine.templateIds || [];

      // Only update cursor if this template is still in the routine
      if (!templateIds.includes(workout.source_template_id)) {
        console.log(`Workout ${workoutId}: Template ${workout.source_template_id} not in routine's template_ids, skipping cursor update`);
        return null;
      }

      // Update the routine's cursor fields
      await routineRef.update({
        last_completed_template_id: workout.source_template_id,
        last_completed_at: workout.end_time
      });

      console.log(`Workout ${workoutId}: Updated routine ${workout.source_routine_id} cursor to template ${workout.source_template_id}`);
      return null;

    } catch (error) {
      console.error(`Error updating routine cursor for workout ${workoutId}:`, error);
      // Don't throw - cursor update is best-effort, shouldn't fail workout creation
      return null;
    }
  }
);
