/**
 * Progress Summary Endpoints
 * Token-safe summaries for muscle groups, muscles, and exercises
 * 
 * Uses onRequest (not onCall) for compatibility with HTTP clients.
 * 
 * @see docs/TRAINING_ANALYTICS_API_V2_SPEC.md Section 6.4
 */

const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const admin = require('firebase-admin');
const { getAuthenticatedUserId } = require('../utils/auth-helpers');

if (!admin.apps.length) {
  admin.initializeApp();
}

const db = admin.firestore();
const {
  CAPS,
  buildResponse,
  getWeekStart,
  transformWeeklyPoint,
} = require('../utils/caps');
const {
  getMuscleGroupDisplay,
  getMuscleDisplay,
  validateMuscleGroupWithRecovery,
  validateMuscleWithRecovery,
} = require('../utils/muscle-taxonomy');

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
 * Returns recent weeks OR all available weeks if recent is empty
 */
function extractWeeklyPoints(seriesDoc, weekIds) {
  if (!seriesDoc.exists) return [];
  
  const data = seriesDoc.data();
  const weeks = data.weeks || {};
  
  // First try to get recent weeks
  const recentPoints = weekIds
    .filter(wk => weeks[wk])
    .map(wk => {
      const raw = weeks[wk];
      return transformWeeklyPoint({ week_start: wk, ...raw });
    });
  
  // If no recent data, return ALL available weeks (sorted, capped at 52)
  if (recentPoints.length === 0) {
    const allWeeks = Object.keys(weeks).sort();
    return allWeeks.slice(-52).map(wk => {
      const raw = weeks[wk];
      return transformWeeklyPoint({ week_start: wk, ...raw });
    });
  }
  
  return recentPoints;
}

/**
 * Detect plateau - best weekly e1RM within ±1% for last 4 weeks
 */
function detectPlateau(points) {
  if (points.length < 4) return false;
  
  const lastFour = points.slice(-4);
  const e1rms = lastFour.filter(p => p.e1rm_max).map(p => p.e1rm_max);
  
  if (e1rms.length < 3) return false;
  
  const max = Math.max(...e1rms);
  const min = Math.min(...e1rms);
  const range = (max - min) / ((max + min) / 2);
  
  return range <= 0.02; // Within 2% = plateau
}

/**
 * Detect deload - volume drop > 40% week over week
 */
function detectDeload(points) {
  if (points.length < 2) return false;
  
  const lastTwo = points.slice(-2);
  const prev = lastTwo[0].effective_volume || lastTwo[0].volume || 0;
  const curr = lastTwo[1].effective_volume || lastTwo[1].volume || 0;
  
  if (prev === 0) return false;
  
  const drop = (prev - curr) / prev;
  return drop > 0.4;
}

/**
 * Detect overreach - high failure rate + rising volume for 2+ weeks
 */
function detectOverreach(points) {
  if (points.length < 2) return false;
  
  const lastTwo = points.slice(-2);
  const avgFailure = lastTwo.reduce((s, p) => s + (p.failure_rate || 0), 0) / lastTwo.length;
  const avgRir = lastTwo.reduce((s, p) => s + (p.avg_rir || 2), 0) / lastTwo.length;
  
  // Check volume trend
  const volumeTrend = lastTwo.length >= 2 && 
    (lastTwo[1].volume || 0) > (lastTwo[0].volume || 0);
  
  return avgFailure > 0.35 && avgRir < 1 && volumeTrend;
}

/**
 * progress.muscle_group.summary
 * Summary for a muscle group with series, top exercises, and flags
 */
