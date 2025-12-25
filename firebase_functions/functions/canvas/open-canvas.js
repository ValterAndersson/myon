/**
 * openCanvas - Combined endpoint to minimize round trips
 * 
 * Replaces: bootstrapCanvas + initializeSession in a single call
 * Returns: canvasId, sessionId, resumeState (cards, last entry cursor)
 * 
 * This eliminates 1-2 network round trips on canvas open.
 */

const { onRequest, HttpsError } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const admin = require('firebase-admin');
const { GoogleAuth } = require('google-auth-library');
const axios = require('axios');
const { logger } = require('firebase-functions');
const { VERTEX_AI_CONFIG } = require('../strengthos/config');

if (!admin.apps.length) {
  admin.initializeApp();
}
const db = admin.firestore();

// ============================================================================
// GCP AUTH TOKEN CACHE (shared with stream-agent-normalized)
// ============================================================================
let cachedGcpToken = null;
let tokenExpiresAt = 0;
const TOKEN_BUFFER_MS = 5 * 60 * 1000;

async function getGcpAuthToken() {
  const now = Date.now();
  if (cachedGcpToken && now < tokenExpiresAt - TOKEN_BUFFER_MS) {
    return cachedGcpToken;
  }
  const auth = new GoogleAuth({ scopes: ['https://www.googleapis.com/auth/cloud-platform'] });
  cachedGcpToken = await auth.getAccessToken();
  tokenExpiresAt = now + (55 * 60 * 1000);
  return cachedGcpToken;
}

// Session TTL: 10 minutes of inactivity (reduced from 30 to prevent stale session issues)
// Vertex AI agent sessions can become corrupted/stuck, so shorter TTL is safer
const SESSION_TTL_MS = 10 * 60 * 1000;

/**
 * Get or create a Vertex AI session for the user
 */
async function getOrCreateSession(userId, purpose) {
  const sessionDocRef = db.collection('users').doc(userId).collection('agent_sessions').doc(purpose);
  const sessionDoc = await sessionDocRef.get();
  
  const now = Date.now();
  
  if (sessionDoc.exists) {
    const data = sessionDoc.data();
    const lastUsed = data.lastUsedAt?.toMillis?.() || 0;
    const age = now - lastUsed;
    
    // Reuse if within TTL
    if (age < SESSION_TTL_MS && data.sessionId) {
      logger.info('[openCanvas] Reusing existing session', { 
        sessionId: data.sessionId, 
        age: Math.round(age / 1000) + 's' 
      });
      // Touch the session
      await sessionDocRef.update({ lastUsedAt: admin.firestore.FieldValue.serverTimestamp() });
      return { sessionId: data.sessionId, isNew: false };
    }
  }
  
  // Create new session
  logger.info('[openCanvas] Creating new Vertex AI session...');
  const token = await getGcpAuthToken();
  const agentId = '8723635205937561600';
  const projectId = VERTEX_AI_CONFIG.projectId;
  const location = VERTEX_AI_CONFIG.location;
  
  const createUrl = `https://${location}-aiplatform.googleapis.com/v1/projects/${projectId}/locations/${location}/reasoningEngines/${agentId}:query`;
  const response = await axios.post(createUrl, {
    class_method: 'create_session',
    input: { user_id: userId, state: { 'user:id': userId } },
  }, { 
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    timeout: 30000
  });
  
  const sessionId = response.data?.output?.id || response.data?.output?.session_id || response.data?.id;
  
  if (!sessionId) {
    throw new Error('Failed to create Vertex AI session');
  }
  
  // Store session for reuse
  await sessionDocRef.set({
    sessionId,
    purpose,
    createdAt: admin.firestore.FieldValue.serverTimestamp(),
    lastUsedAt: admin.firestore.FieldValue.serverTimestamp()
  });
  
  logger.info('[openCanvas] Created new session', { sessionId });
  return { sessionId, isNew: true };
}

/**
 * Get or create a canvas for the current conversation
 */
