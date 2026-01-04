/**
 * Canonical muscle groups and muscles taxonomy
 * Used for set_facts attribution and series queries
 * 
 * @see docs/TRAINING_ANALYTICS_API_V2_SPEC.md Section 2.1
 */

const MUSCLE_GROUPS = {
  chest: { id: 'chest', display: 'Chest' },
  back: { id: 'back', display: 'Back' },
  shoulders: { id: 'shoulders', display: 'Shoulders' },
  arms: { id: 'arms', display: 'Arms' },
  core: { id: 'core', display: 'Core' },
  legs: { id: 'legs', display: 'Legs' },
  glutes: { id: 'glutes', display: 'Glutes' },
};

const MUSCLES = {
  // Chest
  pectoralis_major: { id: 'pectoralis_major', display: 'Pectoralis Major', group: 'chest' },
  pectoralis_minor: { id: 'pectoralis_minor', display: 'Pectoralis Minor', group: 'chest' },

  // Back
  latissimus_dorsi: { id: 'latissimus_dorsi', display: 'Latissimus Dorsi', group: 'back' },
  rhomboids: { id: 'rhomboids', display: 'Rhomboids', group: 'back' },
  trapezius: { id: 'trapezius', display: 'Trapezius', group: 'back' },
  erector_spinae: { id: 'erector_spinae', display: 'Erector Spinae', group: 'back' },
  teres_major: { id: 'teres_major', display: 'Teres Major', group: 'back' },
  teres_minor: { id: 'teres_minor', display: 'Teres Minor', group: 'back' },

  // Shoulders
  deltoid_anterior: { id: 'deltoid_anterior', display: 'Front Deltoid', group: 'shoulders' },
  deltoid_lateral: { id: 'deltoid_lateral', display: 'Side Deltoid', group: 'shoulders' },
  deltoid_posterior: { id: 'deltoid_posterior', display: 'Rear Deltoid', group: 'shoulders' },
  rotator_cuff: { id: 'rotator_cuff', display: 'Rotator Cuff', group: 'shoulders' },

  // Arms
  biceps_brachii: { id: 'biceps_brachii', display: 'Biceps', group: 'arms' },
  triceps_brachii: { id: 'triceps_brachii', display: 'Triceps', group: 'arms' },
  brachialis: { id: 'brachialis', display: 'Brachialis', group: 'arms' },
  brachioradialis: { id: 'brachioradialis', display: 'Brachioradialis', group: 'arms' },
  forearms: { id: 'forearms', display: 'Forearms', group: 'arms' },

  // Core
  rectus_abdominis: { id: 'rectus_abdominis', display: 'Rectus Abdominis', group: 'core' },
  obliques: { id: 'obliques', display: 'Obliques', group: 'core' },
  transverse_abdominis: { id: 'transverse_abdominis', display: 'Transverse Abdominis', group: 'core' },

  // Legs
  quadriceps: { id: 'quadriceps', display: 'Quadriceps', group: 'legs' },
  hamstrings: { id: 'hamstrings', display: 'Hamstrings', group: 'legs' },
  calves: { id: 'calves', display: 'Calves', group: 'legs' },
  adductors: { id: 'adductors', display: 'Adductors', group: 'legs' },
  abductors: { id: 'abductors', display: 'Abductors', group: 'legs' },
  tibialis_anterior: { id: 'tibialis_anterior', display: 'Tibialis Anterior', group: 'legs' },

  // Glutes
  gluteus_maximus: { id: 'gluteus_maximus', display: 'Gluteus Maximus', group: 'glutes' },
  gluteus_medius: { id: 'gluteus_medius', display: 'Gluteus Medius', group: 'glutes' },
  gluteus_minimus: { id: 'gluteus_minimus', display: 'Gluteus Minimus', group: 'glutes' },
};

/**
 * Map from common catalog identifiers to canonical muscle IDs
 */
