const { onRequest } = require('firebase-functions/v2/https');
const { logger } = require('firebase-functions');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');
const { ok, fail } = require('../utils/response');
const admin = require('firebase-admin');

const db = new FirestoreHelper();

/**
 * Firebase Function: Get Specific Routine
 *
 * Description: Gets a specific routine by ID.
 * Enriches the response with `is_active` derived from the user's `activeRoutineId`.
 */
async function getRoutineHandler(req, res) {
  // Bearer-lane: derive userId from verified token; API-key-lane: from params
  const userId = req.auth?.uid || req.query.userId || req.body?.userId;
  const routineId = req.query.routineId || req.body?.routineId;
  if (!userId || !routineId) return fail(res, 'INVALID_ARGUMENT', 'Missing required parameters', ['userId','routineId'], 400);

  try {
    const [routine, userSnap] = await Promise.all([
      db.getDocumentFromSubcollection('users', userId, 'routines', routineId),
      admin.firestore().collection('users').doc(userId).get(),
    ]);
    if (!routine) return fail(res, 'NOT_FOUND', 'Routine not found', null, 404);

    // Derive is_active from user-level activeRoutineId
    const activeRoutineId = userSnap.exists ? userSnap.data().activeRoutineId : null;
    routine.is_active = routine.id === activeRoutineId;

    return ok(res, routine);

  } catch (error) {
    logger.error('[getRoutine] Failed to get routine', { userId, routineId, error: error.message });
    return fail(res, 'INTERNAL', 'Failed to get routine', { message: error.message }, 500);
  }
}

// Export Firebase Function
exports.getRoutine = onRequest(requireFlexibleAuth(getRoutineHandler)); 