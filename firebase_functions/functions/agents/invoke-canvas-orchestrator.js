'use strict';
const { GoogleAuth } = require('google-auth-library');
const axios = require('axios');
const admin = require('firebase-admin');

exports.invokeCanvasOrchestrator = async (req, res) => {
  try {
    if (req.method !== 'POST') {
      return res.status(405).json({ error: { code: 'METHOD_NOT_ALLOWED', message: 'POST only' } });
    }
    const body = typeof req.body === 'string' ? JSON.parse(req.body || '{}') : (req.body || {});
    const userId = body.userId;
    const canvasId = body.canvasId;
    const message = (body.message || '').toString();
    if (!userId || !canvasId || !message) {
      return res.status(400).json({ error: { code: 'INVALID_ARGUMENT', message: 'userId, canvasId, message are required' } });
    }

    const engineId = 'projects/919326069447/locations/us-central1/reasoningEngines/8723635205937561600';
    if (!engineId) {
      return res.status(500).json({ error: { code: 'MISSING_CONFIG', message: 'CANVAS_ENGINE_ID not set' } });
    }

    // Regional host (matches other working calls in this codebase)
    const regionHost = 'https://us-central1-aiplatform.googleapis.com';
    const auth = new GoogleAuth({ scopes: ['https://www.googleapis.com/auth/cloud-platform'] });
    const token = await auth.getAccessToken();

    const contextPrefix = `(context: canvas_id=${canvasId} user_id=${userId}; if route=workout then call tool_workout_stage1_publish(canvas_id=${canvasId}, user_id=${userId})) `;

    // Insert a short-lived placeholder agent_stream card immediately (idempotent by groupId)
    const PLACEHOLDER_GROUP = 'agent_stream_placeholder';
    let placeholderIds = [];
    try {
      const db = admin.firestore();
      const now = admin.firestore.FieldValue.serverTimestamp();
      const cardsCol = db.collection(`users/${userId}/canvases/${canvasId}/cards`);
      const cardRef = cardsCol.doc('agent_stream');
      const existing = await cardRef.get();
      if (!existing.exists) {
        const upRef = db.collection(`users/${userId}/canvases/${canvasId}/up_next`).doc();
        await db.runTransaction(async (tx) => {
          tx.set(cardRef, {
            type: 'analysis_task',
            status: 'proposed',
            lane: 'analysis',
            content: { steps: [ { kind: 'thinking' }, { kind: 'lookup', text: 'Planning your program…', durationMs: 1200 } ] },
            layout: { width: 'full' },
            meta: { groupId: PLACEHOLDER_GROUP },
            by: 'agent',
            created_at: now,
            updated_at: now,
            ttl: { minutes: 1 },
          });
          tx.set(upRef, { card_id: cardRef.id, priority: 10, inserted_at: now });
        });
        placeholderIds.push(cardRef.id);
      }
    } catch (e) {
      console.error('Failed to insert placeholder agent stream card', e);
    }

    try {
      // 1) Create session
      const createUrl = `${regionHost}/v1/${engineId}:query`;
      const createResp = await axios.post(createUrl, {
        class_method: 'create_session',
        input: { user_id: userId, state: { 'user:id': userId, canvas_id: canvasId } },
      }, { headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' } });
      const sessionId = createResp.data?.output?.id || createResp.data?.output?.session_id || createResp.data?.id;
      if (!sessionId) throw new Error('No session id from create_session');

      // 2) Stream query (we don't consume stream here; side effects will publish cards)
      const streamUrl = `${regionHost}/v1/${engineId}:streamQuery`;
      await axios.post(streamUrl, {
        class_method: 'stream_query',
        input: { user_id: userId, session_id: sessionId, message: contextPrefix + message + ' // be concise. Explicitly call tool_workout_stage1_publish(canvas_id="'+canvasId+'", user_id="'+userId+'").' },
      }, { headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }, timeout: 30000 });

      // Cleanup any placeholders
      try {
        const db = admin.firestore();
        const cardsCol = db.collection(`users/${userId}/canvases/${canvasId}/cards`);
        const snap = await cardsCol.where('meta.groupId', '==', PLACEHOLDER_GROUP).get();
        if (!snap.empty) {
          const batch = db.batch();
          for (const doc of snap.docs) {
            batch.delete(doc.ref);
            const upSnap = await db.collection(`users/${userId}/canvases/${canvasId}/up_next`).where('card_id', '==', doc.id).get();
            upSnap.forEach(u => batch.delete(u.ref));
          }
          await batch.commit();
        }
      } catch (e) {
        console.error('Failed to cleanup placeholder agent stream card', e);
      }
      return res.json({ ok: true, via: 'vertex' });
    } catch (vertexErr) {
      console.error('invokeCanvasOrchestrator Vertex error', vertexErr);
      return res.status(502).json({ ok: false, error: { code: 'VERTEX_ERROR', message: String(vertexErr?.message || vertexErr) } });
    }
  } catch (e) {
    console.error('invokeCanvasOrchestrator error', e);
    const msg = (e && e.message) ? e.message : String(e);
    return res.status(500).json({ error: { code: 'INTERNAL', message: msg } });
  }
};


