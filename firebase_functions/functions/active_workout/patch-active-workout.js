/**
 * patchActiveWorkout - Edit values, add/remove sets
 * 
 * Per FOCUS_MODE_WORKOUT_EXECUTION.md spec:
 * - Supports set_field, add_set, remove_set ops
 * - Enforces homogeneous request constraint (one op type per request, same set for set_field)
 * - AI scope validation for user_ai_action cause
 * - Recomputes totals and writes events
 * - Uses workout-scoped idempotency with response caching
 */
const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');

// Function options - allow public invocations (auth handled at application level)
const functionOptions = {
  invoker: 'public',
};
const admin = require('firebase-admin');
const { fail, ok } = require('../utils/response');
const { PatchActiveWorkoutSchema } = require('../utils/validators');
const { 
  checkWorkoutIdempotency, 
  storeWorkoutIdempotency 
} = require('../utils/idempotency');

const db = admin.firestore();

/**
 * Compute totals from exercises array (same as log-set.js)
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

/**
 * Find exercise by instance_id
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
 * Find set within exercise by set_id
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
 * Validate homogeneous request constraint
 */
function validateHomogeneous(ops) {
  if (ops.length === 0) return { valid: false, error: 'No ops provided' };
  
  const opTypes = new Set(ops.map(op => op.op));
  
  // Only one op type allowed
  if (opTypes.size > 1) {
    return { valid: false, error: 'MIXED_OP_TYPES', message: 'Cannot mix different op types in one request' };
  }
  
  const opType = ops[0].op;
  
  // For set_field, all ops must target same set
  if (opType === 'set_field') {
    const targets = new Set(ops.map(op => `${op.target.exercise_instance_id}:${op.target.set_id}`));
    if (targets.size > 1) {
      return { valid: false, error: 'MULTI_SET_EDIT', message: 'set_field ops must target the same set' };
    }
  }
  
  // For add_set and remove_set, only one op allowed
  if ((opType === 'add_set' || opType === 'remove_set') && ops.length > 1) {
    return { valid: false, error: 'MULTIPLE_STRUCTURAL_OPS', message: `Only one ${opType} op allowed per request` };
  }
  
  return { valid: true, opType };
}

/**
 * Validate AI scope restrictions
 */
function validateAIScope(ops, aiScope, exercises) {
  const scopeExerciseId = aiScope.exercise_instance_id;
  
  for (const op of ops) {
    const targetExerciseId = op.target.exercise_instance_id;
    
    // Must be within scope
    if (targetExerciseId !== scopeExerciseId) {
      return { valid: false, error: 'PERMISSION_DENIED', message: 'AI action outside scope' };
    }
    
    if (op.op === 'set_field') {
      // Find the set to check status
      const exFound = findExercise(exercises, targetExerciseId);
      if (!exFound) continue;
      
      const setFound = findSet(exFound.exercise, op.target.set_id);
      if (!setFound) continue;
      
      // AI cannot modify done or skipped sets
      if (setFound.set.status === 'done' || setFound.set.status === 'skipped') {
        return { valid: false, error: 'PERMISSION_DENIED', message: 'AI cannot modify completed sets' };
      }
      
      // AI cannot modify status, set_type, or tags
      if (['status', 'set_type', 'tags.is_failure'].includes(op.field)) {
        return { valid: false, error: 'PERMISSION_DENIED', message: `AI cannot modify ${op.field}` };
      }
    }
    
    // AI cannot remove sets
    if (op.op === 'remove_set') {
      return { valid: false, error: 'PERMISSION_DENIED', message: 'AI cannot remove sets' };
    }
  }
  
  return { valid: true };
}

/**
 * Apply set_field operation
 */
function applySetField(exercises, op) {
  const { exercise_instance_id: exId, set_id: setId } = op.target;
  const { field, value } = op;
  
  return exercises.map(ex => {
    if (ex.instance_id !== exId) return ex;
    return {
      ...ex,
      sets: ex.sets.map(s => {
        if (s.id !== setId) return s;
        if (field === 'tags.is_failure') {
          return { ...s, tags: { ...s.tags, is_failure: value } };
        }
        return { ...s, [field]: value };
      }),
    };
  });
}

/**
 * Apply add_set operation
 */
