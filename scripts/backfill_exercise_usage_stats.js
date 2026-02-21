#!/usr/bin/env node

/**
 * Backfill Exercise Usage Stats Script
 *
 * Computes exercise_usage_stats from completed workouts for exercise sorting
 * by recency and frequency. Safe to re-run (overwrites with computed values).
 *
 * Usage:
 *   node scripts/backfill_exercise_usage_stats.js [--user <userId>] [--dry-run] [--limit <n>]
 *
 * Options:
 *   --user <userId>  Only backfill for a specific user
 *   --dry-run        Don't write, just log what would be written
 *   --limit <n>      Limit number of workouts processed per user
 *   --all-users      Process all users (required if --user not specified)
 */

const admin = require('firebase-admin');

// Initialize Firebase Admin — same pattern as backfill_set_facts.js
const serviceAccountPath = process.env.FIREBASE_SERVICE_ACCOUNT_PATH;

try {
  if (serviceAccountPath) {
    const serviceAccount = require(serviceAccountPath);
    admin.initializeApp({
      credential: admin.credential.cert(serviceAccount),
    });
    console.log('Initialized with service account:', serviceAccountPath);
  } else {
    admin.initializeApp({
      projectId: 'myon-53d85',
    });
    console.log('Initialized with default credentials (gcloud auth)');
  }
} catch (e) {
  if (!e.message.includes('already exists')) {
    throw e;
  }
}

const db = admin.firestore();

// Parse command line arguments
const args = process.argv.slice(2);
const options = {
  userId: null,
  dryRun: false,
  limit: null,
  allUsers: false,
};

for (let i = 0; i < args.length; i++) {
  if (args[i] === '--user' && args[i + 1]) {
    options.userId = args[i + 1];
    i++;
  } else if (args[i] === '--dry-run') {
    options.dryRun = true;
  } else if (args[i] === '--limit' && args[i + 1]) {
    options.limit = parseInt(args[i + 1], 10);
    i++;
  } else if (args[i] === '--all-users') {
    options.allUsers = true;
  }
}

// Validate arguments
if (!options.userId && !options.allUsers) {
  console.error('Error: Must specify --user <userId> or --all-users');
  process.exit(1);
}

/**
 * Process all completed workouts for a user and compute exercise usage stats.
 * Overwrites existing stats (safe to re-run).
 */
async function processUser(userId) {
  console.log(`\nProcessing user: ${userId}`);

  let query = db.collection('users').doc(userId).collection('workouts')
    .orderBy('end_time', 'desc');

  if (options.limit) {
    query = query.limit(options.limit);
  }

  const workoutsSnap = await query.get();
  console.log(`  Found ${workoutsSnap.size} workouts`);

  if (workoutsSnap.empty) {
    return { userId, workouts: 0, statsWritten: 0 };
  }

  // Aggregate per-exercise stats across all workouts
  // exerciseId -> { name, lastWorkoutDate, workoutCount, lastWorkoutId }
  const statsMap = new Map();

  for (const doc of workoutsSnap.docs) {
    const workout = doc.data();
    if (!workout.end_time || !Array.isArray(workout.exercises)) continue;

    const endTime = workout.end_time.toDate
      ? workout.end_time.toDate().toISOString()
      : workout.end_time;
    const workoutDate = typeof endTime === 'string' ? endTime.split('T')[0] : null;
    if (!workoutDate) continue;

    const seen = new Set();
    for (const ex of workout.exercises) {
      if (!ex.exercise_id || seen.has(ex.exercise_id)) continue;
      seen.add(ex.exercise_id);

      const existing = statsMap.get(ex.exercise_id);
      if (!existing) {
        statsMap.set(ex.exercise_id, {
          name: ex.name || '',
          lastWorkoutDate: workoutDate,
          workoutCount: 1,
          lastWorkoutId: doc.id,
        });
      } else {
        existing.workoutCount += 1;
        // Keep the most recent date (workouts are ordered desc, so first seen is latest)
        // but be safe in case ordering changes
        if (workoutDate > existing.lastWorkoutDate) {
          existing.lastWorkoutDate = workoutDate;
          existing.lastWorkoutId = doc.id;
        }
      }
    }
  }

  console.log(`  Found ${statsMap.size} unique exercises`);

  if (options.dryRun) {
    for (const [exerciseId, stats] of statsMap) {
      console.log(`    [DRY RUN] ${exerciseId}: ${stats.name} — ${stats.workoutCount} workouts, last ${stats.lastWorkoutDate}`);
    }
    return { userId, workouts: workoutsSnap.size, statsWritten: statsMap.size, dryRun: true };
  }

  // Write stats using batched writes (500-doc Firestore batch limit)
  const entries = Array.from(statsMap.entries());
  const batchSize = 500;
  let totalWritten = 0;

  for (let i = 0; i < entries.length; i += batchSize) {
    const batch = db.batch();
    const chunk = entries.slice(i, i + batchSize);

    for (const [exerciseId, stats] of chunk) {
      const ref = db.collection('users').doc(userId)
        .collection('exercise_usage_stats').doc(exerciseId);

      batch.set(ref, {
        exercise_id: exerciseId,
        exercise_name: stats.name,
        last_workout_date: stats.lastWorkoutDate,
        workout_count: stats.workoutCount,
        last_processed_workout_id: stats.lastWorkoutId,
        updated_at: admin.firestore.FieldValue.serverTimestamp(),
      });
    }

    await batch.commit();
    totalWritten += chunk.length;
  }

  console.log(`  Wrote ${totalWritten} exercise_usage_stats docs`);
  return { userId, workouts: workoutsSnap.size, statsWritten: totalWritten };
}

/**
 * Get all user IDs
 */
async function getAllUserIds() {
  const usersSnap = await db.collection('users').select().get();
  return usersSnap.docs.map(doc => doc.id);
}

/**
 * Main function
 */
async function main() {
  console.log('='.repeat(60));
  console.log('Exercise Usage Stats Backfill Script');
  console.log('='.repeat(60));
  console.log('Options:', JSON.stringify(options, null, 2));
  console.log('');

  const startTime = Date.now();
  let userIds = [];

  if (options.userId) {
    userIds = [options.userId];
  } else {
    console.log('Fetching all users...');
    userIds = await getAllUserIds();
    console.log(`Found ${userIds.length} users`);
  }

  const results = [];

  for (const userId of userIds) {
    try {
      const result = await processUser(userId);
      results.push(result);
    } catch (error) {
      console.error(`Error processing user ${userId}:`, error.message);
      results.push({ userId, error: error.message });
    }
  }

  // Summary
  const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
  const totalWorkouts = results.reduce((s, r) => s + (r.workouts || 0), 0);
  const totalStats = results.reduce((s, r) => s + (r.statsWritten || 0), 0);
  const totalErrors = results.filter(r => r.error).length;

  console.log('\n' + '='.repeat(60));
  console.log('Summary');
  console.log('='.repeat(60));
  console.log(`Users processed:     ${results.length}`);
  console.log(`Workouts scanned:    ${totalWorkouts}`);
  console.log(`Stats docs written:  ${totalStats}`);
  console.log(`Errors:              ${totalErrors}`);
  console.log(`Time elapsed:        ${elapsed}s`);

  if (options.dryRun) {
    console.log('\n[DRY RUN] No data was written.');
  }

  console.log('\nDone.');
  process.exit(totalErrors > 0 ? 1 : 0);
}

// Run
main().catch(error => {
  console.error('Fatal error:', error);
  process.exit(1);
});
