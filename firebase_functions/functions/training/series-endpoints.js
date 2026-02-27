/**
 * Series Endpoints
 * Token-safe series endpoints for exercises, muscle groups, and muscles
 * 
 * @see docs/TRAINING_ANALYTICS_API_V2_SPEC.md Section 6.3
 */

const { onCall, HttpsError } = require('firebase-functions/v2/https');
const admin = require('firebase-admin');

if (!admin.apps.length) {
  admin.initializeApp();
}

const db = admin.firestore();
const {
  CAPS,
  buildResponse,
  requireAuth,
  transformWeeklyPoint,
  getWeekStart,
} = require('../utils/caps');
const { isValidMuscleGroup, isValidMuscle, getMuscleGroupDisplay, getMuscleDisplay } = require('../utils/muscle-taxonomy');

/**
 * Helper to get last N weeks as YYYY-MM-DD array
 */
function getRecentWeekStarts(weeks) {
  const result = [];
  const now = new Date();
  
  for (let i = 0; i < weeks; i++) {
    const d = new Date(now);
    d.setDate(d.getDate() - (i * 7));
    result.push(getWeekStart(d));
  }
  
  return result.reverse(); // oldest first
}

/**
 * Extract weekly points from series document
 */
function extractWeeklyPoints(seriesDoc, weekIds) {
  if (!seriesDoc.exists) return [];
  
  const data = seriesDoc.data();
  const weeks = data.weeks || {};
  
  return weekIds
    .filter(wk => weeks[wk])
    .map(wk => {
      const raw = weeks[wk];
      return {
        week_start: wk,
        ...transformWeeklyPoint({ week_start: wk, ...raw }),
      };
    });
}

/**
 * Compute summary statistics from weekly points
 */
function computeSummary(points) {
  if (points.length === 0) {
    return {
      total_weeks: 0,
      avg_weekly_sets: 0,
      avg_weekly_volume: 0,
      avg_weekly_hard_sets: 0,
      trend_direction: null,
    };
  }
  
  const totalSets = points.reduce((s, p) => s + (p.sets || 0), 0);
  const totalVolume = points.reduce((s, p) => s + (p.volume || 0), 0);
  const totalHardSets = points.reduce((s, p) => s + (p.hard_sets || 0), 0);
  
  // Simple trend: compare first half to second half
  const mid = Math.floor(points.length / 2);
  let trendDirection = null;
  if (points.length >= 4) {
    const firstHalfAvg = points.slice(0, mid).reduce((s, p) => s + (p.volume || 0), 0) / mid;
    const secondHalfAvg = points.slice(mid).reduce((s, p) => s + (p.volume || 0), 0) / (points.length - mid);
    
    const change = (secondHalfAvg - firstHalfAvg) / (firstHalfAvg || 1);
    if (change > 0.1) trendDirection = 'increasing';
    else if (change < -0.1) trendDirection = 'decreasing';
    else trendDirection = 'stable';
  }
  
  return {
    total_weeks: points.length,
    avg_weekly_sets: Math.round((totalSets / points.length) * 10) / 10,
    avg_weekly_volume: Math.round((totalVolume / points.length) * 10) / 10,
    avg_weekly_hard_sets: Math.round((totalHardSets / points.length) * 10) / 10,
    trend_direction: trendDirection,
  };
}

/**
 * Helper to normalize exercise name for matching
 * Makes search case-insensitive and handles common variations
 */
