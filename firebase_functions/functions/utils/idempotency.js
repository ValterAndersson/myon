const admin = require('firebase-admin');

/**
 * Global helper (legacy): Ensures idempotency per user+tool+key in a global collection.
 * Prefer canvas-scoped idempotency inside Canvas reducer transactions.
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

module.exports = { ensureIdempotent, ensureCanvasIdempotent };


