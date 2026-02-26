const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');
const { ok, fail } = require('../utils/response');
const { getAuthenticatedUserId } = require('../utils/auth-helpers');

const db = new FirestoreHelper();

/**
 * Firebase Function: Get Specific Workout
 * 
 * Description: Gets full workout details with sets, reps, weights for a specific workout
 */
async function getWorkoutHandler(req, res) {
  const userId = getAuthenticatedUserId(req);
  const workoutId = req.query.workoutId || req.body?.workoutId;
  if (!userId || !workoutId) return fail(res, 'INVALID_ARGUMENT', 'Missing required parameters', ['userId','workoutId'], 400);

  try {
    // Get workout
    const workout = await db.getDocumentFromSubcollection('users', userId, 'workouts', workoutId);
    if (!workout) return fail(res, 'NOT_FOUND', 'Workout not found', null, 404);

    // Get template info if available
    let template = null;
    if (workout.templateId) {
      template = await db.getDocumentFromSubcollection('users', userId, 'templates', workout.templateId);
    }

    // Calculate workout metrics for AI analysis
    const metrics = {
      duration: null,
      totalSets: 0,
      totalReps: 0,
      totalVolume: 0,
      exerciseCount: workout.exercises?.length || 0
    };

    if (workout.startedAt && workout.completedAt) {
      metrics.duration = Math.round((new Date(workout.completedAt) - new Date(workout.startedAt)) / (1000 * 60));
    }

    if (workout.exercises) {
      workout.exercises.forEach(exercise => {
        if (exercise.sets) {
          metrics.totalSets += exercise.sets.length;
          exercise.sets.forEach(set => {
            if (set.reps) metrics.totalReps += set.reps;
            if (set.weight && set.reps) metrics.totalVolume += (set.weight * set.reps);
          });
        }
      });
    }

    return ok(res, { workout, template, metrics });

  } catch (error) {
    console.error('get-workout function error:', error);
    return fail(res, 'INTERNAL', 'Failed to get workout', { message: error.message }, 500);
  }
}

// Export Firebase Function
exports.getWorkout = onRequest(requireFlexibleAuth(getWorkoutHandler)); 