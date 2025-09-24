const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');
const { ok, fail } = require('../utils/response');

const db = new FirestoreHelper();

function looksShorthand(name) {
  const s = String(name || '').trim();
  if (!s) return false;
  // Flags: DB/BB/OHP/T-Bar/Tbar; single-letter abbreviations; excessive hyphens
  const rx = /(\bDB\b|\bBB\b|\bOHP\b|T-?Bar|^db\b|^bb\b|^ohp\b)/i;
  return rx.test(s);
}

async function auditShorthandExercisesHandler(req, res) {
  try {
    const limit = Math.min(parseInt(req.query.limit || req.body?.limit) || 2000, 5000);
    const items = await db.getDocuments('exercises', { orderBy: { field: 'name', direction: 'asc' }, limit });
    const flagged = items.filter(ex => looksShorthand(ex.name)).map(ex => ({ id: ex.id, name: ex.name, family_slug: ex.family_slug, variant_key: ex.variant_key }));
    return ok(res, { total: items.length, flagged_count: flagged.length, items: flagged });
  } catch (error) {
    console.error('audit-shorthand-exercises error:', error);
    return fail(res, 'INTERNAL', 'Failed to audit', { message: error.message }, 500);
  }
}

exports.auditShorthandExercises = onRequest(requireFlexibleAuth(auditShorthandExercisesHandler));


