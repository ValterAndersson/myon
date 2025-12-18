/**
 * Initialize Session - Creates/reuses Vertex AI session for a canvas
 * 
 * Best practice: MINIMAL state. Let the agent call tools for data.
 * Speed comes from session reuse, not pre-loading data.
 */
const { GoogleAuth } = require('google-auth-library');
const axios = require('axios');
const { logger } = require('firebase-functions');
const admin = require('firebase-admin');
const { VERTEX_AI_CONFIG } = require('../strengthos/config');

if (!admin.apps.length) {
  admin.initializeApp();
}
const db = admin.firestore();

// Session validity window (30 minutes)
const SESSION_TTL_MS = 30 * 60 * 1000;

async function initializeSessionHandler(req, res) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method Not Allowed' });
  }

  const userId = req.user?.uid || req.auth?.uid;
  if (!userId) {
    return res.status(401).json({ error: 'Unauthorized' });
  }

  const { canvasId, purpose = 'general', forceNew = false } = req.body;
  if (!canvasId) {
    return res.status(400).json({ error: 'canvasId is required' });
  }

  logger.info('[initializeSession] Starting', { userId, canvasId, purpose, forceNew });
  const startTime = Date.now();

  try {
    const canvasRef = db.collection('users').doc(userId).collection('canvases').doc(canvasId);
    const canvasDoc = await canvasRef.get();
    const canvasData = canvasDoc.data() || {};
    
    const existingSessionId = canvasData.sessionId;
    const lastActivity = canvasData.lastActivity?.toDate?.() || new Date(0);
    const sessionAge = Date.now() - lastActivity.getTime();

    // Reuse session if valid, recent, and not forcing new
    if (!forceNew && existingSessionId && sessionAge < SESSION_TTL_MS) {
      logger.info('[initializeSession] Reusing session', {
        sessionId: existingSessionId,
        ageSeconds: Math.round(sessionAge / 1000)
      });
      
      // Update last activity
      await canvasRef.update({
        lastActivity: admin.firestore.FieldValue.serverTimestamp()
      });

      return res.json({
        success: true,
        sessionId: existingSessionId,
        isReused: true,
        latencyMs: Date.now() - startTime
      });
    }

    // Log if forcing new session
    if (forceNew && existingSessionId) {
      logger.info('[initializeSession] Forcing new session, discarding', { 
        oldSessionId: existingSessionId 
      });
    }

    // Create new session with MINIMAL state
    // Let the agent call tools for profile, workouts, etc.
    const sessionId = await createVertexSession(userId, {
      'user:id': userId,
      'canvas:id': canvasId,
      'canvas:purpose': purpose
    });
    
    logger.info('[initializeSession] Created session', { sessionId });

    // Persist session info
    await canvasRef.set({
      sessionId,
      lastActivity: admin.firestore.FieldValue.serverTimestamp(),
      sessionCreatedAt: admin.firestore.FieldValue.serverTimestamp(),
      purpose
    }, { merge: true });

    const latencyMs = Date.now() - startTime;
    logger.info('[initializeSession] Complete', { sessionId, latencyMs });

    return res.json({
      success: true,
      sessionId,
      isReused: false,
      latencyMs
    });

  } catch (error) {
    logger.error('[initializeSession] Error', { error: error.message, stack: error.stack });
    return res.status(500).json({
      error: 'Failed to initialize session',
      details: error.message
    });
  }
}

/**
 * Create a new Vertex AI session with minimal state
 */
async function createVertexSession(userId, state) {
  const { projectId, location } = VERTEX_AI_CONFIG;
  const agentId = '8723635205937561600'; // Canvas Orchestrator

  const auth = new GoogleAuth({ scopes: ['https://www.googleapis.com/auth/cloud-platform'] });
  const token = await auth.getAccessToken();

  const url = `https://${location}-aiplatform.googleapis.com/v1/projects/${projectId}/locations/${location}/reasoningEngines/${agentId}:query`;
  
  logger.info('[createVertexSession] Creating session', { userId, state });
  
  const response = await axios.post(url, {
    class_method: 'create_session',
    input: {
      user_id: userId,
      state
    }
  }, {
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    timeout: 30000
  });

  const sessionId = response.data?.output?.id 
    || response.data?.output?.session_id 
    || response.data?.id;

  if (!sessionId) {
    logger.error('[createVertexSession] No session ID in response', { response: response.data });
    throw new Error('Failed to create session: no session ID returned');
  }

  return sessionId;
}

module.exports = { initializeSessionHandler };
