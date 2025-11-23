const admin = require('firebase-admin');

// Initialize admin if not already initialized
if (!admin.apps.length) {
  admin.initializeApp();
}

const db = admin.firestore();

/**
 * Helper to determine if a set is a working set
 */
function isWorkingSet(type) {
  // If type is undefined or not a string, assume it is a working set (default)
  if (!type || typeof type !== 'string') {
    return true;
  }

  const workingSetTypes = [
    'working set',
    'working',
    'main',
    'drop set',
    'dropset',
    'failure set',
    'failure',
    'top set',
    'backoff set',
    'straight',
    'drop-set'
  ];

  return workingSetTypes.includes(type.toLowerCase());
}

function estimateE1RM(weightKg, reps) {
  if (typeof weightKg !== 'number' || typeof reps !== 'number' || weightKg <= 0 || reps <= 0) {
    return 0;
  }
  if (reps === 1) return weightKg;
  return weightKg * (1 + reps / 30);
}

function computeRelativeIntensity(weightKg, reps) {
  const e1rm = estimateE1RM(weightKg, reps);
  if (!e1rm) return 0;
  return Math.min(1, Math.max(0, weightKg / e1rm));
}

function isStimulusSet(set) {
  if (!set || typeof set !== 'object') return false;
  if (!set.is_completed) return false;
  if (!isWorkingSet(set.type)) return false;
  if (typeof set.reps !== 'number' || set.reps < 5 || set.reps > 20) return false;
  if (typeof set.rir !== 'number' || set.rir < 0 || set.rir > 5) return false;
  return set.rir <= 3;
}

function addToMap(target, key, delta) {
  if (!target || !key || typeof delta !== 'number' || Number.isNaN(delta)) return;
  target[key] = (target[key] || 0) + delta;
  if (Math.abs(target[key]) < 1e-6) {
    delete target[key];
  }
}

function normalizeMuscleKey(name) {
  if (!name || typeof name !== 'string') return null;
  const trimmed = name.trim();
  if (!trimmed) return null;
  return trimmed.toLowerCase().replace(/\s+/g, ' ');
}

/**
 * Calculate template analytics similar to Swift's StimulusCalculator
 */
async function calculateTemplateAnalytics(template) {
  let totalSets = 0;
  let totalReps = 0;
  let projectedVolume = 0;
  const projectedVolumePerMuscleGroup = {};
  const projectedVolumePerMuscle = {};
  const setsPerMuscleGroup = {};
  const setsPerMuscle = {};
  const repsPerMuscleGroup = {};
  const repsPerMuscle = {};

  // Get exercise data needed for calculations
  const exerciseIds = template.exercises.map(ex => ex.exercise_id).filter(Boolean);
  const exercisePromises = exerciseIds.map(id => 
    db.collection('exercises').doc(id).get()
  );
  const exerciseSnapshots = await Promise.all(exercisePromises);
  const exercises = exerciseSnapshots
    .filter(snap => snap.exists)
    .map(snap => ({ id: snap.id, ...snap.data() }));

  for (const templateExercise of template.exercises) {
    const exercise = exercises.find(ex => ex.id === templateExercise.exercise_id);
    if (!exercise) continue;

    // Filter working sets
    const workingSets = templateExercise.sets.filter(set => isWorkingSet(set.type));
    const exerciseSets = workingSets.length;
    const exerciseReps = workingSets.reduce((sum, set) => sum + set.reps, 0);
    const exerciseVolume = workingSets.reduce((sum, set) => sum + (set.weight * set.reps), 0);

    totalSets += exerciseSets;
    totalReps += exerciseReps;
    projectedVolume += exerciseVolume;

    // Distribute across muscle groups (categories)
    const muscleCategories = exercise.muscles?.category || [];
    for (const category of muscleCategories) {
      setsPerMuscleGroup[category] = (setsPerMuscleGroup[category] || 0) + exerciseSets;
      const categoryVolume = exerciseVolume / muscleCategories.length;
      const categoryReps = exerciseReps / muscleCategories.length;
      projectedVolumePerMuscleGroup[category] = (projectedVolumePerMuscleGroup[category] || 0) + categoryVolume;
      repsPerMuscleGroup[category] = (repsPerMuscleGroup[category] || 0) + categoryReps;
    }

    // Distribute across individual muscles using contributions
    const muscleContributions = exercise.muscles?.contribution || {};
    for (const [muscle, contribution] of Object.entries(muscleContributions)) {
      setsPerMuscle[muscle] = (setsPerMuscle[muscle] || 0) + exerciseSets;
      projectedVolumePerMuscle[muscle] = (projectedVolumePerMuscle[muscle] || 0) + (exerciseVolume * contribution);
      repsPerMuscle[muscle] = (repsPerMuscle[muscle] || 0) + (exerciseReps * contribution);
    }
  }

  // Calculate relative stimulus (normalized scores)
  const maxMuscleGroupVolume = Math.max(...Object.values(projectedVolumePerMuscleGroup), 1);
  const maxMuscleVolume = Math.max(...Object.values(projectedVolumePerMuscle), 1);

  const relativeStimulusPerMuscleGroup = {};
  for (const [group, volume] of Object.entries(projectedVolumePerMuscleGroup)) {
    relativeStimulusPerMuscleGroup[group] = (volume / maxMuscleGroupVolume) * 100;
  }

  const relativeStimulusPerMuscle = {};
  for (const [muscle, volume] of Object.entries(projectedVolumePerMuscle)) {
    relativeStimulusPerMuscle[muscle] = (volume / maxMuscleVolume) * 100;
  }

  return {
    template_id: template.id,
    total_sets: totalSets,
    total_reps: totalReps,
    projected_volume: projectedVolume,
    weight_format: 'kg', // Default to kg, could be made configurable
    projected_volume_per_muscle_group: projectedVolumePerMuscleGroup,
    projected_volume_per_muscle: projectedVolumePerMuscle,
    sets_per_muscle_group: setsPerMuscleGroup,
    sets_per_muscle: setsPerMuscle,
    reps_per_muscle_group: repsPerMuscleGroup,
    reps_per_muscle: repsPerMuscle,
    relative_stimulus_per_muscle_group: relativeStimulusPerMuscleGroup,
    relative_stimulus_per_muscle: relativeStimulusPerMuscle
  };
}

