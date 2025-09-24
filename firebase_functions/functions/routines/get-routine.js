const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');
const { ok, fail } = require('../utils/response');

const db = new FirestoreHelper();

/**
 * Firebase Function: Get Specific Routine
 * 
 * Description: Gets a specific routine by ID
 */
async function getRoutineHandler(req, res) {
  const userId = req.query.userId || req.body?.userId;
  const routineId = req.query.routineId || req.body?.routineId;
  if (!userId || !routineId) return fail(res, 'INVALID_ARGUMENT', 'Missing required parameters', ['userId','routineId'], 400);

  try {
    // Get routine
    const routine = await db.getDocumentFromSubcollection('users', userId, 'routines', routineId);
    if (!routine) return fail(res, 'NOT_FOUND', 'Routine not found', null, 404);

    return ok(res, routine);

  } catch (error) {
    console.error('get-routine function error:', error);
    return fail(res, 'INTERNAL', 'Failed to get routine', { message: error.message }, 500);
  }
}

// Export Firebase Function
exports.getRoutine = onRequest(requireFlexibleAuth(getRoutineHandler)); 