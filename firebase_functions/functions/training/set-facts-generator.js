/**
 * Set Facts Generator
 * Generates set_fact documents from workout data
 * 
 * @see docs/TRAINING_ANALYTICS_API_V2_SPEC.md Section 2.2
 */

const { FieldValue } = require('firebase-admin/firestore');
const { getMuscleContributions, canonicalizeGroup } = require('../utils/muscle-taxonomy');
const { getWeekStart, formatDate, getRepsBucket, CAPS } = require('../utils/caps');

/**
 * Compute e1RM using Epley formula
 * Only computed for sets with reps <= 12
 * @param {number} weight - Weight in kg
 * @param {number} reps - Rep count
 * @returns {number|null} - Estimated 1RM or null
 */
function computeE1rm(weight, reps) {
  if (!weight || !reps || reps > 12) return null;
  if (reps === 1) return weight;
  
  // Epley formula: weight * (1 + reps/30)
  return Math.round(weight * (1 + reps / 30) * 10) / 10;
}

/**
 * Compute e1RM confidence based on rep range
 * @param {number} reps - Rep count
 * @returns {number|null} - Confidence 0-1 or null
 */
function computeE1rmConfidence(reps) {
  if (reps === 1) return 1.0;
  if (reps <= 3) return 0.95;
  if (reps <= 6) return 0.90;
  if (reps <= 10) return 0.80;
  if (reps <= 12) return 0.70;
  return null;
}

/**
 * Compute hard set credit based on RIR/failure
 * @param {number|null} rir - Reps in reserve
 * @param {boolean} isWarmup - Whether this is a warmup set
 * @param {boolean} isFailure - Whether this was a failure set
 * @returns {number} - Credit 0-1
 */
function computeHardSetCredit(rir, isWarmup, isFailure) {
  if (isWarmup) return 0;
  if (isFailure || rir === 0) return 1.0;
  if (rir !== null && rir <= 2) return 1.0;
  if (rir !== null && rir <= 4) return 0.5;
  
  // If no RIR data, assume working set = 0.75 credit
  if (rir === null || rir === undefined) return 0.75;
  
  return 0;
}

/**
 * Normalize weight to kg
 * @param {number} weight - Weight value
 * @param {string} unit - Unit ('kg' or 'lbs')
 * @returns {number} - Weight in kg
 */
function normalizeWeightToKg(weight, unit) {
  if (!weight) return 0;
  if (unit === 'lbs' || unit === 'lb') {
    return Math.round(weight * 0.453592 * 10) / 10;
  }
  return weight;
}

/**
 * Generate deterministic set_id
 * @param {string} workoutId 
 * @param {string} exerciseId 
 * @param {number} setIndex 
 * @returns {string}
 */
function generateSetId(workoutId, exerciseId, setIndex) {
  return `${workoutId}_${exerciseId}_${setIndex}`;
}

/**
 * Generate a single set_fact document from set data
 * @param {Object} params - Parameters
 * @param {string} params.userId - User ID
 * @param {string} params.workoutId - Workout ID
 * @param {Date|Timestamp} params.workoutEndTime - Workout end time
 * @param {Object} params.exercise - Exercise object with metadata
 * @param {Object} params.set - Set object with performance data
 * @param {number} params.setIndex - Index of this set
 * @param {string} params.weightUnit - Weight unit ('kg' or 'lbs')
 * @returns {Object} - set_fact document
 */
