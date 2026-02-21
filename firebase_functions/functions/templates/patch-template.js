const admin = require('firebase-admin');
const { requireFlexibleAuth } = require('../auth/middleware');
const { ok, fail } = require('../utils/response');

const firestore = admin.firestore();

/**
 * Firebase Function: Patch Template
 * 
 * Updates a template with a narrow set of allowed fields.
 * Uses patch semantics (not full replace) to prevent:
 * - Stomping server-computed analytics
 * - Overwriting timestamps
 * - Corruption from concurrent edits
 * 
 * Allowed patch fields:
 * - name: string
 * - description: string
 * - exercises: array (triggers analytics recompute)
 * 
 * Optional concurrency check via expected_updated_at
 */
async function patchTemplateHandler(req, res) {
  // Dual auth: prefer req.auth.uid, fallback to body.userId for API key
  const callerUid = req.auth?.uid || req.body.userId;
  if (!callerUid) {
    return fail(res, 'UNAUTHENTICATED', 'No user identified', null, 401);
  }

  const { templateId, patch } = req.body;

  if (!templateId) {
    return fail(res, 'INVALID_ARGUMENT', 'Missing templateId', null, 400);
  }

  if (!patch || typeof patch !== 'object') {
    return fail(res, 'INVALID_ARGUMENT', 'Missing or invalid patch object', null, 400);
  }

  try {
    // Get current template
    const templateRef = firestore.collection('users').doc(callerUid).collection('templates').doc(templateId);
    const templateDoc = await templateRef.get();

    if (!templateDoc.exists) {
      return fail(res, 'NOT_FOUND', 'Template not found', null, 404);
    }

    const current = templateDoc.data();

    // Optional concurrency check
    if (patch.expected_updated_at) {
      const currentUpdatedAt = current.updated_at?.toMillis?.() || 0;
      const expectedUpdatedAt = typeof patch.expected_updated_at === 'number' 
        ? patch.expected_updated_at 
        : new Date(patch.expected_updated_at).getTime();
      
      if (currentUpdatedAt !== expectedUpdatedAt) {
        return fail(res, 'ABORTED', 'Template was modified concurrently. Please refresh and try again.', {
          current_updated_at: currentUpdatedAt,
          expected_updated_at: expectedUpdatedAt
        }, 409);
      }
    }

    // Allowed patch fields (narrow schema)
    const ALLOWED_FIELDS = ['name', 'description', 'exercises'];
    const sanitizedPatch = {};
    const patchedFields = [];

    for (const field of ALLOWED_FIELDS) {
      if (patch[field] !== undefined) {
        sanitizedPatch[field] = patch[field];
        patchedFields.push(field);
      }
    }

    if (patchedFields.length === 0) {
      return fail(res, 'INVALID_ARGUMENT', 'No valid fields to patch. Allowed: name, description, exercises', null, 400);
    }

    // Validate name if provided
    if (sanitizedPatch.name !== undefined) {
      if (typeof sanitizedPatch.name !== 'string' || sanitizedPatch.name.trim().length === 0) {
        return fail(res, 'INVALID_ARGUMENT', 'name must be a non-empty string', null, 400);
      }
      sanitizedPatch.name = sanitizedPatch.name.trim();
    }

    // Validate exercises if provided
    let exercisesChanged = false;
    if (sanitizedPatch.exercises !== undefined) {
      if (!Array.isArray(sanitizedPatch.exercises)) {
        return fail(res, 'INVALID_ARGUMENT', 'exercises must be an array', null, 400);
      }
      
      if (sanitizedPatch.exercises.length === 0) {
        return fail(res, 'INVALID_ARGUMENT', 'exercises array cannot be empty', null, 400);
      }

      // Validate each exercise has required fields
      for (let i = 0; i < sanitizedPatch.exercises.length; i++) {
        const exercise = sanitizedPatch.exercises[i];
        if (!exercise.exercise_id && !exercise.exerciseId) {
          return fail(res, 'INVALID_ARGUMENT', `Exercise at index ${i} missing exercise_id`, null, 400);
        }
        if (!Array.isArray(exercise.sets)) {
          return fail(res, 'INVALID_ARGUMENT', `Exercise at index ${i} missing sets array`, null, 400);
        }
        
        // Validate sets
        for (let j = 0; j < exercise.sets.length; j++) {
          const set = exercise.sets[j];
          if (typeof set.reps !== 'number') {
            return fail(res, 'INVALID_ARGUMENT', `Exercise ${i} set ${j} missing reps`, null, 400);
          }
          if (set.rir !== null && set.rir !== undefined && typeof set.rir !== 'number') {
            return fail(res, 'INVALID_ARGUMENT', `Exercise ${i} set ${j} rir must be number or null`, null, 400);
          }
          // weight can be null (bodyweight exercises)
          if (set.weight !== null && set.weight !== undefined && typeof set.weight !== 'number') {
            return fail(res, 'INVALID_ARGUMENT', `Exercise ${i} set ${j} weight must be number or null`, null, 400);
          }
        }
      }

      // Check if exercises actually changed
      exercisesChanged = JSON.stringify(sanitizedPatch.exercises) !== JSON.stringify(current.exercises);
    }

    // Add timestamp
    sanitizedPatch.updated_at = admin.firestore.FieldValue.serverTimestamp();

    // If exercises changed, clear analytics so trigger will recompute
    if (exercisesChanged) {
      sanitizedPatch.analytics = admin.firestore.FieldValue.delete();
    }

    // Apply patch
    await templateRef.update(sanitizedPatch);

    return ok(res, {
      templateId,
      patchedFields,
      analyticsWillRecompute: exercisesChanged,
      message: 'Template updated successfully'
    });

  } catch (error) {
    console.error('patch-template function error:', error);
    return fail(res, 'INTERNAL', 'Failed to patch template', { message: error.message }, 500);
  }
}

exports.patchTemplate = requireFlexibleAuth(patchTemplateHandler);
