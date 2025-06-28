const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');

const db = new FirestoreHelper();

/**
 * Firebase Function: Get Specific Exercise
 */
async function getExerciseHandler(req, res) {
  const exerciseId = req.query.exerciseId || req.body?.exerciseId;
  
  if (!exerciseId) {
    return res.status(400).json({
      success: false,
      error: 'Missing exerciseId parameter'
    });
  }

  try {
    const exercise = await db.getDocument('exercises', exerciseId);
    
    if (!exercise) {
      return res.status(404).json({
        success: false,
        error: 'Exercise not found',
        exerciseId: exerciseId
      });
    }

    return res.status(200).json({
      success: true,
      data: exercise,
      metadata: {
        function: 'get-exercise',
        exerciseId: exerciseId,
        requestedAt: new Date().toISOString()
      }
    });

  } catch (error) {
    console.error('get-exercise function error:', error);
    return res.status(500).json({
      success: false,
      error: 'Failed to get exercise',
      details: error.message
    });
  }
}

exports.getExercise = onRequest(requireFlexibleAuth(getExerciseHandler)); 