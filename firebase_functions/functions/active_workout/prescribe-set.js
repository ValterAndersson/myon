const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');
const { fail, ok } = require('../utils/response');
const { PrescribeSchema } = require('../utils/validators');
const admin = require('firebase-admin');
const { ensureIdempotent } = require('../utils/idempotency');

const db = new FirestoreHelper();

async function prescribeSetHandler(req, res) {
  try {
    if (req.method !== 'POST') {
      return res.status(405).json({ success: false, error: 'Method Not Allowed' });
    }
    const userId = req.user?.uid || req.auth?.uid;
    if (!userId) return res.status(401).json({ success: false, error: 'Unauthorized' });

    const parsed = PrescribeSchema.safeParse(req.body || {});
    if (!parsed.success) return fail(res, 'INVALID_ARGUMENT', 'Invalid request', parsed.error.flatten(), 400);
    const { workout_id, exercise_id, set_index, context } = parsed.data;
    const idempotencyKey = req.body?.idempotency_key;
    if (idempotencyKey) {
      const idem = await ensureIdempotent(userId, 'prescribe_set', idempotencyKey);
      if (idem.isDuplicate) return ok(res, { duplicate: true });
    }

    // Very simple stub prescription
    const prescription = {
      reps: 8,
      rir_target: 2,
      weight: context?.previous?.weight || null,
      tempo: '3-1-1',
      rest_sec: 120,
    };

    const parentCollection = `users/${userId}/active_workouts`;
    const eventId = await db.addDocumentToSubcollection(parentCollection, workout_id, 'events', {
      type: 'prescribe_set',
      payload: { exercise_id, set_index, prescription },
      created_at: admin.firestore.FieldValue.serverTimestamp(),
    });

    await db.updateDocument(parentCollection, workout_id, {
      current: { exercise_id, set_index, prescription },
      updated_at: admin.firestore.FieldValue.serverTimestamp(),
    });

    return ok(res, { event_id: eventId, prescription, next_hint: null });
  } catch (error) {
    console.error('prescribe-set error:', error);
    return fail(res, 'INTERNAL', 'Failed to prescribe set', { message: error.message }, 500);
  }
}

exports.prescribeSet = onRequest(requireFlexibleAuth(prescribeSetHandler));


