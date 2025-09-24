const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');
const { ok, fail } = require('../utils/response');
const admin = require('firebase-admin');

const db = new FirestoreHelper();

async function startActiveWorkoutHandler(req, res) {
  try {
    if (req.method !== 'POST') {
      return res.status(405).json({ success: false, error: 'Method Not Allowed' });
    }

    const userId = req.user?.uid || req.auth?.uid;
    if (!userId) return fail(res, 'UNAUTHENTICATED', 'Unauthorized', null, 401);

    const plan = req.body?.plan || null;

    const workout = {
      id: null,
      user_id: userId,
      status: 'in_progress',
      source_template_id: null,
      notes: null,
      plan: plan || null,
      current: null,
      exercises: [],
      totals: { sets: 0, reps: 0, volume: 0, stimulus_score: 0 },
      start_time: admin.firestore.FieldValue.serverTimestamp(),
      end_time: null,
    };

    const collectionPath = `users/${userId}/active_workouts`;
    const workoutId = await db.addDocument(collectionPath, workout);

    return ok(res, { workout_id: workoutId, active_workout_doc: { ...workout, id: workoutId } });
  } catch (error) {
    console.error('start-active-workout error:', error);
    return fail(res, 'INTERNAL', 'Failed to start active workout', { message: error.message }, 500);
  }
}

exports.startActiveWorkout = onRequest(requireFlexibleAuth(startActiveWorkoutHandler));


