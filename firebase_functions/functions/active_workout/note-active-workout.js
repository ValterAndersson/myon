const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');
const admin = require('firebase-admin');

const db = new FirestoreHelper();

async function noteActiveWorkoutHandler(req, res) {
  try {
    if (req.method !== 'POST') {
      return res.status(405).json({ success: false, error: 'Method Not Allowed' });
    }
    const userId = req.user?.uid || req.auth?.uid;
    if (!userId) return res.status(401).json({ success: false, error: 'Unauthorized' });

    const { workout_id, note } = req.body || {};
    if (!workout_id || !note) return res.status(400).json({ success: false, error: 'Missing workout_id or note' });

    const parent = `users/${userId}/active_workouts`;
    const eventId = await db.addDocumentToSubcollection(parent, workout_id, 'events', {
      type: 'note',
      payload: { note },
      created_at: admin.firestore.FieldValue.serverTimestamp(),
    });

    await db.updateDocument(parent, workout_id, { updated_at: admin.firestore.FieldValue.serverTimestamp() });
    return res.status(200).json({ success: true, data: { event_id: eventId } });
  } catch (error) {
    console.error('note-active-workout error:', error);
    return res.status(500).json({ success: false, error: 'Failed to add note' });
  }
}

exports.noteActiveWorkout = onRequest(requireFlexibleAuth(noteActiveWorkoutHandler));


