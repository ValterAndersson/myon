const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const { ok, fail } = require('../utils/response');
const { computeAliasCandidates } = require('../utils/aliases');

async function suggestAliasesHandler(req, res) {
  try {
    const exercise = req.body?.exercise || req.body || {};
    if (!exercise.name) return fail(res, 'INVALID_ARGUMENT', 'exercise.name required');
    const suggestions = computeAliasCandidates(exercise);
    return ok(res, { suggestions, count: suggestions.length });
  } catch (error) {
    console.error('suggest-aliases error:', error);
    return fail(res, 'INTERNAL', 'Failed to suggest aliases', { message: error.message }, 500);
  }
}

exports.suggestAliases = onRequest(requireFlexibleAuth(suggestAliasesHandler));


