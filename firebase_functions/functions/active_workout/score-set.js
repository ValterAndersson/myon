const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const { fail, ok } = require('../utils/response');
const { ScoreSetSchema } = require('../utils/validators');

async function scoreSetHandler(req, res) {
  try {
    if (req.method !== 'POST') {
      return res.status(405).json({ success: false, error: 'Method Not Allowed' });
    }
    const userId = req.user?.uid || req.auth?.uid;
    if (!userId) return res.status(401).json({ success: false, error: 'Unauthorized' });

    const parsed = ScoreSetSchema.safeParse(req.body || {});
    if (!parsed.success) return fail(res, 'INVALID_ARGUMENT', 'Invalid request', parsed.error.flatten(), 400);
    const { actual } = parsed.data;

    // Simple heuristic stub
    const base = Math.min(10, Math.max(0, 5 + (actual.reps / 2) - actual.rir));
    const stimulus_score = Number(base.toFixed(1));
    const adjustments = {
      next_weight: actual.weight ? Number((actual.weight * (actual.rir <= 1 ? 1.0 : 1.025)).toFixed(1)) : null,
      next_rir: Math.max(0, actual.rir - 1)
    };
    const rationale = 'Heuristic score based on reps and RIR';

    return ok(res, { stimulus_score, adjustments, rationale });
  } catch (error) {
    console.error('score-set error:', error);
    return fail(res, 'INTERNAL', 'Failed to score set', { message: error.message }, 500);
  }
}

exports.scoreSet = onRequest(requireFlexibleAuth(scoreSetHandler));


