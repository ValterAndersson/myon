const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');
const { ok, fail } = require('../utils/response');

const db = new FirestoreHelper();

/**
 * Firebase Function: Get User Routines
 * 
 * Description: Gets all routines for a user
 */
async function getUserRoutinesHandler(req, res) {
  const userId = req.query.userId || req.body?.userId;
  if (!userId) return fail(res, 'INVALID_ARGUMENT', 'Missing userId parameter', null, 400);

  try {
    // Get all routines for user (removed orderBy due to timestamp conflicts)
    const routines = await db.getDocumentsFromSubcollection('users', userId, 'routines');

    return ok(res, { items: routines, count: routines.length });

  } catch (error) {
    console.error('get-user-routines function error:', error);
    return fail(res, 'INTERNAL', 'Failed to get user routines', { message: error.message }, 500);
  }
}

// Export Firebase Function
exports.getUserRoutines = onRequest(requireFlexibleAuth(getUserRoutinesHandler)); 