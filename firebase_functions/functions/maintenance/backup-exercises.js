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


/**
 * Duplicate exercises catalog to a new collection (e.g., exercises-v2-backup).
 * 
 * Unlike backupExercises (which creates timestamped copies), this creates an
 * exact duplicate with migration metadata for the catalog admin v2 system.
 * 
 * Body params:
 * - target: Target collection name (default: 'exercises-v2-backup')
 * - incremental: If true, only copy docs newer than target's last update (default: false)
 */
async function duplicateCatalogHandler(req, res) {
  try {
    if (req.method !== 'POST') return fail(res, 'METHOD_NOT_ALLOWED', 'Method Not Allowed', null, 405);
    const userId = req.user?.uid || req.auth?.uid;
    if (!userId) return fail(res, 'UNAUTHORIZED', 'Unauthorized', null, 401);

    const targetCollection = req.body?.target || 'exercises-v2-backup';
    const incremental = req.body?.incremental === true;
    const sourceCollection = 'exercises';
    
    // Validate target collection name
    if (!/^[a-z0-9_-]+$/i.test(targetCollection)) {
      return fail(res, 'INVALID_TARGET', 'Target collection name must be alphanumeric with - or _', null, 400);
    }
    
    // Prevent overwriting source
    if (targetCollection === sourceCollection) {
      return fail(res, 'INVALID_TARGET', 'Cannot duplicate to same collection', null, 400);
    }

    const now = new Date();
    const migrationTs = now.toISOString();
    
    // For incremental: find the latest _migration_meta.duplicated_at in target
    let cutoffTime = null;
    if (incremental) {
      const latestDoc = await db.db.collection(targetCollection)
        .orderBy('_migration_meta.duplicated_at', 'desc')
        .limit(1)
        .get();
      if (!latestDoc.empty) {
        cutoffTime = latestDoc.docs[0].get('_migration_meta.duplicated_at')?.toDate?.() || null;
      }
    }

    // Read all exercises in pages
    const pageSize = 200;
    let lastDoc = null;
    let copied = 0;
    let skipped = 0;
    
    while (true) {
      let query = db.db.collection(sourceCollection).orderBy('name').limit(pageSize);
      if (lastDoc) query = query.startAfter(lastDoc);
      const snap = await query.get();
      if (snap.empty) break;
      
      const batch = db.db.batch();
      let batchHasWrites = false;
      
      for (const doc of snap.docs) {
        const data = doc.data();
        
        // For incremental: skip if doc hasn't been updated since cutoff
        if (incremental && cutoffTime) {
          const updatedAt = data.updated_at?.toDate?.() || data.created_at?.toDate?.();
          if (updatedAt && updatedAt <= cutoffTime) {
            skipped++;
            continue;
          }
        }
        
        // Duplicate with migration metadata
        const ref = db.db.collection(targetCollection).doc(doc.id);
        batch.set(ref, {
          ...data,
          _migration_meta: {
            source_collection: sourceCollection,
            source_doc_id: doc.id,
            duplicated_at: admin.firestore.FieldValue.serverTimestamp(),
            migration_tag: migrationTs,
            duplicated_by: userId,
          },
        }, { merge: false });
        batchHasWrites = true;
        copied++;
      }
      
      if (batchHasWrites) {
        await batch.commit();
      }
      
      lastDoc = snap.docs[snap.docs.length - 1];
      if (snap.size < pageSize) break;
    }

    console.log(`duplicateCatalog: copied ${copied}, skipped ${skipped} to ${targetCollection}`);
    
    return ok(res, { 
      copied, 
      skipped,
      target_collection: targetCollection,
      migration_tag: migrationTs,
      incremental,
    });
  } catch (error) {
    console.error('duplicate-catalog error:', error);
    return fail(res, 'INTERNAL', 'Failed to duplicate catalog', { message: error.message }, 500);
  }
}

exports.duplicateCatalog = onRequest(requireFlexibleAuth(duplicateCatalogHandler));
