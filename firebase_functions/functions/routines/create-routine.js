const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');
const { ok, fail } = require('../utils/response');
const { RoutineSchema } = require('../utils/validators');
const admin = require('firebase-admin');

const db = new FirestoreHelper();

/**
 * Firebase Function: Create Routine
 * 
 * Description: Creates weekly/monthly routine structures for AI
 */
async function createRoutineHandler(req, res) {
  const { userId, routine } = req.body || {};
  if (!userId) return fail(res, 'INVALID_ARGUMENT', 'Missing userId', null, 400);
  const parsed = RoutineSchema.safeParse(routine);
  if (!parsed.success) return fail(res, 'INVALID_ARGUMENT', 'Invalid routine data', parsed.error.flatten(), 400);

  try {
    // Enhanced routine (remove manual timestamps - FirestoreHelper handles them)
    const enhancedRoutine = {
      ...routine,
      frequency: routine.frequency || 3,
      template_ids: routine.template_ids || routine.templateIds || [],
      created_at: admin.firestore.FieldValue.serverTimestamp(),
      updated_at: admin.firestore.FieldValue.serverTimestamp(),
    };
    
    // Remove camelCase version if it exists
    delete enhancedRoutine.templateIds;

    // Create routine
    const routineId = await db.addDocumentToSubcollection('users', userId, 'routines', enhancedRoutine);
    
    // Ensure the document has an `id` field (use the Firestore doc ID)
    await db.updateDocumentInSubcollection('users', userId, 'routines', routineId, { id: routineId });

    // Get the created routine for response
    const createdRoutine = await db.getDocumentFromSubcollection('users', userId, 'routines', routineId);

    return ok(res, { routine: createdRoutine, routineId });

  } catch (error) {
    console.error('create-routine function error:', error);
    return fail(res, 'INTERNAL', 'Failed to create routine', { message: error.message }, 500);
  }
}

// Export Firebase Function
exports.createRoutine = onRequest(requireFlexibleAuth(createRoutineHandler)); 