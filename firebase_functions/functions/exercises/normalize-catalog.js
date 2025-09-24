const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');
const { ok, fail } = require('../utils/response');
const admin = require('firebase-admin');
const { toSlug } = require('../utils/strings');
const { computeFamilySlug, computeVariantKey, reserveAliasesNonTxn, transferAliases, computeAliasCandidates } = require('../utils/aliases');

const db = new FirestoreHelper();

function pickCanonical(a, b) {
  if ((a.status === 'approved') !== (b.status === 'approved')) return a.status === 'approved' ? a : b;
  const richnessA = (a.execution_notes?.length || 0) + (a.common_mistakes?.length || 0) + (a.programming_use_cases?.length || 0);
  const richnessB = (b.execution_notes?.length || 0) + (b.common_mistakes?.length || 0) + (b.programming_use_cases?.length || 0);
  if (richnessA !== richnessB) return richnessA > richnessB ? a : b;
  const ta = a.created_at?._seconds || 0;
  const tb = b.created_at?._seconds || 0;
  if (ta !== tb) return ta < tb ? a : b;
  return a;
}

async function normalizeCatalogHandler(req, res) {
  try {
    if (req.method !== 'POST') return fail(res, 'METHOD_NOT_ALLOWED', 'Method Not Allowed', null, 405);
    const userId = req.user?.uid || req.auth?.uid;
    if (!userId) return fail(res, 'UNAUTHORIZED', 'Unauthorized', null, 401);

    const applyMerges = !!req.body?.applyMerges;
    const pageSize = 200;
    let lastName = null;
    let total = 0;
    let normalized = 0;
    const conflicts = [];
    const groups = new Map(); // key: family|variant -> array of doc objects

    while (true) {
      let query = db.db.collection('exercises').orderBy('name').limit(pageSize);
      if (lastName) query = query.startAfter(lastName);
      const snap = await query.get();
      if (snap.empty) break;
      for (const doc of snap.docs) {
        total += 1;
        const data = doc.data() || {};
        const name = String(data.name || '').trim();
        if (!name) continue;
        const nameSlug = data.name_slug || toSlug(name);
        const familySlug = computeFamilySlug(name);
        const variantKey = computeVariantKey({ ...data, name });
        const update = {
          id: doc.id,
          name_slug: nameSlug,
          family_slug: familySlug,
          variant_key: variantKey,
          _debug_project_id: process.env.GCLOUD_PROJECT || process.env.GCP_PROJECT || 'unknown',
          updated_at: admin.firestore.FieldValue.serverTimestamp(),
        };
        await db.updateDocument('exercises', doc.id, update);
        normalized += 1;

        // Reserve alias registry entries (name slug always)
        const aliasSlugs = [nameSlug]
          .concat(Array.isArray(data.aliases) ? data.aliases.map(toSlug) : [])
          .concat(computeAliasCandidates({ ...data, name }));
        const conf = await reserveAliasesNonTxn(db.db, aliasSlugs.filter(Boolean), doc.id, familySlug);
        conflicts.push(...conf);

        const key = `${familySlug}|${variantKey}`;
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push({ id: doc.id, ...data, family_slug: familySlug, variant_key: variantKey });
      }
      lastName = snap.docs[snap.docs.length - 1].get('name');
      if (snap.size < pageSize) break;
    }

    const mergePlan = [];
    for (const [k, arr] of groups.entries()) {
      if (arr.length <= 1) continue;
      let canonical = arr[0];
      for (let i = 1; i < arr.length; i++) canonical = pickCanonical(canonical, arr[i]);
      const dups = arr.filter(x => x.id !== canonical.id).map(x => x.id);
      if (dups.length) mergePlan.push({ group: k, canonical: canonical.id, duplicates: dups });
    }

    const merges = [];
    if (applyMerges) {
      for (const grp of mergePlan) {
        const targetId = grp.canonical;
        const targetSnap = await db.getDocument('exercises', targetId);
        const family = targetSnap?.family_slug || null;
        for (const sourceId of grp.duplicates) {
          const sourceSnap = await db.getDocument('exercises', sourceId);
          if (!sourceSnap) continue;
          const toTransfer = [];
          if (sourceSnap.name_slug) toTransfer.push(sourceSnap.name_slug);
          if (Array.isArray(sourceSnap.aliases)) {
            for (const a of sourceSnap.aliases) {
              const s = toSlug(a);
              if (s) toTransfer.push(s);
            }
          }
          await transferAliases(db.db, toTransfer, targetId, family);
          await db.updateDocument('exercises', sourceId, {
            status: 'merged',
            merged_into: targetId,
            updated_at: admin.firestore.FieldValue.serverTimestamp(),
          });
          merges.push({ merged: sourceId, into: targetId });
        }
      }
    }

    return ok(res, {
      total,
      normalized,
      conflicts,
      plan_groups: mergePlan.length,
      plan_size: mergePlan.reduce((a, p) => a + p.duplicates.length, 0),
      applied_merges: merges.length,
    });
  } catch (error) {
    console.error('normalize-catalog error:', error);
    return fail(res, 'INTERNAL', 'Normalization failed', { message: error.message }, 500);
  }
}

exports.normalizeCatalog = onRequest(requireFlexibleAuth(normalizeCatalogHandler));


