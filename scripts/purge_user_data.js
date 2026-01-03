'use strict';

/**
 * Purge User Data Script
 * 
 * Cleans up a user's workout-related data in Firestore:
 * - All active workouts (in_progress or otherwise)
 * - All routines 
 * - All templates
 * - Optionally: workouts history, weekly_stats, analytics
 * 
 * Usage:
 *   node scripts/purge_user_data.js <userId> [--all]
 * 
 * Flags:
 *   --all    Also delete workouts history and analytics data
 */

const admin = require('firebase-admin');

// Initialize with your service account
// Option 1: Use GOOGLE_APPLICATION_CREDENTIALS env var
// Option 2: Pass path directly
const serviceAccountPath = process.env.FIREBASE_SERVICE_ACCOUNT_PATH;
if (serviceAccountPath) {
  const serviceAccount = require(serviceAccountPath);
  admin.initializeApp({
    credential: admin.credential.cert(serviceAccount)
  });
} else {
  // Use default credentials (gcloud auth)
  admin.initializeApp({
    projectId: 'myon-53d85'
  });
}

const db = admin.firestore();

async function deleteCollection(collectionRef, batchSize = 100) {
  const query = collectionRef.limit(batchSize);
  let deleted = 0;
  
  while (true) {
    const snapshot = await query.get();
    if (snapshot.empty) {
      break;
    }
    
    const batch = db.batch();
    snapshot.docs.forEach(doc => {
      batch.delete(doc.ref);
      deleted++;
    });
    await batch.commit();
    
    console.log(`  Deleted ${deleted} documents so far...`);
  }
  
  return deleted;
}

async function deleteSubcollection(docRef, subcollectionName) {
  const subcollectionRef = docRef.collection(subcollectionName);
  const snapshot = await subcollectionRef.get();
  
  if (snapshot.empty) return 0;
  
  const batch = db.batch();
  snapshot.docs.forEach(doc => {
    batch.delete(doc.ref);
  });
  await batch.commit();
  
  return snapshot.size;
}

async function purgeActiveWorkouts(userId) {
  console.log('\n🗑️  Purging active_workouts...');
  
  const activeWorkoutsRef = db.collection('users').doc(userId).collection('active_workouts');
  const snapshot = await activeWorkoutsRef.get();
  
  let deleted = 0;
  for (const doc of snapshot.docs) {
    // Delete events subcollection first
    const eventsDeleted = await deleteSubcollection(doc.ref, 'events');
    if (eventsDeleted > 0) {
      console.log(`  Deleted ${eventsDeleted} events for workout ${doc.id}`);
    }
    
    // Delete the workout doc
    await doc.ref.delete();
    console.log(`  Deleted active workout: ${doc.id} (status: ${doc.data()?.status})`);
    deleted++;
  }
  
  console.log(`  ✅ Deleted ${deleted} active workouts`);
  return deleted;
}

async function purgeRoutines(userId) {
  console.log('\n🗑️  Purging routines...');
  
  const routinesRef = db.collection('users').doc(userId).collection('routines');
  const deleted = await deleteCollection(routinesRef);
  
  // Also clear the activeRoutineId from user doc
  const userRef = db.collection('users').doc(userId);
  const userDoc = await userRef.get();
  if (userDoc.exists && userDoc.data()?.activeRoutineId) {
    await userRef.update({ activeRoutineId: admin.firestore.FieldValue.delete() });
    console.log('  Cleared activeRoutineId from user doc');
  }
  
  console.log(`  ✅ Deleted ${deleted} routines`);
  return deleted;
}

async function purgeTemplates(userId) {
  console.log('\n🗑️  Purging templates...');
  
  const templatesRef = db.collection('users').doc(userId).collection('templates');
  const deleted = await deleteCollection(templatesRef);
  
  console.log(`  ✅ Deleted ${deleted} templates`);
  return deleted;
}