const CATALOG_MUSCLE_MAP = {
  // Direct mappings
  'chest': 'pectoralis_major',
  'pecs': 'pectoralis_major',
  'pectoralis': 'pectoralis_major',
  'lats': 'latissimus_dorsi',
  'lat': 'latissimus_dorsi',
  'traps': 'trapezius',
  'trap': 'trapezius',
  'biceps': 'biceps_brachii',
  'bicep': 'biceps_brachii',
  'triceps': 'triceps_brachii',
  'tricep': 'triceps_brachii',
  'quads': 'quadriceps',
  'quad': 'quadriceps',
  'hams': 'hamstrings',
  'hamstring': 'hamstrings',
  'glutes': 'gluteus_maximus',
  'glute': 'gluteus_maximus',
  'abs': 'rectus_abdominis',
  'abdominals': 'rectus_abdominis',
  'shoulders': 'deltoid_lateral',
  'delts': 'deltoid_lateral',
  'front_delt': 'deltoid_anterior',
  'side_delt': 'deltoid_lateral',
  'rear_delt': 'deltoid_posterior',
  'calves': 'calves',
  'calf': 'calves',
  'forearm': 'forearms',
  'lower_back': 'erector_spinae',
  'upper_back': 'rhomboids',
  'mid_back': 'rhomboids',
  'core': 'rectus_abdominis',
};

/**
 * Default muscle contribution weights for common exercises
 * Used when exercise catalog doesn't have specific attribution
 */
