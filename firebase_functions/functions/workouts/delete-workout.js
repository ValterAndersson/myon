/**
 * =============================================================================
 * delete-workout.js - Permanently Delete a Completed Workout
 * =============================================================================
 *
 * PURPOSE:
 * Deletes a completed workout from the user's workouts collection.
 * The existing onWorkoutDeleted Firestore trigger in triggers/weekly-analytics.js
 * handles rolling back weekly_stats automatically.
 *
 * AUTH: requireFlexibleAuth (Bearer lane — iOS app calls)
 * userId derived from req.auth.uid, never from client body.
 *
 * FIRESTORE OPERATIONS:
 * - Deletes: users/{uid}/workouts/{workout_id}
 *
 * CALLED BY:
 * - iOS: WorkoutRepository.deleteWorkout()
 *
 * =============================================================================
 */

const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const admin = require('firebase-admin');
const { ok, fail } = require('../utils/response');

const firestore = admin.firestore();

async function deleteWorkoutHandler(req, res) {
  try {
    if (req.method !== 'POST') {
      return res.status(405).json({ success: false, error: 'Method Not Allowed' });
    }

    const userId = req.user?.uid || req.auth?.uid;
    if (!userId) return res.status(401).json({ success: false, error: 'Unauthorized' });

    const { workout_id } = req.body || {};
    if (!workout_id) return fail(res, 'INVALID_ARGUMENT', 'Missing workout_id', null, 400);

    const workoutRef = firestore.collection('users').doc(userId).collection('workouts').doc(workout_id);
    const doc = await workoutRef.get();

    if (!doc.exists) return fail(res, 'NOT_FOUND', 'Workout not found', null, 404);

    await workoutRef.delete();
    console.log(`Deleted workout ${workout_id} for user ${userId}`);

    return ok(res, { deleted: true, workout_id });
  } catch (error) {
    console.error('delete-workout error:', error);
    return fail(res, 'INTERNAL', 'Failed to delete workout', { message: error.message }, 500);
  }
}

exports.deleteWorkout = onRequest(
  { invoker: 'public' },
  requireFlexibleAuth(deleteWorkoutHandler)
);
