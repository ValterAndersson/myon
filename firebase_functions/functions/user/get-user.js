const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');

const db = new FirestoreHelper();

/**
 * Firebase Function: Get User Profile
 * 
 * Description: Retrieves comprehensive user profile data including fitness preferences,
 * recent activity context, and statistics for AI analysis
 */
async function getUserHandler(req, res) {
  const userId = req.query.userId || req.body?.userId;
  
  if (!userId) {
    return res.status(400).json({
      success: false,
      error: 'Missing userId parameter',
      usage: 'Provide userId as query parameter (?userId=123) or in request body'
    });
  }

  try {
    // Get user data
    const user = await db.getDocument('users', userId);
    if (!user) {
      return res.status(404).json({
        success: false,
        error: 'User not found',
        userId: userId
      });
    }

    // Get additional context for AI including fitness profile
    const [recentWorkouts, activeRoutine, templateCount, userAttributes] = await Promise.all([
      // Recent workouts (last 5 for context) - fixed field names
      db.getDocumentsFromSubcollection('users', userId, 'workouts', {
        orderBy: { field: 'end_time', direction: 'desc' },
        limit: 5
        // Remove isCompleted filter - presence of end_time indicates completion
      }),
      // Active routine if set
      user.activeRoutineId ? 
        db.getDocumentFromSubcollection('users', userId, 'routines', user.activeRoutineId) : 
        null,
      // Template count
      db.getDocumentsFromSubcollection('users', userId, 'templates', { limit: 1 }),
      // User fitness attributes (single document with userId as document ID)
      db.getDocumentFromSubcollection('users', userId, 'user_attributes', userId)
    ]);

    // Calculate days since last workout (fixed field name)
    const daysSinceLastWorkout = recentWorkouts.length > 0 ? 
      Math.floor((new Date() - new Date(recentWorkouts[0].end_time)) / (1000 * 60 * 60 * 24)) : 
      null;

    // Process user attributes for fitness profile (single document structure)
    const fitnessProfile = userAttributes || {};

    const response = {
      success: true,
      data: user,
      context: {
        recentWorkoutsCount: recentWorkouts.length,
        lastWorkoutDate: recentWorkouts[0]?.end_time || null,
        daysSinceLastWorkout: daysSinceLastWorkout,
        hasActiveRoutine: !!activeRoutine,
        activeRoutineName: activeRoutine?.name || null,
        hasTemplates: templateCount.length > 0,
        fitnessLevel: fitnessProfile.fitness_level || user.fitnessLevel || 'unknown',
        preferredEquipment: fitnessProfile.equipment_preference || user.equipment || 'unknown',
        fitnessGoals: fitnessProfile.fitness_goal || 'unknown',
        experienceLevel: fitnessProfile.fitness_level || 'beginner',
        availableEquipment: fitnessProfile.equipment_preference || 'unknown',
        workoutFrequency: fitnessProfile.workouts_per_week_goal || 'unknown',
        height: fitnessProfile.height || null,
        weight: fitnessProfile.weight || null,
        fitnessProfile: fitnessProfile // Include all attributes for debugging
      },
      metadata: {
        function: 'get-user',
        userId: userId,
        requestedAt: new Date().toISOString(),
        authType: req.auth?.type || 'firebase',
        source: req.auth?.source || 'user_app'
      }
    };

    // Add requestedBy only for Firebase Auth (has email)
    if (req.auth?.email) {
      response.metadata.requestedBy = req.auth.email;
    }

    return res.status(200).json(response);

  } catch (error) {
    console.error('get-user function error:', error);
    return res.status(500).json({
      success: false,
      error: 'Failed to get user profile',
      details: error.message,
      function: 'get-user',
      timestamp: new Date().toISOString()
    });
  }
}

// Export Firebase Function
exports.getUser = onRequest(requireFlexibleAuth(getUserHandler)); 