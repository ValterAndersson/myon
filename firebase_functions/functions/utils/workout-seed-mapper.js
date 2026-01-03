/**
 * =============================================================================
 * workout-seed-mapper.js - Template/Plan to Active Workout Mapper
 * =============================================================================
 *
 * PURPOSE:
 * Transforms workout templates and session plans into the active workout
 * exercises format required by Focus Mode. Handles exercise name lookup,
 * set type inference, and value validation.
 *
 * ARCHITECTURE CONTEXT:
 * ┌─────────────────────────────────────────────────────────────────────────┐
 * │ WORKOUT SEED FLOW                                                       │
 * │                                                                         │
 * │ Template or Plan                                                        │
 * │   │                                                                     │
 * │   ▼                                                                     │
 * │ workout-seed-mapper.js (THIS FILE)                                     │
 * │   │                                                                     │
 * │   ├──▶ templateToExercises() - Convert template to exercises           │
 * │   ├──▶ planBlocksToExercises() - Convert plan blocks to exercises      │
 * │   └──▶ normalizePlan() - Normalize stored plan shape                   │
 * │   │                                                                     │
 * │   ▼                                                                     │
 * │ Active Workout Exercises (Focus Mode schema)                           │
 * │ [{                                                                      │
 * │   instance_id, exercise_id, name, position,                            │
 * │   sets: [{ id, set_type, weight, reps, rir, status, tags }]            │
 * │ }]                                                                      │
 * └─────────────────────────────────────────────────────────────────────────┘
 *
 * OUTPUT SCHEMA (per Focus Mode execution contract):
 * {
 *   instance_id: string,
 *   exercise_id: string,
 *   name: string,
 *   position: number,
 *   sets: [{
 *     id: string,
 *     set_type: 'warmup' | 'working' | 'dropset',
 *     weight: number | null,
 *     reps: number,           // Validated: 1-30
 *     rir: number,            // Validated: 0-5
 *     status: 'planned' | 'done' | 'skipped',
 *     tags: { is_failure?: boolean | null }
 *   }]
 * }
 *
 * CALLED BY:
 * - start-active-workout.js: When seeding from template or plan
 *
 * =============================================================================
 */

const { v4: uuidv4 } = require('uuid');
const admin = require('firebase-admin');

const firestore = admin.firestore();

/**
 * Transform a workout template into active workout exercises.
 * Fetches exercise names from the catalog using batch reads.
 * 
 * @param {string} userId - User ID who owns the template
 * @param {string} templateId - Template document ID
 * @returns {Promise<Array>} Array of exercises in Focus Mode format
 */
async function templateToExercises(userId, templateId) {
  // Fetch template
  const templateDoc = await firestore
    .collection('users')
    .doc(userId)
    .collection('templates')
    .doc(templateId)
    .get();
  
  if (!templateDoc.exists) {
    console.log(`Template ${templateId} not found for user ${userId}`);
    return [];
  }
  
  const template = templateDoc.data();
  const templateExercises = template.exercises || [];
  
  if (templateExercises.length === 0) {
    return [];
  }
  
  // Batch fetch exercise names using getAll()
  const exerciseIds = [...new Set(templateExercises.map(e => e.exercise_id).filter(Boolean))];
  const nameMap = await batchFetchExerciseNames(exerciseIds);
  
  // Transform template exercises to Focus Mode format
  return templateExercises.map((te, position) => ({
    instance_id: uuidv4(),
    exercise_id: te.exercise_id,
    name: nameMap[te.exercise_id] || te.exercise_id, // Fallback to ID
    position,
    sets: (te.sets || []).map(s => ({
      id: uuidv4(),
      set_type: s.set_type || inferSetType(s.type), // Prefer normalized, fallback to inferred
      weight: validateWeight(s.weight),
      reps: validateReps(s.reps),
      rir: validateRir(s.rir),
      status: 'planned',
      tags: {}
    }))
  }));
}

/**
 * Transform session plan blocks into active workout exercises.
 * Handles both { target: { reps, rir, weight } } and flat shapes.
 * 
 * @param {Array} blocks - Plan blocks from session_plan card
 * @returns {Promise<Array>} Array of exercises in Focus Mode format
 */