function generateSetFact({
  userId,
  workoutId,
  workoutEndTime,
  exercise,
  set,
  setIndex,
  weightUnit = 'kg',
}) {
  const endTime = workoutEndTime instanceof Date ? workoutEndTime : workoutEndTime.toDate();
  // Handle both set.weight_kg (already in kg) and set.weight (needs unit conversion)
  const rawWeight = set.weight_kg ?? set.weightKg ?? set.weight ?? 0;
  // If weight_kg is used, it's already in kg, skip conversion
  const weightKg = (set.weight_kg !== undefined || set.weightKg !== undefined)
    ? rawWeight
    : normalizeWeightToKg(rawWeight, weightUnit);
  const reps = set.reps || 0;
  const volume = reps * weightKg;
  const isWarmup = set.is_warmup || set.isWarmup || false;
  const isFailure = set.is_failure || set.isFailure || false;
  const rir = set.rir ?? null;
  const rpe = set.rpe ?? null;
  
  // Compute strength proxies
  const e1rm = computeE1rm(weightKg, reps);
  const e1rmConfidence = computeE1rmConfidence(reps);
  
  // Compute hard set credit
  const hardSetCredit = computeHardSetCredit(rir, isWarmup, isFailure);
  
  // Get muscle contributions
  const contrib = getMuscleContributions(exercise);
  const rawMuscleGroupContrib = contrib.groups || {};
  const rawMuscleContrib = contrib.muscles || {};
  
  // Normalize muscle group and muscle keys to lowercase (canonical form)
  const muscleGroupContrib = {};
  const muscleContrib = {};
  
  for (const [group, weight] of Object.entries(rawMuscleGroupContrib)) {
    const normalizedGroup = group.toLowerCase().replace(/[\s-]/g, '_');
    muscleGroupContrib[normalizedGroup] = weight;
  }
  
  for (const [muscle, weight] of Object.entries(rawMuscleContrib)) {
    const normalizedMuscle = muscle.toLowerCase().replace(/[\s-]/g, '_');
    muscleContrib[normalizedMuscle] = weight;
  }
  
  // Compute effective volumes and hard set credits by target
  const effectiveVolumeByGroup = {};
  const effectiveVolumeByMuscle = {};
  const hardSetCreditByGroup = {};
  const hardSetCreditByMuscle = {};
  
  for (const [group, weight] of Object.entries(muscleGroupContrib)) {
    effectiveVolumeByGroup[group] = Math.round(volume * weight * 10) / 10;
    hardSetCreditByGroup[group] = Math.round(hardSetCredit * weight * 100) / 100;
  }
  
  for (const [muscle, weight] of Object.entries(muscleContrib)) {
    effectiveVolumeByMuscle[muscle] = Math.round(volume * weight * 10) / 10;
    hardSetCreditByMuscle[muscle] = Math.round(hardSetCredit * weight * 100) / 100;
  }
  
  // Generate filter arrays for Firestore queries
  const muscleGroupKeys = Object.keys(muscleGroupContrib);
  const muscleKeys = Object.keys(muscleContrib);
  
  // Determine set_id
  const setId = generateSetId(workoutId, exercise.exercise_id || exercise.exerciseId || exercise.id, setIndex);
  
  return {
    // Identity
    set_id: setId,
    user_id: userId,
    workout_id: workoutId,
    workout_end_time: workoutEndTime,
    workout_date: formatDate(endTime),
    exercise_id: exercise.exercise_id || exercise.exerciseId || exercise.id,
    exercise_name: exercise.exercise_name || exercise.exerciseName || exercise.name,
    set_index: setIndex,
    
    // Set performance
    reps,
    weight_kg: weightKg,
    rir,
    rpe,
    is_warmup: isWarmup,
    is_failure: isFailure,
    volume,
    
    // Strength proxy
    e1rm,
    e1rm_formula: e1rm !== null ? 'epley' : null,
    e1rm_confidence: e1rmConfidence,
    
    // Classification
    equipment: exercise.equipment || 'unknown',
    movement_pattern: exercise.movement_pattern || exercise.movementPattern || 'unknown',
    is_isolation: exercise.is_isolation || exercise.isIsolation || false,
    side: exercise.side || 'bilateral',
    
    // Attribution maps
    muscle_group_contrib: muscleGroupContrib,
    muscle_contrib: muscleContrib,
    effective_volume_by_group: effectiveVolumeByGroup,
    effective_volume_by_muscle: effectiveVolumeByMuscle,
    hard_set_credit_by_group: hardSetCreditByGroup,
    hard_set_credit_by_muscle: hardSetCreditByMuscle,
    
    // Filter arrays
    muscle_group_keys: muscleGroupKeys,
    muscle_keys: muscleKeys,
    
    // Timestamps
    created_at: FieldValue.serverTimestamp(),
    updated_at: FieldValue.serverTimestamp(),
    
    // Internal
    hard_set_credit: hardSetCredit,
  };
}

