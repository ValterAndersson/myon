/**
 * Shared helpers for active workout mutation endpoints.
 *
 * Extracted from log-set.js, patch-active-workout.js, and autofill-exercise.js
 * to eliminate duplication. All four hot-path endpoints use these.
 */

/**
 * Compute totals from exercises array.
 * Rules:
 * - Only count sets with status: 'done'
 * - Only count set_type: 'working' or 'dropset' (exclude warmups)
 * - Volume = sum of weight * reps (null weight = 0 contribution)
 */
function computeTotals(exercises) {
  let totalSets = 0;
  let totalReps = 0;
  let totalVolume = 0;

  for (const exercise of exercises) {
    for (const set of exercise.sets || []) {
      if (set.status !== 'done') continue;
      if (set.set_type !== 'working' && set.set_type !== 'dropset') continue;

      totalSets += 1;
      totalReps += set.reps || 0;

      if (set.weight !== null && set.weight !== undefined) {
        totalVolume += (set.weight * (set.reps || 0));
      }
    }
  }

  return {
    sets: totalSets,
    reps: totalReps,
    volume: totalVolume,
  };
}

/**
 * Find exercise by instance_id.
 * @returns {{ index: number, exercise: object } | null}
 */
function findExercise(exercises, exerciseInstanceId) {
  for (let idx = 0; idx < exercises.length; idx++) {
    if (exercises[idx].instance_id === exerciseInstanceId) {
      return { index: idx, exercise: exercises[idx] };
    }
  }
  return null;
}

/**
 * Find set within exercise by set_id.
 * @returns {{ index: number, set: object } | null}
 */
function findSet(exercise, setId) {
  for (let idx = 0; idx < (exercise.sets || []).length; idx++) {
    if (exercise.sets[idx].id === setId) {
      return { index: idx, set: exercise.sets[idx] };
    }
  }
  return null;
}

/**
 * Find exercise and set by stable IDs (convenience for log-set).
 * @returns {{ exerciseIndex: number, setIndex: number, exercise: object, set: object } | null}
 */
function findExerciseAndSet(exercises, exerciseInstanceId, setId) {
  for (let exIdx = 0; exIdx < exercises.length; exIdx++) {
    const exercise = exercises[exIdx];
    if (exercise.instance_id === exerciseInstanceId) {
      for (let setIdx = 0; setIdx < (exercise.sets || []).length; setIdx++) {
        const set = exercise.sets[setIdx];
        if (set.id === setId) {
          return { exerciseIndex: exIdx, setIndex: setIdx, exercise, set };
        }
      }
    }
  }
  return null;
}

module.exports = { computeTotals, findExercise, findSet, findExerciseAndSet };
