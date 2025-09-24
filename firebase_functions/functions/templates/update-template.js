const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');
const { calculateTemplateAnalytics } = require('../utils/analytics-calculator');
const { ok, fail } = require('../utils/response');
const { TemplateSchema } = require('../utils/validators');
const admin = require('firebase-admin');

const db = new FirestoreHelper();

/**
 * Firebase Function: Update Workout Template
 * 
 * Description: Updates an existing workout template with analytics recalculated
 */
async function updateTemplateHandler(req, res) {
  const { templateId: bodyTemplateId, userId, template } = req.body || {};
  const { templateId: queryTemplateId } = req.query || {};
  // Accept templateId from params (if router ever sets it), body, or query for compatibility
  const templateId = (req.params && req.params.templateId) || bodyTemplateId || queryTemplateId;
  
  if (!userId || !templateId || !template) {
    return fail(res, 'INVALID_ARGUMENT', 'Missing required parameters', ['userId','templateId','template'], 400);
  }
  const parsed = TemplateSchema.safeParse(template);
  if (!parsed.success) return fail(res, 'INVALID_ARGUMENT', 'Invalid template data', parsed.error.flatten(), 400);

  try {
    // Check if template exists
    const existingTemplate = await db.getDocumentFromSubcollection('users', userId, 'templates', templateId);
    if (!existingTemplate) return fail(res, 'NOT_FOUND', 'Template not found', null, 404);

    // Update the template
    await db.updateDocumentInSubcollection('users', userId, 'templates', templateId, {
      ...template,
      updated_at: admin.firestore.FieldValue.serverTimestamp(),
    });
    
    // Get the updated template
    const updatedTemplate = await db.getDocumentFromSubcollection('users', userId, 'templates', templateId);

    // Recalculate analytics if exercises changed (for AI updates)
    if (req.auth?.source === 'third_party_agent' && template.exercises) {
      try {
        const analytics = await calculateTemplateAnalytics(updatedTemplate);
        await db.updateDocumentInSubcollection('users', userId, 'templates', templateId, { analytics });
        updatedTemplate.analytics = analytics;
      } catch (analyticsError) {
        console.error('Error calculating analytics:', analyticsError);
        // Continue without analytics rather than failing the whole operation
      }
    }

    return ok(res, { template: updatedTemplate });

  } catch (error) {
    console.error('update-template function error:', error);
    return fail(res, 'INTERNAL', 'Failed to update template', { message: error.message }, 500);
  }
}

// Export Firebase Function
exports.updateTemplate = onRequest(requireFlexibleAuth(updateTemplateHandler)); 