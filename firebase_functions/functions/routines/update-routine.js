const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');
const { ok, fail } = require('../utils/response');
const { RoutineSchema } = require('../utils/validators');
const admin = require('firebase-admin');

const db = new FirestoreHelper();

/**
 * Firebase Function: Update Routine
 */
async function updateRoutineHandler(req, res) {
  const { userId, routineId, routine } = req.body || {};
  if (!userId || !routineId || !routine) return fail(res, 'INVALID_ARGUMENT', 'Missing required parameters', ['userId','routineId','routine'], 400);
  const parsed = RoutineSchema.safeParse(routine);
  if (!parsed.success) return fail(res, 'INVALID_ARGUMENT', 'Invalid routine data', parsed.error.flatten(), 400);

  try {
    const existingRoutine = await db.getDocumentFromSubcollection('users', userId, 'routines', routineId);
    if (!existingRoutine) return fail(res, 'NOT_FOUND', 'Routine not found', null, 404);

    const updatedRoutine = {
      ...routine,
      // Guarantee an `id` field inside the document
      id: routine.id || routineId
    };

    await db.updateDocumentInSubcollection('users', userId, 'routines', routineId, {
      ...updatedRoutine,
      updated_at: admin.firestore.FieldValue.serverTimestamp(),
    });
    const result = await db.getDocumentFromSubcollection('users', userId, 'routines', routineId);

    return ok(res, { routine: result });

  } catch (error) {
    console.error('update-routine function error:', error);
    return fail(res, 'INTERNAL', 'Failed to update routine', { message: error.message }, 500);
  }
}

exports.updateRoutine = onRequest(requireFlexibleAuth(updateRoutineHandler)); 