const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');
const { ok, fail } = require('../utils/response');
const { ExerciseUpsertSchema } = require('../utils/validators');
const { toSlug } = require('../utils/strings');
const { computeFamilySlug, computeVariantKey, reserveAliasesTransaction } = require('../utils/aliases');

const db = new FirestoreHelper();

async function ensureExerciseExistsHandler(req, res) {
  try {
    if (req.method !== 'POST') {
      return fail(res, 'METHOD_NOT_ALLOWED', 'Method Not Allowed', null, 405);
    }
    const userId = req.user?.uid || req.auth?.uid;
    if (!userId) return fail(res, 'UNAUTHORIZED', 'Unauthorized', null, 401);

    const payload = req.body?.exercise || req.body;
    if (!payload || !payload.name) {
      return fail(res, 'INVALID_ARGUMENT', 'Missing exercise name');
    }

    const name = String(payload.name);
    const nameSlug = toSlug(name);

    // Try lookup by name_slug first
    const bySlug = await db.getDocuments('exercises', { where: [{ field: 'name_slug', operator: '==', value: nameSlug }], limit: 1 });
    if (bySlug && bySlug.length) {
      return ok(res, { exercise_id: bySlug[0].id, found: true });
    }

    // If alias exists, return the mapped exercise
    const aliasDoc = await db.db.collection('exercise_aliases').doc(nameSlug).get();
    if (aliasDoc.exists) {
      const mapped = aliasDoc.data();
      if (mapped.exercise_id) {
        return ok(res, { exercise_id: mapped.exercise_id, found: true, via: 'alias_registry' });
      }
    }

    // Create minimal draft if not found
    const ex = ExerciseUpsertSchema.partial().parse(payload);
    const familySlug = ex.family_slug || computeFamilySlug(name);
    const variantKey = ex.variant_key || computeVariantKey(ex);
    const data = {
      name,
      name_slug: nameSlug,
      aliases: Array.isArray(ex.aliases) ? ex.aliases : [],
      alias_slugs: Array.isArray(ex.aliases) ? ex.aliases.map(toSlug) : [],
      family_slug: familySlug,
      variant_key: variantKey,
      category: ex.category || 'general',
      movement: ex.movement || { type: ex?.movement?.type || 'other', split: ex?.movement?.split || null },
      equipment: Array.isArray(ex.equipment) ? ex.equipment : [],
      metadata: ex.metadata || { level: 'beginner' },
      status: ex.status || 'draft',
      version: ex.version || 1,
      created_by: userId,
    };

    const id = await db.addDocument('exercises', data);
    await db.updateDocument('exercises', id, { id });
    await reserveAliasesTransaction(db.db, [nameSlug, ...(data.alias_slugs || [])], id, familySlug);

    return ok(res, { exercise_id: id, created: true, family_slug: familySlug, variant_key: variantKey });
  } catch (error) {
    console.error('ensure-exercise-exists error:', error);
    return fail(res, 'INTERNAL', 'Failed to ensure exercise', { message: error.message }, 500);
  }
}

exports.ensureExerciseExists = onRequest(requireFlexibleAuth(ensureExerciseExistsHandler));


