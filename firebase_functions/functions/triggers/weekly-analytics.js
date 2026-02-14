const { onDocumentCreated, onDocumentUpdated, onDocumentDeleted } = require('firebase-functions/v2/firestore');
const { onSchedule } = require('firebase-functions/v2/scheduler');
const { onCall } = require('firebase-functions/v2/https');
const admin = require('firebase-admin');

if (!admin.apps.length) {
  admin.initializeApp();
}

const db = admin.firestore();
const AnalyticsWrites = require('../utils/analytics-writes');

// Token-safe Training Analytics imports
const {
  generateSetFactsForWorkout,
  writeSetFactsInChunks,
  updateSeriesForWorkout,
} = require('../training/set-facts-generator');
const { CAPS } = require('../utils/caps');

// Helper function to get week start for a date with Sunday as default
function getWeekStartSunday(dateString) {
  const date = new Date(dateString);
  const day = date.getUTCDay();
  // Sunday = 0, so no adjustment needed for Sunday start
  const diff = day;
  date.setUTCDate(date.getUTCDate() - diff);
  date.setUTCHours(0, 0, 0, 0);
  return date.toISOString().split('T')[0];
}

// Helper function to get week start for a date with Monday as start
function getWeekStartMonday(dateString) {
  const date = new Date(dateString);
  const day = date.getUTCDay();
  // Monday = 1, Sunday = 0, so we need to adjust
  const diff = day === 0 ? 6 : day - 1; // If Sunday, go back 6 days, otherwise go back (day-1) days
  date.setUTCDate(date.getUTCDate() - diff);
  date.setUTCHours(0, 0, 0, 0);
  return date.toISOString().split('T')[0];
}

// Get week start based on user preference
async function getWeekStartForUser(userId, dateString) {
  try {
    const userDoc = await db.collection('users').doc(userId).get();
    if (userDoc.exists) {
      const userData = userDoc.data();
      const weekStartsOnMonday = userData.week_starts_on_monday !== undefined ? userData.week_starts_on_monday : true;
      
      return weekStartsOnMonday ? getWeekStartMonday(dateString) : getWeekStartSunday(dateString);
    }
  } catch (error) {
    console.warn(`Error fetching user preferences for ${userId}, defaulting to Monday start:`, error);
  }
  
  // Default to Monday if user preferences can't be fetched
  return getWeekStartMonday(dateString);
}

function mergeMetrics(target = {}, source = {}, increment = 1) {
  if (!source || typeof source !== 'object') return;
  
  for (const [key, value] of Object.entries(source)) {
    if (typeof value !== 'number') continue;
    const current = target[key] || 0;
    const updated = current + value * increment;
    if (updated === 0) {
      delete target[key];
    } else {
      target[key] = updated;
    }
  }
}

// Simple e1RM estimator (Epley by default)
function estimateE1RM(weightKg, reps) {
  if (typeof weightKg !== 'number' || typeof reps !== 'number' || reps <= 0) return 0;
  if (reps === 1) return weightKg;
  return weightKg * (1 + reps / 30);
}

function validateAnalytics(analytics) {
  if (!analytics || typeof analytics !== 'object') {
    return { isValid: false, error: 'Analytics object is missing or invalid' };
  }

  const requiredNumericFields = ['total_sets', 'total_reps', 'total_weight'];
  for (const field of requiredNumericFields) {
    if (typeof analytics[field] !== 'number') {
      return { isValid: false, error: `Analytics missing or invalid field: ${field}` };
    }
  }

  return { isValid: true };
}

