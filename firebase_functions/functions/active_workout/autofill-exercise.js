/**
 * autofillExercise - AI bulk prescription for a single exercise
 * 
 * Per FOCUS_MODE_WORKOUT_EXECUTION.md spec:
 * - Updates existing planned sets and/or adds new sets
 * - Only targets planned sets (done/skipped are protected)
 * - Validates all values (reps 1-30, rir 0-5, weight >= 0 or null)
 * - Max 8 sets per exercise after additions
 * - Writes single 'autofill_applied' event
 */
const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const admin = require('firebase-admin');
const { fail, ok } = require('../utils/response');
const { AutofillExerciseSchema } = require('../utils/validators');
const { 
  checkWorkoutIdempotency, 
  storeWorkoutIdempotency 
} = require('../utils/idempotency');

const db = admin.firestore();

const MAX_SETS_PER_EXERCISE = 8;

/**
 * Compute totals from exercises array
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

  return { sets: totalSets, reps: totalReps, volume: totalVolume };
}

async function autofillExerciseHandler(req, res) {
  try {
    if (req.method !== 'POST') {
      return res.status(405).json({ success: false, error: 'Method Not Allowed' });
    }
    
    const userId = req.user?.uid || req.auth?.uid;
    if (!userId) {
      return res.status(401).json({ success: false, error: 'Unauthorized' });
    }

    // 1. Validate request
    const parsed = AutofillExerciseSchema.safeParse(req.body || {});
    if (!parsed.success) {
      return fail(res, 'INVALID_ARGUMENT', 'Invalid request', parsed.error.flatten(), 400);
    }
    
    const { 
      workout_id: workoutId,
      exercise_instance_id: exerciseInstanceId,
      updates = [],
      additions = [],
      idempotency_key: idempotencyKey,
      client_timestamp: clientTimestamp,
    } = parsed.data;

    // 2. Check idempotency
    const idem = await checkWorkoutIdempotency(userId, workoutId, idempotencyKey);
    if (idem.isDuplicate && idem.cachedResponse) {
      return ok(res, idem.cachedResponse);
    }

    // 3. Fetch workout
    const workoutRef = db.doc(`users/${userId}/active_workouts/${workoutId}`);
    const workoutSnap = await workoutRef.get();
    
    if (!workoutSnap.exists) {
      return fail(res, 'NOT_FOUND', 'Workout not found', null, 404);
    }
    
    const workout = workoutSnap.data();
    
    if (workout.status !== 'in_progress') {
      return fail(res, 'INVALID_STATE', 'Workout is not in progress', null, 400);
    }

    // 4. Find target exercise
    let exerciseIndex = -1;
    let targetExercise = null;
    for (let i = 0; i < (workout.exercises || []).length; i++) {
      if (workout.exercises[i].instance_id === exerciseInstanceId) {
        exerciseIndex = i;
        targetExercise = workout.exercises[i];
        break;
      }
    }
    
    if (!targetExercise) {
      return fail(res, 'TARGET_NOT_FOUND', 'Exercise not found', { exercise_instance_id: exerciseInstanceId }, 404);
    }

    // 5. Build a map of current sets
    const currentSets = [...(targetExercise.sets || [])];
    const setMap = new Map();
    for (const set of currentSets) {
      setMap.set(set.id, set);
    }

    // 6. Validate and apply updates
    const setsUpdated = [];
    const diffOps = [];
    
    for (const update of updates) {
      const existingSet = setMap.get(update.set_id);
      if (!existingSet) {
        return fail(res, 'TARGET_NOT_FOUND', `Set not found: ${update.set_id}`, null, 404);
      }
      
      // AI can only update planned sets
      if (existingSet.status !== 'planned') {
        return fail(res, 'PERMISSION_DENIED', 'AI can only update planned sets', { set_id: update.set_id }, 403);
      }
      
      // Apply updates
      if (update.weight !== undefined) {
        existingSet.weight = update.weight;
      }
      if (update.reps !== undefined) {
        existingSet.reps = update.reps;
      }
      if (update.rir !== undefined) {
        existingSet.rir = update.rir;
      }
      
      setsUpdated.push(update.set_id);
    }

    // 7. Validate additions
    const setsAdded = [];
    
    // Check max sets constraint
    const totalSetsAfterAdditions = currentSets.length + additions.length;
    if (totalSetsAfterAdditions > MAX_SETS_PER_EXERCISE) {
      return fail(res, 'VALIDATION_ERROR', `Max ${MAX_SETS_PER_EXERCISE} sets per exercise`, { 
        current: currentSets.length, 
        adding: additions.length,
        max: MAX_SETS_PER_EXERCISE,
      }, 400);
    }

    // Check for duplicate IDs
    const allSetIds = new Set(currentSets.map(s => s.id));
    for (const addition of additions) {
      if (allSetIds.has(addition.id)) {
        return fail(res, 'DUPLICATE_SET_ID', `Set ID already exists: ${addition.id}`, null, 400);
      }
      allSetIds.add(addition.id);
    }

    // Add new sets
    for (const addition of additions) {
      const newSet = {
        id: addition.id,
        set_type: addition.set_type,
        reps: addition.reps,
        rir: addition.rir,
        weight: addition.weight,
        status: 'planned',
        tags: {},
      };
      currentSets.push(newSet);
      setsAdded.push(addition.id);
    }

    // 8. Update exercise in workout
    const updatedExercises = workout.exercises.map((ex, idx) => {
      if (idx !== exerciseIndex) return ex;
      return {
        ...ex,
        sets: currentSets,
      };
    });

    // 9. Recompute totals
    const totals = computeTotals(updatedExercises);

    // 10. Create event
    const eventRef = db.collection(`users/${userId}/active_workouts/${workoutId}/events`).doc();
    const event = {
      id: eventRef.id,
      type: 'autofill_applied',
      payload: {
        exercise_instance_id: exerciseInstanceId,
        sets_updated: setsUpdated.length > 0 ? setsUpdated : undefined,
        sets_added: setsAdded.length > 0 ? setsAdded : undefined,
      },
      diff_ops: diffOps,
      cause: 'user_ai_action',
      ui_source: 'ai_button',
      idempotency_key: idempotencyKey,
      client_timestamp: clientTimestamp || null,
      created_at: admin.firestore.FieldValue.serverTimestamp(),
    };

    // 11. Update workout
    await workoutRef.update({
      exercises: updatedExercises,
      totals,
      updated_at: admin.firestore.FieldValue.serverTimestamp(),
    });

    // 12. Write event
    await eventRef.set(event);

    // 13. Build response
    const response = {
      success: true,
      event_id: eventRef.id,
      totals,
    };

    // 14. Store idempotency
    await storeWorkoutIdempotency(userId, workoutId, idempotencyKey, response);

    return ok(res, response);
  } catch (error) {
    console.error('autofill-exercise error:', error);
    return fail(res, 'INTERNAL', 'Failed to autofill exercise', { message: error.message }, 500);
  }
}

exports.autofillExercise = onRequest(requireFlexibleAuth(autofillExerciseHandler));
