const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');
const { ok, fail } = require('../utils/response');
const admin = require('firebase-admin');
const { toSlug } = require('../utils/strings');
const { computeFamilySlug, computeVariantKey, reserveAliasesNonTxn, computeAliasCandidates, canonicalizeName } = require('../utils/aliases');

const db = new FirestoreHelper();

async function normalizeCatalogPageHandler(req, res) {
  try {
    if (req.method !== 'POST') return fail(res, 'METHOD_NOT_ALLOWED', 'Method Not Allowed', null, 405);
    const userId = req.user?.uid || req.auth?.uid;
    if (!userId) return fail(res, 'UNAUTHORIZED', 'Unauthorized', null, 401);

    const pageSize = Math.min(parseInt(req.body?.pageSize || req.query.pageSize) || 50, 200);
    const startAfterName = req.body?.startAfterName || req.query.startAfterName || null;

    let query = db.db.collection('exercises').orderBy('name').limit(pageSize);
    if (startAfterName) query = query.startAfter(startAfterName);
    const snap = await query.get();
    if (snap.empty) return ok(res, { processed: 0, nextStartAfterName: null });

    let processed = 0;
    const conflicts = [];
    for (const doc of snap.docs) {
      const data = doc.data() || {};
      // Canonicalize name to verbose standard; keep alias for previous raw name
      const rawName = String(data.name || '').trim();
      const { name, changed, aliasSlug } = canonicalizeName(rawName);
      if (!name) continue;
      const nameSlug = data.name_slug || toSlug(name);
      const familySlug = computeFamilySlug(name);
      const variantKey = computeVariantKey({ ...data, name });
      const updatePayload = {
        id: doc.id,
        name_slug: nameSlug,
        family_slug: familySlug,
        variant_key: variantKey,
        _debug_project_id: process.env.GCLOUD_PROJECT || process.env.GCP_PROJECT || 'unknown',
        updated_at: admin.firestore.FieldValue.serverTimestamp(),
      };
      if (changed) updatePayload.name = name;
      await db.updateDocument('exercises', doc.id, updatePayload);
      processed += 1;

      const aliasSlugs = [nameSlug]
        .concat(Array.isArray(data.aliases) ? data.aliases.map(toSlug) : [])
        .concat(computeAliasCandidates({ ...data, name }))
        .concat(aliasSlug ? [aliasSlug] : []);
      const conf = await reserveAliasesNonTxn(db.db, aliasSlugs.filter(Boolean), doc.id, familySlug);
      conflicts.push(...conf);
    }

    const lastName = snap.docs[snap.docs.length - 1].get('name');
    const next = snap.size < pageSize ? null : lastName;
    return ok(res, { processed, pageSize, nextStartAfterName: next, conflicts });
  } catch (error) {
    console.error('normalize-catalog-page error:', error);
    return fail(res, 'INTERNAL', 'Normalization page failed', { message: error.message }, 500);
  }
}

exports.normalizeCatalogPage = onRequest(requireFlexibleAuth(normalizeCatalogPageHandler));