async function updateWeeklyStats(userId, weekId, analytics, increment = 1, retries = 3) {
  const validation = validateAnalytics(analytics);
  if (!validation.isValid) {
    console.warn(`Invalid analytics for user ${userId}, week ${weekId}: ${validation.error}`);
    return { success: false, error: validation.error };
  }

  const ref = db
    .collection('users')
    .doc(userId)
    .collection('weekly_stats')
    .doc(weekId);

  for (let attempt = 1; attempt <= retries; attempt++) {
    try {
      await db.runTransaction(async (tx) => {
        const snap = await tx.get(ref);
        const data = snap.exists
          ? snap.data()
          : {
              workouts: 0,
              total_sets: 0,
              total_reps: 0,
              total_weight: 0,
              weight_per_muscle_group: {},
              weight_per_muscle: {},
              reps_per_muscle_group: {},
              reps_per_muscle: {},
              sets_per_muscle_group: {},
              sets_per_muscle: {},
              hard_sets_total: 0,
              low_rir_sets_total: 0,
              hard_sets_per_muscle: {},
              low_rir_sets_per_muscle: {},
              load_per_muscle: {},
            };

        data.workouts += increment;
        data.total_sets += analytics.total_sets * increment;
        data.total_reps += analytics.total_reps * increment;
        data.total_weight += analytics.total_weight * increment;

        mergeMetrics(data.weight_per_muscle_group, analytics.weight_per_muscle_group, increment);
        mergeMetrics(data.weight_per_muscle, analytics.weight_per_muscle, increment);
        mergeMetrics(data.reps_per_muscle_group, analytics.reps_per_muscle_group, increment);
        mergeMetrics(data.reps_per_muscle, analytics.reps_per_muscle, increment);
        mergeMetrics(data.sets_per_muscle_group, analytics.sets_per_muscle_group, increment);
        mergeMetrics(data.sets_per_muscle, analytics.sets_per_muscle, increment);
        if (analytics.intensity) {
          const intensity = analytics.intensity;
          data.hard_sets_total += (intensity.hard_sets || 0) * increment;
          data.low_rir_sets_total += (intensity.low_rir_sets || 0) * increment;
          mergeMetrics(data.hard_sets_per_muscle, intensity.hard_sets_per_muscle, increment);
          mergeMetrics(data.low_rir_sets_per_muscle, intensity.low_rir_sets_per_muscle, increment);
          mergeMetrics(data.load_per_muscle, intensity.load_per_muscle, increment);
        }

        data.updated_at = admin.firestore.FieldValue.serverTimestamp();
        tx.set(ref, data, { merge: true });
      });

      return { success: true, weekId, attempt };
    } catch (error) {
      console.warn(`Transaction attempt ${attempt} failed for user ${userId}, week ${weekId}:`, error.message);
      
      if (attempt === retries) {
        console.error(`All ${retries} attempts failed for user ${userId}, week ${weekId}:`, error);
        return { success: false, error: error.message, finalAttempt: true };
      }
      
      // Exponential backoff: wait 2^attempt * 100ms
      await new Promise(resolve => setTimeout(resolve, Math.pow(2, attempt) * 100));
    }
  }
}

/**
 * Periodic function to recalculate weekly stats for data consistency
 * Runs daily to catch any missed updates or resolve inconsistencies
 */
async function recalculateWeeklyStats(userId, weekId, weekStartsOnMonday = null) {
  try {
    // Get all completed workouts for this week
    const weekStart = new Date(weekId + 'T00:00:00.000Z');
    const weekEnd = new Date(weekStart);
    weekEnd.setDate(weekEnd.getDate() + 7);
    
    // Convert to Firestore Timestamps for the query
    const weekStartTimestamp = admin.firestore.Timestamp.fromDate(weekStart);
    const weekEndTimestamp = admin.firestore.Timestamp.fromDate(weekEnd);
    
    const workoutsSnap = await db
      .collection('users')
      .doc(userId)
      .collection('workouts')
      .where('end_time', '>=', weekStartTimestamp)
      .where('end_time', '<', weekEndTimestamp)
      .get();

    // Calculate fresh weekly stats
    const freshStats = {
      workouts: 0,
      total_sets: 0,
      total_reps: 0,
      total_weight: 0,
      weight_per_muscle_group: {},
      weight_per_muscle: {},
      reps_per_muscle_group: {},
      reps_per_muscle: {},
      sets_per_muscle_group: {},
      sets_per_muscle: {},
      hard_sets_total: 0,
      low_rir_sets_total: 0,
      hard_sets_per_muscle: {},
      low_rir_sets_per_muscle: {},
      load_per_muscle: {},
    };

    workoutsSnap.docs.forEach(doc => {
      const workout = doc.data();
      
      if (!workout.analytics) {
        console.warn(`Workout ${doc.id} missing analytics during recalculation`);
        return;
      }

      const validation = validateAnalytics(workout.analytics);
      if (!validation.isValid) {
        console.warn(`Invalid analytics for workout ${doc.id}: ${validation.error}`);
        return;
      }

      freshStats.workouts += 1;
      freshStats.total_sets += workout.analytics.total_sets;
      freshStats.total_reps += workout.analytics.total_reps;
      freshStats.total_weight += workout.analytics.total_weight;

      mergeMetrics(freshStats.weight_per_muscle_group, workout.analytics.weight_per_muscle_group, 1);
      mergeMetrics(freshStats.weight_per_muscle, workout.analytics.weight_per_muscle, 1);
      mergeMetrics(freshStats.reps_per_muscle_group, workout.analytics.reps_per_muscle_group, 1);
      mergeMetrics(freshStats.reps_per_muscle, workout.analytics.reps_per_muscle, 1);
      mergeMetrics(freshStats.sets_per_muscle_group, workout.analytics.sets_per_muscle_group, 1);
      mergeMetrics(freshStats.sets_per_muscle, workout.analytics.sets_per_muscle, 1);
      if (workout.analytics.intensity) {
        const intensity = workout.analytics.intensity;
        freshStats.hard_sets_total += intensity.hard_sets || 0;
        freshStats.low_rir_sets_total += intensity.low_rir_sets || 0;
        mergeMetrics(freshStats.hard_sets_per_muscle, intensity.hard_sets_per_muscle, 1);
        mergeMetrics(freshStats.low_rir_sets_per_muscle, intensity.low_rir_sets_per_muscle, 1);
        mergeMetrics(freshStats.load_per_muscle, intensity.load_per_muscle, 1);
      }
    });

    // Update the weekly stats document
    const ref = db
      .collection('users')
      .doc(userId)
      .collection('weekly_stats')
      .doc(weekId);

    freshStats.updated_at = admin.firestore.FieldValue.serverTimestamp();
    freshStats.recalculated_at = admin.firestore.FieldValue.serverTimestamp();
    
    await ref.set(freshStats, { merge: true });
    
    return { success: true, userId, weekId, workoutCount: freshStats.workouts };
  } catch (error) {
    console.error(`Error recalculating weekly stats for user ${userId}, week ${weekId}:`, error);
    return { success: false, error: error.message, userId, weekId };
  }
}

