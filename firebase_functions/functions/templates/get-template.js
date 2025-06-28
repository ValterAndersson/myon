const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');

const db = new FirestoreHelper();

/**
 * Firebase Function: Get Specific Template
 * 
 * Description: Gets a specific workout template by ID
 */
async function getTemplateHandler(req, res) {
  const userId = req.query.userId || req.body?.userId;
  const templateId = req.query.templateId || req.body?.templateId;
  
  if (!userId || !templateId) {
    return res.status(400).json({
      success: false,
      error: 'Missing required parameters',
      required: ['userId', 'templateId'],
      usage: 'Provide both userId and templateId'
    });
  }

  try {
    // Get template
    const template = await db.getDocumentFromSubcollection('users', userId, 'templates', templateId);
    
    if (!template) {
      return res.status(404).json({
        success: false,
        error: 'Template not found',
        userId: userId,
        templateId: templateId
      });
    }

    return res.status(200).json({
      success: true,
      data: template,
      metadata: {
        function: 'get-template',
        userId: userId,
        templateId: templateId,
        requestedAt: new Date().toISOString(),
        authType: req.auth?.type || 'firebase',
        source: req.auth?.source || 'user_app'
      }
    });

  } catch (error) {
    console.error('get-template function error:', error);
    return res.status(500).json({
      success: false,
      error: 'Failed to get template',
      details: error.message,
      function: 'get-template',
      timestamp: new Date().toISOString()
    });
  }
}

// Export Firebase Function
exports.getTemplate = onRequest(requireFlexibleAuth(getTemplateHandler)); 