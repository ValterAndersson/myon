const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');
const { ok, fail } = require('../utils/response');

const db = new FirestoreHelper();

/**
 * Firebase Function: Get All Exercises
 */
async function getExercisesHandler(req, res) {
  try {
    const limit = parseInt(req.query.limit) || 200;
    const includeMerged = String(req.query.includeMerged || '').toLowerCase() === 'true';
    // canonicalOnly defaults to true unless includeMerged=true explicitly set
    const canonicalOnly = includeMerged ? false : (String(req.query.canonicalOnly || 'true').toLowerCase() !== 'false');

    let items = await db.getDocuments('exercises', { orderBy: { field: 'name', direction: 'asc' }, limit });

    if (canonicalOnly) {
      items = items.filter(ex => !ex?.merged_into && (ex?.status || '').toLowerCase() !== 'merged');
    }
    return ok(res, { items, count: items.length, limit, canonicalOnly, includeMerged });
  } catch (error) {
    console.error('get-exercises function error:', error);
    return fail(res, 'INTERNAL', 'Failed to get exercises', { message: error.message }, 500);
  }
}

exports.getExercises = onRequest(requireFlexibleAuth(getExercisesHandler)); 