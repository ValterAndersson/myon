const admin = require('firebase-admin');

async function expireProposalsScheduledHandler() {
  const db = admin.firestore();
  const nowMs = Date.now();

  // Process proposed cards older than a minute; verify TTL before expiring
  const threshold = new Date(nowMs - 60 * 1000);
  let processed = 0;
  let expired = 0;
  const pageSize = 500; // stay under batch limits

  let lastCreatedAt = null;
  // Page through proposed cards ordered by created_at
  while (true) {
    let q = db
      .collectionGroup('cards')
      .where('status', '==', 'proposed')
      .where('created_at', '<', admin.firestore.Timestamp.fromDate(threshold))
      .orderBy('created_at', 'asc')
      .limit(pageSize);
    if (lastCreatedAt) q = q.startAfter(lastCreatedAt);

    const snap = await q.get();
    if (snap.empty) break;

    let batch = db.batch();
    let ops = 0;

    for (const doc of snap.docs) {
      processed += 1;
      const data = doc.data();
      const ttlMin = data?.ttl?.minutes;
      const createdAt = data?.created_at?.toMillis ? data.created_at.toMillis() : null;
      if (!ttlMin || !createdAt) continue;
      if (createdAt + ttlMin * 60 * 1000 > nowMs) continue; // not expired yet

      // Mark card expired
      batch.update(doc.ref, { status: 'expired', updated_at: admin.firestore.FieldValue.serverTimestamp() });
      ops += 1;
      expired += 1;

      // Remove from up_next
      const canvasRef = doc.ref.parent.parent; // .../canvases/{canvasId}
      if (canvasRef) {
        const upNextSnap = await canvasRef.collection('up_next').where('card_id', '==', doc.id).limit(10).get();
        upNextSnap.forEach((u) => {
          batch.delete(u.ref);
          ops += 1;
        });
      }

      if (ops >= 450) {
        await batch.commit();
        batch = db.batch();
        ops = 0;
      }
    }

    if (ops > 0) await batch.commit();
    lastCreatedAt = snap.docs[snap.docs.length - 1].get('created_at');
  }

  console.log('[expireProposalsScheduled] processed=', processed, 'expired=', expired);
  return { processed, expired };
}

module.exports = { expireProposalsScheduledHandler };


