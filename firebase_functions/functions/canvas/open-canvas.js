/**
 * openCanvas - Combined endpoint to minimize round trips
 * 
 * Replaces: bootstrapCanvas + initializeSession in a single call
 * Returns: canvasId, sessionId, resumeState (cards, last entry cursor)
 * 
 * CANVAS LIFECYCLE: Tied to session lifecycle
 * - New session = new canvas (fresh start)
 * - Resume session = resume canvas (same conversation)
 * - Explicit canvasId = resume specific conversation (conversation history feature)
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

// Session TTL: 55 minutes of inactivity
// Vertex AI sessions auto-expire at ~60min. 55min gives buffer while maximizing reuse.
const SESSION_TTL_MS = 55 * 60 * 1000;

// Agent version - MUST MATCH initialize-session.js and stream-agent-normalized.js
// When agent is updated, bump this to invalidate all existing sessions
const AGENT_VERSION = '2.6.0'; // Session-canvas lifecycle binding

/**
 * Create a new canvas for the user
 */
async function createCanvas(userId, purpose) {
  const canvasesRef = db.collection('users').doc(userId).collection('canvases');
  const canvasDoc = canvasesRef.doc();
  const canvasId = canvasDoc.id;
  
  await canvasDoc.set({
    purpose: purpose || 'general',
    createdAt: admin.firestore.FieldValue.serverTimestamp(),
    status: 'active'
  });
  
  logger.info('[openCanvas] Created new canvas', { canvasId });
  return canvasId;
}

/**
 * Get or create a Vertex AI session for the user.
 * Now also manages canvas lifecycle - new session = new canvas.
 * 
 * Returns: { sessionId, canvasId, isNew }
 */
async function getOrCreateSessionWithCanvas(userId, purpose, requestedCanvasId) {
  const sessionDocRef = db.collection('users').doc(userId).collection('agent_sessions').doc(purpose);
  const sessionDoc = await sessionDocRef.get();
  
  const now = Date.now();
  
  // CASE 1: Explicit canvas resume (conversation history feature)
  // User wants to resume a specific conversation - use that canvas
  if (requestedCanvasId) {
    const canvasesRef = db.collection('users').doc(userId).collection('canvases');
    const existingCanvas = await canvasesRef.doc(requestedCanvasId).get();
    
    if (existingCanvas.exists) {
      // Resume the specific canvas - always create fresh session for resumed conversations
      // (The old session context won't match the resumed conversation anyway)
      logger.info('[openCanvas] Resuming specific canvas - creating fresh session', { 
        canvasId: requestedCanvasId 
      });
      
      const sessionId = await createVertexSession(userId);
      
      await sessionDocRef.set({
        sessionId,
        canvasId: requestedCanvasId,
        agentVersion: AGENT_VERSION,
        purpose,
        createdAt: admin.firestore.FieldValue.serverTimestamp(),
        lastUsedAt: admin.firestore.FieldValue.serverTimestamp()
      });
      
      return { sessionId, canvasId: requestedCanvasId, isNew: true };
    }
    // If requested canvas doesn't exist, fall through to normal logic
    logger.warn('[openCanvas] Requested canvas not found, creating new', { requestedCanvasId });
  }
  
  // CASE 2: Check for existing valid session
  if (sessionDoc.exists) {
    const data = sessionDoc.data();
    const lastUsed = data.lastUsedAt?.toMillis?.() || 0;
    const age = now - lastUsed;
    const storedVersion = data.agentVersion || 'unknown';
    const storedCanvasId = data.canvasId;
    
    // Version mismatch = stale session, force new
    const versionMismatch = storedVersion !== AGENT_VERSION;
    if (versionMismatch && data.sessionId) {
      logger.info('[openCanvas] Version mismatch - creating fresh session + canvas', {
        oldVersion: storedVersion,
        newVersion: AGENT_VERSION,
        oldSessionId: data.sessionId
      });
      // Fall through to create new
    } else if (age < SESSION_TTL_MS && data.sessionId && storedCanvasId) {
      // CASE 2a: Valid session with canvas - reuse both
      logger.info('[openCanvas] Reusing existing session + canvas', { 
        sessionId: data.sessionId,
        canvasId: storedCanvasId,
        age: Math.round(age / 1000) + 's',
        agentVersion: AGENT_VERSION
      });
      
      // Touch the session
      await sessionDocRef.update({ lastUsedAt: admin.firestore.FieldValue.serverTimestamp() });
      
      return { sessionId: data.sessionId, canvasId: storedCanvasId, isNew: false };
    }
    // Session expired or no canvas linked - fall through to create new
  }
  
  // CASE 3: Create new session AND new canvas (fresh start)
  logger.info('[openCanvas] Creating new session + canvas (fresh start)');
  
  const sessionId = await createVertexSession(userId);
  const canvasId = await createCanvas(userId, purpose);
  
  // Store session with linked canvas
  await sessionDocRef.set({
    sessionId,
    canvasId,
    agentVersion: AGENT_VERSION,
    purpose,
    createdAt: admin.firestore.FieldValue.serverTimestamp(),
    lastUsedAt: admin.firestore.FieldValue.serverTimestamp()
  });
  
  logger.info('[openCanvas] Created new session + canvas', { sessionId, canvasId });
  return { sessionId, canvasId, isNew: true };
}

