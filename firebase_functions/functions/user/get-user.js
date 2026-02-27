const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');
const admin = require('firebase-admin');
const { getAuthenticatedUserId } = require('../utils/auth-helpers');

if (!admin.apps.length) {
  admin.initializeApp();
}

const db = new FirestoreHelper();
const firestore = admin.firestore();

// ============================================================================
// USER PROFILE CACHE (24-hour TTL)
// Memory cache for hot path, Firestore cache for persistence
// ============================================================================
const PROFILE_CACHE_TTL_MS = 24 * 60 * 60 * 1000; // 24 hours
const MEMORY_CACHE_TTL_MS = 5 * 60 * 1000; // 5 minutes (function instance lifetime)

// In-memory cache (per function instance)
const profileCache = new Map();

async function getCachedProfile(userId) {
  // Layer 1: Memory cache (fastest)
  const memoryCached = profileCache.get(userId);
  if (memoryCached && Date.now() < memoryCached.expiresAt) {
    console.log('[ProfileCache] Memory hit', { userId });
    return { data: memoryCached.data, source: 'memory' };
  }
  
  // Layer 2: Firestore cache
  try {
    const cacheDoc = await firestore.collection('cache').doc(`profile_${userId}`).get();
    if (cacheDoc.exists) {
      const cached = cacheDoc.data();
      const cachedAt = cached.cachedAt?.toMillis?.() || 0;
      const age = Date.now() - cachedAt;
      
      if (age < PROFILE_CACHE_TTL_MS) {
        console.log('[ProfileCache] Firestore hit', { userId, age: Math.round(age / 1000) + 's' });
        // Warm memory cache
        profileCache.set(userId, {
          data: cached.data,
          expiresAt: Date.now() + MEMORY_CACHE_TTL_MS
        });
        return { data: cached.data, source: 'firestore' };
      }
    }
  } catch (e) {
    console.warn('[ProfileCache] Firestore read error:', e.message);
  }
  
  return null; // Cache miss
}

async function setCachedProfile(userId, data) {
  // Set memory cache
  profileCache.set(userId, {
    data,
    expiresAt: Date.now() + MEMORY_CACHE_TTL_MS
  });
  
  // Set Firestore cache (async, don't await)
  firestore.collection('cache').doc(`profile_${userId}`).set({
    data,
    userId,
    cachedAt: admin.firestore.FieldValue.serverTimestamp()
  }).catch(e => console.warn('[ProfileCache] Firestore write error:', e.message));
}

// Export cache invalidation helper for use by update-user.js
async function invalidateProfileCache(userId) {
  profileCache.delete(userId);
  try {
    await firestore.collection('cache').doc(`profile_${userId}`).delete();
    console.log('[ProfileCache] Cache invalidated', { userId });
  } catch (e) {
    console.warn('[ProfileCache] Cache invalidation error:', e.message);
  }
}
exports.invalidateProfileCache = invalidateProfileCache;

/**
 * Firebase Function: Get User Profile (with caching)
 * 
 * Description: Retrieves comprehensive user profile data including fitness preferences,
 * recent activity context, and statistics for AI analysis
 */
async function getUserHandler(req, res) {
  const userId = getAuthenticatedUserId(req);
  const skipCache = req.query.skipCache || req.body?.skipCache;

  if (!userId) {
    return res.status(400).json({
      success: false,
      error: 'Missing userId parameter',
      usage: 'Provide userId as query parameter (?userId=123) or in request body'
    });
  }

  try {
    // Check cache first (unless skipCache=true)
    if (String(skipCache).toLowerCase() !== 'true') {
      const cached = await getCachedProfile(userId);
      if (cached) {
        return res.status(200).json({
          ...cached.data,
          metadata: {
            ...cached.data.metadata,
            source: cached.source,
            cachedAt: new Date().toISOString()
          }
        });
      }
    }
    console.log('[ProfileCache] Cache miss, querying Firestore...');
    
    // Get user data
    const user = await db.getDocument('users', userId);
    if (!user) {
      return res.status(404).json({
        success: false,
        error: 'User not found',
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

    // Normalize user preferences for agents (backwards-compatible)
    const tz = user.timezone || userAttributes?.timezone || null;
    const weightFormat = userAttributes?.weight_format || user.weightFormat || 'kilograms';
    const heightFormat = userAttributes?.height_format || user.heightFormat || 'centimeter';
    const weekStartsMonday = (
      userAttributes?.week_starts_on_monday ?? user.week_starts_on_monday ?? false
    );
    const preferences = {
      timezone: tz,
      weight_format: weightFormat,              // 'kilograms' | 'pounds'
      height_format: heightFormat,              // 'centimeter' | 'feet'
      week_starts_on_monday: !!weekStartsMonday,
      first_day_of_week: weekStartsMonday ? 'monday' : 'sunday',
      weight_unit: weightFormat === 'pounds' ? 'lbs' : 'kg',
      height_unit: heightFormat === 'feet' ? 'ft' : 'cm',
      locale: user.locale || userAttributes?.locale || null
    };

    // Strip sensitive internal fields before returning to client
    const SENSITIVE_FIELDS = [
      'subscription_original_transaction_id',
      'subscription_app_account_token',
      'apple_authorization_code',
      'subscription_environment',
    ];
    const sanitizedUser = { ...user };
    for (const field of SENSITIVE_FIELDS) {
      delete sanitizedUser[field];
    }

    const response = {
      success: true,
      data: sanitizedUser,
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
        preferences,
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

    // Never expose email in API responses — available in server logs if needed

    // Cache the results for future requests (async, don't wait)
    response.metadata.source = 'fresh';
    setCachedProfile(userId, response);
    console.log('[ProfileCache] Cached profile', { userId });

    return res.status(200).json(response);

  } catch (error) {
    console.error('get-user function error:', error);
    return res.status(500).json({
      success: false,
      error: 'Failed to get user profile',
    });
  }
}

// Export Firebase Function
exports.getUser = onRequest(requireFlexibleAuth(getUserHandler));