async function getOrCreateCanvas(userId, purpose) {
  const canvasesRef = db.collection('users').doc(userId).collection('canvases');
  
  // Always create a new canvas for each conversation (clean slate)
  const canvasDoc = canvasesRef.doc();
  const canvasId = canvasDoc.id;
  
  await canvasDoc.set({
    purpose: purpose || 'general',
    createdAt: admin.firestore.FieldValue.serverTimestamp(),
    status: 'active'
  });
  
  logger.info('[openCanvas] Created new canvas', { canvasId });
  return { canvasId, isNew: true };
}

/**
 * Get resume state for the canvas (cards, last entry cursor)
 */
async function getResumeState(userId, canvasId) {
  const [cardsSnapshot, lastEntrySnapshot] = await Promise.all([
    db.collection('users').doc(userId).collection('canvases').doc(canvasId)
      .collection('cards').orderBy('createdAt', 'desc').limit(10).get(),
    db.collection('users').doc(userId).collection('canvases').doc(canvasId)
      .collection('workspace_entries').orderBy('created_at', 'desc').limit(1).get()
  ]);
  
  const cards = cardsSnapshot.docs.map(doc => ({ id: doc.id, ...doc.data() }));
  const lastEntry = lastEntrySnapshot.docs[0]?.data() || null;
  
  return {
    cards,
    lastEntryCursor: lastEntry?.created_at || null,
    cardCount: cards.length
  };
}

/**
 * Combined openCanvas handler
 * 
 * Input: { userId, purpose }
 * Output: { canvasId, sessionId, resumeState, isNewSession }
 */
async function openCanvasHandler(req, res) {
  const startTime = Date.now();
  const userId = req.body?.userId || req.query?.userId;
  const purpose = req.body?.purpose || req.query?.purpose || 'chat';
  
  if (!userId) {
    return res.status(400).json({
      success: false,
      error: 'userId is required'
    });
  }
  
  try {
    // Run canvas creation and session init in parallel
    const [canvasResult, sessionResult] = await Promise.all([
      getOrCreateCanvas(userId, purpose),
      getOrCreateSession(userId, purpose)
    ]);
    
    // Get resume state (optional, can be empty for new canvas)
    let resumeState = { cards: [], lastEntryCursor: null, cardCount: 0 };
    if (!canvasResult.isNew) {
      resumeState = await getResumeState(userId, canvasResult.canvasId);
    }
    
    const totalTime = Date.now() - startTime;
    logger.info('[openCanvas] Complete', { 
      canvasId: canvasResult.canvasId,
      sessionId: sessionResult.sessionId,
      isNewSession: sessionResult.isNew,
      totalTime: `${totalTime}ms`
    });
    
    return res.status(200).json({
      success: true,
      canvasId: canvasResult.canvasId,
      sessionId: sessionResult.sessionId,
      isNewSession: sessionResult.isNew,
      resumeState,
      timing: {
        totalMs: totalTime
      }
    });
    
  } catch (error) {
    logger.error('[openCanvas] Error', { error: error.message });
    return res.status(500).json({
      success: false,
      error: error.message
    });
  }
}

// Export WITHOUT min instances for now (avoids ~$12.60/month fixed cost)
// Add minInstances: 1 when ready for production
exports.openCanvas = onRequest({
  timeoutSeconds: 60,
  memory: '512MiB'
}, requireFlexibleAuth(openCanvasHandler));

// Also export a pre-warm endpoint that can be called on app launch
async function preWarmSessionHandler(req, res) {
  const userId = req.body?.userId || req.query?.userId;
  const purpose = req.body?.purpose || req.query?.purpose || 'chat';
  
  if (!userId) {
    return res.status(400).json({ success: false, error: 'userId required' });
  }
  
  try {
    const sessionResult = await getOrCreateSession(userId, purpose);
    logger.info('[preWarmSession] Session ready', { sessionId: sessionResult.sessionId });
    
    return res.status(200).json({
      success: true,
      sessionId: sessionResult.sessionId,
      isNew: sessionResult.isNew
    });
  } catch (error) {
    logger.error('[preWarmSession] Error', { error: error.message });
    return res.status(500).json({ success: false, error: error.message });
  }
}

// Also without minInstances for now - add when app goes to production
exports.preWarmSession = onRequest({
  timeoutSeconds: 30,
  memory: '256MiB'
}, requireFlexibleAuth(preWarmSessionHandler));
