const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');
const admin = require('firebase-admin');
const { ensureIdempotent } = require('../utils/idempotency');

const db = new FirestoreHelper();

async function addExerciseHandler(req, res) {
  try {
    if (req.method !== 'POST') {
      return res.status(405).json({ success: false, error: 'Method Not Allowed' });
    }
    const userId = req.user?.uid || req.auth?.uid;
    if (!userId) return res.status(401).json({ success: false, error: 'Unauthorized' });

    const { workout_id, exercise_id, name, position } = req.body || {};
    const idempotencyKey = req.body?.idempotency_key;
    if (idempotencyKey) {
      const idem = await ensureIdempotent(userId, 'add_exercise', idempotencyKey);
      if (idem.isDuplicate) return res.status(200).json({ success: true, data: { duplicate: true } });
    }
    if (!workout_id || !exercise_id) {
      return res.status(400).json({ success: false, error: 'Missing workout_id or exercise_id' });
    }

    const parent = `users/${userId}/active_workouts`;
    const eventId = await db.addDocumentToSubcollection(parent, workout_id, 'events', {
      type: 'exercise_added',
      payload: { exercise_id, name: name || null, position: typeof position === 'number' ? position : null },
      created_at: admin.firestore.FieldValue.serverTimestamp(),
    });

    await db.updateDocument(parent, workout_id, { updated_at: admin.firestore.FieldValue.serverTimestamp() });

    return res.status(200).json({ success: true, data: { event_id: eventId } });
  } catch (error) {
    console.error('add-exercise error:', error);
    return res.status(500).json({ success: false, error: 'Failed to add exercise' });
  }
}

exports.addExercise = onRequest(requireFlexibleAuth(addExerciseHandler));


