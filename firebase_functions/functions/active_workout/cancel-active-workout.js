const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');
const admin = require('firebase-admin');

const db = new FirestoreHelper();

/**
 * Cancel (discard) an active workout.
 * Sets status to 'cancelled' and end_time.
 */
async function cancelActiveWorkoutHandler(req, res) {
  try {
    if (req.method !== 'POST') {
      return res.status(405).json({ success: false, error: 'Method Not Allowed' });
    }
    const userId = req.user?.uid || req.auth?.uid;
    if (!userId) return res.status(401).json({ success: false, error: 'Unauthorized' });

    const { workout_id } = req.body || {};
    if (!workout_id) return res.status(400).json({ success: false, error: 'Missing workout_id' });

    const parent = `users/${userId}/active_workouts`;
    await db.updateDocument(parent, workout_id, { status: 'cancelled', end_time: admin.firestore.FieldValue.serverTimestamp(), updated_at: admin.firestore.FieldValue.serverTimestamp() });
    return res.status(200).json({ success: true, data: { status: 'cancelled' } });
  } catch (error) {
    console.error('cancel-active-workout error:', error);
    return res.status(500).json({ success: false, error: 'Failed to cancel active workout' });
  }
}

exports.cancelActiveWorkout = onRequest(
  { invoker: 'public' },
  requireFlexibleAuth(cancelActiveWorkoutHandler)
);