function applyAddSet(exercises, op) {
  const { exercise_instance_id: exId } = op.target;
  const newSet = { ...op.value, tags: op.value.tags || {} };
  
  return exercises.map(ex => {
    if (ex.instance_id !== exId) return ex;
    return {
      ...ex,
      sets: [...ex.sets, newSet],
    };
  });
}

/**
 * Apply remove_set operation
 */
function applyRemoveSet(exercises, op) {
  const { exercise_instance_id: exId, set_id: setId } = op.target;
  
  return exercises.map(ex => {
    if (ex.instance_id !== exId) return ex;
    return {
      ...ex,
      sets: ex.sets.filter(s => s.id !== setId),
    };
  });
}

async function patchActiveWorkoutHandler(req, res) {
  try {
    if (req.method !== 'POST') {
      return res.status(405).json({ success: false, error: 'Method Not Allowed' });
    }
    
    // User ID from Firebase Auth or API key middleware
    const userId = req.user?.uid || req.auth?.uid;
    if (!userId) {
      return res.status(401).json({ success: false, error: 'Unauthorized' });
    }

    // 1. Validate request
    const parsed = PatchActiveWorkoutSchema.safeParse(req.body || {});
    if (!parsed.success) {
      return fail(res, 'INVALID_ARGUMENT', 'Invalid request', parsed.error.flatten(), 400);
    }
    
    const { 
      workout_id: workoutId,
      ops,
      cause,
      ui_source: uiSource,
      idempotency_key: idempotencyKey,
      client_timestamp: clientTimestamp,
      ai_scope: aiScope,
    } = parsed.data;

    // 2. Check idempotency
    const idem = await checkWorkoutIdempotency(userId, workoutId, idempotencyKey);
    if (idem.isDuplicate && idem.cachedResponse) {
      return ok(res, idem.cachedResponse);
    }

    // 3. Validate homogeneous constraint
    const homoResult = validateHomogeneous(ops);
    if (!homoResult.valid) {
      return fail(res, homoResult.error, homoResult.message, null, 400);
    }

    // 4. Fetch workout
    const workoutRef = db.doc(`users/${userId}/active_workouts/${workoutId}`);
    const workoutSnap = await workoutRef.get();
    
    if (!workoutSnap.exists) {
      return fail(res, 'NOT_FOUND', 'Workout not found', null, 404);
    }
    
    const workout = workoutSnap.data();
    
    if (workout.status !== 'in_progress') {
      return fail(res, 'INVALID_STATE', 'Workout is not in progress', null, 400);
    }

    // 5. Validate AI scope if applicable
    if (cause === 'user_ai_action') {
      const scopeResult = validateAIScope(ops, aiScope, workout.exercises || []);
      if (!scopeResult.valid) {
        return fail(res, scopeResult.error, scopeResult.message, null, 403);
      }
    }

    // 6. Validate targets exist and apply validation rules
    let exercises = [...workout.exercises];
    const { opType } = homoResult;
    const diffOps = [];
    const fieldsChanged = [];
    
    if (opType === 'set_field') {
      const target = ops[0].target;
      const exFound = findExercise(exercises, target.exercise_instance_id);
      if (!exFound) {
        return fail(res, 'TARGET_NOT_FOUND', 'Exercise not found', { exercise_instance_id: target.exercise_instance_id }, 404);
      }
      const setFound = findSet(exFound.exercise, target.set_id);
      if (!setFound) {
        return fail(res, 'TARGET_NOT_FOUND', 'Set not found', { set_id: target.set_id }, 404);
      }
      
      // Validate status transitions
      for (const op of ops) {
        if (op.field === 'status') {
          const currentStatus = setFound.set.status;
          const newStatus = op.value;
          
          // planned -> done is NOT allowed via patch (use logSet)
          if (currentStatus === 'planned' && newStatus === 'done') {
            return fail(res, 'VALIDATION_ERROR', 'Use logSet to mark sets as done', null, 400);
          }
          
          // done -> skipped is NEVER allowed
          if (currentStatus === 'done' && newStatus === 'skipped') {
            return fail(res, 'VALIDATION_ERROR', 'Cannot change done to skipped', null, 400);
          }
          
          // skipped -> done is NEVER allowed (must unskip first, then logSet)
          if (currentStatus === 'skipped' && newStatus === 'done') {
            return fail(res, 'VALIDATION_ERROR', 'Cannot mark skipped as done. Unskip first, then use logSet.', null, 400);
          }
        }
        
        // Validate reps range for planned sets (must be 1-30)
        if (op.field === 'reps' && cause === 'user_edit') {
          const currentStatus = setFound.set.status;
          if (currentStatus === 'planned' && (op.value < 1 || op.value > 30)) {
            return fail(res, 'VALIDATION_ERROR', 'Planned sets must have reps 1-30', null, 400);
          }
        }
      }
      
      // Apply all set_field ops
      for (const op of ops) {
        exercises = applySetField(exercises, op);
        diffOps.push({
          op: 'replace',
          path: `/exercises/${exFound.index}/sets/${setFound.index}/${op.field.replace('.', '/')}`,
          value: op.value,
        });
        fieldsChanged.push(op.field);
      }
    }
    
    if (opType === 'add_set') {
      const op = ops[0];
      const exFound = findExercise(exercises, op.target.exercise_instance_id);
      if (!exFound) {
        return fail(res, 'TARGET_NOT_FOUND', 'Exercise not found', null, 404);
      }
      
      // Check for duplicate set ID
      const duplicateSet = exFound.exercise.sets?.find(s => s.id === op.value.id);
      if (duplicateSet) {
        return fail(res, 'DUPLICATE_SET_ID', 'Set ID already exists in workout', null, 400);
      }
      
      exercises = applyAddSet(exercises, op);
      diffOps.push({
        op: 'add',
        path: `/exercises/${exFound.index}/sets/-`,
        value: op.value,
      });
    }
    
    if (opType === 'remove_set') {
      const op = ops[0];
      const exFound = findExercise(exercises, op.target.exercise_instance_id);
      if (!exFound) {
        return fail(res, 'TARGET_NOT_FOUND', 'Exercise not found', null, 404);
      }
      const setFound = findSet(exFound.exercise, op.target.set_id);
      if (!setFound) {
        return fail(res, 'TARGET_NOT_FOUND', 'Set not found', null, 404);
      }
      
      exercises = applyRemoveSet(exercises, op);
      diffOps.push({
        op: 'remove',
        path: `/exercises/${exFound.index}/sets/${setFound.index}`,
      });
    }

    // 7. Recompute totals
    const totals = computeTotals(exercises);

    // 8. Determine event type
    let eventType;
    if (opType === 'set_field') {
      eventType = fieldsChanged.includes('status') ? 'set_updated' : 'set_updated';
    } else if (opType === 'add_set') {
      eventType = 'set_added';
    } else {
      eventType = 'set_removed';
    }

    // 9. Create event (avoid undefined values for Firestore)
    const eventRef = db.collection(`users/${userId}/active_workouts/${workoutId}/events`).doc();
    const eventPayload = {
      exercise_instance_id: ops[0].target.exercise_instance_id,
      set_id: ops[0].target.set_id || ops[0].value?.id || null,
    };
    if (fieldsChanged.length > 0) eventPayload.fields_changed = fieldsChanged;
    
    const event = {
      id: eventRef.id,
      type: eventType,
      payload: eventPayload,
      diff_ops: diffOps,
      cause,
      ui_source: uiSource,
      idempotency_key: idempotencyKey,
      client_timestamp: clientTimestamp || null,
      created_at: admin.firestore.FieldValue.serverTimestamp(),
    };

    // 10. Update workout
    await workoutRef.update({
      exercises,
      totals,
      updated_at: admin.firestore.FieldValue.serverTimestamp(),
    });

    // 11. Write event
    await eventRef.set(event);

    // 12. Build response
    const response = {
      success: true,
      event_id: eventRef.id,
      totals,
    };

    // 13. Store idempotency
    await storeWorkoutIdempotency(userId, workoutId, idempotencyKey, response);

    return ok(res, response);
  } catch (error) {
    console.error('patch-active-workout error:', error);
    return fail(res, 'INTERNAL', 'Failed to patch workout', { message: error.message }, 500);
  }
}

exports.patchActiveWorkout = onRequest(functionOptions, requireFlexibleAuth(patchActiveWorkoutHandler));