/**
 * Cloud Scheduler function to run periodic recalculations
 * Runs daily at 2 AM UTC to recalculate stats for active users
 */
exports.weeklyStatsRecalculation = onSchedule({
  schedule: '0 2 * * *', // Daily at 2 AM UTC
  timeZone: 'UTC',
  retryConfig: {
    retryCount: 3,
    maxRetryDuration: '600s'
  }
}, async (event) => {
  try {
    // Get current week and last week IDs
    const now = new Date();
    const currentWeekId = await getWeekStartForUser(null, now.toISOString());
    const lastWeek = new Date(now);
    lastWeek.setDate(lastWeek.getDate() - 7);
    const lastWeekId = await getWeekStartForUser(null, lastWeek.toISOString());
    
    // Find users who have completed workouts in the last 2 weeks
    const twoWeeksAgo = new Date(now);
    twoWeeksAgo.setDate(twoWeeksAgo.getDate() - 14);
    const twoWeeksAgoTimestamp = admin.firestore.Timestamp.fromDate(twoWeeksAgo);
    
    const usersSnap = await db.collectionGroup('workouts')
      .where('end_time', '>=', twoWeeksAgoTimestamp)
      .select('end_time') // Only get minimal data
      .get();

    const activeUserIds = [...new Set(usersSnap.docs.map(doc => doc.ref.parent.parent.id))];

    const results = [];
    
    // Process users in batches to avoid overwhelming the system
    const batchSize = 10;
    for (let i = 0; i < activeUserIds.length; i += batchSize) {
      const batch = activeUserIds.slice(i, i + batchSize);
      const batchPromises = [];
      
      for (const userId of batch) {
        // Get user-specific week IDs based on their preference
        const userCurrentWeekId = await getWeekStartForUser(userId, now.toISOString());
        const userLastWeek = new Date(now);
        userLastWeek.setDate(userLastWeek.getDate() - 7);
        const userLastWeekId = await getWeekStartForUser(userId, userLastWeek.toISOString());
        
        batchPromises.push(
          recalculateWeeklyStats(userId, userCurrentWeekId),
          recalculateWeeklyStats(userId, userLastWeekId)
        );
      }
      
      const batchResults = await Promise.allSettled(batchPromises);
      results.push(...batchResults);
      
      // Small delay between batch to avoid rate limits
      if (i + batchSize < activeUserIds.length) {
        await new Promise(resolve => setTimeout(resolve, 1000));
      }
    }

    const successful = results.filter(r => r.status === 'fulfilled' && r.value.success).length;
    const failed = results.length - successful;
    
    return {
      success: true,
      processed: results.length,
      successful,
      failed,
      activeUsers: activeUserIds.length
    };
  } catch (error) {
    console.error('Error in weekly stats recalculation job:', error);
    return { success: false, error: error.message };
  }
});

