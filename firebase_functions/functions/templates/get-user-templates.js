const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');
const { ok, fail } = require('../utils/response');

const db = new FirestoreHelper();

/**
 * Firebase Function: Get User Templates
 * 
 * Description: Gets all workout templates for the authenticated user.
 * 
 * SECURITY: Uses authenticated user ID only. Client-provided userId is IGNORED
 * to prevent data exfiltration (user A requesting user B's templates).
 */
async function getUserTemplatesHandler(req, res) {
  // P0 Security Fix: ONLY use authenticated user ID, ignore any client-provided userId
  const userId = req.user?.uid || req.auth?.uid;
  
  if (!userId) return fail(res, 'UNAUTHENTICATED', 'Authentication required', null, 401);

  try {
    // Get all templates for authenticated user (removed orderBy due to timestamp conflicts)
    const templates = await db.getDocumentsFromSubcollection('users', userId, 'templates');

    return ok(res, { items: templates, count: templates.length });

  } catch (error) {
    console.error('get-user-templates function error:', error);
    return fail(res, 'INTERNAL', 'Failed to get user templates', { message: error.message }, 500);
  }
}

// Export Firebase Function
exports.getUserTemplates = onRequest(requireFlexibleAuth(getUserTemplatesHandler));
