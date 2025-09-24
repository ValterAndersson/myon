const admin = require('firebase-admin');
const { ok, fail } = require('../utils/response');

async function upsertProgressReport(req, res) {
  try {
    if (req.method !== 'POST') return res.status(405).json({ success: false, error: 'Method Not Allowed' });
    const auth = req.auth;
    if (!auth || auth.type !== 'api_key') return fail(res, 'UNAUTHORIZED', 'Service-only endpoint', null, 401);
    const uid = req.headers['x-user-id'] || req.get('X-User-Id') || req.query.userId || auth.uid;
    if (!uid) return fail(res, 'INVALID_ARGUMENT', 'Missing X-User-Id', null, 400);

    const { reportId, period, metrics, proposals } = req.body || {};
    if (!reportId || !period || !period.start || !period.end) return fail(res, 'INVALID_ARGUMENT', 'Missing reportId/period', null, 400);
    const ref = admin.firestore().doc(`users/${uid}/progress_reports/${reportId}`);
    await ref.set({ period, metrics: metrics || {}, proposals: proposals || {}, updated_at: admin.firestore.FieldValue.serverTimestamp(), created_at: admin.firestore.FieldValue.serverTimestamp() }, { merge: true });
    return ok(res, { report_id: reportId });
  } catch (e) {
    console.error('upsertProgressReport error', e);
    return fail(res, 'INTERNAL', 'Failed to upsert progress report', { message: e.message }, 500);
  }
}

async function getProgressReports(req, res) {
  try {
    if (req.method !== 'GET') return res.status(405).json({ success: false, error: 'Method Not Allowed' });
    const auth = req.user || req.auth;
    const uid = req.query.userId || auth?.uid;
    if (!uid) return fail(res, 'UNAUTHORIZED', 'Missing user', null, 401);
    const snap = await admin.firestore().collection(`users/${uid}/progress_reports`).orderBy('period.start', 'desc').limit(20).get();
    const items = snap.docs.map(d => ({ id: d.id, ...d.data() }));
    return ok(res, { items });
  } catch (e) {
    console.error('getProgressReports error', e);
    return fail(res, 'INTERNAL', 'Failed to get progress reports', { message: e.message }, 500);
  }
}

module.exports = { upsertProgressReport, getProgressReports };


