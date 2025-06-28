const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');

const db = new FirestoreHelper();

/**
 * Firebase Function: Get All Exercises
 */
async function getExercisesHandler(req, res) {
  try {
    const exercises = await db.getDocuments('exercises');

    return res.status(200).json({
      success: true,
      data: exercises,
      count: exercises.length,
      metadata: {
        function: 'get-exercises',
        requestedAt: new Date().toISOString(),
        authType: req.auth?.type || 'firebase',
        source: req.auth?.source || 'user_app'
      }
    });

  } catch (error) {
    console.error('get-exercises function error:', error);
    return res.status(500).json({
      success: false,
      error: 'Failed to get exercises',
      details: error.message
    });
  }
}

exports.getExercises = onRequest(requireFlexibleAuth(getExercisesHandler)); 