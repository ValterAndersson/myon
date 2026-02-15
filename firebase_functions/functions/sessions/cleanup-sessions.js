/**
 * Cleanup Stale Sessions - Scheduled function
 *
 * Runs every 6 hours to purge expired agent_sessions from Firestore.
 * Vertex AI sessions auto-expire at ~60min. Sessions older than 2 hours
 * are guaranteed dead. The 2-hour cutoff gives margin for the 55min TTL.
 *
 * Uses collectionGroup query on 'agent_sessions' to find stale docs
 * across all users, then batch-deletes them.
 */

const admin = require('firebase-admin');
const { logger } = require('firebase-functions');

if (!admin.apps.length) {
  admin.initializeApp();
}
const db = admin.firestore();

// Sessions older than 2 hours are guaranteed dead
const STALE_CUTOFF_MS = 2 * 60 * 60 * 1000;

// Max docs per batch (Firestore limit is 500)
const BATCH_LIMIT = 500;

async function cleanupStaleSessions() {
  const cutoff = Date.now() - STALE_CUTOFF_MS;
  const cutoffTimestamp = admin.firestore.Timestamp.fromMillis(cutoff);

  logger.info('[cleanupStaleSessions] Starting cleanup', {
    cutoff: new Date(cutoff).toISOString(),
  });

  const staleSessionsQuery = db
    .collectionGroup('agent_sessions')
    .where('lastUsedAt', '<', cutoffTimestamp)
    .limit(BATCH_LIMIT);

  const snapshot = await staleSessionsQuery.get();

  if (snapshot.empty) {
    logger.info('[cleanupStaleSessions] No stale sessions found');
    return { deleted: 0 };
  }

  const batch = db.batch();
  snapshot.docs.forEach((doc) => batch.delete(doc.ref));
  await batch.commit();

  logger.info('[cleanupStaleSessions] Deleted stale sessions', {
    deleted: snapshot.size,
  });

  return { deleted: snapshot.size };
}

module.exports = { cleanupStaleSessions };
