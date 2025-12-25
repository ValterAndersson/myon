const functions = require('firebase-functions');
const admin = require('firebase-admin');

const firestore = admin.firestore();

/**
 * Firestore Trigger: Update Routine Cursor on Workout Creation
 * 
 * When a workout is completed (archived to workouts collection), this trigger
 * updates the routine's cursor fields to track the last completed template.
 * 
 * This enables O(1) next-workout selection instead of scanning history.
 * 
 * Key behaviors:
 * - Uses source_routine_id from the workout (not current active routine)
 * - Only updates if source_template_id is in the routine's template_ids
 * - Updates last_completed_template_id and last_completed_at
 * 
 * This approach is correct because:
 * - User might change activeRoutineId while a workout is in progress
 * - User might log an ad-hoc workout not from any routine
 * - The source_routine_id captures the routine context at workout start time
 */
exports.onWorkoutCreatedUpdateRoutineCursor = functions.firestore
  .document('users/{userId}/workouts/{workoutId}')
  .onCreate(async (snap, context) => {
    const { userId, workoutId } = context.params;
    const workout = snap.data();

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
  });
