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

    // Try validate; if invalid, coerce into a minimal safe form (clarify-questions)
    let body = req.body || {};
    let { canvasId, cards } = body;
    const v = validateProposeCardsRequest(body);
    if (!v.valid) {
      try { console.warn('[proposeCards] validation failed; attempting to coerce', { errors: v.errors }); } catch (_) {}
      function coerceToClarifyCard(item) {
        const qs = Array.isArray(item?.content?.questions)
          ? item.content.questions
          : Array.isArray(item?.question_texts)
            ? item.question_texts
            : Array.isArray(item?.questiona_texts)
              ? item.questiona_texts
              : [];
        const questions = (qs || []).slice(0, 6).map((q, idx) => ({ id: `q_${idx}`, text: String(q) }));
        if (questions.length === 0) {
          questions.push(
            { id: 'q_0', text: 'What are your primary fitness goals?' },
            { id: 'q_1', text: 'How many days per week can you train?' },
            { id: 'q_2', text: 'What equipment do you have access to?' }
          );
        }
        return {
          type: 'clarify-questions',
          lane: 'analysis',
          content: { title: 'A few questions', questions },
          priority: 50,
        };
      }
      function coerceCards(list) {
        if (!Array.isArray(list) || list.length === 0) return [coerceToClarifyCard({})];
        const out = [];
        for (const c of list) {
          if (c && typeof c === 'object' && c.type === 'session_plan' && c.content) {
            out.push(c); // already fine; keep
          } else if (c && typeof c === 'object' && c.type === 'clarify-questions' && c.content) {
            out.push(c);
          } else {
            out.push(coerceToClarifyCard(c));
          }
        }
        return out;
      }
      cards = coerceCards(cards);
      body = { canvasId, cards };
    }

    const { canvasId: canvasIdSafe } = body;
    const cardsInput = body.cards;
    if (!canvasIdSafe) return fail(res, 'INVALID_ARGUMENT', 'Missing canvasId', null, 400);

    // Correlation (from header preferred; fallback to body if provided by clients)
    const correlationId = req.headers['x-correlation-id'] || req.get('X-Correlation-Id') || (req.body && req.body.correlationId) || null;
    try {
      console.log('[proposeCards] request', {
        uid,
        canvasId: canvasIdSafe,
        count: Array.isArray(cardsInput) ? cardsInput.length : 0,
        correlationId,
        hasApiKey: !!(req.get('X-API-Key') || req.query.apiKey),
        hasUserHeader: !!(req.get('X-User-Id'))
      });
    } catch (_) {}
    const canvasPath = `users/${uid}/canvases/${canvasIdSafe}`;
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
    for (const card of cardsInput) {
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
    try { await batch.commit(); } catch (e) {
      console.error('[proposeCards] batch commit failed', { error: e?.message, canvasId: canvasIdSafe, uid });
      try {
        const evtRef = admin.firestore().collection(`${canvasPath}/events`).doc();
        await evtRef.set({ type: 'agent_publish_failed', payload: { error: String(e?.message || e), correlation_id: correlationId || null }, created_at: now });
      } catch (_) {}
      return fail(res, 'INTERNAL', 'Commit failed', { message: e?.message }, 500);
    }

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
    // Emit compact event for telemetry/traceability (best-effort)
    try {
      const evtRef = admin.firestore().collection(`${canvasPath}/events`).doc();
      await evtRef.set({
        type: 'agent_propose',
        payload: { created_card_ids: created, correlation_id: correlationId || null },
        created_at: now,
      });
    } catch (e) {
      console.warn('[proposeCards] event emission failed', { canvasId: canvasIdSafe, error: e?.message });
    }

    try { console.log('[proposeCards] ok', { uid, canvasId: canvasIdSafe, created: created.length, correlationId }); } catch (_) {}
    return ok(res, { created_card_ids: created });
  } catch (error) {
    console.error('proposeCards error:', error);
    return fail(res, 'INTERNAL', 'Failed to propose cards', { message: error.message }, 500);
  }
}

module.exports = { proposeCards };


