const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');
const { calculateTemplateAnalytics } = require('../utils/analytics-calculator');
const { ok, fail } = require('../utils/response');
const { TemplateSchema } = require('../utils/validators');
const admin = require('firebase-admin');

const db = new FirestoreHelper();

/**
 * Firebase Function: Create Workout Template
 * 
 * Description: Creates a new workout template with analytics calculated
 */
async function createTemplateHandler(req, res) {
  const { userId, template } = req.body;
  
  if (!userId) return fail(res, 'INVALID_ARGUMENT', 'Missing userId', null, 400);
  const parsed = TemplateSchema.safeParse(template);
  if (!parsed.success) return fail(res, 'INVALID_ARGUMENT', 'Invalid template data', parsed.error.flatten(), 400);

  try {
    // Create template first
    const templateId = await db.addDocumentToSubcollection('users', userId, 'templates', {
      ...template,
      created_at: admin.firestore.FieldValue.serverTimestamp(),
      updated_at: admin.firestore.FieldValue.serverTimestamp(),
    });

    // Ensure the document has an `id` field (use the Firestore doc ID)
    await db.updateDocumentInSubcollection('users', userId, 'templates', templateId, { id: templateId });

    // Get the created template to calculate analytics
    const createdTemplate = await db.getDocumentFromSubcollection('users', userId, 'templates', templateId);

    // Calculate analytics if not already present (for AI-created templates)
    if (!createdTemplate.analytics && req.auth?.source === 'third_party_agent') {
      try {
        const analytics = await calculateTemplateAnalytics(createdTemplate);
        await db.updateDocumentInSubcollection('users', userId, 'templates', templateId, { analytics });
        createdTemplate.analytics = analytics;
      } catch (analyticsError) {
        console.error('Error calculating analytics:', analyticsError);
        // Continue without analytics rather than failing the whole operation
      }
    }

    return ok(res, { template: createdTemplate, templateId });

  } catch (error) {
    console.error('create-template function error:', error);
    return fail(res, 'INTERNAL', 'Failed to create template', { message: error.message }, 500);
  }
}

// Export Firebase Function
exports.createTemplate = onRequest(requireFlexibleAuth(createTemplateHandler)); 