const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const { ok, fail } = require('../utils/response');
const admin = require('firebase-admin');

async function searchAliasesHandler(req, res) {
  try {
    const q = String(req.query.q || req.body?.q || '').toLowerCase();
    if (!q) return fail(res, 'INVALID_ARGUMENT', 'q required');
    const db = admin.firestore();
    const snap = await db.collection('exercise_aliases').orderBy('alias_slug').startAt(q).endBefore(q + '\uf8ff').limit(50).get();
    const items = snap.docs.map(d => d.data());
    return ok(res, { items, count: items.length });
  } catch (error) {
    console.error('search-aliases error:', error);
    return fail(res, 'INTERNAL', 'Failed to search aliases', { message: error.message }, 500);
  }
}

exports.searchAliases = onRequest(requireFlexibleAuth(searchAliasesHandler));


