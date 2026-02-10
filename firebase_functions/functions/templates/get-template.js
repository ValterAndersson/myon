const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');
const { ok, fail } = require('../utils/response');

const db = new FirestoreHelper();

/**
 * Firebase Function: Get Specific Template
 * 
 * Description: Gets a specific workout template by ID
 * Enhancement: Resolves exercise names from exercise_id references
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

    // Resolve exercise names if missing
    if (template.exercises && Array.isArray(template.exercises)) {
      const exerciseIdsToResolve = template.exercises
        .filter(ex => !ex.name && ex.exercise_id)
        .map(ex => ex.exercise_id);
      
      if (exerciseIdsToResolve.length > 0) {
        // Batch fetch exercise names from master catalog
        const exerciseNames = await resolveExerciseNames(exerciseIdsToResolve);
        
        // Populate names in template
        template.exercises = template.exercises.map(ex => {
          if (!ex.name && ex.exercise_id && exerciseNames[ex.exercise_id]) {
            return { ...ex, name: exerciseNames[ex.exercise_id] };
          }
          return ex;
        });
      }
    }

    return ok(res, template);

  } catch (error) {
    console.error('get-template function error:', error);
    return fail(res, 'INTERNAL', 'Failed to get template', { message: error.message }, 500);
  }
}

/**
 * Resolve exercise names from exercise IDs by looking up the master catalog
 * @param {string[]} exerciseIds - Array of exercise IDs to resolve
 * @returns {Object} Map of exercise_id -> name
 */
async function resolveExerciseNames(exerciseIds) {
  const names = {};

  await Promise.all(exerciseIds.map(async (exerciseId) => {
    const exercise = await db.getDocument('exercises', exerciseId);
    if (exercise) {
      names[exerciseId] = exercise.name || exerciseId;
    }
  }));

  return names;
}

// Export Firebase Function
exports.getTemplate = onRequest(requireFlexibleAuth(getTemplateHandler)); 