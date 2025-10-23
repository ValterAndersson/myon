'use strict';
const { GoogleAuth } = require('google-auth-library');
const functions = require('firebase-functions');
const axios = require('axios');
const { proposeCardsCore } = require('../canvas/propose-cards-core');

exports.invokeCanvasOrchestrator = async (req, res) => {
  try {
    if (req.method !== 'POST') {
      return res.status(405).json({ error: { code: 'METHOD_NOT_ALLOWED', message: 'POST only' } });
    }
    const body = typeof req.body === 'string' ? JSON.parse(req.body || '{}') : (req.body || {});
    const userId = body.userId;
    const canvasId = body.canvasId;
    const message = (body.message || '').toString();
    const correlationId = body.correlationId || null;
    if (!userId || !canvasId || !message) {
      return res.status(400).json({ error: { code: 'INVALID_ARGUMENT', message: 'userId, canvasId, message are required' } });
    }

    // Engine id from env (fallback only for staging/dev)
    const ENGINE_ID_DEFAULT = process.env.ENGINE_ID_DEFAULT || 'projects/919326069447/locations/us-central1/reasoningEngines/8723635205937561600';
    const engineId = process.env.CANVAS_ENGINE_ID || ENGINE_ID_DEFAULT;
    if (!engineId) {
      return res.status(500).json({ error: { code: 'MISSING_CONFIG', message: 'CANVAS_ENGINE_ID not set' } });
    }

    const projectId = engineId.split('/')[1] || process.env.GCLOUD_PROJECT || process.env.GCP_PROJECT || 'unknown';
    const location = engineId.split('/')[3] || 'us-central1';

    // Pre-publish a light info card so UI shows activity (do not treat as success for pipeline)
    try {
      await proposeCardsCore({
        uid: userId,
        canvasId,
        cards: [{ type: 'inline-info', lane: 'analysis', content: { text: 'Connecting…' }, priority: -100, ttl: { minutes: 1 } }]
      });
      functions.logger.info('invokeCanvasOrchestrator: pre-publish connecting', { userId, canvasId, correlationId });
    } catch (e) {
      functions.logger.warn('invokeCanvasOrchestrator: pre-publish failed', { error: String(e?.message || e), userId, canvasId, correlationId });
    }

    // Auth
    const auth = new GoogleAuth({ scopes: ['https://www.googleapis.com/auth/cloud-platform'] });
    const token = await auth.getAccessToken();

    // Endpoints (Reasoning Engines v1)
    const base = `https://${location}-aiplatform.googleapis.com/v1/${engineId}`;

    // 1) Create session
    const createResp = await axios.post(
      `${base}:query`,
      { class_method: 'create_session', input: { user_id: userId, state: { 'user:id': userId } } },
      { headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }, validateStatus: (s) => s >= 200 && s < 500 }
    );
    if (createResp.status >= 400) {
      functions.logger.error('create_session failed', { status: createResp.status, data: createResp.data, userId, canvasId, correlationId });
      return res.status(502).json({ error: { code: 'UPSTREAM', message: 'create_session failed', status: createResp.status } });
    }
    const sessionId = createResp.data?.output?.id || createResp.data?.output?.session_id || createResp.data?.id || null;
    if (!sessionId) {
      functions.logger.error('create_session missing session id', { data: createResp.data });
      return res.status(502).json({ error: { code: 'UPSTREAM', message: 'missing session id' } });
    }

    // 2) Stream query (fire-and-forget for now; we rely on the agent to publish cards via tools)
    const contextHint = `(context: canvas_id=${canvasId} user_id=${userId} corr=${correlationId || 'none'}; if route=workout then call tool_workout_stage1_publish)`;
    const streamPayload = {
      class_method: 'stream_query',
      input: { user_id: userId, session_id: sessionId, message: `${contextHint}\n${message}` },
    };
    const streamUrl = `${base}:streamQuery`;
    const streamResp = await axios.post(streamUrl, streamPayload, {
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      responseType: 'stream',
      timeout: 60000,
      validateStatus: (s) => s >= 200 && s < 500,
    });
    functions.logger.info('streamQuery status', { status: streamResp.status, userId, canvasId, correlationId });

    // 200..299 considered OK; even if agent takes time to publish.
    return res.json({ ok: true, sessionId });
  } catch (e) {
    functions.logger.error('invokeCanvasOrchestrator error', String(e?.message || e));
    return res.status(500).json({ error: { code: 'INTERNAL', message: String(e?.message || e) } });
  }
};


