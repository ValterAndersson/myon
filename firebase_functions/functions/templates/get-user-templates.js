const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');
const { ok, fail } = require('../utils/response');

const db = new FirestoreHelper();

/**
 * Firebase Function: Get User Templates
 * 
 * Description: Gets all workout templates for a user
 */
async function getUserTemplatesHandler(req, res) {
  const userId = req.query.userId || req.body?.userId;
  
  if (!userId) return fail(res, 'INVALID_ARGUMENT', 'Missing userId parameter', null, 400);

  try {
    // Get all templates for user (removed orderBy due to timestamp conflicts)
    const templates = await db.getDocumentsFromSubcollection('users', userId, 'templates');

    return ok(res, { items: templates, count: templates.length });

  } catch (error) {
    console.error('get-user-templates function error:', error);
    return fail(res, 'INTERNAL', 'Failed to get user templates', { message: error.message }, 500);
  }
}

// Export Firebase Function
exports.getUserTemplates = onRequest(requireFlexibleAuth(getUserTemplatesHandler)); 