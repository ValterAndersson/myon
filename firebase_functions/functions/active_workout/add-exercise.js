/**
 * addExercise - Add a new exercise to an active workout
 * 
 * Per FOCUS_MODE_WORKOUT_EXECUTION.md spec:
 * - Adds exercise to exercises array with client-provided instance_id
 * - Creates event with exercise_added type
 * - Uses workout-scoped idempotency
 */
const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const admin = require('firebase-admin');
const { ok, fail } = require('../utils/response');
const { 
  checkWorkoutIdempotency, 
  storeWorkoutIdempotency 
} = require('../utils/idempotency');

const db = admin.firestore();

// Function options - allow public invocations (auth handled at application level)
const functionOptions = {
  invoker: 'public',
};

async function addExerciseHandler(req, res) {
  try {
    if (req.method !== 'POST') {
      return res.status(405).json({ success: false, error: 'Method Not Allowed' });
    }
    
    const userId = req.user?.uid || req.auth?.uid;
    if (!userId) {
      return res.status(401).json({ success: false, error: 'Unauthorized' });
    }

    const { 
      workout_id: workoutId, 
      instance_id: instanceId,
      exercise_id: exerciseId, 
      name, 
      position,
      sets,
      idempotency_key: idempotencyKey,
      client_timestamp: clientTimestamp,
    } = req.body || {};

    // Validate required fields
    if (!workoutId || !exerciseId) {
      return fail(res, 'INVALID_ARGUMENT', 'Missing workout_id or exercise_id', null, 400);
    }
    
    if (!instanceId) {
      return fail(res, 'INVALID_ARGUMENT', 'Missing instance_id', null, 400);
    }

    // Check idempotency
    if (idempotencyKey) {
      const idem = await checkWorkoutIdempotency(userId, workoutId, idempotencyKey);
      if (idem.isDuplicate && idem.cachedResponse) {
        return ok(res, idem.cachedResponse);
      }
    }

    // Fetch workout
    const workoutRef = db.doc(`users/${userId}/active_workouts/${workoutId}`);
    const workoutSnap = await workoutRef.get();
    
    if (!workoutSnap.exists) {
      return fail(res, 'NOT_FOUND', 'Workout not found', null, 404);
    }
    
    const workout = workoutSnap.data();
    
    if (workout.status !== 'in_progress') {
      return fail(res, 'INVALID_STATE', 'Workout is not in progress', null, 400);
    }

    // Check for duplicate instance_id
    const existingExercise = (workout.exercises || []).find(ex => ex.instance_id === instanceId);
    if (existingExercise) {
      return fail(res, 'DUPLICATE_INSTANCE_ID', 'Exercise instance already exists', null, 400);
    }

    // Build new exercise object
    const exercisePosition = typeof position === 'number' ? position : (workout.exercises || []).length;
    
    // Process sets - ensure they have proper structure
    console.log('[addExercise] Received sets from client:', JSON.stringify(sets));
    
    const processedSets = (sets || []).map(set => ({
      id: set.id,
      set_type: set.set_type || 'working',
      status: set.status || 'planned',
      weight: set.target_weight ?? set.weight ?? null,
      reps: set.target_reps ?? set.reps ?? null,
      rir: set.target_rir ?? set.rir ?? null,
      tags: set.tags || {},
    }));
    
    console.log('[addExercise] Processed sets to store:', JSON.stringify(processedSets));
    
    const newExercise = {
      instance_id: instanceId,
      exercise_id: exerciseId,
      name: name || null,
      position: exercisePosition,
      sets: processedSets,
    };

    // Add to exercises array
    const updatedExercises = [...(workout.exercises || []), newExercise];

    // Create event
    const eventRef = db.collection(`users/${userId}/active_workouts/${workoutId}/events`).doc();
    const event = {
      id: eventRef.id,
      type: 'exercise_added',
      payload: {
        exercise_instance_id: instanceId,
        exercise_id: exerciseId,
        name: name || null,
        position: exercisePosition,
        sets_count: processedSets.length,
      },
      diff_ops: [{
        op: 'add',
        path: `/exercises/-`,
        value: newExercise,
      }],
      cause: 'user_edit',
      ui_source: 'add_exercise_button',
      idempotency_key: idempotencyKey || null,
      client_timestamp: clientTimestamp || null,
      created_at: admin.firestore.FieldValue.serverTimestamp(),
    };

    // Update workout document
    await workoutRef.update({
      exercises: updatedExercises,
      updated_at: admin.firestore.FieldValue.serverTimestamp(),
    });

    // Write event
    await eventRef.set(event);

    // Build response
    const response = {
      success: true,
      exercise_instance_id: instanceId,
      event_id: eventRef.id,
    };

    // Store idempotency
    if (idempotencyKey) {
      await storeWorkoutIdempotency(userId, workoutId, idempotencyKey, response);
    }

    return ok(res, response);
  } catch (error) {
    console.error('add-exercise error:', error);
    return fail(res, 'INTERNAL', 'Failed to add exercise', { message: error.message }, 500);
  }
}

exports.addExercise = onRequest(functionOptions, requireFlexibleAuth(addExerciseHandler));
