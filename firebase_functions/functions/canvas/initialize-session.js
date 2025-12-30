/**
 * Initialize Session - Creates/reuses Vertex AI session
 * 
 * OPTIMIZATION: Sessions are now reused at USER level, not canvas level.
 * This means a new canvas can still benefit from an existing warm session.
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

// Agent version - INCREMENT THIS ON EVERY DEPLOY
// This forces fresh sessions when the agent schema changes
const AGENT_VERSION = '2.4.0'; // Fix ADK transfer semantics

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
    // USER-LEVEL session reuse: Check for any recent session from this user
    // This allows new canvases to benefit from warm sessions
    const userSessionRef = db.collection('users').doc(userId).collection('agent_sessions').doc(purpose);
    const userSessionDoc = await userSessionRef.get();
    const userSessionData = userSessionDoc.data() || {};
    
    const existingSessionId = userSessionData.sessionId;
    const lastActivity = userSessionData.lastActivity?.toDate?.() || new Date(0);
    const sessionAge = Date.now() - lastActivity.getTime();
    const storedVersion = userSessionData.agentVersion || 'unknown';
    
    // Version mismatch = stale session, force new
    const versionMismatch = storedVersion !== AGENT_VERSION;
    if (versionMismatch && existingSessionId) {
      logger.info('[initializeSession] Version mismatch - invalidating stale session', {
        oldVersion: storedVersion,
        newVersion: AGENT_VERSION,
        oldSessionId: existingSessionId
      });
    }

    // Reuse session if valid, recent, same version, and not forcing new
    if (!forceNew && !versionMismatch && existingSessionId && sessionAge < SESSION_TTL_MS) {
      logger.info('[initializeSession] Reusing USER-LEVEL session', {
        sessionId: existingSessionId,
        ageSeconds: Math.round(sessionAge / 1000),
        purpose,
        agentVersion: AGENT_VERSION
      });
      
      // Update last activity and link to this canvas
      const batch = db.batch();
      batch.update(userSessionRef, {
        lastActivity: admin.firestore.FieldValue.serverTimestamp(),
        currentCanvasId: canvasId
      });
      
      // Also update canvas with session info
      const canvasRef = db.collection('users').doc(userId).collection('canvases').doc(canvasId);
      batch.set(canvasRef, {
        sessionId: existingSessionId,
        lastActivity: admin.firestore.FieldValue.serverTimestamp()
      }, { merge: true });
      
      await batch.commit();

      return res.json({
        success: true,
        sessionId: existingSessionId,
        isReused: true,
        reuseLevel: 'user',
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
    
    logger.info('[initializeSession] Created new session', { sessionId });

    // Persist session info at USER level (for future reuse across canvases)
    const batch = db.batch();
    batch.set(userSessionRef, {
      sessionId,
      agentVersion: AGENT_VERSION, // Track version for staleness detection
      lastActivity: admin.firestore.FieldValue.serverTimestamp(),
      sessionCreatedAt: admin.firestore.FieldValue.serverTimestamp(),
      currentCanvasId: canvasId,
      purpose
    });
    
    // Also update canvas with session info
    const canvasRef = db.collection('users').doc(userId).collection('canvases').doc(canvasId);
    batch.set(canvasRef, {
      sessionId,
      lastActivity: admin.firestore.FieldValue.serverTimestamp()
    }, { merge: true });
    
    await batch.commit();

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
