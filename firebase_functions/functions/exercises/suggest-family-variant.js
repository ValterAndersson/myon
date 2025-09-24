const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const { ok, fail } = require('../utils/response');
const { computeFamilySlug, computeVariantKey, computeAliasCandidates } = require('../utils/aliases');
const { toSlug } = require('../utils/strings');

async function suggestFamilyVariantHandler(req, res) {
  try {
    const name = req.query.name || req.body?.name;
    if (!name) return fail(res, 'INVALID_ARGUMENT', 'name required');
    const meta = req.body?.metadata || {};
    const fam = computeFamilySlug(String(name));
    const variant = computeVariantKey({ name, metadata: meta, movement: req.body?.movement, equipment: req.body?.equipment });
    const aliases = computeAliasCandidates({ name, metadata: meta, movement: req.body?.movement, equipment: req.body?.equipment });
    return ok(res, { family_slug: fam, variant_key: variant, name_slug: toSlug(name), aliases });
  } catch (error) {
    console.error('suggest-family-variant error:', error);
    return fail(res, 'INTERNAL', 'Failed to suggest', { message: error.message }, 500);
  }
}

exports.suggestFamilyVariant = onRequest(requireFlexibleAuth(suggestFamilyVariantHandler));


