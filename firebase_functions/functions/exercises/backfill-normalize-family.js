const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');
const { ok, fail } = require('../utils/response');
const admin = require('firebase-admin');
const { computeFamilySlug, computeVariantKey, transferAliases } = require('../utils/aliases');

const db = new FirestoreHelper();

function pickCanonical(a, b) {
  // Prefer approved
  if ((a.status === 'approved') !== (b.status === 'approved')) {
    return a.status === 'approved' ? a : b;
  }
  // Prefer richer metadata length
  const richnessA = (a.execution_notes?.length || 0) + (a.common_mistakes?.length || 0) + (a.programming_use_cases?.length || 0);
  const richnessB = (b.execution_notes?.length || 0) + (b.common_mistakes?.length || 0) + (b.programming_use_cases?.length || 0);
  if (richnessA !== richnessB) return richnessA > richnessB ? a : b;
  // Prefer older
  const ta = a.created_at?._seconds || 0;
  const tb = b.created_at?._seconds || 0;
  if (ta !== tb) return ta < tb ? a : b;
  return a; // stable
}

async function backfillNormalizeFamilyHandler(req, res) {
  try {
    if (req.method !== 'POST') return fail(res, 'METHOD_NOT_ALLOWED', 'Method Not Allowed', null, 405);
    const userId = req.user?.uid || req.auth?.uid;
    if (!userId) return fail(res, 'UNAUTHORIZED', 'Unauthorized', null, 401);

    const family = String(req.body?.family || '').trim().toLowerCase();
    const apply = !!req.body?.apply;
    const limit = parseInt(req.body?.limit) || 1000;
    if (!family) return fail(res, 'INVALID_ARGUMENT', 'family is required');

    // Load a batch and filter in memory by computed family
    const items = await db.getDocuments('exercises', { orderBy: { field: 'name', direction: 'asc' }, limit });
    const candidates = items.filter(x => computeFamilySlug(x.name) === family);

    // Compute normalized fields for reporting
    const normalized = candidates.map(x => ({
      ...x,
      family_slug: x.family_slug || computeFamilySlug(x.name),
      variant_key: x.variant_key || computeVariantKey(x),
    }));

    // Group by refined variant_key (same family only)
    const byVariant = new Map();
    for (const ex of normalized) {
      const key = `${ex.family_slug}::${ex.variant_key || 'variant:default'}`;
      if (!byVariant.has(key)) byVariant.set(key, []);
      byVariant.get(key).push(ex);
    }

    const plan = [];
    for (const [variant, list] of byVariant.entries()) {
      if (list.length <= 1) continue;
      // choose canonical
      let canonical = list[0];
      for (let i = 1; i < list.length; i++) canonical = pickCanonical(canonical, list[i]);
      const duplicates = list.filter(x => x.id !== canonical.id).map(x => x.id);
      if (duplicates.length) plan.push({ variant, canonical: canonical.id, duplicates });
    }

    if (!apply) {
      return ok(res, { family, candidates: normalized.length, groups: plan.length, plan });
    }

    // Apply merges
    const results = [];
    for (const grp of plan) {
      for (const dupId of grp.duplicates) {
        const source = normalized.find(x => x.id === dupId);
        const target = normalized.find(x => x.id === grp.canonical);
        if (!source || !target) continue;
        // transfer aliases
        const toTransfer = [
          ...(source.alias_slugs || []).filter(Boolean),
          source.name_slug,
        ].filter(Boolean);
        await transferAliases(db.db, toTransfer, target.id, target.family_slug || null);
        // mark source merged
        await db.updateDocument('exercises', source.id, {
          status: 'merged',
          merged_into: target.id,
          updated_at: admin.firestore.FieldValue.serverTimestamp(),
        });
        // update target
        const newAliasesSet = new Set();
        for (const v of (target.alias_slugs || [])) if (v) newAliasesSet.add(v);
        for (const v of (source.alias_slugs || [])) if (v) newAliasesSet.add(v);
        if (source.name_slug) newAliasesSet.add(source.name_slug);
        const newAliases = Array.from(newAliasesSet);
        const newLineage = Array.from(new Set([...(target.merge_lineage || []).filter(Boolean), source.id]));
        await db.updateDocument('exercises', target.id, {
          // alias_slugs maintenance is optional; rely on alias registry for canonicalization
          merge_lineage: newLineage,
          updated_at: admin.firestore.FieldValue.serverTimestamp(),
        });
        results.push({ merged: dupId, into: target.id });
      }
    }

    return ok(res, { family, applied: results.length, merges: results });
  } catch (error) {
    console.error('backfill-normalize-family error:', error);
    return fail(res, 'INTERNAL', 'Backfill failed', { message: error.message }, 500);
  }
}

exports.backfillNormalizeFamily = onRequest(requireFlexibleAuth(backfillNormalizeFamilyHandler));


