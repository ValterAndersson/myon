const admin = require('firebase-admin');
const { requireFlexibleAuth } = require('../auth/middleware');
const { ok, fail } = require('../utils/response');
const { logger } = require('firebase-functions');
const { getAuthenticatedUserId } = require('../utils/auth-helpers');

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
  const callerUid = getAuthenticatedUserId(req);
  if (!callerUid) {
    return fail(res, 'UNAUTHENTICATED', 'Authentication required', null, 401);
  }

  const { templateId, patch, change_source, recommendation_id, workout_id } = req.body;

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

    // Build changelog entry
    const changesSummary = [];
    if (exercisesChanged) {
      // Detect specific exercise changes
      const currentExIds = (current.exercises || []).map(e => e.exercise_id);
      const newExIds = (sanitizedPatch.exercises || []).map(e => e.exercise_id);
      const added = newExIds.filter(id => !currentExIds.includes(id));
      const removed = currentExIds.filter(id => !newExIds.includes(id));

      if (added.length > 0 && removed.length > 0) {
        changesSummary.push({ field: 'exercises.swap', operation: 'swap', summary: `Swapped ${removed.length} exercise(s)` });
      } else {
        if (added.length > 0) changesSummary.push({ field: 'exercises', operation: 'add', summary: `Added ${added.length} exercise(s)` });
        if (removed.length > 0) changesSummary.push({ field: 'exercises', operation: 'remove', summary: `Removed ${removed.length} exercise(s)` });
      }
      if (JSON.stringify(newExIds.filter(id => currentExIds.includes(id))) !== JSON.stringify(currentExIds.filter(id => newExIds.includes(id)))) {
        changesSummary.push({ field: 'exercises', operation: 'reorder', summary: 'Reordered exercises' });
      }
      if (changesSummary.length === 0) {
        changesSummary.push({ field: 'exercises', operation: 'update', summary: 'Updated exercise sets' });
      }
    }
    if (sanitizedPatch.name !== undefined) {
      changesSummary.push({ field: 'name', operation: 'update', summary: `Renamed to "${sanitizedPatch.name}"` });
    }
    if (sanitizedPatch.description !== undefined) {
      changesSummary.push({ field: 'description', operation: 'update', summary: 'Updated description' });
    }

    // Batched write: template update + changelog entry for atomicity
    const batch = firestore.batch();
    batch.update(templateRef, sanitizedPatch);

    const changelogRef = templateRef.collection('changelog').doc();
    batch.set(changelogRef, {
      timestamp: admin.firestore.FieldValue.serverTimestamp(),
      source: change_source || 'user_edit',
      workout_id: workout_id || null,
      recommendation_id: recommendation_id || null,
      changes: changesSummary,
      expires_at: new Date(Date.now() + 90 * 24 * 60 * 60 * 1000)
    });

    await batch.commit();

    logger.info('[patchTemplate] Template updated with changelog', {
      userId: callerUid, templateId, patchedFields, source: change_source || 'user_edit'
    });

    return ok(res, {
      templateId,
      patchedFields,
      analyticsWillRecompute: exercisesChanged,
      message: 'Template updated successfully'
    });

  } catch (error) {
    logger.error('[patchTemplate] Error:', { error: error.message });
    return fail(res, 'INTERNAL', 'Failed to patch template', { message: error.message }, 500);
  }
}

exports.patchTemplate = requireFlexibleAuth(patchTemplateHandler);