/**
 * Generate all set_facts for a completed workout
 * @param {Object} params - Parameters
 * @param {string} params.userId - User ID
 * @param {Object} params.workout - Workout document
 * @returns {Object[]} - Array of set_fact documents
 */
function generateSetFactsForWorkout({ userId, workout }) {
  const setFacts = [];
  const workoutId = workout.id || workout.workout_id;
  const workoutEndTime = workout.end_time || workout.endTime || workout.completed_at || new Date();
  const weightUnit = workout.weight_unit || workout.weightUnit || 'kg';
  
  const exercises = workout.exercises || [];
  
  for (const exercise of exercises) {
    const sets = exercise.sets || [];
    let setIndex = 0;
    
    for (const set of sets) {
      // Skip sets that aren't completed
      if (set.is_completed === false || set.isCompleted === false) {
        continue;
      }
      
      const setFact = generateSetFact({
        userId,
        workoutId,
        workoutEndTime,
        exercise,
        set,
        setIndex,
        weightUnit,
      });
      
      setFacts.push(setFact);
      setIndex++;
    }
  }
  
  return setFacts;
}

/**
 * Aggregate set_facts into deltas for series updates
 * @param {Object[]} setFacts - Array of set_fact documents
 * @param {string} weekId - Week start date YYYY-MM-DD
 * @returns {Object} - { exerciseDeltas, muscleGroupDeltas, muscleDeltas }
 */
function aggregateSetFactsForSeries(setFacts, weekId) {
  const exerciseDeltas = new Map();
  const muscleGroupDeltas = new Map();
  const muscleDeltas = new Map();
  
  for (const sf of setFacts) {
    // Skip warmups for series aggregation
    if (sf.is_warmup) continue;
    
    const repsBucket = getRepsBucket(sf.reps);
    
    // Aggregate to exercise - include exercise_name for agent readability
    aggregateDelta(exerciseDeltas, sf.exercise_id, {
      sets: 1,
      hard_sets: sf.hard_set_credit,
      volume: sf.volume,
      rir_sum: sf.rir ?? 0,
      rir_count: sf.rir !== null ? 1 : 0,
      rir_min: sf.rir,  // Track min RIR (closest to failure)
      rir_max: sf.rir,  // Track max RIR (most conservative)
      load_min: sf.weight_kg > 0 ? sf.weight_kg : null,  // Track load range
      load_max: sf.weight_kg > 0 ? sf.weight_kg : null,
      failure_sets: sf.is_failure ? 1 : 0,
      set_count: 1,
      e1rm_max: sf.e1rm,
      [`reps_bucket_${repsBucket}`]: 1,
      // Metadata for agent readability
      exercise_name: sf.exercise_name,
    });
    
    // Aggregate to muscle groups
    for (const [group, contrib] of Object.entries(sf.muscle_group_contrib)) {
      aggregateDelta(muscleGroupDeltas, group, {
        sets: 1,
        hard_sets: sf.hard_set_credit * contrib,
        volume: sf.volume * contrib,
        effective_volume: sf.volume * contrib,
        rir_sum: (sf.rir ?? 0) * contrib,
        rir_count: sf.rir !== null ? 1 : 0,
        rir_min: sf.rir,
        rir_max: sf.rir,
        load_min: sf.weight_kg > 0 ? sf.weight_kg : null,
        load_max: sf.weight_kg > 0 ? sf.weight_kg : null,
        failure_sets: sf.is_failure ? 1 : 0,
        set_count: 1,
        [`reps_bucket_${repsBucket}`]: 1,
      });
    }
    
    // Aggregate to muscles
    for (const [muscle, contrib] of Object.entries(sf.muscle_contrib)) {
      aggregateDelta(muscleDeltas, muscle, {
        sets: 1,
        hard_sets: sf.hard_set_credit * contrib,
        volume: sf.volume * contrib,
        effective_volume: sf.volume * contrib,
        rir_sum: (sf.rir ?? 0) * contrib,
        rir_count: sf.rir !== null ? 1 : 0,
        rir_min: sf.rir,
        rir_max: sf.rir,
        load_min: sf.weight_kg > 0 ? sf.weight_kg : null,
        load_max: sf.weight_kg > 0 ? sf.weight_kg : null,
        failure_sets: sf.is_failure ? 1 : 0,
        set_count: 1,
        [`reps_bucket_${repsBucket}`]: 1,
      });
    }
  }
  
  return { exerciseDeltas, muscleGroupDeltas, muscleDeltas };
}