/**
 * Create a new Vertex AI session
 */
async function createVertexSession(userId) {
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
  
  return sessionId;
}

/**
 * Get resume state for the canvas (cards, last entry cursor)
 */
async function getResumeState(userId, canvasId) {
  const [cardsSnapshot, lastEntrySnapshot] = await Promise.all([
    db.collection('users').doc(userId).collection('canvases').doc(canvasId)
      .collection('cards').orderBy('created_at', 'desc').limit(10).get(),
    db.collection('users').doc(userId).collection('canvases').doc(canvasId)
      .collection('workspace_entries').orderBy('created_at', 'desc').limit(1).get()
  ]);
  
  const cards = cardsSnapshot.docs.map(doc => ({ id: doc.id, ...doc.data() }));
  const lastEntry = lastEntrySnapshot.docs[0]?.data() || null;
  
  // Convert Firestore timestamp to ISO string for iOS compatibility
  let lastEntryCursor = null;
  if (lastEntry?.created_at) {
    const ts = lastEntry.created_at;
    if (ts.toDate) {
      // Firestore Timestamp - convert to ISO string
      lastEntryCursor = ts.toDate().toISOString();
    } else if (ts._seconds) {
      // Already serialized Firestore timestamp format
      lastEntryCursor = new Date(ts._seconds * 1000).toISOString();
    } else {
      // Already a string or other format
      lastEntryCursor = String(ts);
    }
  }
  
  return {
    cards,
    lastEntryCursor,
    cardCount: cards.length
  };
}

/**
 * Combined openCanvas handler
 * 
 * Input: { userId, purpose, canvasId? }
 * Output: { canvasId, sessionId, resumeState, isNewSession }
 * 
 * Lifecycle:
 * - No canvasId provided = auto-manage (new session = new canvas, resume session = resume canvas)
 * - canvasId provided = resume that specific conversation (for conversation history feature)
 */
async function openCanvasHandler(req, res) {
  const startTime = Date.now();
  const userId = req.body?.userId || req.query?.userId;
  const purpose = req.body?.purpose || req.query?.purpose || 'chat';
  const requestedCanvasId = req.body?.canvasId || req.query?.canvasId;
  
  if (!userId) {
    return res.status(400).json({
      success: false,
      error: 'userId is required'
    });
  }
  
  try {
    // Get or create session with linked canvas
    const { sessionId, canvasId, isNew } = await getOrCreateSessionWithCanvas(
      userId, 
      purpose, 
      requestedCanvasId
    );
    
    // Get resume state (for existing canvas, or empty for new)
    const resumeState = await getResumeState(userId, canvasId);
    
    const totalTime = Date.now() - startTime;
    logger.info('[openCanvas] Complete', { 
      canvasId,
      sessionId,
      isNewSession: isNew,
      cardCount: resumeState.cardCount,
      totalTime: `${totalTime}ms`
    });
    
    return res.status(200).json({
      success: true,
      canvasId,
      sessionId,
      isNewSession: isNew,
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

exports.openCanvas = onRequest({
  timeoutSeconds: 60,
  memory: '512MiB'
  // minInstances: 1
}, requireFlexibleAuth(openCanvasHandler));

// Also export a pre-warm endpoint that can be called on app launch
async function preWarmSessionHandler(req, res) {
  const userId = req.body?.userId || req.query?.userId;
  const purpose = req.body?.purpose || req.query?.purpose || 'chat';
  
  if (!userId) {
    return res.status(400).json({ success: false, error: 'userId required' });
  }
  
  try {
    const { sessionId, canvasId, isNew } = await getOrCreateSessionWithCanvas(userId, purpose, null);
    logger.info('[preWarmSession] Session ready', { sessionId, canvasId });
    
    return res.status(200).json({
      success: true,
      sessionId,
      canvasId,
      isNew
    });
  } catch (error) {
    logger.error('[preWarmSession] Error', { error: error.message });
    return res.status(500).json({ success: false, error: error.message });
  }
}

exports.preWarmSession = onRequest({
  timeoutSeconds: 30,
  memory: '256MiB'
  // minInstances: 1
}, requireFlexibleAuth(preWarmSessionHandler));
