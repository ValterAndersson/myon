const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');

const db = new FirestoreHelper();

/**
 * Firebase Function: Get Active Routine
 */
async function getActiveRoutineHandler(req, res) {
  const userId = req.query.userId || req.body?.userId;
  
  if (!userId) {
    return res.status(400).json({
      success: false,
      error: 'Missing userId parameter'
    });
  }

  try {
    const user = await db.getDocument('users', userId);
    if (!user) {
      return res.status(404).json({
        success: false,
        error: 'User not found'
      });
    }

    if (!user.activeRoutineId) {
      return res.status(200).json({
        success: true,
        data: null,
        message: 'No active routine set'
      });
    }

    const activeRoutine = await db.getDocumentFromSubcollection('users', userId, 'routines', user.activeRoutineId);

    return res.status(200).json({
      success: true,
      data: activeRoutine,
      metadata: {
        function: 'get-active-routine',
        userId: userId,
        requestedAt: new Date().toISOString()
      }
    });

  } catch (error) {
    console.error('get-active-routine function error:', error);
    return res.status(500).json({
      success: false,
      error: 'Failed to get active routine',
      details: error.message
    });
  }
}

exports.getActiveRoutine = onRequest(requireFlexibleAuth(getActiveRoutineHandler)); 