const admin = require('firebase-admin');
const { ok, fail } = require('../utils/response');
const { validateProposeCardsRequest } = require('./validators');


async function proposeCards(req, res) {
  try {
    if (req.method !== 'POST') {
      return res.status(405).json({ success: false, error: 'Method Not Allowed' });
    }

    // Service-only: must be API key auth (env-based) and explicit X-User-Id
    const auth = req.auth;
    if (!auth || auth.type !== 'api_key') {
      return fail(res, 'UNAUTHORIZED', 'Service-only endpoint', null, 401);
    }

    const uid = req.headers['x-user-id'] || req.get('X-User-Id') || req.query.userId || auth.uid;
    if (!uid) return fail(res, 'INVALID_ARGUMENT', 'Missing X-User-Id', null, 400);

    const v = validateProposeCardsRequest(req.body || {});
    if (!v.valid) return fail(res, 'INVALID_ARGUMENT', 'Invalid request', v.errors, 400);

    const { canvasId, cards } = v.data;
    const canvasPath = `users/${uid}/canvases/${canvasId}`;
    const { FieldValue } = require('firebase-admin/firestore');
    const now = FieldValue.serverTimestamp();

    const db = admin.firestore();
    const batch = db.batch();
    const created = [];
    function normalizeGroupId(value) {
      if (typeof value !== 'string') return value;
      let gid = value.trim().toLowerCase();
      gid = gid.replace(/\s+/g, '-');
      gid = gid.replace(/[^a-z0-9_-]/g, '-');
      gid = gid.replace(/-+/g, '-');
      gid = gid.replace(/^-|-$/g, '');
      return gid;
    }
    function buildDefaults(card) {
      const lane = card.lane || 'analysis';
      const layout = card.layout || { width: lane === 'workout' ? 'full' : 'oneHalf' };
      const actions = Array.isArray(card.actions) ? card.actions : [];
      const menuItems = Array.isArray(card.menuItems) ? card.menuItems : [];
      const metaIn = typeof card.meta === 'object' && card.meta !== null ? { ...card.meta } : {};
      if (typeof metaIn.groupId === 'string') {
        metaIn.groupId = normalizeGroupId(metaIn.groupId);
      }
      const refs = typeof card.refs === 'object' && card.refs !== null ? card.refs : {};
      return { lane, layout, actions, menuItems, meta: metaIn, refs };
    }
    for (const card of cards) {
      const d = buildDefaults(card);
      const ref = db.collection(`${canvasPath}/cards`).doc();
      batch.set(ref, {
        type: card.type,
        status: 'proposed',
        lane: d.lane,
        content: card.content || {},
        refs: d.refs,
        layout: d.layout,
        actions: d.actions,
        menuItems: d.menuItems,
        meta: d.meta,
        ttl: card.ttl || null,
        by: 'agent',
        created_at: now,
        updated_at: now,
      });
      const upRef = db.collection(`${canvasPath}/up_next`).doc();
      let priority = typeof card.priority === 'number' ? card.priority : 100;
      if (!Number.isFinite(priority)) priority = 100;
      if (priority > 1000) priority = 1000;
      if (priority < -1000) priority = -1000;
      batch.set(upRef, { card_id: ref.id, priority, inserted_at: now });
      created.push(ref.id);
    }
    await batch.commit();

    // Enforce up_next cap N=20 (trim lowest priorities)
    const upCol = db.collection(`${canvasPath}/up_next`);
    // Single-field order avoids composite index requirement. Tie-break on client side by slice order.
    const upSnap = await upCol.orderBy('priority', 'desc').get();
    const MAX = 20;
    if (upSnap.size > MAX) {
      const toDelete = upSnap.docs.slice(MAX);
      const trimBatch = admin.firestore().batch();
      toDelete.forEach(doc => trimBatch.delete(doc.ref));
      await trimBatch.commit();
    }

    return ok(res, { created_card_ids: created });
  } catch (error) {
    console.error('proposeCards error:', error);
    return fail(res, 'INTERNAL', 'Failed to propose cards', { message: error.message }, 500);
  }
}

module.exports = { proposeCards };