function normalizeExerciseName(name) {
  if (!name) return '';
  return name.toLowerCase()
    .replace(/[-_]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

/**
 * Find exercise series by name search
 * Searches user's series_exercises collection for matching exercise_name
 * Returns best match or null
 */
async function findExerciseSeriesByName(db, userId, searchName) {
  const normalized = normalizeExerciseName(searchName);
  if (!normalized) return null;
  
  // Get all exercise series for the user
  const seriesSnap = await db.collection('users').doc(userId)
    .collection('series_exercises')
    .get();
  
  if (seriesSnap.empty) return null;
  
  // Find best match
  let bestMatch = null;
  let bestScore = 0;
  
  for (const doc of seriesSnap.docs) {
    const data = doc.data();
    const exerciseName = data.exercise_name;
    if (!exerciseName) continue;
    
    const docNormalized = normalizeExerciseName(exerciseName);
    
    // Exact match
    if (docNormalized === normalized) {
      return { doc, exerciseId: doc.id, exerciseName };
    }
    
    // Contains match
    if (docNormalized.includes(normalized) || normalized.includes(docNormalized)) {
      const score = Math.min(normalized.length, docNormalized.length) / 
                    Math.max(normalized.length, docNormalized.length);
      if (score > bestScore) {
        bestScore = score;
        bestMatch = { doc, exerciseId: doc.id, exerciseName };
      }
    }
    
    // Word match (e.g., "bench" matches "Bench Press")
    const searchWords = normalized.split(' ');
    const docWords = docNormalized.split(' ');
    const matchingWords = searchWords.filter(w => docWords.some(dw => dw.includes(w) || w.includes(dw)));
    if (matchingWords.length > 0) {
      const score = matchingWords.length / Math.max(searchWords.length, docWords.length);
      if (score > bestScore) {
        bestScore = score;
        bestMatch = { doc, exerciseId: doc.id, exerciseName };
      }
    }
  }
  
  // Only return if match quality is reasonable
  return bestScore >= 0.5 ? bestMatch : null;
}

/**
 * series.exercise.get
 * Get weekly series for a specific exercise
 * 
 * Accepts either:
 * - exercise_id: direct ID lookup
 * - exercise_name: fuzzy name search (for agent queries like "bench press")
 */
exports.getExerciseSeries = onCall(async (request) => {
  try {
    const userId = requireAuth(request);
    const { exercise_id, exercise_name, window_weeks } = request.data || {};
    
    if (!exercise_id && !exercise_name) {
      throw new HttpsError('invalid-argument', 'exercise_id or exercise_name is required');
    }
    
    const weeks = Math.min(Math.max(1, window_weeks || CAPS.DEFAULT_WEEKS), CAPS.MAX_WEEKS);
    const weekIds = getRecentWeekStarts(weeks);
    
    let seriesDoc = null;
    let resolvedExerciseId = exercise_id;
    let resolvedExerciseName = null;
    
    if (exercise_id) {
      // Direct ID lookup
      const seriesRef = db.collection('users').doc(userId)
        .collection('series_exercises').doc(exercise_id);
      seriesDoc = await seriesRef.get();
      
      // Get exercise name from series doc or catalog
      if (seriesDoc.exists && seriesDoc.data().exercise_name) {
        resolvedExerciseName = seriesDoc.data().exercise_name;
      } else {
        try {
          const exDoc = await db.collection('exercises').doc(exercise_id).get();
          if (exDoc.exists) {
            resolvedExerciseName = exDoc.data().name;
          }
        } catch (e) {
          // Ignore - name is optional
        }
      }
    } else {
      // Name-based search
      const match = await findExerciseSeriesByName(db, userId, exercise_name);
      
      if (!match) {
        // No matching exercise found in user's training history
        return buildResponse({
          exercise_id: null,
          exercise_name: exercise_name,
          matched: false,
          message: `No training history found for "${exercise_name}". Try a different exercise name or check spelling.`,
          weekly_points: [],
          summary: computeSummary([]),
        }, { limit: weeks });
      }
      
      seriesDoc = match.doc;
      resolvedExerciseId = match.exerciseId;
      resolvedExerciseName = match.exerciseName;
    }
    
    const points = extractWeeklyPoints(seriesDoc, weekIds);
    const summary = computeSummary(points);
    
    return buildResponse({
      exercise_id: resolvedExerciseId,
      exercise_name: resolvedExerciseName,
      matched: true,
      weekly_points: points,
      summary,
    }, { limit: weeks });
    
  } catch (error) {
    if (error instanceof HttpsError) throw error;
    console.error('Error in getExerciseSeries:', error);
    throw new HttpsError('internal', 'Internal error');
  }
});

/**
 * series.muscle_group.get
 * Get weekly series for a muscle group
 */
exports.getMuscleGroupSeries = onCall(async (request) => {
  try {
    const userId = requireAuth(request);
    const { muscle_group, window_weeks } = request.data || {};
    
    if (!muscle_group) {
      throw new HttpsError('invalid-argument', 'muscle_group is required');
    }
    
    if (!isValidMuscleGroup(muscle_group)) {
      throw new HttpsError('invalid-argument', `Invalid muscle_group: ${muscle_group}`);
    }
    
    const weeks = Math.min(Math.max(1, window_weeks || CAPS.DEFAULT_WEEKS), CAPS.MAX_WEEKS);
    const weekIds = getRecentWeekStarts(weeks);
    
    // Get series document
    const seriesRef = db.collection('users').doc(userId)
      .collection('series_muscle_groups').doc(muscle_group);
    const seriesDoc = await seriesRef.get();
    
    const points = extractWeeklyPoints(seriesDoc, weekIds);
    const summary = computeSummary(points);
    
    return buildResponse({
      muscle_group,
      display_name: getMuscleGroupDisplay(muscle_group),
      weekly_points: points,
      summary,
    }, { limit: weeks });
    
  } catch (error) {
    if (error instanceof HttpsError) throw error;
    console.error('Error in getMuscleGroupSeries:', error);
    throw new HttpsError('internal', 'Internal error');
  }
});

/**
 * series.muscle.get
 * Get weekly series for a specific muscle
 */
exports.getMuscleSeries = onCall(async (request) => {
  try {
    const userId = requireAuth(request);
    const { muscle, window_weeks } = request.data || {};
    
    if (!muscle) {
      throw new HttpsError('invalid-argument', 'muscle is required');
    }
    
    if (!isValidMuscle(muscle)) {
      throw new HttpsError('invalid-argument', `Invalid muscle: ${muscle}`);
    }
    
    const weeks = Math.min(Math.max(1, window_weeks || CAPS.DEFAULT_WEEKS), CAPS.MAX_WEEKS);
    const weekIds = getRecentWeekStarts(weeks);
    
    // Get series document
    const seriesRef = db.collection('users').doc(userId)
      .collection('series_muscles').doc(muscle);
    const seriesDoc = await seriesRef.get();
    
    const points = extractWeeklyPoints(seriesDoc, weekIds);
    const summary = computeSummary(points);
    
    return buildResponse({
      muscle,
      display_name: getMuscleDisplay(muscle),
      weekly_points: points,
      summary,
    }, { limit: weeks });
    
  } catch (error) {
    if (error instanceof HttpsError) throw error;
    console.error('Error in getMuscleSeries:', error);
    throw new HttpsError('internal', 'Internal error');
  }
});
