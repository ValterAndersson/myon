const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');
const { ok, fail } = require('../utils/response');
const { RoutineSchema } = require('../utils/validators');
const { formatValidationResponse } = require('../utils/validation-response');
const admin = require('firebase-admin');

const db = new FirestoreHelper();
const firestore = admin.firestore();

/**
 * Firebase Function: Create Routine
 * 
 * Description: Creates weekly/monthly routine structures for AI
 * 
 * IMPORTANT: Validates that all template_ids reference existing templates.
 * This prevents creating orphan routines with non-existent template references.
 */
async function createRoutineHandler(req, res) {
  const { userId, routine } = req.body || {};
  if (!userId) return fail(res, 'INVALID_ARGUMENT', 'Missing userId', null, 400);
  const parsed = RoutineSchema.safeParse(routine);
  if (!parsed.success) {
    // Return self-healing error format for agents
    const details = formatValidationResponse(routine, parsed.error.errors, null);
    return fail(res, 'INVALID_ARGUMENT', 'Invalid routine data', details, 400);
  }

  try {
    // Collect template IDs from either format
    const templateIds = routine.template_ids || routine.templateIds || [];
    
    // =========================================================================
    // CRITICAL: Validate all template_ids exist before creating routine
    // This prevents orphan routines with references to non-existent templates
    // =========================================================================
    if (templateIds.length > 0) {
      const templatesCol = firestore.collection('users').doc(userId).collection('templates');
      const missingIds = [];
      
      // Use getAll for efficient batch lookup
      const templateRefs = templateIds.map(tid => templatesCol.doc(tid));
      const templateDocs = await firestore.getAll(...templateRefs);
      
      templateDocs.forEach((doc, idx) => {
        if (!doc.exists) {
          missingIds.push(templateIds[idx]);
        }
      });
      
      if (missingIds.length > 0) {
        return fail(res, 'INVALID_ARGUMENT', 'Templates not found', {
          missing_template_ids: missingIds,
          hint: `Templates [${missingIds.join(', ')}] do not exist. Create templates first using tool_save_workout_as_template, or use tool_propose_routine which creates templates automatically when user saves.`,
          retryable: true,
          recovery_options: [
            'Create the missing templates first',
            'Use tool_propose_routine instead (recommended)',
            'Remove the invalid template_ids from the request',
          ],
        }, 400);
      }
    }

    // Enhanced routine (remove manual timestamps - FirestoreHelper handles them)
    const enhancedRoutine = {
      ...routine,
      frequency: routine.frequency || 3,
      template_ids: templateIds,
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
