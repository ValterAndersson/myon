const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');
const { ok, fail } = require('../utils/response');

const db = new FirestoreHelper();

/**
 * Firebase Function: Delete Template
 * 
 * Description: Deletes a workout template and cleans up routine references
 */
async function deleteTemplateHandler(req, res) {
  const { userId, templateId } = req.body || {};
  
  if (!userId || !templateId) return fail(res, 'INVALID_ARGUMENT', 'Missing required parameters', ['userId','templateId'], 400);

  try {
    // Check if template exists
    const template = await db.getDocumentFromSubcollection('users', userId, 'templates', templateId);
    if (!template) return fail(res, 'NOT_FOUND', 'Template not found', null, 404);

    // Check for routine references and clean them up
    const routines = await db.getDocumentsFromSubcollection('users', userId, 'routines');
    const routinesToUpdate = routines.filter(routine => 
      routine.templateIds && routine.templateIds.includes(templateId)
    );

    // Update routines to remove template reference
    for (const routine of routinesToUpdate) {
      const updatedTemplateIds = routine.templateIds.filter(id => id !== templateId);
      await db.updateDocumentInSubcollection('users', userId, 'routines', routine.id, {
        templateIds: updatedTemplateIds
        // Remove manual timestamp - FirestoreHelper handles this
      });
    }

    // Delete template
    await db.deleteDocumentFromSubcollection('users', userId, 'templates', templateId);

    return ok(res, { message: 'Template deleted', templateId, routinesUpdated: routinesToUpdate.length });

  } catch (error) {
    console.error('delete-template function error:', error);
    return fail(res, 'INTERNAL', 'Failed to delete template', { message: error.message }, 500);
  }
}

// Export Firebase Function
exports.deleteTemplate = onRequest(requireFlexibleAuth(deleteTemplateHandler)); 