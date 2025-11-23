'use strict';

const admin = require('firebase-admin');
const { ok, fail } = require('../utils/response');

async function purgeCollection(ref, batchSize = 250) {
  const db = admin.firestore();
  let deleted = 0;
  while (true) {
    const snap = await ref.limit(batchSize).get();
    if (snap.empty) break;
    const batch = db.batch();
    snap.docs.forEach(doc => batch.delete(doc.ref));
    await batch.commit();
    deleted += snap.size;
    if (snap.size < batchSize) break;
  }
  return deleted;
}

async function purgeCanvas(req, res) {
  try {
    if (req.method !== 'POST') {
      return res.status(405).json({ success: false, error: 'Method Not Allowed' });
    }

    const auth = req.user || req.auth;
    if (!auth) return fail(res, 'UNAUTHORIZED', 'Authentication required', null, 401);

    const uid = req.body?.userId || auth.uid;
    const canvasId = req.body?.canvasId;
    const dropEvents = Boolean(req.body?.dropEvents || false);
    const dropState = Boolean(req.body?.dropState || false);
    const dropIdem = Boolean(req.body?.dropIdempotency || false);
    if (!uid || !canvasId) return fail(res, 'INVALID_ARGUMENT', 'userId and canvasId are required', null, 400);

    const basePath = `users/${uid}/canvases/${canvasId}`;
    const db = admin.firestore();

    // Delete cards and up_next deterministically
    const deletedCards = await purgeCollection(db.collection(`${basePath}/cards`));
    const deletedUpNext = await purgeCollection(db.collection(`${basePath}/up_next`));
    let deletedEvents = 0;
    let deletedIdem = 0;

    if (dropEvents) {
      deletedEvents = await purgeCollection(db.collection(`${basePath}/events`));
    }
    if (dropIdem) {
      deletedIdem = await purgeCollection(db.collection(`${basePath}/idempotency`));
    }
    if (dropState) {
      await db.doc(basePath).set({ state: { version: 0, phase: 'planning' } }, { merge: true });
    }

    return ok(res, { deleted: { cards: deletedCards, up_next: deletedUpNext, events: deletedEvents, idempotency: deletedIdem } });
  } catch (e) {
    console.error('purgeCanvas error:', e);
    return fail(res, 'INTERNAL', 'Failed to purge canvas', { message: e?.message }, 500);
  }
}

module.exports = { purgeCanvas };