const DEFAULT_MUSCLE_CONTRIB = {
  // Chest exercises
  bench_press: {
    muscles: { pectoralis_major: 0.6, deltoid_anterior: 0.25, triceps_brachii: 0.15 },
    groups: { chest: 0.6, shoulders: 0.25, arms: 0.15 },
  },
  incline_bench_press: {
    muscles: { pectoralis_major: 0.5, deltoid_anterior: 0.35, triceps_brachii: 0.15 },
    groups: { chest: 0.5, shoulders: 0.35, arms: 0.15 },
  },
  incline_press: {
    muscles: { pectoralis_major: 0.5, deltoid_anterior: 0.35, triceps_brachii: 0.15 },
    groups: { chest: 0.5, shoulders: 0.35, arms: 0.15 },
  },
  decline_press: {
    muscles: { pectoralis_major: 0.65, deltoid_anterior: 0.2, triceps_brachii: 0.15 },
    groups: { chest: 0.65, shoulders: 0.2, arms: 0.15 },
  },
  chest_fly: {
    muscles: { pectoralis_major: 0.85, deltoid_anterior: 0.15 },
    groups: { chest: 0.85, shoulders: 0.15 },
  },
  chest_press: {
    muscles: { pectoralis_major: 0.6, deltoid_anterior: 0.25, triceps_brachii: 0.15 },
    groups: { chest: 0.6, shoulders: 0.25, arms: 0.15 },
  },
  dip: {
    muscles: { pectoralis_major: 0.4, triceps_brachii: 0.4, deltoid_anterior: 0.2 },
    groups: { chest: 0.4, arms: 0.4, shoulders: 0.2 },
  },
  push_up: {
    muscles: { pectoralis_major: 0.5, triceps_brachii: 0.3, deltoid_anterior: 0.2 },
    groups: { chest: 0.5, arms: 0.3, shoulders: 0.2 },
  },
  
  // Back exercises - EXPANDED
  lat_pulldown: {
    muscles: { latissimus_dorsi: 0.6, biceps_brachii: 0.25, rhomboids: 0.15 },
    groups: { back: 0.75, arms: 0.25 },
  },
  pulldown: {  // Catch variations like "close grip pulldown"
    muscles: { latissimus_dorsi: 0.6, biceps_brachii: 0.25, rhomboids: 0.15 },
    groups: { back: 0.75, arms: 0.25 },
  },
  cable_row: {  // Matches "seated cable row"
    muscles: { latissimus_dorsi: 0.35, rhomboids: 0.35, biceps_brachii: 0.2, erector_spinae: 0.1 },
    groups: { back: 0.8, arms: 0.2 },
  },
  seated_row: {  // Matches "seated row", "seated cable row"
    muscles: { latissimus_dorsi: 0.35, rhomboids: 0.35, biceps_brachii: 0.2, erector_spinae: 0.1 },
    groups: { back: 0.8, arms: 0.2 },
  },
  barbell_row: {
    muscles: { latissimus_dorsi: 0.4, rhomboids: 0.3, biceps_brachii: 0.2, erector_spinae: 0.1 },
    groups: { back: 0.8, arms: 0.2 },
  },
  row: {  // Generic row catch-all
    muscles: { latissimus_dorsi: 0.4, rhomboids: 0.3, biceps_brachii: 0.2, erector_spinae: 0.1 },
    groups: { back: 0.8, arms: 0.2 },
  },
  pull_up: {
    muscles: { latissimus_dorsi: 0.55, biceps_brachii: 0.3, rhomboids: 0.15 },
    groups: { back: 0.7, arms: 0.3 },
  },
  chin_up: {
    muscles: { latissimus_dorsi: 0.45, biceps_brachii: 0.4, rhomboids: 0.15 },
    groups: { back: 0.6, arms: 0.4 },
  },
  deadlift: {
    muscles: { erector_spinae: 0.3, gluteus_maximus: 0.3, hamstrings: 0.25, quadriceps: 0.15 },
    groups: { back: 0.3, glutes: 0.3, legs: 0.4 },
  },
  face_pull: {
    muscles: { deltoid_posterior: 0.4, rhomboids: 0.3, trapezius: 0.3 },
    groups: { shoulders: 0.4, back: 0.6 },
  },
  shrug: {
    muscles: { trapezius: 1.0 },
    groups: { back: 1.0 },
  },
  
  // Shoulder exercises
  overhead_press: {
    muscles: { deltoid_anterior: 0.4, deltoid_lateral: 0.3, triceps_brachii: 0.3 },
    groups: { shoulders: 0.7, arms: 0.3 },
  },
  shoulder_press: {
    muscles: { deltoid_anterior: 0.4, deltoid_lateral: 0.3, triceps_brachii: 0.3 },
    groups: { shoulders: 0.7, arms: 0.3 },
  },
  military_press: {
    muscles: { deltoid_anterior: 0.4, deltoid_lateral: 0.3, triceps_brachii: 0.3 },
    groups: { shoulders: 0.7, arms: 0.3 },
  },
  lateral_raise: {
    muscles: { deltoid_lateral: 0.85, deltoid_anterior: 0.15 },
    groups: { shoulders: 1.0 },
  },
  side_raise: {
    muscles: { deltoid_lateral: 0.85, deltoid_anterior: 0.15 },
    groups: { shoulders: 1.0 },
  },
  front_raise: {
    muscles: { deltoid_anterior: 0.85, deltoid_lateral: 0.15 },
    groups: { shoulders: 1.0 },
  },
  rear_delt: {
    muscles: { deltoid_posterior: 0.85, rhomboids: 0.15 },
    groups: { shoulders: 0.85, back: 0.15 },
  },
  reverse_fly: {
    muscles: { deltoid_posterior: 0.7, rhomboids: 0.3 },
    groups: { shoulders: 0.7, back: 0.3 },
  },
  
  // Arm exercises
  bicep_curl: {
    muscles: { biceps_brachii: 0.8, brachialis: 0.2 },
    groups: { arms: 1.0 },
  },
  curl: {  // Generic curl catch-all
    muscles: { biceps_brachii: 0.8, brachialis: 0.2 },
    groups: { arms: 1.0 },
  },
  hammer_curl: {
    muscles: { biceps_brachii: 0.5, brachialis: 0.3, brachioradialis: 0.2 },
    groups: { arms: 1.0 },
  },
  preacher_curl: {
    muscles: { biceps_brachii: 0.9, brachialis: 0.1 },
    groups: { arms: 1.0 },
  },
  tricep_extension: {
    muscles: { triceps_brachii: 1.0 },
    groups: { arms: 1.0 },
  },
  tricep_pushdown: {
    muscles: { triceps_brachii: 1.0 },
    groups: { arms: 1.0 },
  },
  pushdown: {
    muscles: { triceps_brachii: 1.0 },
    groups: { arms: 1.0 },
  },
  skull_crusher: {
    muscles: { triceps_brachii: 1.0 },
    groups: { arms: 1.0 },
  },
  close_grip_bench: {
    muscles: { triceps_brachii: 0.6, pectoralis_major: 0.3, deltoid_anterior: 0.1 },
    groups: { arms: 0.6, chest: 0.3, shoulders: 0.1 },
  },
  
  // Leg exercises
  squat: {
    muscles: { quadriceps: 0.5, gluteus_maximus: 0.3, hamstrings: 0.15, erector_spinae: 0.05 },
    groups: { legs: 0.65, glutes: 0.3, back: 0.05 },
  },
  leg_press: {
    muscles: { quadriceps: 0.6, gluteus_maximus: 0.25, hamstrings: 0.15 },
    groups: { legs: 0.75, glutes: 0.25 },
  },
  lunge: {
    muscles: { quadriceps: 0.45, gluteus_maximus: 0.35, hamstrings: 0.2 },
    groups: { legs: 0.65, glutes: 0.35 },
  },
  split_squat: {
    muscles: { quadriceps: 0.45, gluteus_maximus: 0.35, hamstrings: 0.2 },
    groups: { legs: 0.65, glutes: 0.35 },
  },
  bulgarian: {
    muscles: { quadriceps: 0.45, gluteus_maximus: 0.35, hamstrings: 0.2 },
    groups: { legs: 0.65, glutes: 0.35 },
  },
  romanian_deadlift: {
    muscles: { hamstrings: 0.5, gluteus_maximus: 0.35, erector_spinae: 0.15 },
    groups: { legs: 0.5, glutes: 0.35, back: 0.15 },
  },
  rdl: {
    muscles: { hamstrings: 0.5, gluteus_maximus: 0.35, erector_spinae: 0.15 },
    groups: { legs: 0.5, glutes: 0.35, back: 0.15 },
  },
  hip_thrust: {
    muscles: { gluteus_maximus: 0.7, hamstrings: 0.2, quadriceps: 0.1 },
    groups: { glutes: 0.7, legs: 0.3 },
  },
  glute_bridge: {
    muscles: { gluteus_maximus: 0.75, hamstrings: 0.25 },
    groups: { glutes: 0.75, legs: 0.25 },
  },
  leg_curl: {
    muscles: { hamstrings: 0.9, calves: 0.1 },
    groups: { legs: 1.0 },
  },
  hamstring_curl: {
    muscles: { hamstrings: 0.9, calves: 0.1 },
    groups: { legs: 1.0 },
  },
  leg_extension: {
    muscles: { quadriceps: 1.0 },
    groups: { legs: 1.0 },
  },
  calf_raise: {
    muscles: { calves: 1.0 },
    groups: { legs: 1.0 },
  },
  hack_squat: {
    muscles: { quadriceps: 0.65, gluteus_maximus: 0.2, hamstrings: 0.15 },
    groups: { legs: 0.8, glutes: 0.2 },
  },
  step_up: {
    muscles: { quadriceps: 0.45, gluteus_maximus: 0.35, hamstrings: 0.2 },
    groups: { legs: 0.65, glutes: 0.35 },
  },
  
  // Core exercises
  crunch: {
    muscles: { rectus_abdominis: 0.8, obliques: 0.2 },
    groups: { core: 1.0 },
  },
  sit_up: {
    muscles: { rectus_abdominis: 0.7, obliques: 0.3 },
    groups: { core: 1.0 },
  },
  plank: {
    muscles: { transverse_abdominis: 0.5, rectus_abdominis: 0.3, obliques: 0.2 },
    groups: { core: 1.0 },
  },
  leg_raise: {
    muscles: { rectus_abdominis: 0.8, obliques: 0.2 },
    groups: { core: 1.0 },
  },
  russian_twist: {
    muscles: { obliques: 0.7, rectus_abdominis: 0.3 },
    groups: { core: 1.0 },
  },
  cable_crunch: {
    muscles: { rectus_abdominis: 0.85, obliques: 0.15 },
    groups: { core: 1.0 },
  },
  ab_wheel: {
    muscles: { rectus_abdominis: 0.6, transverse_abdominis: 0.3, obliques: 0.1 },
    groups: { core: 1.0 },
  },
};