/**
 * Accumulate delta values into a map
 */
function aggregateDelta(map, key, values) {
  if (!map.has(key)) {
    map.set(key, { ...values });
    return;
  }
  
  const existing = map.get(key);
  for (const [field, value] of Object.entries(values)) {
    if (field === 'e1rm_max' || field === 'load_max' || field === 'rir_max') {
      // Max tracking
      if (value !== null && (existing[field] === null || existing[field] === undefined || value > existing[field])) {
        existing[field] = value;
      }
    } else if (field === 'load_min' || field === 'rir_min') {
      // Min tracking (null means no data, ignore)
      if (value !== null && (existing[field] === null || existing[field] === undefined || value < existing[field])) {
        existing[field] = value;
      }
    } else if (field === 'exercise_name') {
      // String field - keep first non-null value
      if (!existing[field] && value) {
        existing[field] = value;
      }
    } else {
      // Sum tracking
      existing[field] = (existing[field] || 0) + value;
    }
  }
}

/**
 * Build Firestore update object for series with FieldValue.increment
 * @param {string} weekId - Week start YYYY-MM-DD
 * @param {Object} delta - Aggregated delta values
 * @param {number} sign - 1 for add, -1 for delete
 * @returns {Object} - Firestore update object
 */
function buildSeriesUpdate(weekId, delta, sign = 1, isExerciseSeries = false) {
  const update = {
    [`weeks.${weekId}.sets`]: FieldValue.increment((delta.sets || 0) * sign),
    [`weeks.${weekId}.hard_sets`]: FieldValue.increment((delta.hard_sets || 0) * sign),
    [`weeks.${weekId}.volume`]: FieldValue.increment((delta.volume || 0) * sign),
    [`weeks.${weekId}.rir_sum`]: FieldValue.increment((delta.rir_sum || 0) * sign),
    [`weeks.${weekId}.rir_count`]: FieldValue.increment((delta.rir_count || 0) * sign),
    [`weeks.${weekId}.failure_sets`]: FieldValue.increment((delta.failure_sets || 0) * sign),
    [`weeks.${weekId}.set_count`]: FieldValue.increment((delta.set_count || 0) * sign),
    [`weeks.${weekId}.reps_bucket.1-5`]: FieldValue.increment((delta['reps_bucket_1-5'] || 0) * sign),
    [`weeks.${weekId}.reps_bucket.6-10`]: FieldValue.increment((delta['reps_bucket_6-10'] || 0) * sign),
    [`weeks.${weekId}.reps_bucket.11-15`]: FieldValue.increment((delta['reps_bucket_11-15'] || 0) * sign),
    [`weeks.${weekId}.reps_bucket.16-20`]: FieldValue.increment((delta['reps_bucket_16-20'] || 0) * sign),
    updated_at: FieldValue.serverTimestamp(),
  };
  
  // effective_volume for muscle/muscle_group series
  if (delta.effective_volume !== undefined) {
    update[`weeks.${weekId}.effective_volume`] = FieldValue.increment((delta.effective_volume || 0) * sign);
  }
  
  // For exercise series, add exercise_name at top level for agent readability
  if (isExerciseSeries && delta.exercise_name) {
    update.exercise_name = delta.exercise_name;
  }
  
  return update;
}