exports.onWorkoutCompleted = onDocumentUpdated(
  'users/{userId}/workouts/{workoutId}',
  async (event) => {
    try {
      const before = event.data.before.data();
      const after = event.data.after.data();
      
      // Only process if workout was just completed (end_time was added)
      if (!after || !after.end_time) return null;
      if (before && before.end_time === after.end_time) return null;

      const analytics = after.analytics;
      if (!analytics) {
        console.warn(`Workout ${event.params.workoutId} for user ${event.params.userId} missing analytics`);
        return null;
      }

      // Convert Firestore timestamp to ISO string for week calculation
      const endTime = after.end_time.toDate ? after.end_time.toDate().toISOString() : after.end_time;
      const weekId = await getWeekStartForUser(event.params.userId, endTime);
      const result = await updateWeeklyStats(event.params.userId, weekId, analytics, 1);

      // Also upsert rollups and per-muscle weekly series
      try {
        await AnalyticsWrites.upsertRollup(event.params.userId, weekId, {
          total_sets: analytics.total_sets,
          total_reps: analytics.total_reps,
          total_weight: analytics.total_weight,
          weight_per_muscle_group: analytics.weight_per_muscle_group || {},
          workouts: 1,
          hard_sets_total: analytics.intensity?.hard_sets || 0,
          low_rir_sets_total: analytics.intensity?.low_rir_sets || 0,
          hard_sets_per_muscle: analytics.intensity?.hard_sets_per_muscle || {},
          low_rir_sets_per_muscle: analytics.intensity?.low_rir_sets_per_muscle || {},
          load_per_muscle: analytics.intensity?.load_per_muscle || {},
        }, 1);

        const setsByGroup = analytics.sets_per_muscle_group || {};
        const volByGroup = analytics.weight_per_muscle_group || {};
        const hardSetsByMuscle = analytics.intensity?.hard_sets_per_muscle || {};
        const loadByMuscle = analytics.intensity?.load_per_muscle || {};
        const lowRirByMuscle = analytics.intensity?.low_rir_sets_per_muscle || {};
        const muscles = new Set([
          ...Object.keys(setsByGroup),
          ...Object.keys(volByGroup),
          ...Object.keys(hardSetsByMuscle),
          ...Object.keys(loadByMuscle),
          ...Object.keys(lowRirByMuscle),
        ]);
        const writes = [];
        for (const muscle of muscles) {
          writes.push(
            AnalyticsWrites.appendMuscleSeries(
              event.params.userId,
              muscle,
              weekId,
              {
                sets: setsByGroup[muscle] || 0,
                volume: volByGroup[muscle] || 0,
                hard_sets: hardSetsByMuscle[muscle] || 0,
                load: loadByMuscle[muscle] || 0,
                low_rir_sets: lowRirByMuscle[muscle] || 0,
              },
              1
            )
          );
        }
        if (writes.length) await Promise.allSettled(writes);
      } catch (e) {
        console.warn('Non-fatal: failed to write analytics series/rollups for workout update', e?.message || e);
      }

      // Update watermark
      try {
        await AnalyticsWrites.updateWatermark(event.params.userId, { last_processed_workout_at: endTime });
      } catch (e) {
        console.warn('Non-fatal: failed to update watermark', e?.message || e);
      }

      // Append per-exercise daily points (e1RM max, volume sum)
      try {
        const dayKey = endTime.split('T')[0];
        const exercises = Array.isArray(after.exercises) ? after.exercises : [];
        const perExercise = new Map();
        for (const ex of exercises) {
          const exId = ex.exercise_id;
          if (!exId || !Array.isArray(ex.sets)) continue;
          let maxE1 = 0; let vol = 0;
          for (const s of ex.sets) {
            if (!s.is_completed) continue;
            const reps = typeof s.reps === 'number' ? s.reps : 0;
            const w = typeof s.weight_kg === 'number' ? s.weight_kg : 0;
            if (reps > 0 && w > 0) {
              maxE1 = Math.max(maxE1, estimateE1RM(w, reps));
              vol += w * reps;
            }
          }
          const curr = perExercise.get(exId) || { e1rm: 0, vol: 0 };
          curr.e1rm = Math.max(curr.e1rm, maxE1);
          curr.vol += vol;
          perExercise.set(exId, curr);
        }
        const writes = [];
        for (const [exerciseId, point] of perExercise.entries()) {
          writes.push(AnalyticsWrites.appendExerciseSeries(event.params.userId, exerciseId, dayKey, point, 1));
        }
        if (writes.length) await Promise.allSettled(writes);
      } catch (e) {
        console.warn('Non-fatal: failed to write per-exercise daily series', e?.message || e);
      }

      // =============== TOKEN-SAFE ANALYTICS: set_facts + new series ===============
      // Skip if set_facts were already synced by upsertWorkout (within last 10 seconds)
      const setFactsSyncedAt = after.set_facts_synced_at;
      const syncedRecently = setFactsSyncedAt && 
        (Date.now() - (setFactsSyncedAt.toMillis ? setFactsSyncedAt.toMillis() : setFactsSyncedAt)) < 10000;
      
      if (syncedRecently) {
        console.log(`Skipping set_facts generation for workout ${event.params.workoutId} - already synced by upsertWorkout`);
      } else {
        try {
          // Generate set_facts from workout
          const workoutWithId = { ...after, id: event.params.workoutId };
          const setFacts = generateSetFactsForWorkout({
            userId: event.params.userId,
            workout: workoutWithId,
          });
          
          if (setFacts.length > 0) {
            // Write set_facts documents
            await writeSetFactsInChunks(db, event.params.userId, setFacts);
            
            // Update new series (series_exercises, series_muscle_groups, series_muscles)
            await updateSeriesForWorkout(db, event.params.userId, workoutWithId, 1);
            
            console.log(`Token-safe analytics: wrote ${setFacts.length} set_facts for workout ${event.params.workoutId}`);
          }
        } catch (e) {
          console.warn('Non-fatal: failed to write token-safe analytics (set_facts/series)', e?.message || e);
        }
      }
      // =============== END TOKEN-SAFE ANALYTICS ===============

      // Enqueue background analysis job
      try {
        await db.collection('training_analysis_jobs').add({
          type: 'POST_WORKOUT',
          status: 'queued',
          priority: 100,
          payload: {
            user_id: event.params.userId,
            workout_id: event.params.workoutId,
            window_weeks: 4,
          },
          attempts: 0,
          max_attempts: 3,
          created_at: admin.firestore.FieldValue.serverTimestamp(),
          updated_at: admin.firestore.FieldValue.serverTimestamp(),
        });
      } catch (e) {
        console.warn('Non-fatal: failed to enqueue analysis job', e?.message);
      }

      if (!result.success) {
        console.error(`Failed to update weekly stats:`, result);
      }

      return result;
    } catch (error) {
      console.error('Error in onWorkoutCompleted:', error);
      return { success: false, error: error.message };
    }
  }
);

