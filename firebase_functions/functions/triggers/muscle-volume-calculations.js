const { onDocumentCreated, onDocumentUpdated } = require('firebase-functions/v2/firestore');
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

/**
 * Calculate template analytics similar to Swift's StimulusCalculator
 */
async function calculateTemplateAnalytics(template, exercises) {
  let totalSets = 0;
  let totalReps = 0;
  let projectedVolume = 0;
  const projectedVolumePerMuscleGroup = {};
  const projectedVolumePerMuscle = {};
  const setsPerMuscleGroup = {};
  const setsPerMuscle = {};
  const repsPerMuscleGroup = {};
  const repsPerMuscle = {};

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
async function calculateWorkoutAnalytics(workout, exercises) {
  let totalSets = 0;
  let totalReps = 0;
  let totalWeight = 0;
  const weightPerMuscleGroup = {};
  const weightPerMuscle = {};
  const repsPerMuscleGroup = {};
  const repsPerMuscle = {};
  const setsPerMuscleGroup = {};
  const setsPerMuscle = {};

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
      sets_per_muscle: {}
    };

    // Distribute across muscle groups
    const muscleCategories = exercise.muscles?.category || [];
    if (muscleCategories.length > 0) {
      for (const category of muscleCategories) {
        const categoryWeight = exerciseWeight / muscleCategories.length;
        const categoryReps = exerciseReps / muscleCategories.length;

        exerciseAnalytics.sets_per_muscle_group[category] = exerciseSets;
        exerciseAnalytics.weight_per_muscle_group[category] = categoryWeight;
        exerciseAnalytics.reps_per_muscle_group[category] = categoryReps;

        // Accumulate for workout totals
        setsPerMuscleGroup[category] = (setsPerMuscleGroup[category] || 0) + exerciseSets;
        weightPerMuscleGroup[category] = (weightPerMuscleGroup[category] || 0) + categoryWeight;
        repsPerMuscleGroup[category] = (repsPerMuscleGroup[category] || 0) + categoryReps;
      }
    }

    // Distribute across individual muscles
    const muscleContributions = exercise.muscles?.contribution || {};
    if (Object.keys(muscleContributions).length > 0) {
      for (const [muscle, contribution] of Object.entries(muscleContributions)) {
        exerciseAnalytics.weight_per_muscle[muscle] = exerciseWeight * contribution;
        exerciseAnalytics.reps_per_muscle[muscle] = exerciseReps * contribution;
        exerciseAnalytics.sets_per_muscle[muscle] = exerciseSets;

        // Accumulate for workout totals
        weightPerMuscle[muscle] = (weightPerMuscle[muscle] || 0) + (exerciseWeight * contribution);
        repsPerMuscle[muscle] = (repsPerMuscle[muscle] || 0) + (exerciseReps * contribution);
        setsPerMuscle[muscle] = (setsPerMuscle[muscle] || 0) + exerciseSets;
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
    sets_per_muscle: setsPerMuscle
  };

  return { workoutAnalytics, updatedExercises: workout.exercises };
}

/**
 * Firestore trigger for template creation
 * Only runs when source is 'ai_agent' (not when Swift app creates)
 */
exports.onTemplateCreated = onDocumentCreated(
  'users/{userId}/templates/{templateId}',
  async (event) => {
    const template = event.data.data();
    const { userId, templateId } = event.params;

    // Only process if created by AI agent (check for missing analytics)
    if (template.analytics || !template.exercises || template.exercises.length === 0) {
      return null;
    }

    try {
      // Get exercise data needed for calculations
      const exerciseIds = template.exercises.map(ex => ex.exercise_id).filter(Boolean);
      const exercisePromises = exerciseIds.map(id => 
        db.collection('exercises').doc(id).get()
      );
      const exerciseSnapshots = await Promise.all(exercisePromises);
      const exercises = exerciseSnapshots
        .filter(snap => snap.exists)
        .map(snap => ({ id: snap.id, ...snap.data() }));

      // Calculate analytics
      const analytics = await calculateTemplateAnalytics(template, exercises);

      // Persist analytics (merge to avoid overwriting)
      await event.data.ref.set({ analytics }, { merge: true });

      console.log(`Template analytics calculated for ${templateId}`);
      return { success: true, templateId };
    } catch (error) {
      console.error('Error calculating template analytics:', error);
      return { success: false, error: error.message };
    }
  }
);

/**
 * Firestore trigger for template updates
 * Only runs when source is 'ai_agent'
 */
exports.onTemplateUpdated = onDocumentUpdated(
  'users/{userId}/templates/{templateId}',
  async (event) => {
    const newTemplate = event.data.after.data();
    const oldTemplate = event.data.before.data();
    const { userId, templateId } = event.params;

    // Skip if analytics already present or no exercises changed
    if (newTemplate.analytics || 
        JSON.stringify(newTemplate.exercises) === JSON.stringify(oldTemplate.exercises)) {
      return null;
    }

    try {
      // Get exercise data
      const exerciseIds = newTemplate.exercises.map(ex => ex.exercise_id).filter(Boolean);
      const exercisePromises = exerciseIds.map(id => 
        db.collection('exercises').doc(id).get()
      );
      const exerciseSnapshots = await Promise.all(exercisePromises);
      const exercises = exerciseSnapshots
        .filter(snap => snap.exists)
        .map(snap => ({ id: snap.id, ...snap.data() }));

      // Calculate analytics
      const analytics = await calculateTemplateAnalytics(newTemplate, exercises);

      // Persist analytics (merge)
      await event.data.after.ref.set({ analytics }, { merge: true });

      console.log(`Template analytics updated for ${templateId}`);
      return { success: true, templateId };
    } catch (error) {
      console.error('Error updating template analytics:', error);
      return { success: false, error: error.message };
    }
  }
);

/**
 * Firestore trigger for workout creation
 * Only runs when source is 'ai_agent'
 */
exports.onWorkoutCreated = onDocumentCreated(
  'users/{userId}/workouts/{workoutId}',
  async (event) => {
    const workout = event.data.data();
    const { userId, workoutId } = event.params;

    // Only process if created by AI agent (check for missing analytics)
    if (workout.analytics || !workout.exercises || workout.exercises.length === 0) {
      return null;
    }

    try {
      // Get exercise data
      const exerciseIds = workout.exercises.map(ex => ex.exercise_id).filter(Boolean);
      const exercisePromises = exerciseIds.map(id => 
        db.collection('exercises').doc(id).get()
      );
      const exerciseSnapshots = await Promise.all(exercisePromises);
      const exercises = exerciseSnapshots
        .filter(snap => snap.exists)
        .map(snap => ({ id: snap.id, ...snap.data() }));

      // Calculate analytics
      const { workoutAnalytics, updatedExercises } = await calculateWorkoutAnalytics(workout, exercises);

      // Persist analytics and updated exercises (merge)
      await event.data.ref.set({ 
        analytics: workoutAnalytics,
        exercises: updatedExercises 
      }, { merge: true });

      console.log(`Workout analytics calculated for ${workoutId}`);
      return { success: true, workoutId };
    } catch (error) {
      console.error('Error calculating workout analytics:', error);
      return { success: false, error: error.message };
    }
  }
);

 