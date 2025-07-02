const { onDocumentUpdated, onDocumentDeleted } = require('firebase-functions/v2/firestore');
const { onSchedule } = require('firebase-functions/v2/scheduler');
const { onCall } = require('firebase-functions/v2/https');
const admin = require('firebase-admin');

if (!admin.apps.length) {
  admin.initializeApp();
}

const db = admin.firestore();

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

// Cache for user preferences to avoid redundant database calls
const userPreferencesCache = new Map();

// Get week start based on user preference with caching
async function getWeekStartForUser(userId, dateString, useCache = true) {
  if (!userId) {
    // Default behavior for system-level calls
    return getWeekStartMonday(dateString);
  }

  let weekStartsOnMonday = true; // default

  if (useCache && userPreferencesCache.has(userId)) {
    weekStartsOnMonday = userPreferencesCache.get(userId);
  } else {
    try {
      const userDoc = await db.collection('users').doc(userId).get();
      if (userDoc.exists) {
        const userData = userDoc.data();
        weekStartsOnMonday = userData.week_starts_on_monday !== undefined ? userData.week_starts_on_monday : true;
        
        if (useCache) {
          userPreferencesCache.set(userId, weekStartsOnMonday);
        }
      }
    } catch (error) {
      console.warn(`Error fetching user preferences for ${userId}, defaulting to Monday start:`, error);
    }
  }
  
  return weekStartsOnMonday ? getWeekStartMonday(dateString) : getWeekStartSunday(dateString);
}

