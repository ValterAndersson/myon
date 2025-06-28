const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');

const db = new FirestoreHelper();

/**
 * Firebase Function: Create Routine
 * 
 * Description: Creates weekly/monthly routine structures for AI
 */
async function createRoutineHandler(req, res) {
  const { userId, routine } = req.body;
  
  if (!userId) {
    return res.status(400).json({
      success: false,
      error: 'Missing userId',
      usage: 'Provide userId in request body'
    });
  }
  
  if (!routine || !routine.name) {
    return res.status(400).json({
      success: false,
      error: 'Invalid routine data',
      required: {
        name: 'string',
        template_ids: 'array (optional)',
        frequency: 'number (optional)',
        description: 'string (optional)'
      },
      usage: 'Provide routine object with at least name'
    });
  }

  try {
    // Enhanced routine (remove manual timestamps - FirestoreHelper handles them)
    const enhancedRoutine = {
      ...routine,
      frequency: routine.frequency || 3,
      template_ids: routine.template_ids || routine.templateIds || [] // Support both snake_case and camelCase
    };
    
    // Remove camelCase version if it exists
    delete enhancedRoutine.templateIds;

    // Create routine
    const routineId = await db.addDocumentToSubcollection('users', userId, 'routines', enhancedRoutine);
    
    // Ensure the document has an `id` field (use the Firestore doc ID)
    await db.updateDocumentInSubcollection('users', userId, 'routines', routineId, { id: routineId });

    // Get the created routine for response
    const createdRoutine = await db.getDocumentFromSubcollection('users', userId, 'routines', routineId);

    return res.status(201).json({
      success: true,
      data: createdRoutine,
      routineId: routineId,
      metadata: {
        function: 'create-routine',
        userId: userId,
        createdAt: new Date().toISOString(),
        authType: req.auth?.type || 'firebase',
        source: req.auth?.source || 'user_app'
      }
    });

  } catch (error) {
    console.error('create-routine function error:', error);
    return res.status(500).json({
      success: false,
      error: 'Failed to create routine',
      details: error.message,
      function: 'create-routine',
      timestamp: new Date().toISOString()
    });
  }
}

// Export Firebase Function
exports.createRoutine = onRequest(requireFlexibleAuth(createRoutineHandler)); 