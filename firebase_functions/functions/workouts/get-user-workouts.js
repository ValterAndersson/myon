const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');
const { ok, fail } = require('../utils/response');

const db = new FirestoreHelper();

/**
 * Firebase Function: Get User Workouts
 * 
 * Description: Retrieves user's workout history with analytics and insights
 * for AI progress analysis and workout recommendations
 */
async function getUserWorkoutsHandler(req, res) {
  const userId = req.query.userId || req.body?.userId;
  const limit = parseInt(req.query?.limit) || 50;
  const startDate = req.query?.startDate;
  const endDate = req.query?.endDate;
  
  if (!userId) return fail(res, 'INVALID_ARGUMENT', 'Missing userId parameter', null, 400);

  try {
    // Build query parameters (fixed field names to match Firestore schema)
    const queryParams = {
      orderBy: { field: 'end_time', direction: 'desc' },
      limit: limit,
      where: [] // Remove isCompleted filter - use presence of end_time to indicate completion
    };

    // Add date filters if provided (using end_time field)
    if (startDate) {
      queryParams.where.push({
        field: 'end_time',
        operator: '>=',
        value: new Date(startDate)
      });
    }
    
    if (endDate) {
      queryParams.where.push({
        field: 'end_time',
        operator: '<=',
        value: new Date(endDate)
      });
    }

    // Get workouts
    const workouts = await db.getDocumentsFromSubcollection('users', userId, 'workouts', queryParams);

    // Calculate analytics for AI (fixed field names)
    const analytics = {
      totalWorkouts: workouts.length,
      dateRange: {
        earliest: workouts[workouts.length - 1]?.end_time || null,
        latest: workouts[0]?.end_time || null
      },
      templates: {},
      averageDuration: null,
      totalVolume: 0,
      exerciseFrequency: {}
    };

    if (workouts.length > 0) {
      // Template usage
      const templateCounts = {};
      workouts.forEach(workout => {
        if (workout.templateId) {
          templateCounts[workout.templateId] = (templateCounts[workout.templateId] || 0) + 1;
        }
      });
      analytics.templates = templateCounts;

      // Duration analysis (fixed field names)
      const durations = workouts
        .filter(w => w.start_time && w.end_time)
        .map(w => (new Date(w.end_time) - new Date(w.start_time)) / (1000 * 60));
      
      if (durations.length > 0) {
        analytics.averageDuration = Math.round(durations.reduce((a, b) => a + b, 0) / durations.length);
      }

      // Exercise frequency and volume
      const exerciseCounts = {};
      let totalWeight = 0;
      
      workouts.forEach(workout => {
        if (workout.exercises) {
          workout.exercises.forEach(exercise => {
            exerciseCounts[exercise.exerciseId] = (exerciseCounts[exercise.exerciseId] || 0) + 1;
            
            // Calculate volume if sets data available
            if (exercise.sets) {
              exercise.sets.forEach(set => {
                if (set.weight && set.reps) {
                  totalWeight += (set.weight * set.reps);
                }
              });
            }
          });
        }
      });
      
      analytics.exerciseFrequency = exerciseCounts;
      analytics.totalVolume = totalWeight;
    }

    return ok(res, { items: workouts, analytics, filters: { userId, limit, startDate: startDate || null, endDate: endDate || null } });

  } catch (error) {
    console.error('get-user-workouts function error:', error);
    return fail(res, 'INTERNAL', 'Failed to get user workouts', { message: error.message }, 500);
  }
}

// Export Firebase Function
exports.getUserWorkouts = onRequest(requireFlexibleAuth(getUserWorkoutsHandler)); 