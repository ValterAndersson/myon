const admin = require('firebase-admin');
const { requireFlexibleAuth } = require('../auth/middleware');
const { ok, fail } = require('../utils/response');
const { getAuthenticatedUserId } = require('../utils/auth-helpers');

const firestore = admin.firestore();

/**
 * Firebase Function: Patch Routine
 * 
 * Updates a routine with a narrow set of allowed fields.
 * Uses patch semantics to enable:
 * - Reordering template_ids (for UI reorder)
 * - Replacing templates in the routine
 * - Updating routine metadata
 * 
 * Allowed patch fields:
 * - name: string
 * - description: string
 * - frequency: number
 * - template_ids: array of template IDs
 * 
 * Special behaviors:
 * - Validates all template_ids exist (parallel reads)
 * - Clears cursor if last_completed_template_id is removed from template_ids
 */
async function patchRoutineHandler(req, res) {
  // Dual auth: prefer req.auth.uid, fallback to body.userId for API key
  const callerUid = getAuthenticatedUserId(req);
  if (!callerUid) {
    return fail(res, 'UNAUTHENTICATED', 'Authentication required', null, 401);
  }

  const { routineId, patch } = req.body;

  if (!routineId) {
    return fail(res, 'INVALID_ARGUMENT', 'Missing routineId', null, 400);
  }

  if (!patch || typeof patch !== 'object') {
    return fail(res, 'INVALID_ARGUMENT', 'Missing or invalid patch object', null, 400);
  }

  try {
    // Get current routine
    const routineRef = firestore.collection('users').doc(callerUid).collection('routines').doc(routineId);
    const routineDoc = await routineRef.get();

    if (!routineDoc.exists) {
      return fail(res, 'NOT_FOUND', 'Routine not found', null, 404);
    }

    const current = routineDoc.data();

    // Allowed patch fields
    const ALLOWED_FIELDS = ['name', 'description', 'frequency', 'template_ids'];
    const sanitizedPatch = {};
    const patchedFields = [];

    for (const field of ALLOWED_FIELDS) {
      if (patch[field] !== undefined) {
        sanitizedPatch[field] = patch[field];
        patchedFields.push(field);
      }
    }

    if (patchedFields.length === 0) {
      return fail(res, 'INVALID_ARGUMENT', 'No valid fields to patch. Allowed: name, description, frequency, template_ids', null, 400);
    }

    // Validate name if provided
    if (sanitizedPatch.name !== undefined) {
      if (typeof sanitizedPatch.name !== 'string' || sanitizedPatch.name.trim().length === 0) {
        return fail(res, 'INVALID_ARGUMENT', 'name must be a non-empty string', null, 400);
      }
      sanitizedPatch.name = sanitizedPatch.name.trim();
    }

    // Validate frequency if provided
    if (sanitizedPatch.frequency !== undefined) {
      if (typeof sanitizedPatch.frequency !== 'number' || sanitizedPatch.frequency < 1 || sanitizedPatch.frequency > 7) {
        return fail(res, 'INVALID_ARGUMENT', 'frequency must be a number between 1 and 7', null, 400);
      }
    }

    // Validate template_ids if provided
    if (sanitizedPatch.template_ids !== undefined) {
      if (!Array.isArray(sanitizedPatch.template_ids)) {
        return fail(res, 'INVALID_ARGUMENT', 'template_ids must be an array', null, 400);
      }

      // Validate all templates exist (parallel reads for performance)
      const templateChecks = await Promise.all(
        sanitizedPatch.template_ids.map(async (tid) => {
          const templateDoc = await firestore.collection('users').doc(callerUid).collection('templates').doc(tid).get();
          return { tid, exists: templateDoc.exists };
        })
      );

      const missing = templateChecks.filter(c => !c.exists);
      if (missing.length > 0) {
        return fail(res, 'INVALID_ARGUMENT', `Templates not found: ${missing.map(m => m.tid).join(', ')}`, null, 400);
      }

      // Cursor consistency: clear if last_completed_template_id is no longer in template_ids
      const currentCursorId = current.last_completed_template_id;
      if (currentCursorId && !sanitizedPatch.template_ids.includes(currentCursorId)) {
        sanitizedPatch.last_completed_template_id = null;
        sanitizedPatch.last_completed_at = null;
        patchedFields.push('last_completed_template_id', 'last_completed_at');
      }
    }

    // Add timestamp
    sanitizedPatch.updated_at = admin.firestore.FieldValue.serverTimestamp();

    // Apply patch
    await routineRef.update(sanitizedPatch);

    return ok(res, {
      routineId,
      patchedFields,
      cursorCleared: sanitizedPatch.last_completed_template_id === null,
      message: 'Routine updated successfully'
    });

  } catch (error) {
    console.error('patch-routine function error:', error);
    return fail(res, 'INTERNAL', 'Failed to patch routine', { message: error.message }, 500);
  }
}

exports.patchRoutine = requireFlexibleAuth(patchRoutineHandler);
