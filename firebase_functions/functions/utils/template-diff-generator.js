/**
 * =============================================================================
 * template-diff-generator.js - Compare workout vs template exercises
 * =============================================================================
 *
 * Pure function that generates a structured diff between what a template
 * prescribed and what the user actually did during the workout.
 *
 * Used by complete-active-workout.js to store template_diff on archived workouts.
 * The training analyst uses this to detect user self-progression.
 *
 * CALLED BY:
 * - complete-active-workout.js (during workout archival)
 *
 * =============================================================================
 */

/**
 * Generate a structured diff between workout exercises and template exercises.
 *
 * @param {Array} workoutExercises - Normalized workout exercises (from active workout)
 *   Each: { exercise_id, name, sets: [{ weight_kg, reps, rir, type }] }
 * @param {Array} templateExercises - Template exercises
 *   Each: { exercise_id, name, sets: [{ weight, reps, rir, type }] }
 * @returns {Object} template_diff structure
 */
function generateTemplateDiff(workoutExercises, templateExercises) {
  if (!workoutExercises || !templateExercises) {
    return { changes_detected: false };
  }

  const workoutExIds = workoutExercises.map(e => e.exercise_id);
  const templateExIds = templateExercises.map(e => e.exercise_id);

  // Build lookup maps
  const templateByExId = {};
  for (const tex of templateExercises) {
    templateByExId[tex.exercise_id] = tex;
  }
  const workoutByExId = {};
  for (const wex of workoutExercises) {
    workoutByExId[wex.exercise_id] = wex;
  }

  // Exercises added (in workout but not in template)
  const exercisesAdded = workoutExercises
    .filter(wex => !templateExIds.includes(wex.exercise_id))
    .map(wex => ({ exercise_id: wex.exercise_id, exercise_name: wex.name || wex.exercise_id }));

  // Exercises removed (in template but not in workout)
  const exercisesRemoved = templateExercises
    .filter(tex => !workoutExIds.includes(tex.exercise_id))
    .map(tex => ({ exercise_id: tex.exercise_id, exercise_name: tex.name || tex.exercise_id }));

  // Detect swaps: pair added+removed at same position index
  const exercisesSwapped = [];
  if (exercisesAdded.length > 0 && exercisesRemoved.length > 0) {
    // Simple heuristic: match by position
    for (let i = 0; i < Math.min(workoutExercises.length, templateExercises.length); i++) {
      const wex = workoutExercises[i];
      const tex = templateExercises[i];
      if (wex.exercise_id !== tex.exercise_id &&
          !templateExIds.includes(wex.exercise_id) &&
          !workoutExIds.includes(tex.exercise_id)) {
        exercisesSwapped.push({
          from_id: tex.exercise_id,
          from_name: tex.name || tex.exercise_id,
          to_id: wex.exercise_id,
          to_name: wex.name || wex.exercise_id
        });
      }
    }
  }

  // Filter swapped exercises out of added/removed to avoid redundant entries
  if (exercisesSwapped.length > 0) {
    const swappedFromIds = new Set(exercisesSwapped.map(s => s.from_id));
    const swappedToIds = new Set(exercisesSwapped.map(s => s.to_id));
    const filteredAdded = exercisesAdded.filter(e => !swappedToIds.has(e.exercise_id));
    const filteredRemoved = exercisesRemoved.filter(e => !swappedFromIds.has(e.exercise_id));
    exercisesAdded.length = 0;
    exercisesAdded.push(...filteredAdded);
    exercisesRemoved.length = 0;
    exercisesRemoved.push(...filteredRemoved);
  }

  // Exercise reorder: compare order of common exercises
  const commonWorkoutOrder = workoutExIds.filter(id => templateExIds.includes(id));
  const commonTemplateOrder = templateExIds.filter(id => workoutExIds.includes(id));
  const exercisesReordered = JSON.stringify(commonWorkoutOrder) !== JSON.stringify(commonTemplateOrder);

  // Weight and rep changes for matched exercises
  const weightChanges = [];
  const repChanges = [];
  let setsAddedCount = 0;
  let setsRemovedCount = 0;

  for (const wex of workoutExercises) {
    const tex = templateByExId[wex.exercise_id];
    if (!tex) continue; // New exercise, not a change

    const workoutSets = wex.sets || [];
    const templateSets = tex.sets || [];

    // Track set count differences
    if (workoutSets.length > templateSets.length) {
      setsAddedCount += workoutSets.length - templateSets.length;
    } else if (templateSets.length > workoutSets.length) {
      setsRemovedCount += templateSets.length - workoutSets.length;
    }

    // Compare matched sets by index
    const compareCount = Math.min(workoutSets.length, templateSets.length);
    let maxWeightDelta = 0;
    let weightDirection = null;
    let maxRepDelta = 0;
    let repDirection = null;

    for (let i = 0; i < compareCount; i++) {
      const ws = workoutSets[i];
      const ts = templateSets[i];

      // Weight comparison (workout uses weight_kg, template uses weight)
      const workoutWeight = typeof ws.weight_kg === 'number' ? ws.weight_kg : (typeof ws.weight === 'number' ? ws.weight : 0);
      const templateWeight = typeof ts.weight === 'number' ? ts.weight : (typeof ts.weight_kg === 'number' ? ts.weight_kg : 0);
      const wDelta = workoutWeight - templateWeight;

      if (Math.abs(wDelta) > 0.01) {
        if (Math.abs(wDelta) > Math.abs(maxWeightDelta)) {
          maxWeightDelta = wDelta;
          weightDirection = wDelta > 0 ? 'increased' : 'decreased';
        }
      }

      // Rep comparison
      const workoutReps = typeof ws.reps === 'number' ? ws.reps : 0;
      const templateReps = typeof ts.reps === 'number' ? ts.reps : 0;
      const rDelta = workoutReps - templateReps;

      if (Math.abs(rDelta) > 0) {
        if (Math.abs(rDelta) > Math.abs(maxRepDelta)) {
          maxRepDelta = rDelta;
          repDirection = rDelta > 0 ? 'increased' : 'decreased';
        }
      }
    }

    if (weightDirection) {
      weightChanges.push({
        exercise_id: wex.exercise_id,
        exercise_name: wex.name || wex.exercise_id,
        direction: weightDirection,
        max_delta_kg: Math.round(Math.abs(maxWeightDelta) * 100) / 100
      });
    }

    if (repDirection) {
      repChanges.push({
        exercise_id: wex.exercise_id,
        exercise_name: wex.name || wex.exercise_id,
        direction: repDirection,
        max_delta: Math.abs(maxRepDelta)
      });
    }
  }

  // Check if any changes were detected
  const changesDetected =
    exercisesAdded.length > 0 ||
    exercisesRemoved.length > 0 ||
    exercisesSwapped.length > 0 ||
    exercisesReordered ||
    weightChanges.length > 0 ||
    repChanges.length > 0 ||
    setsAddedCount > 0 ||
    setsRemovedCount > 0;

  if (!changesDetected) {
    return { changes_detected: false };
  }

  // Generate summary string
  const summaryParts = [];
  for (const swap of exercisesSwapped) {
    summaryParts.push(`Swapped ${swap.from_name} → ${swap.to_name}`);
  }
  for (const wc of weightChanges) {
    const sign = wc.direction === 'increased' ? '+' : '-';
    summaryParts.push(`${wc.direction} ${wc.exercise_name} ${sign}${wc.max_delta_kg}kg`);
  }
  for (const rc of repChanges) {
    const sign = rc.direction === 'increased' ? '+' : '-';
    summaryParts.push(`${rc.exercise_name} reps ${sign}${rc.max_delta}`);
  }
  if (exercisesAdded.length > 0) {
    summaryParts.push(`Added ${exercisesAdded.map(e => e.exercise_name).join(', ')}`);
  }
  if (exercisesRemoved.length > 0) {
    summaryParts.push(`Removed ${exercisesRemoved.map(e => e.exercise_name).join(', ')}`);
  }
  if (exercisesReordered && summaryParts.length === 0) {
    summaryParts.push('Reordered exercises');
  }

  return {
    changes_detected: true,
    exercises_added: exercisesAdded,
    exercises_removed: exercisesRemoved,
    exercises_swapped: exercisesSwapped,
    exercises_reordered: exercisesReordered,
    weight_changes: weightChanges,
    rep_changes: repChanges,
    sets_added_count: setsAddedCount,
    sets_removed_count: setsRemovedCount,
    summary: summaryParts.join(', ')
  };
}

module.exports = { generateTemplateDiff };
