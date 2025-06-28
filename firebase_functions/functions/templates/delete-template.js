const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');

const db = new FirestoreHelper();

/**
 * Firebase Function: Delete Template
 * 
 * Description: Deletes a workout template and cleans up routine references
 */
async function deleteTemplateHandler(req, res) {
  const { userId, templateId } = req.body;
  
  if (!userId || !templateId) {
    return res.status(400).json({
      success: false,
      error: 'Missing required parameters',
      required: ['userId', 'templateId'],
      usage: 'Provide both userId and templateId in request body'
    });
  }

  try {
    // Check if template exists
    const template = await db.getDocumentFromSubcollection('users', userId, 'templates', templateId);
    if (!template) {
      return res.status(404).json({
        success: false,
        error: 'Template not found',
        userId: userId,
        templateId: templateId
      });
    }

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

    return res.status(200).json({
      success: true,
      message: 'Template deleted successfully',
      templateId: templateId,
      routinesUpdated: routinesToUpdate.length,
      metadata: {
        function: 'delete-template',
        userId: userId,
        templateId: templateId,
        deletedAt: new Date().toISOString(),
        authType: req.auth?.type || 'firebase',
        source: req.auth?.source || 'user_app'
      }
    });

  } catch (error) {
    console.error('delete-template function error:', error);
    return res.status(500).json({
      success: false,
      error: 'Failed to delete template',
      details: error.message,
      function: 'delete-template',
      timestamp: new Date().toISOString()
    });
  }
}

// Export Firebase Function
exports.deleteTemplate = onRequest(requireFlexibleAuth(deleteTemplateHandler)); 