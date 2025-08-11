const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');
const { calculateTemplateAnalytics } = require('../utils/analytics-calculator');

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
    return res.status(400).json({
      success: false,
      error: 'Missing required parameters',
      required: ['userId', 'templateId', 'template']
    });
  }

  try {
    // Check if template exists
    const existingTemplate = await db.getDocumentFromSubcollection('users', userId, 'templates', templateId);
    if (!existingTemplate) {
      return res.status(404).json({
        success: false,
        error: 'Template not found'
      });
    }

    // Update the template
    await db.updateDocumentInSubcollection('users', userId, 'templates', templateId, template);
    
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

    return res.status(200).json({
      success: true,
      data: updatedTemplate,
      metadata: {
        function: 'update-template',
        userId: userId,
        templateId: templateId,
        updatedAt: new Date().toISOString()
      }
    });

  } catch (error) {
    console.error('update-template function error:', error);
    return res.status(500).json({
      success: false,
      error: 'Failed to update template',
      details: error.message
    });
  }
}

// Export Firebase Function
exports.updateTemplate = onRequest(requireFlexibleAuth(updateTemplateHandler)); 