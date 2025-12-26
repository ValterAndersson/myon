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
    // READ BOTH fields for backward compatibility: template_ids (canonical) and templateIds (legacy)
    const routines = await db.getDocumentsFromSubcollection('users', userId, 'routines');
    const routinesToUpdate = routines.filter(routine => {
      const templateIds = routine.template_ids || routine.templateIds || [];
      return templateIds.includes(templateId);
    });

    // Update routines to remove template reference
    // WRITE ONLY canonical field: template_ids
    for (const routine of routinesToUpdate) {
      const currentIds = routine.template_ids || routine.templateIds || [];
      const updatedTemplateIds = currentIds.filter(id => id !== templateId);
      
      // Also clear cursor if this was the last completed template
      const updateData = {
        template_ids: updatedTemplateIds
      };
      
      if (routine.last_completed_template_id === templateId) {
        updateData.last_completed_template_id = null;
        updateData.last_completed_at = null;
      }
      
      await db.updateDocumentInSubcollection('users', userId, 'routines', routine.id, updateData);
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
