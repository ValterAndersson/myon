const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');
const { ok, fail } = require('../utils/response');

const db = new FirestoreHelper();

/**
 * Firebase Function: Get Specific Template
 * 
 * Description: Gets a specific workout template by ID
 */
async function getTemplateHandler(req, res) {
  // Use authenticated user's ID from Bearer token, or fall back to explicit userId param (for API key auth)
  const userId = req.auth?.uid || req.query.userId || req.body?.userId;
  const templateId = req.query.templateId || req.body?.templateId || req.body?.template_id;
  
  if (!userId) return fail(res, 'UNAUTHENTICATED', 'Authentication required', null, 401);
  if (!templateId) return fail(res, 'INVALID_ARGUMENT', 'Missing templateId parameter', null, 400);

  try {
    // Get template
    const template = await db.getDocumentFromSubcollection('users', userId, 'templates', templateId);
    if (!template) return fail(res, 'NOT_FOUND', 'Template not found', null, 404);

    return ok(res, template);

  } catch (error) {
    console.error('get-template function error:', error);
    return fail(res, 'INTERNAL', 'Failed to get template', { message: error.message }, 500);
  }
}

// Export Firebase Function
exports.getTemplate = onRequest(requireFlexibleAuth(getTemplateHandler)); 