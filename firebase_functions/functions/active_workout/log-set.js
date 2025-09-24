const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');
const admin = require('firebase-admin');
const { fail, ok } = require('../utils/response');
const { LogSetSchema } = require('../utils/validators');
const { ensureIdempotent } = require('../utils/idempotency');

const db = new FirestoreHelper();

async function logSetHandler(req, res) {
  try {
    if (req.method !== 'POST') {
      return res.status(405).json({ success: false, error: 'Method Not Allowed' });
    }
    const userId = req.user?.uid || req.auth?.uid;
    if (!userId) return res.status(401).json({ success: false, error: 'Unauthorized' });

    const parsed = LogSetSchema.safeParse(req.body || {});
    if (!parsed.success) return fail(res, 'INVALID_ARGUMENT', 'Invalid request', parsed.error.flatten(), 400);
    const { workout_id, exercise_id, set_index, actual } = parsed.data;
    const idempotencyKey = req.body?.idempotency_key;

    if (idempotencyKey) {
      const idem = await ensureIdempotent(userId, 'log_set', idempotencyKey);
      if (idem.isDuplicate) return ok(res, { duplicate: true });
    }

    const parentCollection = `users/${userId}/active_workouts`;
    const eventId = await db.addDocumentToSubcollection(parentCollection, workout_id, 'events', {
      type: 'set_performed',
      payload: { exercise_id, set_index, actual },
      created_at: admin.firestore.FieldValue.serverTimestamp(),
    });

    // naive totals update (stub)
    await db.updateDocument(parentCollection, workout_id, {
      updated_at: admin.firestore.FieldValue.serverTimestamp(),
    });

    return ok(res, { event_id: eventId });
  } catch (error) {
    console.error('log-set error:', error);
    return fail(res, 'INTERNAL', 'Failed to log set', { message: error.message }, 500);
  }
}

exports.logSet = onRequest(requireFlexibleAuth(logSetHandler));


