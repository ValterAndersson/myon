const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');
const { ok, fail } = require('../utils/response');
const { toSlug } = require('../utils/strings');

const db = new FirestoreHelper();

function scoreCandidate(ex, context) {
  let score = 0;
  const eq = Array.isArray(ex.equipment) ? ex.equipment : [];
  const want = new Set((context?.available_equipment || []).map(String));
  if (eq.length === 0) score += 1; // bodyweight friendly
  if ([...want].some(w => eq.includes(w))) score += 2;
  if (ex.status === 'approved') score += 1;
  return score;
}

async function resolveExerciseHandler(req, res) {
  try {
    const q = req.query.q || req.body?.q || req.query.name || req.body?.name;
    if (!q) return fail(res, 'INVALID_ARGUMENT', 'Missing q');
    const context = req.body?.context || {};

    const slug = toSlug(String(q));
    let candidates = [];
    const bySlug = await db.getDocuments('exercises', { where: [{ field: 'name_slug', operator: '==', value: slug }], limit: 5 });
    candidates.push(...bySlug);
    const byAlias = await db.getDocuments('exercises', { where: [{ field: 'alias_slugs', operator: 'array-contains', value: slug }], limit: 5 });
    candidates.push(...byAlias);
    // Deduplicate
    const map = new Map();
    for (const c of candidates) map.set(c.id, c);
    candidates = [...map.values()];

    // Rank
    const ranked = candidates.map(ex => ({ ex, s: scoreCandidate(ex, context) }))
      .sort((a, b) => b.s - a.s)
      .map(x => x.ex);

    const best = ranked[0] || null;
    return ok(res, { best: best ? { id: best.id, name: best.name } : null, alternatives: ranked.slice(1).map(e => ({ id: e.id, name: e.name })) });
  } catch (error) {
    console.error('resolve-exercise error:', error);
    return fail(res, 'INTERNAL', 'Failed to resolve exercise', { message: error.message }, 500);
  }
}

exports.resolveExercise = onRequest(requireFlexibleAuth(resolveExerciseHandler));