async function planBlocksToExercises(blocks) {
  if (!blocks || blocks.length === 0) {
    return [];
  }
  
  // Batch fetch exercise names using getAll()
  const exerciseIds = [...new Set(blocks.map(b => b.exercise_id).filter(Boolean))];
  const nameMap = await batchFetchExerciseNames(exerciseIds);
  
  // Transform plan blocks to Focus Mode format
  return blocks.map((block, position) => ({
    instance_id: uuidv4(),
    exercise_id: block.exercise_id,
    name: nameMap[block.exercise_id] || block.exercise_id, // Fallback to ID
    position,
    sets: (block.sets || []).map(s => {
      // Unwrap target wrapper if present
      const target = s.target || s;
      // Destructure to omit target from output
      const { target: _ignored, ...setRest } = s;
      
      return {
        id: uuidv4(),
        set_type: setRest.set_type || target.set_type || 'working',
        weight: validateWeight(target.weight),
        reps: validateReps(target.reps),
        rir: validateRir(target.rir),
        status: 'planned',
        tags: {}
      };
    })
  }));
}

/**
 * Normalize plan to canonical shape for storage.
 * - Unwraps target wrapper if present
 * - Validates values (reps 1-30, rir 0-5, weight >= 0 or null)
 * - Preserves unknown fields (alts, notes, etc.)
 * 
 * @param {Object} plan - Raw plan object from request
 * @returns {Object} Normalized plan object
 */
function normalizePlan(plan) {
  if (!plan || !plan.blocks) return plan;
  
  return {
    ...plan,
    blocks: plan.blocks.map(block => {
      // Destructure to handle block-level target if present
      const { target: _blockTarget, ...blockRest } = block;
      
      return {
        ...blockRest,
        sets: (block.sets || []).map(s => {
          // Unwrap target wrapper if present
          const target = s.target || s;
          // Destructure to omit target from output (prevent target leak)
          const { target: _ignored, ...setRest } = s;
          
          return {
            ...setRest,
            reps: validateReps(target.reps),
            rir: validateRir(target.rir),
            weight: validateWeight(target.weight),
            set_type: setRest.set_type || target.set_type || 'working'
          };
        })
      };
    })
  };
}

// =============================================================================
// HELPER FUNCTIONS
// =============================================================================

/**
 * Batch fetch exercise names from the catalog using getAll().
 * 
 * @param {Array<string>} exerciseIds - Array of exercise IDs
 * @returns {Promise<Object>} Map of exerciseId -> name
 */
async function batchFetchExerciseNames(exerciseIds) {
  const nameMap = {};
  
  if (!exerciseIds || exerciseIds.length === 0) {
    return nameMap;
  }
  
  try {
    const exerciseRefs = exerciseIds.map(id => firestore.collection('exercises').doc(id));
    const exerciseDocs = await firestore.getAll(...exerciseRefs);
    
    exerciseDocs.forEach(doc => {
      if (doc.exists) {
        nameMap[doc.id] = doc.data().name || doc.id;
      }
    });
  } catch (error) {
    console.error('Failed to batch fetch exercise names:', error);
    // Return empty map - callers will use exercise_id as fallback
  }
  
  return nameMap;
}

/**
 * Infer set type from freeform type string.
 * 
 * @param {string} typeString - Freeform set type (e.g., "Working Set", "warm-up")
 * @returns {string} Normalized set type
 */
function inferSetType(typeString) {
  if (!typeString) return 'working';
  
  const lower = typeString.toLowerCase();
  if (lower.includes('warmup') || lower.includes('warm-up') || lower.includes('warm up')) {
    return 'warmup';
  }
  if (lower.includes('drop')) {
    return 'dropset';
  }
  // Default to working for any other type
  return 'working';
}

/**
 * Validate and clamp reps to valid range [1, 30].
 * 
 * @param {any} reps - Raw reps value
 * @returns {number} Validated reps (1-30)
 */
function validateReps(reps) {
  const n = parseInt(reps, 10);
  if (isNaN(n) || n < 1) return 1;
  if (n > 30) return 30;
  return n;
}

/**
 * Validate and clamp RIR to valid range [0, 5].
 * 
 * @param {any} rir - Raw RIR value
 * @returns {number} Validated RIR (0-5)
 */
function validateRir(rir) {
  const n = parseInt(rir, 10);
  if (isNaN(n) || n < 0) return 0;
  if (n > 5) return 5;
  return n;
}

/**
 * Validate weight: must be null or non-negative number.
 * 
 * @param {any} weight - Raw weight value
 * @returns {number|null} Validated weight or null
 */
function validateWeight(weight) {
  if (weight === null || weight === undefined) return null;
  const n = parseFloat(weight);
  if (isNaN(n) || n < 0) return null;
  return n;
}

module.exports = {
  templateToExercises,
  planBlocksToExercises,
  normalizePlan,
  // Export helpers for testing
  inferSetType,
  validateReps,
  validateRir,
  validateWeight
};