// Handle newly created workouts that already include end_time and analytics
exports.onWorkoutCreatedWithEnd = onDocumentCreated(
  'users/{userId}/workouts/{workoutId}',
  async (event) => {
    try {
      const workout = event.data.data();
      if (!workout || !workout.end_time || !workout.analytics) return null;

      const endTime = workout.end_time.toDate ? workout.end_time.toDate().toISOString() : workout.end_time;
      const weekId = await getWeekStartForUser(event.params.userId, endTime);
      const result = await updateWeeklyStats(event.params.userId, weekId, workout.analytics, 1);

      try {
        await AnalyticsWrites.upsertRollup(event.params.userId, weekId, {
          total_sets: workout.analytics.total_sets,
          total_reps: workout.analytics.total_reps,
          total_weight: workout.analytics.total_weight,
          weight_per_muscle_group: workout.analytics.weight_per_muscle_group || {},
          workouts: 1,
          hard_sets_total: workout.analytics.intensity?.hard_sets || 0,
          low_rir_sets_total: workout.analytics.intensity?.low_rir_sets || 0,
          hard_sets_per_muscle: workout.analytics.intensity?.hard_sets_per_muscle || {},
          low_rir_sets_per_muscle: workout.analytics.intensity?.low_rir_sets_per_muscle || {},
          load_per_muscle: workout.analytics.intensity?.load_per_muscle || {},
        }, 1);

        const setsByGroup = workout.analytics.sets_per_muscle_group || {};
        const volByGroup = workout.analytics.weight_per_muscle_group || {};
        const hardSetsByMuscle = workout.analytics.intensity?.hard_sets_per_muscle || {};
        const loadByMuscle = workout.analytics.intensity?.load_per_muscle || {};
        const lowRirByMuscle = workout.analytics.intensity?.low_rir_sets_per_muscle || {};
        const muscles = new Set([
          ...Object.keys(setsByGroup),
          ...Object.keys(volByGroup),
          ...Object.keys(hardSetsByMuscle),
          ...Object.keys(loadByMuscle),
          ...Object.keys(lowRirByMuscle),
        ]);
        const writes = [];
        for (const muscle of muscles) {
          writes.push(
            AnalyticsWrites.appendMuscleSeries(
              event.params.userId,
              muscle,
              weekId,
              {
                sets: setsByGroup[muscle] || 0,
                volume: volByGroup[muscle] || 0,
                hard_sets: hardSetsByMuscle[muscle] || 0,
                load: loadByMuscle[muscle] || 0,
                low_rir_sets: lowRirByMuscle[muscle] || 0,
              },
              1
            )
          );
        }
        if (writes.length) await Promise.allSettled(writes);
      } catch (e) {
        console.warn('Non-fatal: failed to write analytics series/rollups for workout create', e?.message || e);
      }

      // Update watermark
      try {
        await AnalyticsWrites.updateWatermark(event.params.userId, { last_processed_workout_at: endTime });
      } catch (e) {
        console.warn('Non-fatal: failed to update watermark (create)', e?.message || e);
      }

      // Append per-exercise daily points
      try {
        const dayKey = endTime.split('T')[0];
        const exercises = Array.isArray(workout.exercises) ? workout.exercises : [];
        const perExercise = new Map();
        for (const ex of exercises) {
          const exId = ex.exercise_id;
          if (!exId || !Array.isArray(ex.sets)) continue;
          let maxE1 = 0; let vol = 0;
          for (const s of ex.sets) {
            if (!s.is_completed) continue;
            const reps = typeof s.reps === 'number' ? s.reps : 0;
            const w = typeof s.weight_kg === 'number' ? s.weight_kg : 0;
            if (reps > 0 && w > 0) {
              maxE1 = Math.max(maxE1, estimateE1RM(w, reps));
              vol += w * reps;
            }
          }
          const curr = perExercise.get(exId) || { e1rm: 0, vol: 0 };
          curr.e1rm = Math.max(curr.e1rm, maxE1);
          curr.vol += vol;
          perExercise.set(exId, curr);
        }
        const writes = [];
        for (const [exerciseId, point] of perExercise.entries()) {
          writes.push(AnalyticsWrites.appendExerciseSeries(event.params.userId, exerciseId, dayKey, point, 1));
        }
        if (writes.length) await Promise.allSettled(writes);
      } catch (e) {
        console.warn('Non-fatal: failed to write per-exercise daily series (create)', e?.message || e);
      }

      // =============== TOKEN-SAFE ANALYTICS: set_facts + new series ===============
      // Skip if set_facts were already synced by upsertWorkout (within last 10 seconds)
      const setFactsSyncedAt = workout.set_facts_synced_at;
      const syncedRecently = setFactsSyncedAt && 
        (Date.now() - (setFactsSyncedAt.toMillis ? setFactsSyncedAt.toMillis() : setFactsSyncedAt)) < 10000;
      
      if (syncedRecently) {
        console.log(`Skipping set_facts generation for workout ${event.params.workoutId} - already synced by upsertWorkout`);
      } else {
        try {
          // Generate set_facts from workout
          const workoutWithId = { ...workout, id: event.params.workoutId };
          const setFacts = generateSetFactsForWorkout({
            userId: event.params.userId,
            workout: workoutWithId,
          });
          
          if (setFacts.length > 0) {
            // Write set_facts documents
            await writeSetFactsInChunks(db, event.params.userId, setFacts);
            
            // Update new series (series_exercises, series_muscle_groups, series_muscles)
            await updateSeriesForWorkout(db, event.params.userId, workoutWithId, 1);
            
            console.log(`Token-safe analytics (create): wrote ${setFacts.length} set_facts for workout ${event.params.workoutId}`);
          }
        } catch (e) {
          console.warn('Non-fatal: failed to write token-safe analytics (set_facts/series) on create', e?.message || e);
        }
      }
      // =============== END TOKEN-SAFE ANALYTICS ===============

      // Enqueue background analysis job
      try {
        await db.collection('training_analysis_jobs').add({
          type: 'POST_WORKOUT',
          status: 'queued',
          priority: 100,
          payload: {
            user_id: event.params.userId,
            workout_id: event.params.workoutId,
            window_weeks: 4,
          },
          attempts: 0,
          max_attempts: 3,
          created_at: admin.firestore.FieldValue.serverTimestamp(),
          updated_at: admin.firestore.FieldValue.serverTimestamp(),
        });
      } catch (e) {
        console.warn('Non-fatal: failed to enqueue analysis job', e?.message);
      }

      return result;
    } catch (error) {
      console.error('Error in onWorkoutCreatedWithEnd:', error);
      return { success: false, error: error.message };
    }
  }
);

