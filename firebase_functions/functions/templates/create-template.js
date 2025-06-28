const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');
const { calculateTemplateAnalytics } = require('../utils/analytics-calculator');

const db = new FirestoreHelper();

/**
 * Firebase Function: Create Workout Template
 * 
 * Description: Creates a new workout template with analytics calculated
 */
async function createTemplateHandler(req, res) {
  const { userId, template } = req.body;
  
  if (!userId) {
    return res.status(400).json({
      success: false,
      error: 'Missing userId',
      usage: 'Provide userId in request body'
    });
  }
  
  if (!template || !template.name || !template.exercises || !Array.isArray(template.exercises) || template.exercises.length === 0) {
    return res.status(400).json({
      success: false,
      error: 'Invalid template data',
      required: {
        name: 'string',
        exercises: 'array (min 1 exercise)',
        description: 'string (optional)'
      },
      usage: 'Provide complete template object with at least name and exercises array'
    });
  }

  try {
    // Create template first
    const templateId = await db.addDocumentToSubcollection('users', userId, 'templates', template);

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

    return res.status(201).json({
      success: true,
      data: createdTemplate,
      templateId: templateId,
      metadata: {
        function: 'create-template',
        userId: userId,
        createdAt: new Date().toISOString(),
        authType: req.auth?.type || 'firebase',
        source: req.auth?.source || 'user_app'
      }
    });

  } catch (error) {
    console.error('create-template function error:', error);
    return res.status(500).json({
      success: false,
      error: 'Failed to create template',
      details: error.message,
      function: 'create-template',
      timestamp: new Date().toISOString()
    });
  }
}

// Export Firebase Function
exports.createTemplate = onRequest(requireFlexibleAuth(createTemplateHandler)); 