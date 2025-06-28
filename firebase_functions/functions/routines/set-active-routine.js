const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');

const db = new FirestoreHelper();

/**
 * Firebase Function: Set Active Routine
 */
async function setActiveRoutineHandler(req, res) {
  const { userId, routineId } = req.body;
  
  if (!userId || !routineId) {
    return res.status(400).json({
      success: false,
      error: 'Missing required parameters',
      required: ['userId', 'routineId']
    });
  }

  try {
    // Check if routine exists
    const routine = await db.getDocumentFromSubcollection('users', userId, 'routines', routineId);
    if (!routine) {
      return res.status(404).json({
        success: false,
        error: 'Routine not found'
      });
    }

    // Update user's active routine
    await db.updateDocument('users', userId, {
      activeRoutineId: routineId
      // Remove manual timestamp - FirestoreHelper handles this
    });

    return res.status(200).json({
      success: true,
      message: 'Active routine set successfully',
      routineId: routineId,
      routine: routine,
      metadata: {
        function: 'set-active-routine',
        userId: userId,
        routineId: routineId,
        updatedAt: new Date().toISOString()
      }
    });

  } catch (error) {
    console.error('set-active-routine function error:', error);
    return res.status(500).json({
      success: false,
      error: 'Failed to set active routine',
      details: error.message
    });
  }
}

exports.setActiveRoutine = onRequest(requireFlexibleAuth(setActiveRoutineHandler)); 