async function purgeWorkoutsHistory(userId) {
  console.log('\n🗑️  Purging workouts history...');
  
  const workoutsRef = db.collection('users').doc(userId).collection('workouts');
  const deleted = await deleteCollection(workoutsRef);
  
  console.log(`  ✅ Deleted ${deleted} workouts`);
  return deleted;
}

async function purgeWeeklyStats(userId) {
  console.log('\n🗑️  Purging weekly_stats...');
  
  const statsRef = db.collection('users').doc(userId).collection('weekly_stats');
  const deleted = await deleteCollection(statsRef);
  
  console.log(`  ✅ Deleted ${deleted} weekly_stats`);
  return deleted;
}

async function purgeAnalytics(userId) {
  console.log('\n🗑️  Purging analytics...');
  
  let totalDeleted = 0;
  
  // Delete analytics_series_exercise
  const exerciseSeriesRef = db.collection('users').doc(userId).collection('analytics_series_exercise');
  totalDeleted += await deleteCollection(exerciseSeriesRef);
  
  // Delete analytics_series_muscle
  const muscleSeriesRef = db.collection('users').doc(userId).collection('analytics_series_muscle');
  totalDeleted += await deleteCollection(muscleSeriesRef);
  
  // Delete analytics_rollups
  const rollupsRef = db.collection('users').doc(userId).collection('analytics_rollups');
  totalDeleted += await deleteCollection(rollupsRef);
  
  console.log(`  ✅ Deleted ${totalDeleted} analytics documents`);
  return totalDeleted;
}

async function purgeMeta(userId) {
  console.log('\n🗑️  Purging meta subcollection...');
  
  const metaRef = db.collection('users').doc(userId).collection('meta');
  const deleted = await deleteCollection(metaRef);
  
  console.log(`  ✅ Deleted ${deleted} meta documents`);
  return deleted;
}

async function main() {
  const args = process.argv.slice(2);
  const userId = args.find(a => !a.startsWith('--'));
  const purgeAll = args.includes('--all');
  
  if (!userId) {
    console.error('Usage: node scripts/purge_user_data.js <userId> [--all]');
    console.error('');
    console.error('This will delete:');
    console.error('  - All active workouts');
    console.error('  - All routines');
    console.error('  - All templates');
    console.error('  - Meta subcollection (active workout pointer)');
    console.error('');
    console.error('With --all flag, also deletes:');
    console.error('  - Workouts history');
    console.error('  - Weekly stats');
    console.error('  - Analytics series and rollups');
    process.exit(1);
  }
  
  console.log(`\n======================================`);
  console.log(`PURGING DATA FOR USER: ${userId}`);
  console.log(`Mode: ${purgeAll ? 'FULL PURGE (including history)' : 'Workout state only'}`);
  console.log(`======================================`);
  
  // Verify user exists
  const userRef = db.collection('users').doc(userId);
  const userDoc = await userRef.get();
  
  if (!userDoc.exists) {
    console.error(`\n❌ User not found: ${userId}`);
    process.exit(1);
  }
  
  console.log(`\n✅ Found user: ${userDoc.data()?.email || userDoc.data()?.name || userId}`);
  
  // Core cleanup (always run)
  await purgeActiveWorkouts(userId);
  await purgeMeta(userId);
  await purgeRoutines(userId);
  await purgeTemplates(userId);
  
  // Extended cleanup (only with --all)
  if (purgeAll) {
    await purgeWorkoutsHistory(userId);
    await purgeWeeklyStats(userId);
    await purgeAnalytics(userId);
  }
  
  console.log(`\n======================================`);
  console.log(`✅ PURGE COMPLETE`);
  console.log(`======================================`);
  console.log(`\nUser ${userId} is now in a clean state.`);
  if (!purgeAll) {
    console.log('(Workouts history and analytics preserved. Use --all to delete those too.)');
  }
}

main().catch((err) => {
  console.error('\n❌ Purge failed:', err?.message || err);
  process.exit(1);
});
