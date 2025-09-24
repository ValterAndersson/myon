const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');
const { ok, fail } = require('../utils/response');

const db = new FirestoreHelper();

async function approveExerciseHandler(req, res) {
  try {
    if (req.method !== 'POST') {
      return fail(res, 'METHOD_NOT_ALLOWED', 'Method Not Allowed', null, 405);
    }
    const userId = req.user?.uid || req.auth?.uid || 'service';

    const { exercise_id, version } = req.body || {};
    if (!exercise_id) return fail(res, 'INVALID_ARGUMENT', 'Missing exercise_id', null, 400);

    await db.updateDocument('exercises', exercise_id, { status: 'approved', version: version ?? 1 });
    return ok(res, { exercise_id, status: 'approved' });
  } catch (error) {
    console.error('approve-exercise error:', error);
    return fail(res, 'INTERNAL', 'Failed to approve exercise', { message: error.message }, 500);
  }
}

exports.approveExercise = onRequest(requireFlexibleAuth(approveExerciseHandler));


