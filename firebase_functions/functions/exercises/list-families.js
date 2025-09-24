const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');
const { ok, fail } = require('../utils/response');
const { computeFamilySlug } = require('../utils/aliases');

const db = new FirestoreHelper();

async function listFamiliesHandler(req, res) {
  try {
    const minSize = parseInt(req.query.minSize || req.body?.minSize) || 1;
    const limitFamilies = parseInt(req.query.limit || req.body?.limit) || 1000;

    const items = await db.getDocuments('exercises', { orderBy: { field: 'name', direction: 'asc' }, limit: 5000 });

    const families = new Map();
    for (const ex of items) {
      const fam = ex.family_slug || computeFamilySlug(ex.name || '');
      if (!fam) continue;
      if (!families.has(fam)) families.set(fam, []);
      families.get(fam).push({
        id: ex.id,
        name: ex.name,
        status: ex.status || 'draft',
        equipment: Array.isArray(ex.equipment) ? ex.equipment : [],
        movement: ex.movement || {},
        variant_key: ex.variant_key || null,
      });
    }

    const result = Array.from(families.entries())
      .map(([family, members]) => ({ family, count: members.length, members }))
      .filter(g => g.count >= minSize)
      .sort((a, b) => b.count - a.count)
      .slice(0, limitFamilies);

    return ok(res, { families: result, totalFamilies: result.length });
  } catch (error) {
    console.error('list-families error:', error);
    return fail(res, 'INTERNAL', 'Failed to list families', { message: error.message }, 500);
  }
}

exports.listFamilies = onRequest(requireFlexibleAuth(listFamiliesHandler));


