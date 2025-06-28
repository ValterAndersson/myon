const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');

const db = new FirestoreHelper();

/**
 * Firebase Function: Delete Routine
 */
async function deleteRoutineHandler(req, res) {
  const { userId, routineId } = req.body;
  
  if (!userId || !routineId) {
    return res.status(400).json({
      success: false,
      error: 'Missing required parameters',
      required: ['userId', 'routineId']
    });
  }

  try {
    const routine = await db.getDocumentFromSubcollection('users', userId, 'routines', routineId);
    if (!routine) {
      return res.status(404).json({
        success: false,
        error: 'Routine not found'
      });
    }

    // Check if this is the active routine and clear it
    const user = await db.getDocument('users', userId);
    if (user?.activeRoutineId === routineId) {
      await db.updateDocument('users', userId, {
        activeRoutineId: null
        // Remove manual timestamp - FirestoreHelper handles this
      });
    }

    await db.deleteDocumentFromSubcollection('users', userId, 'routines', routineId);

    return res.status(200).json({
      success: true,
      message: 'Routine deleted successfully',
      routineId: routineId,
      activeRoutineCleared: user?.activeRoutineId === routineId,
      metadata: {
        function: 'delete-routine',
        userId: userId,
        routineId: routineId,
        deletedAt: new Date().toISOString()
      }
    });

  } catch (error) {
    console.error('delete-routine function error:', error);
    return res.status(500).json({
      success: false,
      error: 'Failed to delete routine',
      details: error.message
    });
  }
}

exports.deleteRoutine = onRequest(requireFlexibleAuth(deleteRoutineHandler)); 