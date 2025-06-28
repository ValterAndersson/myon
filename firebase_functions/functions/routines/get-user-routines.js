const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');

const db = new FirestoreHelper();

/**
 * Firebase Function: Get User Routines
 * 
 * Description: Gets all routines for a user
 */
async function getUserRoutinesHandler(req, res) {
  const userId = req.query.userId || req.body?.userId;
  
  if (!userId) {
    return res.status(400).json({
      success: false,
      error: 'Missing userId parameter',
      usage: 'Provide userId as query parameter or in request body'
    });
  }

  try {
    // Get all routines for user (removed orderBy due to timestamp conflicts)
    const routines = await db.getDocumentsFromSubcollection('users', userId, 'routines');

    return res.status(200).json({
      success: true,
      data: routines,
      count: routines.length,
      metadata: {
        function: 'get-user-routines',
        userId: userId,
        requestedAt: new Date().toISOString(),
        authType: req.auth?.type || 'firebase',
        source: req.auth?.source || 'user_app'
      }
    });

  } catch (error) {
    console.error('get-user-routines function error:', error);
    return res.status(500).json({
      success: false,
      error: 'Failed to get user routines',
      details: error.message,
      function: 'get-user-routines',
      timestamp: new Date().toISOString()
    });
  }
}

// Export Firebase Function
exports.getUserRoutines = onRequest(requireFlexibleAuth(getUserRoutinesHandler)); 