// Batch fetch user preferences to improve performance
async function batchFetchUserPreferences(userIds) {
  const batchSize = 500; // Firestore batch read limit
  const preferences = new Map();
  
  for (let i = 0; i < userIds.length; i += batchSize) {
    const batch = userIds.slice(i, i + batchSize);
    const docs = await Promise.all(
      batch.map(userId => 
        db.collection('users').doc(userId).get().catch(error => {
          console.warn(`Failed to fetch preferences for user ${userId}:`, error);
          return null;
        })
      )
    );
    
    docs.forEach((doc, index) => {
      const userId = batch[index];
      if (doc && doc.exists) {
        const userData = doc.data();
        const weekStartsOnMonday = userData.week_starts_on_monday !== undefined ? userData.week_starts_on_monday : true;
        preferences.set(userId, weekStartsOnMonday);
        userPreferencesCache.set(userId, weekStartsOnMonday);
      } else {
        // Default to Monday start
        preferences.set(userId, true);
        userPreferencesCache.set(userId, true);
      }
    });
  }
  
  return preferences;
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
 * Check if weekly stats need recalculation by comparing last update timestamps
 */
async function needsRecalculation(userId, weekId) {
  try {
    const [statsDoc, workoutsSnap] = await Promise.all([
      db.collection('users').doc(userId).collection('weekly_stats').doc(weekId).get(),
      db.collection('users').doc(userId).collection('workouts')
        .where('end_time', '>=', admin.firestore.Timestamp.fromDate(new Date(weekId + 'T00:00:00.000Z')))
        .where('end_time', '<', admin.firestore.Timestamp.fromDate(new Date(new Date(weekId + 'T00:00:00.000Z').getTime() + 7 * 24 * 60 * 60 * 1000)))
        .orderBy('end_time', 'desc')
        .limit(1)
        .get()
    ]);

    if (!statsDoc.exists) {
      return true; // No stats exist, need to calculate
    }

    if (workoutsSnap.empty) {
      return false; // No workouts, stats should be empty/zero
    }

    const statsData = statsDoc.data();
    const lastWorkout = workoutsSnap.docs[0].data();
    
    if (!statsData.updated_at || !lastWorkout.end_time) {
      return true; // Missing timestamp data, better to recalculate
    }

    // Compare timestamps to see if there are newer workouts than last stats update
    const statsTimestamp = statsData.updated_at.toDate();
    const workoutTimestamp = lastWorkout.end_time.toDate();
    
    return workoutTimestamp > statsTimestamp;
  } catch (error) {
    console.warn(`Error checking recalculation need for user ${userId}, week ${weekId}:`, error);
    return true; // When in doubt, recalculate
  }
}

/**
 * Periodic function to recalculate weekly stats for data consistency
 * Runs daily to catch any missed updates or resolve inconsistencies
 */
async function recalculateWeeklyStats(userId, weekId, forceRecalculation = false) {
  try {
    // Skip unnecessary recalculations unless forced
    if (!forceRecalculation && !(await needsRecalculation(userId, weekId))) {
      return { success: true, userId, weekId, skipped: true, reason: 'No changes detected' };
    }

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
      .select('analytics') // Only fetch analytics field for performance
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
  region: 'us-central1', // Explicitly set region for v2 functions
  timeoutSeconds: 540, // 9 minutes timeout (max is 9 minutes for scheduled functions)
  memory: '1GiB', // Increase memory for better performance
  retryConfig: {
    retryCount: 3,
    maxRetryDuration: '600s'
  }
}, async (event) => {
  const startTime = Date.now();
  const maxExecutionTime = 480000; // 8 minutes in milliseconds (leave buffer before timeout)
  console.log('Starting weekly stats recalculation job at:', new Date().toISOString());
  
  // Clear cache at the start of each run
  userPreferencesCache.clear();
  
  try {
    // Get current week and last week IDs using default (Monday start)
    const now = new Date();
    const currentWeekId = getWeekStartMonday(now.toISOString());
    const lastWeek = new Date(now);
    lastWeek.setDate(lastWeek.getDate() - 7);
    const lastWeekId = getWeekStartMonday(lastWeek.toISOString());
    
    console.log(`Processing weeks: current=${currentWeekId}, last=${lastWeekId}`);
    
    // Find users who have completed workouts in the last 2 weeks with pagination
    const twoWeeksAgo = new Date(now);
    twoWeeksAgo.setDate(twoWeeksAgo.getDate() - 14);
    const twoWeeksAgoTimestamp = admin.firestore.Timestamp.fromDate(twoWeeksAgo);
    
    // Use a more efficient query with limit and pagination
    const maxUsers = 1000; // Process at most 1000 users per run
    const usersSnap = await db.collectionGroup('workouts')
      .where('end_time', '>=', twoWeeksAgoTimestamp)
      .select() // Get document references only, no data
      .limit(maxUsers * 2) // Multiply by 2 to account for multiple workouts per user
      .get();

    const activeUserIds = [...new Set(usersSnap.docs.map(doc => doc.ref.parent.parent.id))].slice(0, maxUsers);
    
    if (activeUserIds.length === 0) {
      console.log('No active users found for recalculation');
      return {
        success: true,
        processed: 0,
        successful: 0,
        failed: 0,
        activeUsers: 0,
        completedAt: new Date().toISOString()
      };
    }

    console.log(`Found ${activeUserIds.length} active users to process`);

    // Batch fetch user preferences for all users upfront
    await batchFetchUserPreferences(activeUserIds);
    console.log('User preferences cached');

    const results = [];
    let processedUsers = 0;
    let skippedCount = 0;
    
    // Dynamic batch sizing based on execution time and user count
    let batchSize = Math.max(5, Math.min(20, Math.floor(activeUserIds.length / 10)));
    
    for (let i = 0; i < activeUserIds.length; i += batchSize) {
      // Check if we're running out of time
      const elapsedTime = Date.now() - startTime;
      if (elapsedTime > maxExecutionTime) {
        console.log(`Stopping due to timeout. Processed ${processedUsers}/${activeUserIds.length} users`);
        break;
      }

      const batch = activeUserIds.slice(i, i + batchSize);
      const batchStartTime = Date.now();
      const batchPromises = [];
      
      for (const userId of batch) {
        // Get user-specific week IDs based on cached preferences
        const userCurrentWeekId = await getWeekStartForUser(userId, now.toISOString(), true);
        const userLastWeek = new Date(now);
        userLastWeek.setDate(userLastWeek.getDate() - 7);
        const userLastWeekId = await getWeekStartForUser(userId, userLastWeek.toISOString(), true);
        
        batchPromises.push(
          recalculateWeeklyStats(userId, userCurrentWeekId, false),
          recalculateWeeklyStats(userId, userLastWeekId, false)
        );
      }
      
      const batchResults = await Promise.allSettled(batchPromises);
      results.push(...batchResults);
      processedUsers += batch.length;
      
      // Count skipped recalculations
      const batchSkipped = batchResults.filter(r => 
        r.status === 'fulfilled' && r.value.success && r.value.skipped
      ).length;
      skippedCount += batchSkipped;
      
      // Adaptive batch sizing based on performance
      const batchDuration = Date.now() - batchStartTime;
      if (batchDuration > 5000 && batchSize > 5) {
        batchSize = Math.max(5, Math.floor(batchSize * 0.8)); // Reduce batch size if too slow
      } else if (batchDuration < 2000 && batchSize < 20) {
        batchSize = Math.min(20, Math.floor(batchSize * 1.2)); // Increase batch size if fast
      }
      
      console.log(`Processed batch ${Math.floor(i/batchSize) + 1}: ${batch.length} users, ${batchSkipped} skipped, ${batchDuration}ms, next batch size: ${batchSize}`);
      
      // Small delay between batches to avoid rate limits (shorter if running out of time)
      const remainingTime = maxExecutionTime - (Date.now() - startTime);
      const delayTime = remainingTime > 60000 ? 500 : 100; // Shorter delay if less than 1 minute remaining
      
      if (i + batchSize < activeUserIds.length && remainingTime > 10000) {
        await new Promise(resolve => setTimeout(resolve, delayTime));
      }
    }

    const successful = results.filter(r => r.status === 'fulfilled' && r.value.success).length;
    const failed = results.length - successful;
    const totalElapsed = Date.now() - startTime;
    
    const finalResult = {
      success: true,
      processed: results.length,
      successful,
      failed,
      skipped: skippedCount,
      activeUsers: activeUserIds.length,
      processedUsers,
      executionTimeMs: totalElapsed,
      completedAt: new Date().toISOString(),
      cacheHits: userPreferencesCache.size
    };
    
    console.log('Weekly stats recalculation job completed:', finalResult);
    
    return finalResult;
  } catch (error) {
    console.error('Error in weekly stats recalculation job:', error);
    const errorResult = { 
      success: false, 
      error: error.message, 
      executionTimeMs: Date.now() - startTime,
      completedAt: new Date().toISOString() 
    };
    console.log('Weekly stats recalculation job failed:', errorResult);
    return errorResult;
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
    
    // Recalculate both current and last week (force recalculation for manual calls)
    const [currentWeekResult, lastWeekResult] = await Promise.allSettled([
      recalculateWeeklyStats(userId, currentWeekId, true),
      recalculateWeeklyStats(userId, lastWeekId, true)
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