exports.getMuscleGroupSummary = onRequest(requireFlexibleAuth(async (req, res) => {
  try {
    // Get userId from auth or body
    const userId = getAuthenticatedUserId(req);
    if (!userId) {
      return res.status(400).json({ success: false, error: 'userId is required' });
    }
    
    const { muscle_group, window_weeks, include_distribution } = req.body || {};
    
    // Self-healing validation with recovery info
    const validation = validateMuscleGroupWithRecovery(muscle_group);
    if (!validation.valid) {
      return res.status(400).json({
        success: false,
        error: validation.message,
        validOptions: validation.validOptions,
        hint: 'Use one of the validOptions values for muscle_group',
      });
    }
    
    const weeks = Math.min(Math.max(1, window_weeks || CAPS.DEFAULT_WEEKS), CAPS.MAX_WEEKS);
    const weekIds = getRecentWeekStarts(weeks);
    
    // Get muscle group series
    const seriesRef = db.collection('users').doc(userId)
      .collection('series_muscle_groups').doc(muscle_group);
    const seriesDoc = await seriesRef.get();
    const weeklyPoints = extractWeeklyPoints(seriesDoc, weekIds);
    
    // Get top exercises by volume (from set_facts)
    const cutoffDate = weekIds[0];
    const exerciseQuery = db.collection('users').doc(userId)
      .collection('set_facts')
      .where('muscle_group_keys', 'array-contains', muscle_group)
      .where('workout_date', '>=', cutoffDate)
      .where('is_warmup', '==', false)
      .limit(500);
    
    const exerciseSnap = await exerciseQuery.get();
    const exerciseVolumes = new Map();
    
    for (const doc of exerciseSnap.docs) {
      const sf = doc.data();
      const exId = sf.exercise_id;
      const contrib = sf.muscle_group_contrib?.[muscle_group] || 0.5;
      const effVol = (sf.volume || 0) * contrib;
      
      if (!exerciseVolumes.has(exId)) {
        exerciseVolumes.set(exId, {
          exercise_id: exId,
          exercise_name: sf.exercise_name,
          effective_volume: 0,
          sets: 0,
        });
      }
      
      const entry = exerciseVolumes.get(exId);
      entry.effective_volume += effVol;
      entry.sets += 1;
    }
    
    // Sort by volume and take top 5
    const topExercises = Array.from(exerciseVolumes.values())
      .sort((a, b) => b.effective_volume - a.effective_volume)
      .slice(0, CAPS.MAX_TOP_EXERCISES)
      .map(e => ({
        exercise_id: e.exercise_id,
        exercise_name: e.exercise_name,
        effective_volume: Math.round(e.effective_volume * 10) / 10,
        sets: e.sets,
      }));
    
    // Compute summary stats
    const totalVolume = weeklyPoints.reduce((s, p) => s + (p.effective_volume || p.volume || 0), 0);
    const totalSets = weeklyPoints.reduce((s, p) => s + (p.sets || 0), 0);
    const totalHardSets = weeklyPoints.reduce((s, p) => s + (p.hard_sets || 0), 0);
    
    const avgWeeklyVolume = weeklyPoints.length > 0 ? totalVolume / weeklyPoints.length : 0;
    const avgWeeklySets = weeklyPoints.length > 0 ? totalSets / weeklyPoints.length : 0;
    
    // Detect flags
    const flags = {
      plateau: detectPlateau(weeklyPoints),
      deload: detectDeload(weeklyPoints),
      overreach: detectOverreach(weeklyPoints),
    };
    
    // Optional: include reps distribution
    let repDistribution = null;
    if (include_distribution) {
      repDistribution = {
        '1-5': 0,
        '6-10': 0,
        '11-15': 0,
        '16-20': 0,
      };
      for (const p of weeklyPoints) {
        if (p.reps_bucket) {
          for (const [bucket, count] of Object.entries(p.reps_bucket)) {
            repDistribution[bucket] = (repDistribution[bucket] || 0) + count;
          }
        }
      }
    }
    
    return res.json(buildResponse({
      muscle_group,
      display_name: getMuscleGroupDisplay(muscle_group),
      weekly_points: weeklyPoints,
      top_exercises: topExercises,
      summary: {
        total_weeks_with_data: weeklyPoints.length,
        avg_weekly_volume: Math.round(avgWeeklyVolume * 10) / 10,
        avg_weekly_sets: Math.round(avgWeeklySets * 10) / 10,
        avg_weekly_hard_sets: Math.round((totalHardSets / Math.max(weeklyPoints.length, 1)) * 10) / 10,
      },
      flags,
      reps_distribution: repDistribution,
    }, { limit: weeks }));
    
  } catch (error) {
    console.error('Error in getMuscleGroupSummary:', error);
    return res.status(500).json({ success: false, error: 'Internal error' });
  }
}));

/**
 * progress.muscle.summary
 * Summary for a specific muscle
 */
