const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');
const { ok, fail } = require('../utils/response');
const { getAuthenticatedUserId } = require('../utils/auth-helpers');

const db = new FirestoreHelper();

/**
 * Firebase Function: Get Active Routine
 */
async function getActiveRoutineHandler(req, res) {
  const userId = getAuthenticatedUserId(req);
  if (!userId) return fail(res, 'INVALID_ARGUMENT', 'Missing userId parameter', null, 400);

  try {
    const user = await db.getDocument('users', userId);
    if (!user) return fail(res, 'NOT_FOUND', 'User not found', null, 404);

    if (!user.activeRoutineId) {
      return ok(res, { routine: null, message: 'No active routine set' });
    }

    const activeRoutine = await db.getDocumentFromSubcollection('users', userId, 'routines', user.activeRoutineId);

    return ok(res, { routine: activeRoutine });

  } catch (error) {
    console.error('get-active-routine function error:', error);
    return fail(res, 'INTERNAL', 'Failed to get active routine', { message: error.message }, 500);
  }
}

exports.getActiveRoutine = onRequest(requireFlexibleAuth(getActiveRoutineHandler)); 