exports.onWorkoutDeleted = onDocumentDeleted(
  'users/{userId}/workouts/{workoutId}',
  async (event) => {
    try {
      const workout = event.data.data();
      if (!workout || !workout.end_time || !workout.analytics) {
        console.warn(`Deleted workout ${event.params.workoutId} missing required data`);
        return null;
      }
      
      // Convert Firestore timestamp to ISO string for week calculation
      const endTime = workout.end_time.toDate ? workout.end_time.toDate().toISOString() : workout.end_time;
      const weekId = await getWeekStartForUser(event.params.userId, endTime);
      const result = await updateWeeklyStats(event.params.userId, weekId, workout.analytics, -1);

      // Roll back rollups and per-muscle weekly series
      try {
        await AnalyticsWrites.upsertRollup(event.params.userId, weekId, {
          total_sets: workout.analytics.total_sets,
          total_reps: workout.analytics.total_reps,
          total_weight: workout.analytics.total_weight,
          weight_per_muscle_group: workout.analytics.weight_per_muscle_group || {},
          workouts: 1,
          hard_sets_total: workout.analytics.intensity?.hard_sets || 0,
          low_rir_sets_total: workout.analytics.intensity?.low_rir_sets || 0,
          hard_sets_per_muscle: workout.analytics.intensity?.hard_sets_per_muscle || {},
          low_rir_sets_per_muscle: workout.analytics.intensity?.low_rir_sets_per_muscle || {},
          load_per_muscle: workout.analytics.intensity?.load_per_muscle || {},
        }, -1);

        const setsByGroup = workout.analytics.sets_per_muscle_group || {};
        const volByGroup = workout.analytics.weight_per_muscle_group || {};
        const hardSetsByMuscle = workout.analytics.intensity?.hard_sets_per_muscle || {};
        const loadByMuscle = workout.analytics.intensity?.load_per_muscle || {};
        const lowRirByMuscle = workout.analytics.intensity?.low_rir_sets_per_muscle || {};
        const muscles = new Set([
          ...Object.keys(setsByGroup),
          ...Object.keys(volByGroup),
          ...Object.keys(hardSetsByMuscle),
          ...Object.keys(loadByMuscle),
          ...Object.keys(lowRirByMuscle),
        ]);
        const writes = [];
        for (const muscle of muscles) {
          writes.push(
            AnalyticsWrites.appendMuscleSeries(
              event.params.userId,
              muscle,
              weekId,
              {
                sets: setsByGroup[muscle] || 0,
                volume: volByGroup[muscle] || 0,
                hard_sets: hardSetsByMuscle[muscle] || 0,
                load: loadByMuscle[muscle] || 0,
                low_rir_sets: lowRirByMuscle[muscle] || 0,
              },
              -1
            )
          );
        }
        if (writes.length) await Promise.allSettled(writes);
      } catch (e) {
        console.warn('Non-fatal: failed to revert analytics series/rollups for workout delete', e?.message || e);
      }

      // Move watermark backwards only if needed is non-trivial; skip here to avoid regressions.

      // Revert per-exercise daily points
      try {
        const dayKey = endTime.split('T')[0];
        const exercises = Array.isArray(workout.exercises) ? workout.exercises : [];
        const perExercise = new Map();
        for (const ex of exercises) {
          const exId = ex.exercise_id;
          if (!exId || !Array.isArray(ex.sets)) continue;
          let maxE1 = 0; let vol = 0;
          for (const s of ex.sets) {
            if (!s.is_completed) continue;
            const reps = typeof s.reps === 'number' ? s.reps : 0;
            const w = typeof s.weight_kg === 'number' ? s.weight_kg : 0;
            if (reps > 0 && w > 0) {
              maxE1 = Math.max(maxE1, estimateE1RM(w, reps));
              vol += w * reps;
            }
          }
          const curr = perExercise.get(exId) || { e1rm: 0, vol: 0 };
          curr.e1rm = Math.max(curr.e1rm, maxE1);
          curr.vol += vol;
          perExercise.set(exId, curr);
        }
        const writes = [];
        for (const [exerciseId, point] of perExercise.entries()) {
          writes.push(AnalyticsWrites.appendExerciseSeries(event.params.userId, exerciseId, dayKey, point, -1));
        }
        if (writes.length) await Promise.allSettled(writes);
      } catch (e) {
        console.warn('Non-fatal: failed to revert per-exercise daily series', e?.message || e);
      }

      // =============== TOKEN-SAFE ANALYTICS: delete set_facts + revert series ===============
      try {
        const workoutWithId = { ...workout, id: event.params.workoutId };
        
        // Delete set_facts for this workout
        const setFactsQuery = db.collection('users').doc(event.params.userId)
          .collection('set_facts')
          .where('workout_id', '==', event.params.workoutId);
        
        const setFactsSnap = await setFactsQuery.get();
        if (!setFactsSnap.empty) {
          // Delete in batches
          const batchSize = CAPS.FIRESTORE_BATCH_LIMIT;
          const docs = setFactsSnap.docs;
          for (let i = 0; i < docs.length; i += batchSize) {
            const chunk = docs.slice(i, i + batchSize);
            const batch = db.batch();
            for (const doc of chunk) {
              batch.delete(doc.ref);
            }
            await batch.commit();
          }
          
          // Revert series (negative increment)
          await updateSeriesForWorkout(db, event.params.userId, workoutWithId, -1);
          
          console.log(`Token-safe analytics (delete): removed ${setFactsSnap.size} set_facts for workout ${event.params.workoutId}`);
        }
      } catch (e) {
        console.warn('Non-fatal: failed to cleanup token-safe analytics (set_facts/series) on delete', e?.message || e);
      }
      // =============== END TOKEN-SAFE ANALYTICS ===============
      
      if (!result.success) {
        console.error(`Failed to update weekly stats for deleted workout:`, result);
      }
      
      return result;
    } catch (error) {
      console.error('Error in onWorkoutDeleted:', error);
      return { success: false, error: error.message };
    }
  }
);

