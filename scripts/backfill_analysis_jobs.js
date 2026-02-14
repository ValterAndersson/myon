#!/usr/bin/env node

/**
 * Backfill Training Analysis Jobs
 *
 * Enqueues POST_WORKOUT, WEEKLY_REVIEW, and DAILY_BRIEF jobs for historical data.
 * Run after backfill_set_facts.js to generate AI-powered summaries.
 *
 * Idempotent: uses deterministic job IDs so re-runs overwrite existing jobs
 * rather than creating duplicates.
 *
 * Usage:
 *   node scripts/backfill_analysis_jobs.js --user <userId> [--months <n>] [--dry-run]
 *   node scripts/backfill_analysis_jobs.js --all-users [--months <n>] [--dry-run]
 *
 * Options:
 *   --user <userId>   Backfill for a specific user
 *   --all-users       Backfill for all users with recent workouts
 *   --months <n>      How many months back to backfill (default: 3)
 *   --dry-run         Don't write, just log what would be created
 *   --skip-workouts   Skip POST_WORKOUT jobs
 *   --skip-weekly     Skip WEEKLY_REVIEW jobs
 *   --skip-daily      Skip DAILY_BRIEF job
 */

const admin = require('firebase-admin');
const crypto = require('crypto');

// Initialize Firebase Admin
const serviceAccountPath = process.env.FIREBASE_SERVICE_ACCOUNT_PATH;

try {
  if (serviceAccountPath) {
    const serviceAccount = require(serviceAccountPath);
    admin.initializeApp({
      credential: admin.credential.cert(serviceAccount),
    });
    console.log('Initialized with service account:', serviceAccountPath);
  } else {
    admin.initializeApp({ projectId: 'myon-53d85' });
    console.log('Initialized with default credentials');
  }
} catch (e) {
  if (!e.message.includes('already exists')) throw e;
}

const db = admin.firestore();

// Parse CLI args
const args = process.argv.slice(2);
const options = {
  userId: null,
  allUsers: false,
  months: 3,
  dryRun: false,
  skipWorkouts: false,
  skipWeekly: false,
  skipDaily: false,
};

for (let i = 0; i < args.length; i++) {
  if (args[i] === '--user' && args[i + 1]) {
    options.userId = args[i + 1];
    i++;
  } else if (args[i] === '--all-users') {
    options.allUsers = true;
  } else if (args[i] === '--months' && args[i + 1]) {
    options.months = parseInt(args[i + 1], 10);
    i++;
  } else if (args[i] === '--dry-run') {
    options.dryRun = true;
  } else if (args[i] === '--skip-workouts') {
    options.skipWorkouts = true;
  } else if (args[i] === '--skip-weekly') {
    options.skipWeekly = true;
  } else if (args[i] === '--skip-daily') {
    options.skipDaily = true;
  }
}

if (!options.userId && !options.allUsers) {
  console.error('Error: Must specify --user <userId> or --all-users');
  process.exit(1);
}

/**
 * Generate a deterministic job ID for idempotency.
 * Re-running the script overwrites existing jobs instead of creating duplicates.
 */
function deterministicJobId(prefix, ...parts) {
  const hash = crypto.createHash('sha256').update(parts.join('|')).digest('hex').slice(0, 12);
  return `bf-${prefix}-${hash}`;
}

/**
 * Build a job document matching the schema used by both the trigger
 * (weekly-analytics.js) and the Python queue (queue.py).
 */
function buildJobDoc(jobId, jobType, payload) {
  const now = admin.firestore.FieldValue.serverTimestamp();
  return {
    id: jobId,
    type: jobType,
    status: 'queued',
    payload,
    attempts: 0,
    max_attempts: 3,
    created_at: now,
    updated_at: now,
  };
}

/**
 * Get all Sundays (UTC) in the last N months for WEEKLY_REVIEW jobs.
 */
function getSundaysInRange(months) {
  const sundays = [];
  const now = new Date();
  const cutoff = new Date(Date.UTC(
    now.getUTCFullYear(), now.getUTCMonth() - months, now.getUTCDate()
  ));

  // Find the most recent Sunday in UTC
  const current = new Date(Date.UTC(
    now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()
  ));
  current.setUTCDate(current.getUTCDate() - current.getUTCDay());

  while (current >= cutoff) {
    sundays.push(new Date(current));
    current.setUTCDate(current.getUTCDate() - 7);
  }

  return sundays;
}

/**
 * Format a UTC date as YYYY-MM-DD.
 */
function formatDateUTC(date) {
  return date.toISOString().slice(0, 10);
}

/**
 * Process a single user's backfill.
 */
