#!/usr/bin/env node

/**
 * Backfill Set Facts Script
 * 
 * Rebuilds set_facts and series collections from historical workouts.
 * Run this to populate the token-safe analytics data layer for existing users.
 * 
 * Usage:
 *   node scripts/backfill_set_facts.js [--user <userId>] [--dry-run] [--limit <n>]
 * 
 * Options:
 *   --user <userId>  Only backfill for a specific user
 *   --dry-run        Don't write, just log what would be written
 *   --limit <n>      Limit number of workouts processed per user
 *   --all-users      Process all users (required if --user not specified)
 */

const admin = require('firebase-admin');
const path = require('path');

// Initialize Firebase Admin
// Option 1: Use FIREBASE_SERVICE_ACCOUNT_PATH env var
// Option 2: Use default credentials (gcloud auth application-default login)
const serviceAccountPath = process.env.FIREBASE_SERVICE_ACCOUNT_PATH;

try {
  if (serviceAccountPath) {
    const serviceAccount = require(serviceAccountPath);
    admin.initializeApp({
      credential: admin.credential.cert(serviceAccount),
    });
    console.log('Initialized with service account:', serviceAccountPath);
  } else {
    // Use default credentials (gcloud auth)
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

// Import set facts generator
const {
  generateSetFactsForWorkout,
  writeSetFactsInChunks,
  updateSeriesForWorkout,
} = require('../firebase_functions/functions/training/set-facts-generator');
const { CAPS } = require('../firebase_functions/functions/utils/caps');

// Parse command line arguments
const args = process.argv.slice(2);
const options = {
  userId: null,
  dryRun: false,
  limit: null,
  allUsers: false,
  rebuildSeries: false,
  deleteOldSeries: false,
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
  } else if (args[i] === '--rebuild-series') {
    options.rebuildSeries = true;
  } else if (args[i] === '--delete-old-series') {
    options.deleteOldSeries = true;
  }
}

// Validate arguments
if (!options.userId && !options.allUsers) {
  console.error('Error: Must specify --user <userId> or --all-users');
  process.exit(1);
}

/**
 * Process a single workout
 */
async function processWorkout(userId, workoutDoc, options) {
  const workout = workoutDoc.data();
  const workoutId = workoutDoc.id;
  
  // Skip incomplete workouts
  if (!workout.end_time || !workout.exercises || workout.exercises.length === 0) {
    return { skipped: true, reason: 'incomplete' };
  }
  
  const workoutWithId = { ...workout, id: workoutId };
  
  try {
    // Generate set facts
    const setFacts = generateSetFactsForWorkout({
      userId,
      workout: workoutWithId,
    });
    
    if (setFacts.length === 0) {
      return { skipped: true, reason: 'no_sets' };
    }
    
    // Replace FieldValue.serverTimestamp() with actual Date for backfill
    const now = new Date();
    for (const sf of setFacts) {
      sf.created_at = now;
      sf.updated_at = now;
    }
    
    if (options.dryRun) {
      console.log(`  [DRY RUN] Would write ${setFacts.length} set_facts for workout ${workoutId}`);
      return { written: setFacts.length, dryRun: true };
    }
    
    // Write set facts
    await writeSetFactsInChunks(db, userId, setFacts);
    
    // NOTE: Series updates skipped for backfill - use FieldValue.increment which 
    // doesn't work in local scripts. Series will be built via:
    // 1. Workout completion triggers going forward
    // 2. A separate nightly compaction job if needed
    
    console.log(`  Wrote ${setFacts.length} set_facts for workout ${workoutId}`);
    return { written: setFacts.length };
    
  } catch (error) {
    console.error(`  Error processing workout ${workoutId}:`, error.message);
    return { error: error.message };
  }
}

/**
 * Delete all series documents for a user (to remove case-duplicates)
 */
async function deleteSeriesForUser(userId, options) {
  console.log(`  Deleting old series for user ${userId}...`);
  
  const collections = ['series_exercises', 'series_muscle_groups', 'series_muscles'];
  let totalDeleted = 0;
  
  for (const collName of collections) {
    const collRef = db.collection('users').doc(userId).collection(collName);
    const snap = await collRef.get();
    
    if (snap.empty) continue;
    
    if (options.dryRun) {
      console.log(`    [DRY RUN] Would delete ${snap.size} docs from ${collName}`);
      continue;
    }
    
    // Delete in batches
    const batchSize = 500;
    const docs = snap.docs;
    
    for (let i = 0; i < docs.length; i += batchSize) {
      const batch = db.batch();
      const chunk = docs.slice(i, i + batchSize);
      
      for (const doc of chunk) {
        batch.delete(doc.ref);
      }
      
      await batch.commit();
    }
    
    console.log(`    Deleted ${snap.size} docs from ${collName}`);
    totalDeleted += snap.size;
  }
  
  return totalDeleted;
}

/**
 * Rebuild series from set_facts for a user
 */
async function rebuildSeriesForUser(userId, options) {
  console.log(`  Rebuilding series from set_facts for user ${userId}...`);
  
  // Read all set_facts for this user
  const setFactsSnap = await db.collection('users').doc(userId)
    .collection('set_facts')
    .get();
  
  if (setFactsSnap.empty) {
    console.log(`    No set_facts found`);
    return { exercises: 0, muscleGroups: 0, muscles: 0 };
  }
  
  console.log(`    Found ${setFactsSnap.size} set_facts`);
  
  // Aggregate into series
  const exerciseSeries = new Map(); // exerciseId -> { weeks: { weekId: {...} }, exercise_name }
  const muscleGroupSeries = new Map(); // group -> { weeks: { weekId: {...} } }
  const muscleSeries = new Map(); // muscle -> { weeks: { weekId: {...} } }
  
  for (const doc of setFactsSnap.docs) {
    const sf = doc.data();
    
    // Skip warmups
    if (sf.is_warmup) continue;
    
    const weekId = sf.workout_date.substring(0, 10); // YYYY-MM-DD - need to get week start
    // Actually use the workout_date as-is for grouping, we'll compute proper week below
    const workoutDate = sf.workout_date || (sf.workout_end_time?.toDate?.()?.toISOString?.().substring(0, 10));
    
    if (!workoutDate) continue;
    
    // Get week start (Monday)
    const date = new Date(workoutDate);
    const day = date.getDay();
    const diff = date.getDate() - day + (day === 0 ? -6 : 1);
    const weekStart = new Date(date.setDate(diff)).toISOString().substring(0, 10);
    
    // Determine reps bucket
    let repsBucket;
    if (sf.reps <= 5) repsBucket = '1-5';
    else if (sf.reps <= 10) repsBucket = '6-10';
    else if (sf.reps <= 15) repsBucket = '11-15';
    else repsBucket = '16-20';
    
    // Aggregate to exercise series
    if (!exerciseSeries.has(sf.exercise_id)) {
      exerciseSeries.set(sf.exercise_id, { weeks: {}, exercise_name: sf.exercise_name });
    }
    const exSeries = exerciseSeries.get(sf.exercise_id);
    if (!exSeries.weeks[weekStart]) {
      exSeries.weeks[weekStart] = {
        sets: 0, hard_sets: 0, volume: 0,
        rir_sum: 0, rir_count: 0,
        rir_min: null, rir_max: null,
        load_min: null, load_max: null,
        failure_sets: 0, set_count: 0,
        e1rm_max: null,
        reps_bucket: { '1-5': 0, '6-10': 0, '11-15': 0, '16-20': 0 },
      };
    }
    const exWeek = exSeries.weeks[weekStart];
    exWeek.sets += 1;
    exWeek.hard_sets += sf.hard_set_credit || 0;
    exWeek.volume += sf.volume || 0;
    if (sf.rir !== null && sf.rir !== undefined) {
      exWeek.rir_sum += sf.rir;
      exWeek.rir_count += 1;
      if (exWeek.rir_min === null || sf.rir < exWeek.rir_min) exWeek.rir_min = sf.rir;
      if (exWeek.rir_max === null || sf.rir > exWeek.rir_max) exWeek.rir_max = sf.rir;
    }
    if (sf.weight_kg > 0) {
      if (exWeek.load_min === null || sf.weight_kg < exWeek.load_min) exWeek.load_min = sf.weight_kg;
      if (exWeek.load_max === null || sf.weight_kg > exWeek.load_max) exWeek.load_max = sf.weight_kg;
    }
    if (sf.is_failure) exWeek.failure_sets += 1;
    exWeek.set_count += 1;
    if (sf.e1rm !== null && (exWeek.e1rm_max === null || sf.e1rm > exWeek.e1rm_max)) {
      exWeek.e1rm_max = sf.e1rm;
    }
    exWeek.reps_bucket[repsBucket] = (exWeek.reps_bucket[repsBucket] || 0) + 1;
    
    // Aggregate to muscle group series
    for (const [group, contrib] of Object.entries(sf.muscle_group_contrib || {})) {
      if (!muscleGroupSeries.has(group)) {
        muscleGroupSeries.set(group, { weeks: {} });
      }
      const mgSeries = muscleGroupSeries.get(group);
      if (!mgSeries.weeks[weekStart]) {
        mgSeries.weeks[weekStart] = {
          sets: 0, hard_sets: 0, volume: 0, effective_volume: 0,
          rir_sum: 0, rir_count: 0,
          rir_min: null, rir_max: null,
          load_min: null, load_max: null,
          failure_sets: 0, set_count: 0,
          reps_bucket: { '1-5': 0, '6-10': 0, '11-15': 0, '16-20': 0 },
        };
      }
      const mgWeek = mgSeries.weeks[weekStart];
      mgWeek.sets += 1;
      mgWeek.hard_sets += (sf.hard_set_credit || 0) * contrib;
      mgWeek.volume += (sf.volume || 0) * contrib;
      mgWeek.effective_volume += (sf.volume || 0) * contrib;
      if (sf.rir !== null && sf.rir !== undefined) {
        mgWeek.rir_sum += sf.rir * contrib;
        mgWeek.rir_count += 1;
        if (mgWeek.rir_min === null || sf.rir < mgWeek.rir_min) mgWeek.rir_min = sf.rir;
        if (mgWeek.rir_max === null || sf.rir > mgWeek.rir_max) mgWeek.rir_max = sf.rir;
      }
      if (sf.weight_kg > 0) {
        if (mgWeek.load_min === null || sf.weight_kg < mgWeek.load_min) mgWeek.load_min = sf.weight_kg;
        if (mgWeek.load_max === null || sf.weight_kg > mgWeek.load_max) mgWeek.load_max = sf.weight_kg;
      }
      if (sf.is_failure) mgWeek.failure_sets += 1;
      mgWeek.set_count += 1;
      mgWeek.reps_bucket[repsBucket] = (mgWeek.reps_bucket[repsBucket] || 0) + 1;
    }
    
    // Aggregate to muscle series
    for (const [muscle, contrib] of Object.entries(sf.muscle_contrib || {})) {
      if (!muscleSeries.has(muscle)) {
        muscleSeries.set(muscle, { weeks: {} });
      }
      const mSeries = muscleSeries.get(muscle);
      if (!mSeries.weeks[weekStart]) {
        mSeries.weeks[weekStart] = {
          sets: 0, hard_sets: 0, volume: 0, effective_volume: 0,
          rir_sum: 0, rir_count: 0,
          rir_min: null, rir_max: null,
          load_min: null, load_max: null,
          failure_sets: 0, set_count: 0,
          reps_bucket: { '1-5': 0, '6-10': 0, '11-15': 0, '16-20': 0 },
        };
      }
      const mWeek = mSeries.weeks[weekStart];
      mWeek.sets += 1;
      mWeek.hard_sets += (sf.hard_set_credit || 0) * contrib;
      mWeek.volume += (sf.volume || 0) * contrib;
      mWeek.effective_volume += (sf.volume || 0) * contrib;
      if (sf.rir !== null && sf.rir !== undefined) {
        mWeek.rir_sum += sf.rir * contrib;
        mWeek.rir_count += 1;
        if (mWeek.rir_min === null || sf.rir < mWeek.rir_min) mWeek.rir_min = sf.rir;
        if (mWeek.rir_max === null || sf.rir > mWeek.rir_max) mWeek.rir_max = sf.rir;
      }
      if (sf.weight_kg > 0) {
        if (mWeek.load_min === null || sf.weight_kg < mWeek.load_min) mWeek.load_min = sf.weight_kg;
        if (mWeek.load_max === null || sf.weight_kg > mWeek.load_max) mWeek.load_max = sf.weight_kg;
      }
      if (sf.is_failure) mWeek.failure_sets += 1;
      mWeek.set_count += 1;
      mWeek.reps_bucket[repsBucket] = (mWeek.reps_bucket[repsBucket] || 0) + 1;
    }
  }
  
  // Write series documents
  if (options.dryRun) {
    console.log(`    [DRY RUN] Would write ${exerciseSeries.size} exercise series, ${muscleGroupSeries.size} muscle group series, ${muscleSeries.size} muscle series`);
    return { exercises: exerciseSeries.size, muscleGroups: muscleGroupSeries.size, muscles: muscleSeries.size };
  }
  
  const now = new Date();
  
  // Write exercise series
  for (const [exerciseId, data] of exerciseSeries) {
    const ref = db.collection('users').doc(userId).collection('series_exercises').doc(exerciseId);
    await ref.set({
      weeks: data.weeks,
      exercise_name: data.exercise_name,
      updated_at: now,
    }, { merge: false }); // Overwrite entirely
  }
  
  // Write muscle group series
  for (const [group, data] of muscleGroupSeries) {
    const ref = db.collection('users').doc(userId).collection('series_muscle_groups').doc(group);
    await ref.set({
      weeks: data.weeks,
      updated_at: now,
    }, { merge: false });
  }
  
  // Write muscle series
  for (const [muscle, data] of muscleSeries) {
    const ref = db.collection('users').doc(userId).collection('series_muscles').doc(muscle);
    await ref.set({
      weeks: data.weeks,
      updated_at: now,
    }, { merge: false });
  }
  
  console.log(`    Wrote ${exerciseSeries.size} exercise series, ${muscleGroupSeries.size} muscle group series, ${muscleSeries.size} muscle series`);
  
  return { exercises: exerciseSeries.size, muscleGroups: muscleGroupSeries.size, muscles: muscleSeries.size };
}

/**
 * Process all workouts for a user
 */
async function processUser(userId, options) {
  console.log(`\nProcessing user: ${userId}`);
  
  let query = db.collection('users').doc(userId).collection('workouts')
    .orderBy('end_time', 'desc');
  
  if (options.limit) {
    query = query.limit(options.limit);
  }
  
  const workoutsSnap = await query.get();
  console.log(`  Found ${workoutsSnap.size} workouts`);
  
  if (workoutsSnap.empty) {
    return { userId, workouts: 0, setFacts: 0, skipped: 0, errors: 0 };
  }
  
  let totalSetFacts = 0;
  let skipped = 0;
  let errors = 0;
  
  for (const workoutDoc of workoutsSnap.docs) {
    const result = await processWorkout(userId, workoutDoc, options);
    
    if (result.skipped) {
      skipped++;
    } else if (result.error) {
      errors++;
    } else if (result.written) {
      totalSetFacts += result.written;
    }
  }
  
  console.log(`  User ${userId} complete: ${totalSetFacts} set_facts, ${skipped} skipped, ${errors} errors`);
  
  // Optionally rebuild series
  let seriesStats = null;
  if (options.rebuildSeries) {
    // First delete old series if requested
    if (options.deleteOldSeries) {
      await deleteSeriesForUser(userId, options);
    }
    seriesStats = await rebuildSeriesForUser(userId, options);
  }
  
  return { userId, workouts: workoutsSnap.size, setFacts: totalSetFacts, skipped, errors, seriesStats };
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
  console.log('Set Facts Backfill Script');
  console.log('='.repeat(60));
  console.log(`Options:`, JSON.stringify(options, null, 2));
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
      const result = await processUser(userId, options);
      results.push(result);
    } catch (error) {
      console.error(`Error processing user ${userId}:`, error.message);
      results.push({ userId, error: error.message });
    }
  }
  
  // Summary
  const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
  const totalWorkouts = results.reduce((s, r) => s + (r.workouts || 0), 0);
  const totalSetFacts = results.reduce((s, r) => s + (r.setFacts || 0), 0);
  const totalSkipped = results.reduce((s, r) => s + (r.skipped || 0), 0);
  const totalErrors = results.reduce((s, r) => s + (r.errors || 0) + (r.error ? 1 : 0), 0);
  
  // Series stats
  let totalExerciseSeries = 0;
  let totalMuscleGroupSeries = 0;
  let totalMuscleSeries = 0;
  
  for (const r of results) {
    if (r.seriesStats) {
      totalExerciseSeries += r.seriesStats.exercises || 0;
      totalMuscleGroupSeries += r.seriesStats.muscleGroups || 0;
      totalMuscleSeries += r.seriesStats.muscles || 0;
    }
  }
  
  console.log('\n' + '='.repeat(60));
  console.log('Summary');
  console.log('='.repeat(60));
  console.log(`Users processed:    ${results.length}`);
  console.log(`Workouts processed: ${totalWorkouts}`);
  console.log(`Set facts written:  ${totalSetFacts}`);
  console.log(`Skipped:            ${totalSkipped}`);
  console.log(`Errors:             ${totalErrors}`);
  
  if (options.rebuildSeries) {
    console.log(`Exercise series:    ${totalExerciseSeries}`);
    console.log(`Muscle group series: ${totalMuscleGroupSeries}`);
    console.log(`Muscle series:      ${totalMuscleSeries}`);
  }
  
  console.log(`Time elapsed:       ${elapsed}s`);
  
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
