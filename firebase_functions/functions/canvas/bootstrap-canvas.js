const admin = require('firebase-admin');
const { ok, fail } = require('../utils/response');

/**
 * Bootstrap Canvas - ALWAYS creates a new canvas for each conversation
 * 
 * Each new conversation gets its own canvas. Users can return to previous
 * canvases from the home screen. Sessions are reused at the USER level
 * (handled in initializeSession) for speed.
 */
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
    // Allow optional title for the canvas
    const title = (req.body && req.body.title) || null;
    if (!userId || !purpose) return fail(res, 'INVALID_ARGUMENT', 'userId and purpose are required', null, 400);

    const db = admin.firestore();
    const canvasesCol = db.collection(`users/${userId}/canvases`);

    // ALWAYS create a new canvas - no reuse of existing canvases
    // Users can return to previous canvases from the home screen
    const { FieldValue } = require('firebase-admin/firestore');
    const now = FieldValue.serverTimestamp();
    const docRef = canvasesCol.doc();
    const state = { 
      phase: 'planning', 
      version: 0, 
      purpose, 
      lanes: ['workout', 'analysis', 'system'], 
      created_at: now, 
      updated_at: now 
    };
    const meta = { 
      user_id: userId,
      title: title || null,  // Can be set later from first message
      created_at: now
    };
    await docRef.set({ state, meta });
    
    console.log('bootstrapCanvas: created new canvas', { userId, canvasId: docRef.id, purpose });
    return ok(res, { canvasId: docRef.id, isNew: true });
  } catch (err) {
    console.error('bootstrapCanvas error:', err);
    return fail(res, 'INTERNAL', 'Failed to bootstrap canvas', { message: err?.message }, 500);
  }
}

module.exports = { bootstrapCanvas };