async function processUser(userId, cutoff) {
  console.log(`\nProcessing user: ${userId}`);

  let postWorkoutCount = 0;
  let weeklyReviewCount = 0;
  let dailyBriefCount = 0;

  // 1. POST_WORKOUT jobs for workouts in the window
  if (!options.skipWorkouts) {
    const snapshot = await db.collection('users').doc(userId)
      .collection('workouts')
      .where('end_time', '>=', cutoff)
      .orderBy('end_time', 'desc')
      .get();

    console.log(`  Found ${snapshot.size} workouts since ${formatDateUTC(cutoff)}`);

    let batch = db.batch();
    let batchCount = 0;

    for (const doc of snapshot.docs) {
      const workoutId = doc.id;
      const data = doc.data();

      // Skip incomplete workouts (matching backfill_set_facts.js)
      if (!data.end_time || !data.exercises || data.exercises.length === 0) {
        continue;
      }

      const endTime = data.end_time?.toDate?.() || data.end_time;
      const dateStr = endTime ? formatDateUTC(new Date(endTime)) : 'unknown';

      const jobId = deterministicJobId('pw', userId, workoutId);

      if (options.dryRun) {
        console.log(`  [DRY RUN] POST_WORKOUT: ${workoutId} (${dateStr})`);
      } else {
        const ref = db.collection('training_analysis_jobs').doc(jobId);
        batch.set(ref, buildJobDoc(jobId, 'POST_WORKOUT', {
          user_id: userId,
          workout_id: workoutId,
        }));
        batchCount++;

        if (batchCount >= 400) {
          await batch.commit();
          console.log(`  Committed batch of ${batchCount} POST_WORKOUT jobs`);
          batch = db.batch();
          batchCount = 0;
        }
      }

      postWorkoutCount++;
    }

    if (!options.dryRun && batchCount > 0) {
      await batch.commit();
      console.log(`  Committed batch of ${batchCount} POST_WORKOUT jobs`);
    }

    console.log(`  Created ${postWorkoutCount} POST_WORKOUT jobs`);
  }

  // 2. WEEKLY_REVIEW jobs for each Sunday in the window
  if (!options.skipWeekly) {
    const sundays = getSundaysInRange(options.months);
    console.log(`  Creating WEEKLY_REVIEW jobs for ${sundays.length} weeks...`);

    let batch = db.batch();
    let batchCount = 0;

    for (const sunday of sundays) {
      const weekEnding = formatDateUTC(sunday);
      const jobId = deterministicJobId('wr', userId, weekEnding);

      if (options.dryRun) {
        console.log(`  [DRY RUN] WEEKLY_REVIEW: week ending ${weekEnding}`);
      } else {
        const ref = db.collection('training_analysis_jobs').doc(jobId);
        batch.set(ref, buildJobDoc(jobId, 'WEEKLY_REVIEW', {
          user_id: userId,
          window_weeks: 12,
          week_ending: weekEnding,
        }));
        batchCount++;
      }

      weeklyReviewCount++;
    }

    if (!options.dryRun && batchCount > 0) {
      await batch.commit();
      console.log(`  Committed batch of ${batchCount} WEEKLY_REVIEW jobs`);
    }

    console.log(`  Created ${weeklyReviewCount} WEEKLY_REVIEW jobs`);
  }

  // 3. DAILY_BRIEF job for today
  if (!options.skipDaily) {
    const today = formatDateUTC(new Date());
    const jobId = deterministicJobId('db', userId, today);

    if (options.dryRun) {
      console.log(`  [DRY RUN] DAILY_BRIEF: ${today}`);
    } else {
      await db.collection('training_analysis_jobs').doc(jobId).set(
        buildJobDoc(jobId, 'DAILY_BRIEF', { user_id: userId })
      );
    }

    dailyBriefCount = 1;
    console.log(`  Created 1 DAILY_BRIEF job for ${today}`);
  }

  return { postWorkoutCount, weeklyReviewCount, dailyBriefCount };
}

async function main() {
  console.log('============================================================');
  console.log('Training Analysis Backfill');
  console.log('============================================================');
  console.log('Options:', JSON.stringify(options, null, 2));

  const cutoff = new Date();
  cutoff.setMonth(cutoff.getMonth() - options.months);

  let userIds = [];

  if (options.userId) {
    userIds = [options.userId];
  } else {
    // Find all users with recent workouts
    console.log('\nFinding users with recent workouts...');
    const usersSnap = await db.collection('users').get();

    for (const userDoc of usersSnap.docs) {
      const recent = await db.collection('users').doc(userDoc.id)
        .collection('workouts')
        .where('end_time', '>=', cutoff)
        .limit(1)
        .get();

      if (!recent.empty) {
        userIds.push(userDoc.id);
      }
    }

    console.log(`Found ${userIds.length} users with workouts in the last ${options.months} months`);
  }

  let totalPostWorkout = 0;
  let totalWeeklyReview = 0;
  let totalDailyBrief = 0;

  for (const userId of userIds) {
    const result = await processUser(userId, cutoff);
    totalPostWorkout += result.postWorkoutCount;
    totalWeeklyReview += result.weeklyReviewCount;
    totalDailyBrief += result.dailyBriefCount;
  }

  console.log('');
  console.log('============================================================');
  console.log('Summary');
  console.log('============================================================');
  console.log(`Users processed:    ${userIds.length}`);
  console.log(`POST_WORKOUT jobs:  ${totalPostWorkout}`);
  console.log(`WEEKLY_REVIEW jobs: ${totalWeeklyReview}`);
  console.log(`DAILY_BRIEF jobs:   ${totalDailyBrief}`);
  console.log(`Total jobs queued:  ${totalPostWorkout + totalWeeklyReview + totalDailyBrief}`);
  console.log('');
  console.log('Next step: run the worker to process these jobs:');
  console.log('  GOOGLE_APPLICATION_CREDENTIALS=$GCP_SA_KEY \\');
  console.log('  PYTHONPATH=adk_agent/training_analyst \\');
  console.log('  python3 adk_agent/training_analyst/workers/analyst_worker.py');
}

main().catch((err) => {
  console.error('Fatal error:', err);
  process.exit(1);
});
