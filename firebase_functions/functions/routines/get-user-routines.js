const { onRequest } = require('firebase-functions/v2/https');
const { logger } = require('firebase-functions');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');
const { ok, fail } = require('../utils/response');
const { getAuthenticatedUserId } = require('../utils/auth-helpers');
const admin = require('firebase-admin');

const db = new FirestoreHelper();

/**
 * Firebase Function: Get User Routines
 *
 * Description: Gets all routines for a user.
 * Enriches each routine with `is_active` derived from the user's `activeRoutineId`.
 */
async function getUserRoutinesHandler(req, res) {
  // Use authenticated user's ID from Bearer token, or fall back to explicit userId param (for API key auth)
  const userId = getAuthenticatedUserId(req);
  if (!userId) return fail(res, 'UNAUTHENTICATED', 'Authentication required', null, 401);

  try {
    // Fetch routines and user doc in parallel
    const [routines, userSnap] = await Promise.all([
      db.getDocumentsFromSubcollection('users', userId, 'routines'),
      admin.firestore().collection('users').doc(userId).get(),
    ]);

    // Derive is_active from user-level activeRoutineId
    const activeRoutineId = userSnap.exists ? userSnap.data().activeRoutineId : null;
    const enriched = routines.map(r => ({
      ...r,
      is_active: r.id === activeRoutineId,
    }));

    return ok(res, { items: enriched, count: enriched.length });

  } catch (error) {
    logger.error('[getUserRoutines] Failed to get user routines', { userId, error: error.message });
    return fail(res, 'INTERNAL', 'Failed to get user routines', { message: error.message }, 500);
  }
}

// Export Firebase Function
exports.getUserRoutines = onRequest(requireFlexibleAuth(getUserRoutinesHandler)); 