exports.getMuscleSummary = onRequest(requireFlexibleAuth(async (req, res) => {
  try {
    // Get userId from auth or body
    const userId = getAuthenticatedUserId(req);
    if (!userId) {
      return res.status(400).json({ success: false, error: 'userId is required' });
    }
    
    const { muscle, window_weeks } = req.body || {};
    
    // Self-healing validation with recovery info
    const validation = validateMuscleWithRecovery(muscle);
    if (!validation.valid) {
      return res.status(400).json({
        success: false,
        error: validation.message,
        validOptions: validation.validOptions,
        suggestions: validation.suggestions,
        hint: 'Use one of the suggestions or validOptions values for muscle',
      });
    }
    
    const weeks = Math.min(Math.max(1, window_weeks || CAPS.DEFAULT_WEEKS), CAPS.MAX_WEEKS);
    const weekIds = getRecentWeekStarts(weeks);
    
    // Get muscle series
    const seriesRef = db.collection('users').doc(userId)
      .collection('series_muscles').doc(muscle);
    const seriesDoc = await seriesRef.get();
    const weeklyPoints = extractWeeklyPoints(seriesDoc, weekIds);
    
    // Get top exercises for this muscle
    const cutoffDate = weekIds[0];
    const exerciseQuery = db.collection('users').doc(userId)
      .collection('set_facts')
      .where('muscle_keys', 'array-contains', muscle)
      .where('workout_date', '>=', cutoffDate)
      .where('is_warmup', '==', false)
      .limit(500);
    
    const exerciseSnap = await exerciseQuery.get();
    const exerciseVolumes = new Map();
    
    for (const doc of exerciseSnap.docs) {
      const sf = doc.data();
      const exId = sf.exercise_id;
      const contrib = sf.muscle_contrib?.[muscle] || 0.5;
      const effVol = (sf.volume || 0) * contrib;
      
      if (!exerciseVolumes.has(exId)) {
        exerciseVolumes.set(exId, {
          exercise_id: exId,
          exercise_name: sf.exercise_name,
          effective_volume: 0,
          sets: 0,
        });
      }
      
      const entry = exerciseVolumes.get(exId);
      entry.effective_volume += effVol;
      entry.sets += 1;
    }
    
    // Sort by volume and take top 5
    const topExercises = Array.from(exerciseVolumes.values())
      .sort((a, b) => b.effective_volume - a.effective_volume)
      .slice(0, CAPS.MAX_TOP_EXERCISES)
      .map(e => ({
        exercise_id: e.exercise_id,
        exercise_name: e.exercise_name,
        effective_volume: Math.round(e.effective_volume * 10) / 10,
        sets: e.sets,
      }));
    
    // Compute summary stats
    const totalVolume = weeklyPoints.reduce((s, p) => s + (p.effective_volume || p.volume || 0), 0);
    const totalSets = weeklyPoints.reduce((s, p) => s + (p.sets || 0), 0);
    
    // Detect flags
    const flags = {
      plateau: detectPlateau(weeklyPoints),
      deload: detectDeload(weeklyPoints),
      overreach: detectOverreach(weeklyPoints),
    };
    
    return res.json(buildResponse({
      muscle,
      display_name: getMuscleDisplay(muscle),
      weekly_points: weeklyPoints,
      top_exercises: topExercises,
      summary: {
        total_weeks_with_data: weeklyPoints.length,
        avg_weekly_volume: Math.round((totalVolume / Math.max(weeklyPoints.length, 1)) * 10) / 10,
        avg_weekly_sets: Math.round((totalSets / Math.max(weeklyPoints.length, 1)) * 10) / 10,
      },
      flags,
    }, { limit: weeks }));
    
  } catch (error) {
    console.error('Error in getMuscleSummary:', error);
    return res.status(500).json({ success: false, error: 'Internal error' });
  }
}));

/**
 * progress.exercise.summary
 * Summary for a specific exercise
 */
