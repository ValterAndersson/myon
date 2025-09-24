'use strict';
const { GoogleAuth } = require('google-auth-library');
const functions = require('firebase-functions');

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

    const engineId = process.env.CANVAS_ENGINE_ID || (functions.config().agents && functions.config().agents.canvas_engine_id);
    if (!engineId) {
      return res.status(500).json({ error: { code: 'MISSING_CONFIG', message: 'CANVAS_ENGINE_ID not set' } });
    }

    const aiplatformEndpoint = 'https://us-central1-aiplatform.googleapis.com';
    const auth = new GoogleAuth({ scopes: ['https://www.googleapis.com/auth/cloud-platform'] });
    const client = await auth.getClient();
    const url = `${aiplatformEndpoint}/ui/v1/${engineId}:query`;

    const contextPrefix = `(context: canvas_id=${canvasId} user_id=${userId}) `;
    const payload = {
      message: contextPrefix + message,
      userId: userId
    };

    await client.request({ url, method: 'POST', data: payload });
    return res.json({ ok: true });
  } catch (e) {
    console.error('invokeCanvasOrchestrator error', e);
    const msg = (e && e.message) ? e.message : String(e);
    return res.status(500).json({ error: { code: 'INTERNAL', message: msg } });
  }
};


