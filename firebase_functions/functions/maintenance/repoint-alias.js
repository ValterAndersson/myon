const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');
const { ok, fail } = require('../utils/response');
const admin = require('firebase-admin');

const db = new FirestoreHelper();

async function repointAliasHandler(req, res) {
  try {
    if (req.method !== 'POST') return fail(res, 'METHOD_NOT_ALLOWED', 'Method Not Allowed', null, 405);
    const userId = req.user?.uid || req.auth?.uid;
    if (!userId) return fail(res, 'UNAUTHORIZED', 'Unauthorized', null, 401);

    const { alias_slug, target_exercise_id, family_slug } = req.body || {};
    if (!alias_slug || !target_exercise_id) return fail(res, 'INVALID_ARGUMENT', 'alias_slug and target_exercise_id are required');

    const ref = db.db.collection('exercise_aliases').doc(String(alias_slug));
    await ref.set({
      alias_slug: String(alias_slug),
      exercise_id: String(target_exercise_id),
      family_slug: family_slug || null,
      updated_at: admin.firestore.FieldValue.serverTimestamp(),
    }, { merge: true });

    return ok(res, { alias_slug, exercise_id: target_exercise_id });
  } catch (error) {
    console.error('repoint-alias error:', error);
    return fail(res, 'INTERNAL', 'Failed to repoint alias', { message: error.message }, 500);
  }
}

exports.repointAlias = onRequest(requireFlexibleAuth(repointAliasHandler));