/**
 * Fallback muscle contribution based on muscle group only
 * Used when no specific exercise pattern matches
 */
const GROUP_FALLBACK = {
  chest: { muscles: { pectoralis_major: 1.0 }, groups: { chest: 1.0 } },
  back: { muscles: { latissimus_dorsi: 0.5, rhomboids: 0.3, trapezius: 0.2 }, groups: { back: 1.0 } },
  shoulders: { muscles: { deltoid_lateral: 0.4, deltoid_anterior: 0.3, deltoid_posterior: 0.3 }, groups: { shoulders: 1.0 } },
  arms: { muscles: { biceps_brachii: 0.5, triceps_brachii: 0.5 }, groups: { arms: 1.0 } },
  core: { muscles: { rectus_abdominis: 0.6, obliques: 0.4 }, groups: { core: 1.0 } },
  legs: { muscles: { quadriceps: 0.4, hamstrings: 0.3, calves: 0.3 }, groups: { legs: 1.0 } },
  glutes: { muscles: { gluteus_maximus: 0.7, gluteus_medius: 0.3 }, groups: { glutes: 1.0 } },
};

/**
 * Get canonical muscle ID from various inputs
 * @param {string} input - Muscle name from catalog or user input
 * @returns {string|null} - Canonical muscle ID or null if not found
 */
