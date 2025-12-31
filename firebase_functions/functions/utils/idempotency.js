const admin = require('firebase-admin');

const IDEMPOTENCY_TTL_MS = 24 * 60 * 60 * 1000; // 24 hours

/**
 * Global helper (legacy): Ensures idempotency per user+tool+key in a global collection.
 * @deprecated Use ensureWorkoutIdempotent for active_workout endpoints
 */
async function ensureIdempotent(userId, tool, key) {
  if (!key) return { isDuplicate: false };
  const db = admin.firestore();
  const docId = `${userId}:${tool}:${key}`;
  const ref = db.collection('idempotency').doc(docId);
  return await db.runTransaction(async (tx) => {
    const snap = await tx.get(ref);
    if (snap.exists) {
      return { isDuplicate: true, previous: snap.data() };
    }
    tx.set(ref, {
      user_id: userId,
      tool,
      key,
      created_at: admin.firestore.FieldValue.serverTimestamp(),
    });
    return { isDuplicate: false };
  });
}

/**
 * Canvas-scoped idempotency: use within a transaction
 */
async function ensureCanvasIdempotent(tx, canvasPath, key) {
  if (!key) return { isDuplicate: false };
  const ref = admin.firestore().doc(`${canvasPath}/idempotency/${key}`);
  const snap = await tx.get(ref);
  if (snap.exists) return { isDuplicate: true };
  tx.set(ref, { key, created_at: admin.firestore.FieldValue.serverTimestamp() });
  return { isDuplicate: false };
}

/**
 * Workout-scoped idempotency with response caching and TTL.
 * Path: users/{uid}/active_workouts/{workoutId}/idempotency/{key}
 * 
 * Per FOCUS_MODE_WORKOUT_EXECUTION.md spec:
 * - Returns cached response if duplicate key
 * - Stores response with 24h TTL
 * - Must be called FIRST in endpoint, before any mutation
 * 
 * @param {string} userId - User ID
 * @param {string} workoutId - Active workout ID
 * @param {string} key - Idempotency key from client
 * @returns {Promise<{isDuplicate: boolean, cachedResponse?: object}>}
 */
async function checkWorkoutIdempotency(userId, workoutId, key) {
  if (!key) return { isDuplicate: false };
  
  const db = admin.firestore();
  const ref = db.doc(`users/${userId}/active_workouts/${workoutId}/idempotency/${key}`);
  
  const snap = await ref.get();
  if (snap.exists) {
    const data = snap.data();
    // Check if expired (cleanup can happen lazily)
    if (data.expires_at && data.expires_at.toMillis() < Date.now()) {
      // Expired - treat as not duplicate, will be overwritten
      return { isDuplicate: false };
    }
    return { isDuplicate: true, cachedResponse: data.response };
  }
  
  return { isDuplicate: false };
}

/**
 * Store idempotency key with response after successful mutation.
 * Should be called after mutation succeeds, before returning to client.
 * 
 * @param {string} userId - User ID
 * @param {string} workoutId - Active workout ID
 * @param {string} key - Idempotency key from client
 * @param {object} response - The successful response to cache
 * @returns {Promise<void>}
 */
async function storeWorkoutIdempotency(userId, workoutId, key, response) {
  if (!key) return;
  
  const db = admin.firestore();
  const ref = db.doc(`users/${userId}/active_workouts/${workoutId}/idempotency/${key}`);
  
  await ref.set({
    key,
    response,
    created_at: admin.firestore.FieldValue.serverTimestamp(),
    expires_at: admin.firestore.Timestamp.fromMillis(Date.now() + IDEMPOTENCY_TTL_MS),
  });
}

/**
 * Combined helper for workout idempotency - use in transaction.
 * Checks and stores in one transaction if not duplicate.
 * 
 * @param {Transaction} tx - Firestore transaction
 * @param {string} userId - User ID
 * @param {string} workoutId - Active workout ID
 * @param {string} key - Idempotency key
 * @returns {Promise<{isDuplicate: boolean, cachedResponse?: object}>}
 */
async function ensureWorkoutIdempotent(tx, userId, workoutId, key) {
  if (!key) return { isDuplicate: false };
  
  const db = admin.firestore();
  const ref = db.doc(`users/${userId}/active_workouts/${workoutId}/idempotency/${key}`);
  
  const snap = await tx.get(ref);
  if (snap.exists) {
    const data = snap.data();
    // Check if expired
    if (data.expires_at && data.expires_at.toMillis() < Date.now()) {
      return { isDuplicate: false }; // Will overwrite
    }
    return { isDuplicate: true, cachedResponse: data.response };
  }
  
  return { isDuplicate: false };
}

/**
 * Store idempotency within transaction.
 * 
 * @param {Transaction} tx - Firestore transaction
 * @param {string} userId - User ID
 * @param {string} workoutId - Active workout ID
 * @param {string} key - Idempotency key
 * @param {object} response - Response to cache
 */
function storeWorkoutIdempotentTx(tx, userId, workoutId, key, response) {
  if (!key) return;
  
  const db = admin.firestore();
  const ref = db.doc(`users/${userId}/active_workouts/${workoutId}/idempotency/${key}`);
  
  tx.set(ref, {
    key,
    response,
    created_at: admin.firestore.FieldValue.serverTimestamp(),
    expires_at: admin.firestore.Timestamp.fromMillis(Date.now() + IDEMPOTENCY_TTL_MS),
  });
}

module.exports = { 
  ensureIdempotent, 
  ensureCanvasIdempotent,
  // New workout-scoped helpers
  checkWorkoutIdempotency,
  storeWorkoutIdempotency,
  ensureWorkoutIdempotent,
  storeWorkoutIdempotentTx,
  IDEMPOTENCY_TTL_MS,
};
