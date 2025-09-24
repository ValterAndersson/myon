const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');
const { ok, fail } = require('../utils/response');
const admin = require('firebase-admin');

const db = new FirestoreHelper();

async function refineExerciseHandler(req, res) {
  try {
    if (req.method !== 'POST') return fail(res, 'METHOD_NOT_ALLOWED', 'Method Not Allowed', null, 405);
    const userId = req.user?.uid || req.auth?.uid || 'service';

    const { exercise_id, updates } = req.body || {};
    if (!exercise_id || !updates) return fail(res, 'INVALID_ARGUMENT', 'exercise_id and updates required');

    // Minimal validation/normalization; agent should pass structured fields
    const payload = {};
    if (updates.name) payload.name = String(updates.name).trim();
    if (updates.movement) payload.movement = updates.movement;
    if (updates.equipment) payload.equipment = updates.equipment;
    if (updates.muscles) payload.muscles = updates.muscles;
    if (updates.metadata) payload.metadata = updates.metadata;
    if (updates.execution_notes) payload.execution_notes = updates.execution_notes;
    if (updates.common_mistakes) payload.common_mistakes = updates.common_mistakes;
    if (updates.programming_use_cases) payload.programming_use_cases = updates.programming_use_cases;

    // If target is merged, route update to canonical parent
    const current = await db.getDocument('exercises', exercise_id);
    const targetId = current?.merged_into || exercise_id;
    payload.updated_at = admin.firestore.FieldValue.serverTimestamp();
    await db.updateDocument('exercises', targetId, payload);
    return ok(res, { exercise_id: targetId, updated: true, redirected_from: current?.merged_into ? exercise_id : undefined });
  } catch (error) {
    console.error('refine-exercise error:', error);
    return fail(res, 'INTERNAL', 'Failed to refine exercise', { message: error.message }, 500);
  }
}

exports.refineExercise = onRequest(requireFlexibleAuth(refineExerciseHandler));