/**
 * Calculate workout analytics similar to Swift's ActiveWorkoutManager
 */
async function calculateWorkoutAnalytics(workout) {
  let totalSets = 0;
  let totalReps = 0;
  let totalWeight = 0;
  const weightPerMuscleGroup = {};
  const weightPerMuscle = {};
  const repsPerMuscleGroup = {};
  const repsPerMuscle = {};
  const setsPerMuscleGroup = {};
  const setsPerMuscle = {};
  const loadPerMuscleGroup = {};
  const hardSetsPerMuscleGroup = {};
  const lowRirSetsPerMuscleGroup = {};
  let totalHardSets = 0;
  let totalLowRirSets = 0;
  let relativeIntensitySum = 0;
  let relativeIntensityCount = 0;
  const loadPerMuscle = {};
  const hardSetsPerMuscle = {};
  const lowRirSetsPerMuscle = {};
  const topSetE1rmPerMuscle = {};

  // Get exercise data
  const exerciseIds = workout.exercises.map(ex => ex.exercise_id).filter(Boolean);
  const exercisePromises = exerciseIds.map(id => 
    db.collection('exercises').doc(id).get()
  );
  const exerciseSnapshots = await Promise.all(exercisePromises);
  const exercises = exerciseSnapshots
    .filter(snap => snap.exists)
    .map(snap => ({ id: snap.id, ...snap.data() }));

  for (const workoutExercise of workout.exercises) {
    const exercise = exercises.find(ex => ex.id === workoutExercise.exercise_id);
    if (!exercise) continue;

    // Filter for completed working sets only
    const workingSets = workoutExercise.sets.filter(set => 
      set.is_completed && isWorkingSet(set.type)
    );

    const exerciseSets = workingSets.length;
    const exerciseReps = workingSets.reduce((sum, set) => sum + set.reps, 0);
    const exerciseWeight = workingSets.reduce((sum, set) => sum + (set.weight_kg * set.reps), 0);

    totalSets += exerciseSets;
    totalReps += exerciseReps;
    totalWeight += exerciseWeight;

    // Calculate exercise analytics
    const exerciseAnalytics = {
      total_sets: exerciseSets,
      total_reps: exerciseReps,
      total_weight: exerciseWeight,
      weight_format: 'kg',
      avg_reps_per_set: exerciseSets > 0 ? exerciseReps / exerciseSets : 0,
      avg_weight_per_set: exerciseSets > 0 ? exerciseWeight / exerciseSets : 0,
      avg_weight_per_rep: exerciseReps > 0 ? exerciseWeight / exerciseReps : 0,
      weight_per_muscle_group: {},
      weight_per_muscle: {},
      reps_per_muscle_group: {},
      reps_per_muscle: {},
      sets_per_muscle_group: {},
      sets_per_muscle: {},
      intensity: {
        hard_sets: 0,
        low_rir_sets: 0,
        load_per_muscle: {},
        hard_sets_per_muscle: {},
        low_rir_sets_per_muscle: {},
        load_per_muscle_group: {},
        hard_sets_per_muscle_group: {},
        low_rir_sets_per_muscle_group: {}
      }
    };

    const muscleCategoriesRaw = Array.isArray(exercise.muscles?.category)
      ? exercise.muscles.category
      : [];
    const muscleCategories = muscleCategoriesRaw.map(normalizeMuscleKey).filter(Boolean);
    const muscleCategoryCount = muscleCategories.length || 0;

    const rawContributions = exercise.muscles?.contribution || {};
    const muscleContributions = {};
    for (const [muscle, contribution] of Object.entries(rawContributions)) {
      const key = normalizeMuscleKey(muscle);
      if (!key) continue;
      const coeff = typeof contribution === 'number' ? contribution : Number(contribution);
      if (!Number.isFinite(coeff) || coeff <= 0) continue;
      muscleContributions[key] = (muscleContributions[key] || 0) + coeff;
    }

    const groupContributions = {};
    if (muscleCategoryCount > 0) {
      for (const category of muscleCategories) {
        groupContributions[category] = (groupContributions[category] || 0) + 1 / muscleCategoryCount;
      }
    }
    if (muscleCategoryCount > 0) {
      for (const category of muscleCategories) {
        hardSetsPerMuscleGroup[category] = hardSetsPerMuscleGroup[category] || 0;
        lowRirSetsPerMuscleGroup[category] = lowRirSetsPerMuscleGroup[category] || 0;
        loadPerMuscleGroup[category] = loadPerMuscleGroup[category] || 0;
      }
    }

      const fallbackGroupContribs = muscleCategories.length
        ? muscleCategories.reduce((acc, category) => {
            acc[category] = 1 / muscleCategories.length;
            return acc;
          }, {})
        : {};


    // Distribute across muscle groups
    if (muscleCategoryCount > 0) {
      for (const category of muscleCategories) {
        const categoryWeight = exerciseWeight / muscleCategoryCount;
        const categoryReps = exerciseReps / muscleCategoryCount;

        exerciseAnalytics.sets_per_muscle_group[category] = exerciseSets;
        exerciseAnalytics.weight_per_muscle_group[category] = categoryWeight;
        exerciseAnalytics.reps_per_muscle_group[category] = categoryReps;

        setsPerMuscleGroup[category] = (setsPerMuscleGroup[category] || 0) + exerciseSets;
        weightPerMuscleGroup[category] = (weightPerMuscleGroup[category] || 0) + categoryWeight;
        repsPerMuscleGroup[category] = (repsPerMuscleGroup[category] || 0) + categoryReps;
      }
    }

    // Distribute across individual muscles
    if (Object.keys(muscleContributions).length > 0) {
      for (const [muscle, contribution] of Object.entries(muscleContributions)) {
        exerciseAnalytics.weight_per_muscle[muscle] = exerciseWeight * contribution;
        exerciseAnalytics.reps_per_muscle[muscle] = exerciseReps * contribution;
        exerciseAnalytics.sets_per_muscle[muscle] = exerciseSets;

        weightPerMuscle[muscle] = (weightPerMuscle[muscle] || 0) + (exerciseWeight * contribution);
        repsPerMuscle[muscle] = (repsPerMuscle[muscle] || 0) + (exerciseReps * contribution);
        setsPerMuscle[muscle] = (setsPerMuscle[muscle] || 0) + exerciseSets;
      }
    }

    // Stimulus-aware intensity metrics
    for (const set of workingSets) {
      if (!isStimulusSet(set)) continue;
      const relIntensity = computeRelativeIntensity(set.weight_kg, set.reps);
      const effortFactor = 1 + (Math.max(0, 3 - set.rir) / 3);
      const loadUnits = relIntensity * effortFactor || 0;

      totalHardSets += 1;
      exerciseAnalytics.intensity.hard_sets += 1;
      if (set.rir <= 1) {
        totalLowRirSets += 1;
        exerciseAnalytics.intensity.low_rir_sets += 1;
      }
      if (relIntensity > 0) {
        relativeIntensitySum += relIntensity;
        relativeIntensityCount += 1;
      }

      const fallbackContribs = muscleCategories.length
        ? muscleCategories.reduce((acc, category) => {
            acc[category] = 1 / muscleCategories.length;
            return acc;
          }, {})
        : {};

      const muscleContribs = Object.keys(muscleContributions).length
        ? muscleContributions
        : fallbackContribs;

      const groupContribsLocal = Object.keys(groupContributions).length
        ? groupContributions
        : fallbackGroupContribs;

      for (const [muscle, contribution] of Object.entries(muscleContribs)) {
        const coeff = typeof contribution === 'number' && contribution > 0 ? contribution : 0;
        if (coeff <= 0) continue;
      for (const [group, contribution] of Object.entries(groupContribsLocal)) {
        const coeff = typeof contribution === 'number' && contribution > 0 ? contribution : 0;
        if (coeff <= 0) continue;
        const loadContribution = loadUnits * coeff;
        addToMap(loadPerMuscleGroup, group, loadContribution);
        addToMap(hardSetsPerMuscleGroup, group, 1 * coeff);
        addToMap(lowRirSetsPerMuscleGroup, group, (set.rir <= 1 ? 1 : 0) * coeff);
        addToMap(exerciseAnalytics.intensity.load_per_muscle_group, group, loadContribution);
        addToMap(exerciseAnalytics.intensity.hard_sets_per_muscle_group, group, 1 * coeff);
        addToMap(exerciseAnalytics.intensity.low_rir_sets_per_muscle_group, group, (set.rir <= 1 ? 1 : 0) * coeff);
      }

        const loadContribution = loadUnits * coeff;

        addToMap(loadPerMuscle, muscle, loadContribution);
        addToMap(hardSetsPerMuscle, muscle, 1 * coeff);
        addToMap(lowRirSetsPerMuscle, muscle, (set.rir <= 1 ? 1 : 0) * coeff);
        addToMap(exerciseAnalytics.intensity.load_per_muscle, muscle, loadContribution);
        addToMap(exerciseAnalytics.intensity.hard_sets_per_muscle, muscle, 1 * coeff);
        addToMap(exerciseAnalytics.intensity.low_rir_sets_per_muscle, muscle, (set.rir <= 1 ? 1 : 0) * coeff);

        const e1rm = estimateE1RM(set.weight_kg, set.reps);
        if (e1rm > (topSetE1rmPerMuscle[muscle] || 0)) {
          topSetE1rmPerMuscle[muscle] = e1rm;
        }
      }
    }

    // Update the exercise with analytics
    workoutExercise.analytics = exerciseAnalytics;
  }

  // Calculate workout analytics
  const workoutAnalytics = {
    total_sets: totalSets,
    total_reps: totalReps,
    total_weight: totalWeight,
    weight_format: 'kg',
    avg_reps_per_set: totalSets > 0 ? totalReps / totalSets : 0,
    avg_weight_per_set: totalSets > 0 ? totalWeight / totalSets : 0,
    avg_weight_per_rep: totalReps > 0 ? totalWeight / totalReps : 0,
    weight_per_muscle_group: weightPerMuscleGroup,
    weight_per_muscle: weightPerMuscle,
    reps_per_muscle_group: repsPerMuscleGroup,
    reps_per_muscle: repsPerMuscle,
    sets_per_muscle_group: setsPerMuscleGroup,
    sets_per_muscle: setsPerMuscle,
    intensity: {
      hard_sets: totalHardSets,
      low_rir_sets: totalLowRirSets,
      avg_relative_intensity: relativeIntensityCount > 0 ? relativeIntensitySum / relativeIntensityCount : 0,
      load_per_muscle: loadPerMuscle,
      hard_sets_per_muscle: hardSetsPerMuscle,
      low_rir_sets_per_muscle: lowRirSetsPerMuscle,
      top_set_e1rm_per_muscle: topSetE1rmPerMuscle,
      load_per_muscle_group: loadPerMuscleGroup,
      hard_sets_per_muscle_group: hardSetsPerMuscleGroup,
      low_rir_sets_per_muscle_group: lowRirSetsPerMuscleGroup
    }
  };

  return { workoutAnalytics, updatedExercises: workout.exercises };
}

module.exports = {
  calculateTemplateAnalytics,
  calculateWorkoutAnalytics
}; 