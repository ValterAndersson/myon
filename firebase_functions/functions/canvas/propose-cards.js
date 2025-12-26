const admin = require('firebase-admin');
const { ok, fail } = require('../utils/response');
const { formatValidationResponse } = require('../utils/validation-response');
const { validateProposeCardsRequest } = require('./validators');
const crypto = require('crypto');

// Load JSON schemas for self-healing agents (map card type -> schema)
const CARD_SCHEMAS = {
  session_plan: require('./schemas/card_types/session_plan.schema.json'),
  routine_summary: require('./schemas/card_types/routine_summary.schema.json'),
  analysis_summary: require('./schemas/card_types/analysis_summary.schema.json'),
  visualization: require('./schemas/card_types/visualization.schema.json'),
};

/**
 * Generate a short unique ID for server-generated fields.
 */
function generateId(prefix = '') {
  const id = crypto.randomBytes(6).toString('hex');
  return prefix ? `${prefix}-${id}` : id;
}

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
    if (!v.valid) {
      // Extract card type and get the corresponding schema for self-healing
      const cards = req.body?.cards || [];
      const cardType = cards[0]?.type || 'unknown';
      const schema = CARD_SCHEMAS[cardType] || null;
      const details = formatValidationResponse(req.body, v.errors, schema);
      console.error('[proposeCards] validation failed', { uid, cardType, errorCount: v.errors.length });
      return fail(res, 'INVALID_ARGUMENT', 'Schema validation failed', details, 400);
    }

    const { canvasId, cards } = v.data;
    // Correlation (from header preferred; fallback to body if provided by clients)
    const correlationId = req.headers['x-correlation-id'] || req.get('X-Correlation-Id') || (req.body && req.body.correlationId) || null;
    try { console.log('[proposeCards] request', { uid, canvasId, count: Array.isArray(cards) ? cards.length : 0, correlationId }); } catch (_) {}
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
    function buildDefaults(card, overrideMeta = {}) {
      const lane = card.lane || 'analysis';
      const layout = card.layout || { width: lane === 'workout' ? 'full' : 'oneHalf' };
      const actions = Array.isArray(card.actions) ? card.actions : [];
      const menuItems = Array.isArray(card.menuItems) ? card.menuItems : [];
      const metaIn = typeof card.meta === 'object' && card.meta !== null ? { ...card.meta } : {};
      // Merge in server-generated meta fields
      Object.assign(metaIn, overrideMeta);
      if (typeof metaIn.groupId === 'string') {
        metaIn.groupId = normalizeGroupId(metaIn.groupId);
      }
      const refs = typeof card.refs === 'object' && card.refs !== null ? card.refs : {};
      return { lane, layout, actions, menuItems, meta: metaIn, refs };
    }

    // =========================================================================
    // ROUTINE PROPOSAL HANDLING
    // Detect if this is a routine proposal (contains routine_summary card).
    // If so, generate server-side IDs (draft_id, group_id) and link all cards.
    // Only the anchor (routine_summary) goes into up_next; day cards are referenced.
    // =========================================================================
    const hasRoutineSummary = cards.some(c => c.type === 'routine_summary');
    let serverGroupId = null;
    let serverDraftId = null;
    let summaryCardDocId = null;
    
    if (hasRoutineSummary) {
      serverGroupId = generateId('grp');
      serverDraftId = generateId('draft');
      console.log('[proposeCards] routine proposal detected', { serverDraftId, serverGroupId, cardCount: cards.length });
    }

    // First pass: create all cards (need doc IDs before we can update workouts[].card_id)
    const cardRefs = [];
    const cardDataList = [];
    
    for (let i = 0; i < cards.length; i++) {
      const card = cards[i];
      const isRoutineSummary = card.type === 'routine_summary';
      const isGroupedDayCard = hasRoutineSummary && card.type === 'session_plan';
      
      // Server-generated meta for routine proposals
      const serverMeta = {};
      if (hasRoutineSummary) {
        serverMeta.groupId = serverGroupId;
        if (isRoutineSummary) {
          serverMeta.draft = true;
          serverMeta.draftId = serverDraftId;
          serverMeta.revision = 1;
        }
      }
      
      const d = buildDefaults(card, serverMeta);
      const ref = db.collection(`${canvasPath}/cards`).doc();
      
      if (isRoutineSummary) {
        summaryCardDocId = ref.id;
      }
      
      cardRefs.push({ ref, card, d, isRoutineSummary, isGroupedDayCard });
    }

    // Second pass: for routine proposals, update workouts[].card_id references in the summary
    if (hasRoutineSummary && summaryCardDocId) {
      // Build a map of day index -> card_id for session_plan cards
      const dayCardMap = new Map(); // day index (0-based from order in array) -> doc id
      let sessionPlanIndex = 0;
      
      for (const { ref, card, isRoutineSummary, isGroupedDayCard } of cardRefs) {
        if (isGroupedDayCard) {
          dayCardMap.set(sessionPlanIndex, ref.id);
          sessionPlanIndex++;
        }
      }
      
      // Find the summary and update its content.workouts[].card_id
      for (const entry of cardRefs) {
        if (entry.isRoutineSummary && entry.card.content?.workouts) {
          const workouts = [...entry.card.content.workouts];
          for (let i = 0; i < workouts.length; i++) {
            if (dayCardMap.has(i)) {
              workouts[i] = { ...workouts[i], card_id: dayCardMap.get(i) };
            }
          }
          entry.card = { ...entry.card, content: { ...entry.card.content, workouts } };
        }
      }
    }

    // Third pass: write all cards to batch
    for (const { ref, card, d, isRoutineSummary, isGroupedDayCard } of cardRefs) {
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
      
      // up_next logic: Skip grouped day cards (only anchor goes into up_next)
      const skipUpNext = isGroupedDayCard;
      
      if (!skipUpNext) {
        const upRef = db.collection(`${canvasPath}/up_next`).doc();
        let priority = typeof card.priority === 'number' ? card.priority : 100;
        if (!Number.isFinite(priority)) priority = 100;
        if (priority > 1000) priority = 1000;
        if (priority < -1000) priority = -1000;
        batch.set(upRef, { card_id: ref.id, priority, inserted_at: now });
      }
      
      created.push(ref.id);
    }
    await batch.commit();

    // Enforce up_next cap N=20 (trim lowest priorities) using transaction to satisfy read/write ordering
    const upCol = db.collection(`${canvasPath}/up_next`);
    const MAX = 20;
    await db.runTransaction(async (tx) => {
      const upSnap = await tx.get(upCol.orderBy('priority', 'desc'));
      if (upSnap.size <= MAX) return;
      const toDelete = upSnap.docs.slice(MAX);
      toDelete.forEach(doc => tx.delete(doc.ref));
    });
    // Emit compact event for telemetry/traceability (best-effort)
    try {
      const evtRef = admin.firestore().collection(`${canvasPath}/events`).doc();
      await evtRef.set({
        type: 'agent_propose',
        payload: { created_card_ids: created, correlation_id: correlationId || null },
        created_at: now,
      });
    } catch (e) {
      console.warn('[proposeCards] event emission failed', { canvasId, error: e?.message });
    }

    try { console.log('[proposeCards] ok', { uid, canvasId, created: created.length, correlationId }); } catch (_) {}
    return ok(res, { created_card_ids: created });
  } catch (error) {
    console.error('proposeCards error:', error);
    return fail(res, 'INTERNAL', 'Failed to propose cards', { message: error.message }, 500);
  }
}

module.exports = { proposeCards };
