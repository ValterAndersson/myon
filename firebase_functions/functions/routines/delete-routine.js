const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');
const { ok, fail } = require('../utils/response');

const db = new FirestoreHelper();

/**
 * Firebase Function: Delete Routine
 */
async function deleteRoutineHandler(req, res) {
  const { userId, routineId } = req.body || {};
  if (!userId || !routineId) return fail(res, 'INVALID_ARGUMENT', 'Missing required parameters', ['userId','routineId'], 400);

  try {
    const routine = await db.getDocumentFromSubcollection('users', userId, 'routines', routineId);
    if (!routine) return fail(res, 'NOT_FOUND', 'Routine not found', null, 404);

    // Check if this is the active routine and clear it
    const user = await db.getDocument('users', userId);
    if (user?.activeRoutineId === routineId) {
      await db.updateDocument('users', userId, {
        activeRoutineId: null
        // Remove manual timestamp - FirestoreHelper handles this
      });
    }

    await db.deleteDocumentFromSubcollection('users', userId, 'routines', routineId);

    return ok(res, { message: 'Routine deleted', routineId, activeRoutineCleared: user?.activeRoutineId === routineId });

  } catch (error) {
    console.error('delete-routine function error:', error);
    return fail(res, 'INTERNAL', 'Failed to delete routine', { message: error.message }, 500);
  }
}

exports.deleteRoutine = onRequest(requireFlexibleAuth(deleteRoutineHandler)); 