function canonicalizeMuscle(input) {
  if (!input) return null;
  const normalized = input.toLowerCase().replace(/[\s-]/g, '_');
  
  // Direct match
  if (MUSCLES[normalized]) return normalized;
  
  // Alias match
  if (CATALOG_MUSCLE_MAP[normalized]) return CATALOG_MUSCLE_MAP[normalized];
  
  return null;
}

/**
 * Get canonical muscle group ID
 * @param {string} input - Muscle group name
 * @returns {string|null} - Canonical group ID or null
 */
function canonicalizeGroup(input) {
  if (!input) return null;
  const normalized = input.toLowerCase().replace(/[\s-]/g, '_');
  
  if (MUSCLE_GROUPS[normalized]) return normalized;
  
  return null;
}

/**
 * Get muscle contributions for an exercise
 * Uses exercise catalog data if available, falls back to defaults
 * 
 * @param {Object} exercise - Exercise object with metadata
 * @returns {Object} - { muscles: {...}, groups: {...} }
 */
function getMuscleContributions(exercise) {
  // First, try exercise catalog attribution
  if (exercise.muscleContrib) {
    return exercise.muscleContrib;
  }
  
  // Try matching by exercise name pattern
  // Handle various field naming conventions: name, exercise_name, exerciseName
  const rawName = exercise.name || exercise.exercise_name || exercise.exerciseName || '';
  const nameKey = rawName.toLowerCase().replace(/[\s-]/g, '_');
  
  for (const [pattern, contrib] of Object.entries(DEFAULT_MUSCLE_CONTRIB)) {
    if (nameKey.includes(pattern)) {
      return contrib;
    }
  }
  
  // Fall back to primary muscle group
  // Handle various field naming conventions
  const primaryGroup = canonicalizeGroup(
    exercise.primaryMuscleGroup || 
    exercise.primary_muscle_group ||
    exercise.muscleGroup || 
    exercise.muscle_group
  );
  if (primaryGroup && GROUP_FALLBACK[primaryGroup]) {
    return GROUP_FALLBACK[primaryGroup];
  }
  
  // Ultimate fallback
  return { muscles: {}, groups: {} };
}

