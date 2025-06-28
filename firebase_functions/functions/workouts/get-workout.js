const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');

const db = new FirestoreHelper();

/**
 * Firebase Function: Get Specific Workout
 * 
 * Description: Gets full workout details with sets, reps, weights for a specific workout
 */
async function getWorkoutHandler(req, res) {
  const userId = req.query.userId || req.body?.userId;
  const workoutId = req.query.workoutId || req.body?.workoutId;
  
  if (!userId || !workoutId) {
    return res.status(400).json({
      success: false,
      error: 'Missing required parameters',
      required: ['userId', 'workoutId'],
      usage: 'Provide both userId and workoutId'
    });
  }

  try {
    // Get workout
    const workout = await db.getDocumentFromSubcollection('users', userId, 'workouts', workoutId);
    
    if (!workout) {
      return res.status(404).json({
        success: false,
        error: 'Workout not found',
        userId: userId,
        workoutId: workoutId
      });
    }

    // Get template info if available
    let template = null;
    if (workout.templateId) {
      template = await db.getDocumentFromSubcollection('users', userId, 'templates', workout.templateId);
    }

    // Calculate workout metrics for AI analysis
    const metrics = {
      duration: null,
      totalSets: 0,
      totalReps: 0,
      totalVolume: 0,
      exerciseCount: workout.exercises?.length || 0
    };

    if (workout.startedAt && workout.completedAt) {
      metrics.duration = Math.round((new Date(workout.completedAt) - new Date(workout.startedAt)) / (1000 * 60));
    }

    if (workout.exercises) {
      workout.exercises.forEach(exercise => {
        if (exercise.sets) {
          metrics.totalSets += exercise.sets.length;
          exercise.sets.forEach(set => {
            if (set.reps) metrics.totalReps += set.reps;
            if (set.weight && set.reps) metrics.totalVolume += (set.weight * set.reps);
          });
        }
      });
    }

    return res.status(200).json({
      success: true,
      data: workout,
      template: template,
      metrics: metrics,
      metadata: {
        function: 'get-workout',
        userId: userId,
        workoutId: workoutId,
        requestedAt: new Date().toISOString(),
        authType: req.auth?.type || 'firebase',
        source: req.auth?.source || 'user_app'
      }
    });

  } catch (error) {
    console.error('get-workout function error:', error);
    return res.status(500).json({
      success: false,
      error: 'Failed to get workout',
      details: error.message,
      function: 'get-workout',
      timestamp: new Date().toISOString()
    });
  }
}

// Export Firebase Function
exports.getWorkout = onRequest(requireFlexibleAuth(getWorkoutHandler)); 