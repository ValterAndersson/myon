const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');
const { ok, fail } = require('../utils/response');
const admin = require('firebase-admin');

const db = new FirestoreHelper();

async function backupExercisesHandler(req, res) {
  try {
    if (req.method !== 'POST') return fail(res, 'METHOD_NOT_ALLOWED', 'Method Not Allowed', null, 405);
    const userId = req.user?.uid || req.auth?.uid;
    if (!userId) return fail(res, 'UNAUTHORIZED', 'Unauthorized', null, 401);

    const ts = new Date().toISOString().replace(/[:.]/g, '-');
    const backupCollection = 'exercises_backup';

    // Read all exercises in pages
    const pageSize = 200;
    let lastName = null;
    let total = 0;
    while (true) {
      let query = db.db.collection('exercises').orderBy('name').limit(pageSize);
      if (lastName) query = query.startAfter(lastName);
      const snap = await query.get();
      if (snap.empty) break;
      const batch = db.db.batch();
      snap.docs.forEach(doc => {
        const data = doc.data();
        // store under exercises_backup/{docId}
        const ref = db.db.collection(backupCollection).doc(doc.id);
        batch.set(ref, {
          ...data,
          _backup_meta: {
            source: 'exercises',
            backed_up_at: admin.firestore.FieldValue.serverTimestamp(),
            tag: ts,
          },
        }, { merge: false });
      });
      await batch.commit();
      total += snap.size;
      lastName = snap.docs[snap.docs.length - 1].get('name');
      if (snap.size < pageSize) break;
    }

    return ok(res, { backed_up: total, collection: backupCollection });
  } catch (error) {
    console.error('backup-exercises error:', error);
    return fail(res, 'INTERNAL', 'Failed to backup exercises', { message: error.message }, 500);
  }
}

exports.backupExercises = onRequest(requireFlexibleAuth(backupExercisesHandler));


