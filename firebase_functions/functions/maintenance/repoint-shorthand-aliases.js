const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const { ok, fail } = require('../utils/response');
const admin = require('firebase-admin');

function computeCanonicalFromShorthand(alias) {
  let s = String(alias || '').toLowerCase();
  if (!s) return null;
  if (s === 'ohp') return 'overhead-press';
  if (s === 'rdl') return 'romanian-deadlift';
  if (s === 'sldl') return 'stiff-leg-deadlift';
  if (s.startsWith('bb-')) return 'barbell-' + s.slice(3);
  if (s.startsWith('db-')) return 'dumbbell-' + s.slice(3);
  if (s.startsWith('tbar-')) return 't-bar-' + s.slice(5);
  return null;
}

async function repointAllShorthandAliasesHandler(req, res) {
  try {
    if (req.method !== 'POST') return fail(res, 'METHOD_NOT_ALLOWED', 'Method Not Allowed', null, 405);
    const userId = req.user?.uid || req.auth?.uid;
    if (!userId) return fail(res, 'UNAUTHORIZED', 'Unauthorized', null, 401);

    const db = admin.firestore();
    const pageSize = 500;
    let lastDoc = null;
    let scanned = 0;
    let repointed = 0;
    let skipped = 0;
    const details = [];

    while (true) {
      let q = db.collection('exercise_aliases').orderBy('alias_slug').limit(pageSize);
      if (lastDoc) q = q.startAfter(lastDoc);
      const snap = await q.get();
      if (snap.empty) break;
      for (const doc of snap.docs) {
        scanned++;
        const data = doc.data() || {};
        const alias = String(data.alias_slug || doc.id || '').toLowerCase();
        const canonical = computeCanonicalFromShorthand(alias);
        if (!canonical || canonical === alias) { skipped++; continue; }

        // Look up canonical alias doc to get target exercise_id
        const canonicalRef = db.collection('exercise_aliases').doc(canonical);
        const canonicalSnap = await canonicalRef.get();
        if (!canonicalSnap.exists) { skipped++; continue; }
        const target = canonicalSnap.data();
        const targetExerciseId = target?.exercise_id;
        if (!targetExerciseId) { skipped++; continue; }

        // If already pointing to target, skip
        if (String(data.exercise_id || '') === String(targetExerciseId)) { skipped++; continue; }

        await doc.ref.set({
          exercise_id: targetExerciseId,
          family_slug: target?.family_slug || null,
          updated_at: admin.firestore.FieldValue.serverTimestamp(),
        }, { merge: true });
        repointed++;
        details.push({ alias_slug: alias, exercise_id: targetExerciseId, canonical_alias: canonical });
      }
      lastDoc = snap.docs[snap.docs.length - 1];
      if (snap.size < pageSize) break;
    }

    return ok(res, { scanned, repointed, skipped, details });
  } catch (error) {
    console.error('repoint-shorthand-aliases error:', error);
    return fail(res, 'INTERNAL', 'Failed to repoint shorthand aliases', { message: error.message }, 500);
  }
}

exports.repointShorthandAliases = onRequest(requireFlexibleAuth(repointAllShorthandAliasesHandler));


