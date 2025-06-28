const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');

const db = new FirestoreHelper();

/**
 * Firebase Function: Get User Templates
 * 
 * Description: Gets all workout templates for a user
 */
async function getUserTemplatesHandler(req, res) {
  const userId = req.query.userId || req.body?.userId;
  
  if (!userId) {
    return res.status(400).json({
      success: false,
      error: 'Missing userId parameter',
      usage: 'Provide userId as query parameter or in request body'
    });
  }

  try {
    // Get all templates for user (removed orderBy due to timestamp conflicts)
    const templates = await db.getDocumentsFromSubcollection('users', userId, 'templates');

    return res.status(200).json({
      success: true,
      data: templates,
      count: templates.length,
      metadata: {
        function: 'get-user-templates',
        userId: userId,
        requestedAt: new Date().toISOString(),
        authType: req.auth?.type || 'firebase',
        source: req.auth?.source || 'user_app'
      }
    });

  } catch (error) {
    console.error('get-user-templates function error:', error);
    return res.status(500).json({
      success: false,
      error: 'Failed to get user templates',
      details: error.message,
      function: 'get-user-templates',
      timestamp: new Date().toISOString()
    });
  }
}

// Export Firebase Function
exports.getUserTemplates = onRequest(requireFlexibleAuth(getUserTemplatesHandler)); 