'use strict';

/**
 * Reset Stuck Job Script
 *
 * Resets a leased analysis job back to queued so the worker can retry it.
 *
 * Usage:
 *   GOOGLE_APPLICATION_CREDENTIALS=$FIREBASE_SA_KEY node scripts/reset_stuck_job.js <jobId>
 */

const admin = require('firebase-admin');

admin.initializeApp({
  projectId: 'myon-53d85',
});

const db = admin.firestore();

async function resetJob(jobId) {
  const jobRef = db.collection('training_analysis_jobs').doc(jobId);
  const snap = await jobRef.get();

  if (!snap.exists) {
    console.error(`Job ${jobId} not found in training_analysis_jobs`);
    process.exit(1);
  }

  const data = snap.data();
  console.log(`Current status: ${data.status}, lease_expires_at: ${data.lease_expires_at?.toDate?.() ?? 'N/A'}`);

  if (data.status !== 'leased') {
    console.log(`Job is not leased (status: ${data.status}), nothing to reset.`);
    process.exit(0);
  }

  await jobRef.update({
    status: 'queued',
    lease_expires_at: admin.firestore.FieldValue.delete(),
    lease_owner: admin.firestore.FieldValue.delete(),
    updated_at: admin.firestore.FieldValue.serverTimestamp(),
  });

  console.log(`Job ${jobId} reset to queued.`);
}

const jobId = process.argv[2];
if (!jobId) {
  console.error('Usage: node scripts/reset_stuck_job.js <jobId>');
  process.exit(1);
}

resetJob(jobId)
  .then(() => process.exit(0))
  .catch((err) => {
    console.error('Error:', err.message);
    process.exit(1);
  });
