const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');

const db = new FirestoreHelper();

/**
 * Firebase Function: Get Specific Routine
 * 
 * Description: Gets a specific routine by ID
 */
async function getRoutineHandler(req, res) {
  const userId = req.query.userId || req.body?.userId;
  const routineId = req.query.routineId || req.body?.routineId;
  
  if (!userId || !routineId) {
    return res.status(400).json({
      success: false,
      error: 'Missing required parameters',
      required: ['userId', 'routineId'],
      usage: 'Provide both userId and routineId'
    });
  }

  try {
    // Get routine
    const routine = await db.getDocumentFromSubcollection('users', userId, 'routines', routineId);
    
    if (!routine) {
      return res.status(404).json({
        success: false,
        error: 'Routine not found',
        userId: userId,
        routineId: routineId
      });
    }

    return res.status(200).json({
      success: true,
      data: routine,
      metadata: {
        function: 'get-routine',
        userId: userId,
        routineId: routineId,
        requestedAt: new Date().toISOString(),
        authType: req.auth?.type || 'firebase',
        source: req.auth?.source || 'user_app'
      }
    });

  } catch (error) {
    console.error('get-routine function error:', error);
    return res.status(500).json({
      success: false,
      error: 'Failed to get routine',
      details: error.message,
      function: 'get-routine',
      timestamp: new Date().toISOString()
    });
  }
}

// Export Firebase Function
exports.getRoutine = onRequest(requireFlexibleAuth(getRoutineHandler)); 