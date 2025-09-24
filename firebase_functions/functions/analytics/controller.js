const { onRequest } = require('firebase-functions/v2/https');
const admin = require('firebase-admin');
const { processUserAnalytics } = require('./worker');
const { ok, fail } = require('../utils/response');
const { requireFlexibleAuth } = require('../auth/middleware');

if (!admin.apps.length) {
  admin.initializeApp();
}

const db = admin.firestore();

async function controllerHandler(req, res) {
  try {
    if (req.method !== 'POST') {
      return res.status(405).json({ success: false, error: 'Method Not Allowed' });
    }
    const userId = req.body?.userId || req.auth?.uid || req.user?.uid;
    if (!userId) return fail(res, 'INVALID_ARGUMENT', 'Missing userId', null, 400);

    const result = await processUserAnalytics(userId, { backfillDays: 90 });
    return ok(res, result);
  } catch (e) {
    console.error('analytics controller error', e);
    return fail(res, 'INTERNAL', 'Failed analytics run', { message: e.message }, 500);
  }
}

exports.runAnalyticsForUser = onRequest(requireFlexibleAuth(controllerHandler));


