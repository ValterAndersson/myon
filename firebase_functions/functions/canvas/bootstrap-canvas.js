const admin = require('firebase-admin');
const { ok, fail } = require('../utils/response');

async function bootstrapCanvas(req, res) {
  try {
    if (req.method !== 'POST') {
      return res.status(405).json({ success: false, error: 'Method Not Allowed' });
    }

    const auth = req.user || req.auth;
    const callerUid = auth?.uid || auth?.uid;
    if (!auth) return fail(res, 'UNAUTHORIZED', 'Authentication required', null, 401);

    const userId = (req.body && req.body.userId) || req.query.userId || callerUid;
    const purpose = (req.body && req.body.purpose) || req.query.purpose;
    if (!userId || !purpose) return fail(res, 'INVALID_ARGUMENT', 'userId and purpose are required', null, 400);

    const db = admin.firestore();
    const canvasesCol = db.collection(`users/${userId}/canvases`);

    // Find existing by purpose
    const existingSnap = await canvasesCol.where('state.purpose', '==', purpose).limit(1).get();
    if (!existingSnap.empty) {
      return ok(res, { canvasId: existingSnap.docs[0].id });
    }

    // Create new canvas
    const { FieldValue } = require('firebase-admin/firestore');
    const now = FieldValue.serverTimestamp();
    const docRef = canvasesCol.doc();
    const state = { phase: 'planning', version: 0, purpose, lanes: ['workout', 'analysis', 'system'], created_at: now, updated_at: now };
    const meta = { user_id: userId };
    await docRef.set({ state, meta });
    return ok(res, { canvasId: docRef.id });
  } catch (err) {
    console.error('bootstrapCanvas error:', err);
    return fail(res, 'INTERNAL', 'Failed to bootstrap canvas', { message: err?.message }, 500);
  }
}

module.exports = { bootstrapCanvas };


