const { onRequest } = require('firebase-functions/v2/https');
const admin = require('firebase-admin');
const { publishWeeklyGroup } = require('../scripts/weekly_publisher');
const { ok, fail } = require('../utils/response');
const { requireFlexibleAuth } = require('../auth/middleware');
const { getAuthenticatedUserId } = require('../utils/auth-helpers');

if (!admin.apps.length) {
  admin.initializeApp();
}

async function handler(req, res) {
  try {
    if (req.method !== 'POST') {
      return res.status(405).json({ success: false, error: 'Method Not Allowed' });
    }
    const uid = getAuthenticatedUserId(req);
    const canvasId = req.body?.canvasId;
    const apiBase = process.env.FUNCTIONS_BASE_URL || process.env.API_BASE_URL;
    const apiKey = process.env.MYON_API_KEY;
    const weekId = req.body?.weekId;
    const bullets = req.body?.bullets || [];
    if (!uid || !canvasId || !apiBase || !apiKey || !weekId) {
      return fail(res, 'INVALID_ARGUMENT', 'Missing required arguments', null, 400);
    }

    const data = await publishWeeklyGroup({
      apiBase,
      apiKey,
      userId: uid,
      canvasId,
      weekId,
      vizDatasetRef: req.body?.vizDatasetRef || null,
      summaryBullets: bullets,
    });
    return ok(res, data);
  } catch (e) {
    console.error('publishWeeklyJob error', e);
    return fail(res, 'INTERNAL', 'Failed to publish weekly group', { message: e.message }, 500);
  }
}

exports.publishWeeklyJob = onRequest(requireFlexibleAuth(handler));