/**
 * Callable function to manually trigger weekly stats recalculation for a user
 * Can be called from the iOS app for testing or manual refresh
 */
exports.manualWeeklyStatsRecalculation = onCall(async (request) => {
  try {
    // Verify authentication
    if (!request.auth) {
      throw new Error('User must be authenticated');
    }
    
    const userId = request.auth.uid;
    
    // Get current and last week IDs
    const now = new Date();
    const currentWeekId = await getWeekStartForUser(userId, now.toISOString());
    const lastWeek = new Date(now);
    lastWeek.setDate(lastWeek.getDate() - 7);
    const lastWeekId = await getWeekStartForUser(userId, lastWeek.toISOString());
    
    // Recalculate both current and last week
    const [currentWeekResult, lastWeekResult] = await Promise.allSettled([
      recalculateWeeklyStats(userId, currentWeekId),
      recalculateWeeklyStats(userId, lastWeekId)
    ]);
    
    const results = {
      currentWeek: {
        weekId: currentWeekId,
        success: currentWeekResult.status === 'fulfilled' && currentWeekResult.value.success,
        workoutCount: currentWeekResult.status === 'fulfilled' ? currentWeekResult.value.workoutCount : 0,
        error: currentWeekResult.status === 'rejected' ? currentWeekResult.reason.message : null
      },
      lastWeek: {
        weekId: lastWeekId,
        success: lastWeekResult.status === 'fulfilled' && lastWeekResult.value.success,
        workoutCount: lastWeekResult.status === 'fulfilled' ? lastWeekResult.value.workoutCount : 0,
        error: lastWeekResult.status === 'rejected' ? lastWeekResult.reason.message : null
      }
    };
    
    return {
      success: true,
      message: 'Weekly stats recalculation completed',
      results
    };
    
  } catch (error) {
    console.error('Error in manual weekly stats recalculation:', error);
    throw new Error(`Failed to recalculate weekly stats: ${error.message}`);
  }
});