exports.getExerciseSummary = onRequest(requireFlexibleAuth(async (req, res) => {
  try {
    // Get userId from auth or body
    const userId = getAuthenticatedUserId(req);
    if (!userId) {
      return res.status(400).json({ success: false, error: 'userId is required' });
    }
    
    let { exercise_id, exercise_name, window_weeks } = req.body || {};

    // Resolve exercise_name to exercise_id via user's training history
    if (!exercise_id && exercise_name) {
      const nameQuery = exercise_name.toLowerCase().trim();
      const scan = await db.collection('users').doc(userId).collection('set_facts')
        .where('is_warmup', '==', false)
        .orderBy('workout_end_time', 'desc')
        .limit(200)
        .get();
      for (const doc of scan.docs) {
        const sf = doc.data();
        const name = (sf.exercise_name || '').toLowerCase();
        if (name.includes(nameQuery)) {
          exercise_id = sf.exercise_id;
          break;
        }
      }
    }

    if (!exercise_id) {
      return res.status(400).json({ success: false, error: 'exercise_id or exercise_name is required' });
    }
    
    const weeks = Math.min(Math.max(1, window_weeks || CAPS.DEFAULT_WEEKS), CAPS.MAX_WEEKS);
    const weekIds = getRecentWeekStarts(weeks);
    
    // Get exercise series
    const seriesRef = db.collection('users').doc(userId)
      .collection('series_exercises').doc(exercise_id);
    const seriesDoc = await seriesRef.get();
    const weeklyPoints = extractWeeklyPoints(seriesDoc, weekIds);
    
    // Get exercise name
    let exerciseName = null;
    try {
      const exDoc = await db.collection('exercises').doc(exercise_id).get();
      if (exDoc.exists) {
        exerciseName = exDoc.data().name;
      }
    } catch (e) {
      // Ignore
    }
    
    // Get last session recap (last 3 sets)
    const lastSessionQuery = db.collection('users').doc(userId)
      .collection('set_facts')
      .where('exercise_id', '==', exercise_id)
      .where('is_warmup', '==', false)
      .orderBy('workout_end_time', 'desc')
      .limit(10);
    
    const lastSnap = await lastSessionQuery.get();
    
    // Group by workout to get last session
    const workoutSets = new Map();
    for (const doc of lastSnap.docs) {
      const sf = doc.data();
      const wId = sf.workout_id;
      if (!workoutSets.has(wId)) {
        workoutSets.set(wId, []);
      }
      workoutSets.get(wId).push({
        set_index: sf.set_index,
        reps: sf.reps,
        weight_kg: sf.weight_kg,
        rir: sf.rir,
        e1rm: sf.e1rm,
      });
    }
    
    // Get first workout's sets (most recent) — all working sets
    let lastSessionSets = [];
    for (const [_, sets] of workoutSets) {
      lastSessionSets = sets.sort((a, b) => a.set_index - b.set_index);
      break;
    }
    
    // Find PR markers
    let allTimeE1rmMax = null;
    let windowE1rmMax = null;
    
    for (const p of weeklyPoints) {
      if (p.e1rm_max !== null && p.e1rm_max !== undefined) {
        if (windowE1rmMax === null || p.e1rm_max > windowE1rmMax) {
          windowE1rmMax = p.e1rm_max;
        }
      }
    }
    
    // All-time: check series doc
    if (seriesDoc.exists) {
      const data = seriesDoc.data();
      const weeks = data.weeks || {};
      for (const wk of Object.values(weeks)) {
        if (wk.e1rm_max !== null && wk.e1rm_max !== undefined) {
          if (allTimeE1rmMax === null || wk.e1rm_max > allTimeE1rmMax) {
            allTimeE1rmMax = wk.e1rm_max;
          }
        }
      }
    }
    
    // Detect plateau
    const flags = {
      plateau: detectPlateau(weeklyPoints),
    };
    
    return res.json(buildResponse({
      exercise_id,
      exercise_name: exerciseName,
      weekly_points: weeklyPoints,
      last_session: lastSessionSets,
      pr_markers: {
        all_time_e1rm: allTimeE1rmMax,
        window_e1rm: windowE1rmMax,
      },
      summary: {
        total_weeks_with_data: weeklyPoints.length,
        avg_weekly_volume: weeklyPoints.length > 0 
          ? Math.round((weeklyPoints.reduce((s, p) => s + (p.volume || 0), 0) / weeklyPoints.length) * 10) / 10
          : 0,
        avg_weekly_sets: weeklyPoints.length > 0
          ? Math.round((weeklyPoints.reduce((s, p) => s + (p.sets || 0), 0) / weeklyPoints.length) * 10) / 10
          : 0,
      },
      flags,
    }, { limit: weeks }));
    
  } catch (error) {
    console.error('Error in getExerciseSummary:', error);
    return res.status(500).json({ success: false, error: 'Internal error' });
  }
}));