/**
 * Get all muscles in a muscle group
 * @param {string} groupId - Canonical group ID
 * @returns {string[]} - Array of muscle IDs
 */
function getMusclesInGroup(groupId) {
  return Object.entries(MUSCLES)
    .filter(([_, muscle]) => muscle.group === groupId)
    .map(([id]) => id);
}

/**
 * Validate that a muscle group ID is valid
 */
function isValidMuscleGroup(groupId) {
  return !!MUSCLE_GROUPS[groupId];
}

/**
 * Validate that a muscle ID is valid
 */
function isValidMuscle(muscleId) {
  return !!MUSCLES[muscleId];
}

/**
 * Get list of all valid muscle group IDs
 * @returns {string[]} Array of valid muscle group IDs
 */
function getValidMuscleGroups() {
  return Object.keys(MUSCLE_GROUPS);
}

/**
 * Get list of all valid muscle IDs
 * @returns {string[]} Array of valid muscle IDs
 */
function getValidMuscles() {
  return Object.keys(MUSCLES);
}

/**
 * Validate muscle group with self-healing response
 * Returns { valid: true } or { valid: false, message, validOptions }
 * @param {string} groupId - Input muscle group ID
 * @returns {Object} Validation result with recovery info
 */
function validateMuscleGroupWithRecovery(groupId) {
  if (!groupId) {
    return {
      valid: false,
      message: 'muscle_group is required',
      validOptions: getValidMuscleGroups(),
    };
  }
  
  if (isValidMuscleGroup(groupId)) {
    return { valid: true };
  }
  
  return {
    valid: false,
    message: `Invalid muscle_group: "${groupId}". Valid options: ${getValidMuscleGroups().join(', ')}`,
    validOptions: getValidMuscleGroups(),
  };
}

/**
 * Validate muscle with self-healing response
 * Returns { valid: true } or { valid: false, message, validOptions }
 * @param {string} muscleId - Input muscle ID
 * @returns {Object} Validation result with recovery info
 */
function validateMuscleWithRecovery(muscleId) {
  if (!muscleId) {
    return {
      valid: false,
      message: 'muscle is required',
      validOptions: getValidMuscles(),
    };
  }
  
  if (isValidMuscle(muscleId)) {
    return { valid: true };
  }
  
  // Try to find similar muscles for suggestions
  const normalized = muscleId.toLowerCase().replace(/[\s-]/g, '_');
  const suggestions = getValidMuscles().filter(m => 
    m.includes(normalized) || normalized.includes(m.split('_')[0])
  ).slice(0, 5);
  
  return {
    valid: false,
    message: `Invalid muscle: "${muscleId}". ${suggestions.length > 0 
      ? `Did you mean: ${suggestions.join(', ')}?` 
      : `Valid examples: ${getValidMuscles().slice(0, 10).join(', ')}, ...`}`,
    validOptions: getValidMuscles(),
    suggestions,
  };
}

/**
 * Get display name for a muscle group
 */
function getMuscleGroupDisplay(groupId) {
  return MUSCLE_GROUPS[groupId]?.display || groupId;
}

/**
 * Get display name for a muscle
 */
function getMuscleDisplay(muscleId) {
  return MUSCLES[muscleId]?.display || muscleId;
}

module.exports = {
  MUSCLE_GROUPS,
  MUSCLES,
  CATALOG_MUSCLE_MAP,
  DEFAULT_MUSCLE_CONTRIB,
  GROUP_FALLBACK,
  canonicalizeMuscle,
  canonicalizeGroup,
  getMuscleContributions,
  getMusclesInGroup,
  isValidMuscleGroup,
  isValidMuscle,
  getMuscleGroupDisplay,
  getMuscleDisplay,
  // Self-healing validation helpers
  getValidMuscleGroups,
  getValidMuscles,
  validateMuscleGroupWithRecovery,
  validateMuscleWithRecovery,
};
