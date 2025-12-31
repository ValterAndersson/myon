/**
 * logSet - Mark a set as done (Hot Path)
 * 
 * Per FOCUS_MODE_WORKOUT_EXECUTION.md spec:
 * - Uses stable IDs (exercise_instance_id + set_id)
 * - Enforces ALREADY_DONE error if set is already done
 * - Updates workout document with new values and status
 * - Recomputes totals (excludes warmups, skipped, planned)
 * - Writes set_done event with stable IDs
 * - Uses workout-scoped idempotency with response caching
 */
const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const admin = require('firebase-admin');
const { fail, ok } = require('../utils/response');
const { LogSetSchemaV2 } = require('../utils/validators');
const { 
  checkWorkoutIdempotency, 
  storeWorkoutIdempotency 
} = require('../utils/idempotency');

const db = admin.firestore();

/**
 * Compute totals from exercises array
 * Rules per spec:
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
 * Find exercise and set by stable IDs
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

async function logSetHandler(req, res) {
  try {
    if (req.method !== 'POST') {
      return res.status(405).json({ success: false, error: 'Method Not Allowed' });
    }
    
    // User ID from Firebase Auth or API key middleware
    const userId = req.user?.uid || req.auth?.uid;
    if (!userId) {
      return res.status(401).json({ success: false, error: 'Unauthorized' });
    }

    // 1. Validate request body
    const parsed = LogSetSchemaV2.safeParse(req.body || {});
    if (!parsed.success) {
      return fail(res, 'INVALID_ARGUMENT', 'Invalid request', parsed.error.flatten(), 400);
    }
    
    const { 
      workout_id: workoutId,
      exercise_instance_id: exerciseInstanceId,
      set_id: setId,
      values,
      is_failure: isFailure,
      idempotency_key: idempotencyKey,
      client_timestamp: clientTimestamp,
    } = parsed.data;

    // 2. Check idempotency FIRST
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
    
    // 4. Check workout status
    if (workout.status !== 'in_progress') {
      return fail(res, 'INVALID_STATE', 'Workout is not in progress', { status: workout.status }, 400);
    }

    // 5. Find exercise and set by stable IDs
    const found = findExerciseAndSet(workout.exercises || [], exerciseInstanceId, setId);
    if (!found) {
      return fail(res, 'TARGET_NOT_FOUND', 'Exercise or set not found', { 
        exercise_instance_id: exerciseInstanceId, 
        set_id: setId 
      }, 404);
    }

    const { exerciseIndex, setIndex, set: currentSet } = found;

    // 6. Check ALREADY_DONE
    if (currentSet.status === 'done') {
      return fail(res, 'ALREADY_DONE', 'Set already marked done. Use patchActiveWorkout to edit.', null, 400);
    }

    // 7. Check skipped (can't mark skipped as done - must unskip first via patch)
    if (currentSet.status === 'skipped') {
      return fail(res, 'INVALID_STATE', 'Cannot mark skipped set as done. Unskip first via patchActiveWorkout.', null, 400);
    }

    // 8. Build updated set
    const updatedSet = {
      ...currentSet,
      weight: values.weight,
      reps: values.reps,
      rir: values.rir,
      status: 'done',
      tags: {
        ...currentSet.tags,
        is_failure: isFailure || null,
      },
    };

    // 9. Update exercises array (immutable update)
    const updatedExercises = workout.exercises.map((ex, exIdx) => {
      if (exIdx !== exerciseIndex) return ex;
      return {
        ...ex,
        sets: ex.sets.map((s, sIdx) => {
          if (sIdx !== setIndex) return s;
          return updatedSet;
        }),
      };
    });

    // 10. Recompute totals
    const totals = computeTotals(updatedExercises);

    // 11. Build diff for event
    const diffOps = [
      { op: 'replace', path: `/exercises/${exerciseIndex}/sets/${setIndex}/status`, value: 'done' },
      { op: 'replace', path: `/exercises/${exerciseIndex}/sets/${setIndex}/weight`, value: values.weight },
      { op: 'replace', path: `/exercises/${exerciseIndex}/sets/${setIndex}/reps`, value: values.reps },
      { op: 'replace', path: `/exercises/${exerciseIndex}/sets/${setIndex}/rir`, value: values.rir },
    ];
    if (isFailure !== undefined) {
      diffOps.push({ op: 'replace', path: `/exercises/${exerciseIndex}/sets/${setIndex}/tags/is_failure`, value: isFailure });
    }

    // 12. Create event
    const eventRef = db.collection(`users/${userId}/active_workouts/${workoutId}/events`).doc();
    const event = {
      id: eventRef.id,
      type: 'set_done',
      payload: {
        exercise_instance_id: exerciseInstanceId,
        set_id: setId,
        fields_changed: ['weight', 'reps', 'rir', 'status'],
      },
      diff_ops: diffOps,
      cause: 'user_edit',
      ui_source: 'set_done_toggle',
      idempotency_key: idempotencyKey,
      client_timestamp: clientTimestamp || null,
      created_at: admin.firestore.FieldValue.serverTimestamp(),
    };

    // 13. Update workout document
    await workoutRef.update({
      exercises: updatedExercises,
      totals,
      updated_at: admin.firestore.FieldValue.serverTimestamp(),
    });

    // 14. Write event
    await eventRef.set(event);

    // 15. Build response
    const response = {
      success: true,
      event_id: eventRef.id,
      totals,
    };

    // 16. Store idempotency with response
    await storeWorkoutIdempotency(userId, workoutId, idempotencyKey, response);

    return ok(res, response);
  } catch (error) {
    console.error('log-set error:', error);
    return fail(res, 'INTERNAL', 'Failed to log set', { message: error.message }, 500);
  }
}

exports.logSet = onRequest(requireFlexibleAuth(logSetHandler));