/**
 * Build min/max update for series (must be done via transaction or set)
 * This returns the min/max fields that need to be updated
 * @param {string} weekId - Week start YYYY-MM-DD
 * @param {Object} delta - Aggregated delta values
 * @returns {Object} - Fields to merge
 */
function buildMinMaxUpdate(weekId, delta) {
  const update = {};
  
  if (delta.load_min !== null && delta.load_min !== undefined) {
    update[`weeks.${weekId}.load_min`] = delta.load_min;
    update[`weeks.${weekId}.load_max`] = delta.load_max;
  }
  
  if (delta.rir_min !== null && delta.rir_min !== undefined) {
    update[`weeks.${weekId}.rir_min`] = delta.rir_min;
    update[`weeks.${weekId}.rir_max`] = delta.rir_max;
  }
  
  return update;
}

/**
 * Write set_facts to Firestore in chunks
 * @param {Object} db - Firestore instance
 * @param {string} userId - User ID
 * @param {Object[]} setFacts - Array of set_fact documents
 */
async function writeSetFactsInChunks(db, userId, setFacts) {
  const BATCH_LIMIT = CAPS.FIRESTORE_BATCH_LIMIT;
  
  for (let i = 0; i < setFacts.length; i += BATCH_LIMIT) {
    const chunk = setFacts.slice(i, i + BATCH_LIMIT);
    const batch = db.batch();
    
    for (const sf of chunk) {
      const ref = db.collection('users').doc(userId)
        .collection('set_facts').doc(sf.set_id);
      batch.set(ref, sf, { merge: true });
    }
    
    await batch.commit();
  }
}

/**
 * Update all series documents for a workout
 * @param {Object} db - Firestore instance
 * @param {string} userId - User ID
 * @param {Object} workout - Workout document
 * @param {number} sign - 1 for create, -1 for delete
 */
async function updateSeriesForWorkout(db, userId, workout, sign = 1) {
  const setFacts = generateSetFactsForWorkout({ userId, workout });
  
  const workoutEndTime = workout.end_time || workout.endTime || workout.completed_at || new Date();
  const endTimeDate = workoutEndTime instanceof Date ? workoutEndTime : workoutEndTime.toDate();
  const weekId = getWeekStart(endTimeDate);
  
  const { exerciseDeltas, muscleGroupDeltas, muscleDeltas } = aggregateSetFactsForSeries(setFacts, weekId);
  
  // Collect all operations
  const operations = [];
  
  for (const [exerciseId, delta] of exerciseDeltas) {
    operations.push({
      ref: db.collection('users').doc(userId).collection('series_exercises').doc(exerciseId),
      delta,
      hasE1rmMax: true,
      isExercise: true,
    });
  }
  
  for (const [group, delta] of muscleGroupDeltas) {
    operations.push({
      ref: db.collection('users').doc(userId).collection('series_muscle_groups').doc(group),
      delta,
      hasE1rmMax: false,
      isExercise: false,
    });
  }
  
  for (const [muscle, delta] of muscleDeltas) {
    operations.push({
      ref: db.collection('users').doc(userId).collection('series_muscles').doc(muscle),
      delta,
      hasE1rmMax: false,
      isExercise: false,
    });
  }
  
  // Write in chunks
  const BATCH_LIMIT = CAPS.FIRESTORE_BATCH_LIMIT;
  
  for (let i = 0; i < operations.length; i += BATCH_LIMIT) {
    const chunk = operations.slice(i, i + BATCH_LIMIT);
    const batch = db.batch();
    
    for (const op of chunk) {
      const update = buildSeriesUpdate(weekId, op.delta, sign, op.isExercise);
      batch.set(op.ref, update, { merge: true });
    }
    
    await batch.commit();
  }
  
  // Update min/max values via separate transaction (only on creates)
  if (sign === 1) {
    for (const op of operations) {
      await updateMinMaxForSeries(db, op.ref, weekId, op.delta);
    }
  }
  
  // Handle e1rm_max updates separately (for creates only)
  if (sign === 1) {
    for (const [exerciseId, delta] of exerciseDeltas) {
      if (delta.e1rm_max !== null) {
        await updateE1rmMax(db, userId, exerciseId, weekId, delta.e1rm_max);
      }
    }
  }
}

