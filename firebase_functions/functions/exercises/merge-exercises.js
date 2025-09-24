const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');
const { ok, fail } = require('../utils/response');
const admin = require('firebase-admin');
const { transferAliases } = require('../utils/aliases');

const db = new FirestoreHelper();

async function mergeExercisesHandler(req, res) {
  try {
    if (req.method !== 'POST') return fail(res, 'METHOD_NOT_ALLOWED', 'Method Not Allowed', null, 405);
    const userId = req.user?.uid || req.auth?.uid;
    if (!userId) return fail(res, 'UNAUTHORIZED', 'Unauthorized', null, 401);

    const { source_id, target_id } = req.body || {};
    if (!source_id || !target_id || source_id === target_id) {
      return fail(res, 'INVALID_ARGUMENT', 'Provide distinct source_id and target_id');
    }

    const source = await db.getDocument('exercises', source_id);
    const target = await db.getDocument('exercises', target_id);
    if (!source || !target) return fail(res, 'NOT_FOUND', 'Source or target not found');

    // Transfer aliases first
    await transferAliases(db.db, (source.alias_slugs || []).concat([source.name_slug]), target_id, target.family_slug || null);

    // Update source as merged
    await db.updateDocument('exercises', source_id, {
      status: 'merged',
      merged_into: target_id,
      updated_at: admin.firestore.FieldValue.serverTimestamp(),
    });

    // Update target lineage and alias_slugs union
    const newAliases = Array.from(new Set([...(target.alias_slugs || []), ...(source.alias_slugs || []), source.name_slug]));
    const newLineage = Array.from(new Set([...(target.merge_lineage || []), source_id]));
    await db.updateDocument('exercises', target_id, {
      alias_slugs: newAliases,
      merge_lineage: newLineage,
      updated_at: admin.firestore.FieldValue.serverTimestamp(),
    });

    return ok(res, { merged: true, source_id, target_id });
  } catch (error) {
    console.error('merge-exercises error:', error);
    return fail(res, 'INTERNAL', 'Failed to merge exercises', { message: error.message }, 500);
  }
}

exports.mergeExercises = onRequest(requireFlexibleAuth(mergeExercisesHandler));


