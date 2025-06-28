const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');

const db = new FirestoreHelper();

/**
 * Firebase Function: Update Routine
 */
async function updateRoutineHandler(req, res) {
  const { userId, routineId, routine } = req.body;
  
  if (!userId || !routineId || !routine) {
    return res.status(400).json({
      success: false,
      error: 'Missing required parameters',
      required: ['userId', 'routineId', 'routine']
    });
  }

  try {
    const existingRoutine = await db.getDocumentFromSubcollection('users', userId, 'routines', routineId);
    if (!existingRoutine) {
      return res.status(404).json({
        success: false,
        error: 'Routine not found'
      });
    }

    const updatedRoutine = {
      ...routine,
      // Guarantee an `id` field inside the document
      id: routine.id || routineId
    };

    await db.updateDocumentInSubcollection('users', userId, 'routines', routineId, updatedRoutine);
    const result = await db.getDocumentFromSubcollection('users', userId, 'routines', routineId);

    return res.status(200).json({
      success: true,
      data: result,
      metadata: {
        function: 'update-routine',
        userId: userId,
        routineId: routineId,
        updatedAt: new Date().toISOString()
      }
    });

  } catch (error) {
    console.error('update-routine function error:', error);
    return res.status(500).json({
      success: false,
      error: 'Failed to update routine',
      details: error.message
    });
  }
}

exports.updateRoutine = onRequest(requireFlexibleAuth(updateRoutineHandler)); 