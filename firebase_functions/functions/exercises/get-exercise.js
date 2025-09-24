const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');
const { ok, fail } = require('../utils/response');
const { toSlug } = require('../utils/strings');

const db = new FirestoreHelper();

/**
 * Firebase Function: Get Specific Exercise
 */
async function getExerciseHandler(req, res) {
  const exerciseId = req.query.exerciseId || req.body?.exerciseId;
  const name = req.query.name || req.body?.name;
  const slug = req.query.slug || req.body?.slug;

  if (!exerciseId && !name && !slug) {
    return fail(res, 'INVALID_ARGUMENT', 'Provide exerciseId or name or slug');
  }

  try {
    let exercise = null;
    if (exerciseId) {
      exercise = await db.getDocument('exercises', exerciseId);
    } else if (slug || name) {
      const s = slug ? String(slug) : toSlug(String(name));
      const bySlug = await db.getDocuments('exercises', { where: [{ field: 'name_slug', operator: '==', value: s }], limit: 1 });
      if (bySlug && bySlug.length) {
        exercise = bySlug[0];
      } else {
        const byAlias = await db.getDocuments('exercises', { where: [{ field: 'alias_slugs', operator: 'array-contains', value: s }], limit: 1 });
        if (byAlias && byAlias.length) exercise = byAlias[0];
        // Fallback to alias registry if still not found
        if (!exercise) {
          const aliasDoc = await db.db.collection('exercise_aliases').doc(s).get();
          const mapped = aliasDoc.exists ? aliasDoc.data() : null;
          if (mapped?.exercise_id) {
            const mappedEx = await db.getDocument('exercises', mapped.exercise_id);
            if (mappedEx) exercise = mappedEx;
          }
        }
      }
    }

    // Follow redirects if merged
    if (exercise && exercise.merged_into) {
      const redirectedFrom = exercise.id;
      const target = await db.getDocument('exercises', exercise.merged_into);
      if (target) {
        return ok(res, { ...target, redirected_from: redirectedFrom });
      }
    }

    if (!exercise) {
      return fail(res, 'NOT_FOUND', 'Exercise not found', { exerciseId, name, slug }, 404);
    }

    return ok(res, exercise);
  } catch (error) {
    console.error('get-exercise function error:', error);
    return fail(res, 'INTERNAL', 'Failed to get exercise', { message: error.message }, 500);
  }
}

exports.getExercise = onRequest(requireFlexibleAuth(getExerciseHandler)); 