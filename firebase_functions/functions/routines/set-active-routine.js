const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');
const { ok, fail } = require('../utils/response');

const db = new FirestoreHelper();

/**
 * Firebase Function: Set Active Routine
 */
async function setActiveRoutineHandler(req, res) {
  const { userId, routineId } = req.body || {};
  if (!userId || !routineId) return fail(res, 'INVALID_ARGUMENT', 'Missing required parameters', ['userId','routineId'], 400);

  try {
    // Check if routine exists
    const routine = await db.getDocumentFromSubcollection('users', userId, 'routines', routineId);
    if (!routine) return fail(res, 'NOT_FOUND', 'Routine not found', null, 404);

    // Update user's active routine
    await db.upsertDocument('users', userId, {
      activeRoutineId: routineId
    });

    return ok(res, { message: 'Active routine set', routineId, routine });

  } catch (error) {
    console.error('set-active-routine function error:', error);
    return fail(res, 'INTERNAL', 'Failed to set active routine', { message: error.message }, 500);
  }
}

exports.setActiveRoutine = onRequest(requireFlexibleAuth(setActiveRoutineHandler)); 