const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');
const admin = require('firebase-admin');
const { ensureIdempotent } = require('../utils/idempotency');
const { ok, fail } = require('../utils/response');

const db = new FirestoreHelper();

async function swapExerciseHandler(req, res) {
  try {
    if (req.method !== 'POST') {
      return fail(res, 'METHOD_NOT_ALLOWED', 'Method Not Allowed', null, 405);
    }
    const userId = req.user?.uid || req.auth?.uid;
    if (!userId) return fail(res, 'UNAUTHORIZED', 'Unauthorized', null, 401);

    const { workout_id, from_exercise_id, to_exercise_id, reason } = req.body || {};
    const idempotencyKey = req.body?.idempotency_key;
    if (idempotencyKey) {
      const idem = await ensureIdempotent(userId, 'swap_exercise', idempotencyKey);
      if (idem.isDuplicate) return ok(res, { duplicate: true });
    }
    if (!workout_id || !from_exercise_id || !to_exercise_id) {
      return fail(res, 'INVALID_ARGUMENT', 'Missing parameters', { required: ['workout_id','from_exercise_id','to_exercise_id'] }, 400);
    }

    const parent = `users/${userId}/active_workouts`;
    const eventId = await db.addDocumentToSubcollection(parent, workout_id, 'events', {
      type: 'exercise_swapped',
      payload: { from_exercise_id, to_exercise_id, reason: reason || null },
      created_at: admin.firestore.FieldValue.serverTimestamp(),
    });

    await db.updateDocument(parent, workout_id, { updated_at: admin.firestore.FieldValue.serverTimestamp() });
    return ok(res, { event_id: eventId });
  } catch (error) {
    console.error('swap-exercise error:', error);
    return fail(res, 'INTERNAL', 'Failed to swap exercise', { message: error.message }, 500);
  }
}

exports.swapExercise = onRequest(
  { invoker: 'public' },
  requireFlexibleAuth(swapExerciseHandler)
);