/**
 * Update e1rm_max via transaction (only on create, not delete)
 * @param {Object} db - Firestore instance
 * @param {string} userId - User ID
 * @param {string} exerciseId - Exercise ID
 * @param {string} weekId - Week start YYYY-MM-DD
 * @param {number} newE1rm - New e1RM value
 */
async function updateE1rmMax(db, userId, exerciseId, weekId, newE1rm) {
  if (newE1rm === null) return;
  
  const ref = db.collection('users').doc(userId)
    .collection('series_exercises').doc(exerciseId);
  
  try {
    await db.runTransaction(async (tx) => {
      const doc = await tx.get(ref);
      const currentMax = doc.data()?.weeks?.[weekId]?.e1rm_max || 0;
      
      if (newE1rm > currentMax) {
        tx.set(ref, {
          [`weeks.${weekId}.e1rm_max`]: newE1rm,
          updated_at: FieldValue.serverTimestamp(),
        }, { merge: true });
      }
    });
  } catch (err) {
    console.warn('e1rm_max update failed:', err.message);
  }
}

/**
 * Update min/max values for a series document via transaction
 * @param {Object} db - Firestore instance
 * @param {Object} ref - Document reference
 * @param {string} weekId - Week start YYYY-MM-DD
 * @param {Object} delta - Delta with min/max values
 */
async function updateMinMaxForSeries(db, ref, weekId, delta) {
  const minMaxUpdate = buildMinMaxUpdate(weekId, delta);
  if (Object.keys(minMaxUpdate).length === 0) return;
  
  try {
    await db.runTransaction(async (tx) => {
      const doc = await tx.get(ref);
      const existing = doc.data()?.weeks?.[weekId] || {};
      
      const updates = {};
      
      // Load min - only update if new value is lower (or no existing value)
      if (delta.load_min !== null && delta.load_min !== undefined) {
        if (existing.load_min === undefined || existing.load_min === null || delta.load_min < existing.load_min) {
          updates[`weeks.${weekId}.load_min`] = delta.load_min;
        }
        if (existing.load_max === undefined || existing.load_max === null || delta.load_max > existing.load_max) {
          updates[`weeks.${weekId}.load_max`] = delta.load_max;
        }
      }
      
      // RIR min - only update if new value is lower
      if (delta.rir_min !== null && delta.rir_min !== undefined) {
        if (existing.rir_min === undefined || existing.rir_min === null || delta.rir_min < existing.rir_min) {
          updates[`weeks.${weekId}.rir_min`] = delta.rir_min;
        }
        if (existing.rir_max === undefined || existing.rir_max === null || delta.rir_max > existing.rir_max) {
          updates[`weeks.${weekId}.rir_max`] = delta.rir_max;
        }
      }
      
      if (Object.keys(updates).length > 0) {
        updates.updated_at = FieldValue.serverTimestamp();
        tx.set(ref, updates, { merge: true });
      }
    });
  } catch (err) {
    console.warn('min/max update failed:', err.message);
  }
}

module.exports = {
  computeE1rm,
  computeE1rmConfidence,
  computeHardSetCredit,
  normalizeWeightToKg,
  generateSetId,
  generateSetFact,
  generateSetFactsForWorkout,
  aggregateSetFactsForSeries,
  buildSeriesUpdate,
  buildMinMaxUpdate,
  writeSetFactsInChunks,
  updateSeriesForWorkout,
  updateE1rmMax,
  updateMinMaxForSeries,
};
