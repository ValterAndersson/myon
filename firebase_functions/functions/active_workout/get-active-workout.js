const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');

const db = new FirestoreHelper();

async function getActiveWorkoutHandler(req, res) {
  try {
    if (req.method !== 'GET' && req.method !== 'POST') {
      return res.status(405).json({ success: false, error: 'Method Not Allowed' });
    }

    const userId = req.user?.uid || req.auth?.uid;
    if (!userId) {
      return res.status(401).json({ success: false, error: 'Unauthorized' });
    }

    const collectionPath = `users/${userId}/active_workouts`;
    const docs = await db.getDocuments(collectionPath, {
      orderBy: { field: 'updated_at', direction: 'desc' },
      limit: 1,
    });
    const workout = docs.length > 0 ? docs[0] : null;

    return res.status(200).json({ success: true, data: { workout } });
  } catch (error) {
    console.error('get-active-workout error:', error);
    return res.status(500).json({ success: false, error: 'Failed to get active workout' });
  }
}

exports.getActiveWorkout = onRequest(requireFlexibleAuth(getActiveWorkoutHandler));


