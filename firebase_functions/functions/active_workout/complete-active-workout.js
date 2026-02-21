/**
 * =============================================================================
 * complete-active-workout.js - Finish and Archive Workout
 * =============================================================================
 *
 * PURPOSE:
 * Called when user finishes a workout. Archives the active_workout to the
 * permanent workouts collection and triggers routine cursor advancement.
 *
 * COMPLETION FLOW:
 * ┌─────────────────────────────────────────────────────────────────────────┐
 * │ User taps "Finish Workout"                                             │
 * │          │                                                              │
 * │          ▼                                                              │
 * │ ┌─────────────────────────────────────────────────────────────────────┐│
 * ││ complete-active-workout.js                                           ││
 * ││  1. Load active_workout doc                                          ││
 * ││  2. Normalize sets (weight → weight_kg)                              ││
 * ││  3. Calculate analytics (sets per muscle, volume, etc.)              ││
 * ││  4. Create workout doc in users/{uid}/workouts                       ││
 * ││  5. Update active_workout status = 'completed'                       ││
 * │└─────────────────────────────────────────────────────────────────────┘│
 * │          │                                                              │
 * │          ▼ (Firestore onCreate trigger)                                │
 * │ ┌─────────────────────────────────────────────────────────────────────┐│
 * ││ workout-routine-cursor.js (trigger)                                  ││
 * ││  If source_routine_id present:                                       ││
 * ││    → Advance routine.cursor to next template                         ││
 * ││    → Updates routine.last_workout_at                                 ││
 * │└─────────────────────────────────────────────────────────────────────┘│
 * └─────────────────────────────────────────────────────────────────────────┘
 *
 * FIRESTORE OPERATIONS:
 * - Reads: users/{uid}/active_workouts/{workout_id}
 * - Creates: users/{uid}/workouts/{new_id} (permanent record)
 * - Updates: users/{uid}/active_workouts/{workout_id} → status='completed'
 *
 * ARCHIVED WORKOUT SCHEMA:
 * {
 *   user_id: string,
 *   source_template_id: string | null,  // Template used for this workout
 *   source_routine_id: string | null,   // Routine this belongs to (for cursor)
 *   created_at: timestamp,
 *   start_time: timestamp,
 *   end_time: timestamp,
 *   exercises: [{ exercise_id, sets: [{ weight_kg, reps, rir, tempo }] }],
 *   notes: string | null,
 *   analytics: {                         // Computed by AnalyticsCalc
 *     total_sets, total_reps, total_weight,
 *     sets_per_muscle_group, reps_per_muscle, etc.
 *   }
 * }
 *
 * CALLED BY:
 * - iOS: ActiveWorkoutManager.completeWorkout()
 *   → MYON2/MYON2/Services/ActiveWorkoutManager.swift
 *
 * RELATED FILES:
 * - start-active-workout.js: Creates the active_workout doc
 * - log-set.js: Adds sets during workout
 * - ../triggers/workout-routine-cursor.js: Advances routine cursor
 * - ../utils/analytics-calculator.js: Computes workout analytics
 *
 * =============================================================================
 */

const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const { ok, fail } = require('../utils/response');
const admin = require('firebase-admin');
const AnalyticsCalc = require('../utils/analytics-calculator');

const firestore = admin.firestore();

async function completeActiveWorkoutHandler(req, res) {
  try {
    if (req.method !== 'POST') {
      return res.status(405).json({ success: false, error: 'Method Not Allowed' });
    }
    const userId = req.user?.uid || req.auth?.uid;
    if (!userId) return res.status(401).json({ success: false, error: 'Unauthorized' });

    const { workout_id } = req.body || {};
    if (!workout_id) return fail(res, 'INVALID_ARGUMENT', 'Missing workout_id', null, 400);

    // Load active doc
    const activeRef = firestore.collection('users').doc(userId).collection('active_workouts').doc(workout_id);
    const activeSnap = await activeRef.get();
    if (!activeSnap.exists) return fail(res, 'NOT_FOUND', 'Active workout not found', null, 404);
    const active = activeSnap.data();

    // Archive minimal workout (analytics TBD)
    const archiveParent = `users/${userId}/workouts`;
    // Normalize active workout fields to archived workout format.
    // Active workout uses: set_type, status, instance_id, weight
    // Archived format uses: type, is_completed, id, weight_kg
    const normalizedExercises = (active.exercises || []).map(ex => ({
      id: ex.instance_id || ex.id || null,
      exercise_id: ex.exercise_id,
      name: ex.name || null,
      position: ex.position ?? 0,
      sets: (ex.sets || []).map(s => ({
        id: s.id || null,
        reps: typeof s.reps === 'number' ? s.reps : 0,
        rir: typeof s.rir === 'number' ? s.rir : null,
        type: s.set_type || s.type || 'working',
        weight_kg: typeof s.weight === 'number' ? s.weight : (typeof s.weight_kg === 'number' ? s.weight_kg : 0),
        is_completed: s.status === 'done',
      }))
    }));

    // Compute full analytics if missing using analytics-calculator
    let analytics = active.analytics;
    try {
      if (!analytics) {
        const workoutLike = { exercises: normalizedExercises };
        const { workoutAnalytics } = await AnalyticsCalc.calculateWorkoutAnalytics(workoutLike);
        analytics = workoutAnalytics;
      }
    } catch (e) {
      console.warn('Non-fatal: failed to compute full analytics, falling back to totals', e?.message || e);
      analytics = {
        total_sets: active?.totals?.sets || 0,
        total_reps: active?.totals?.reps || 0,
        total_weight: active?.totals?.volume || 0,
        weight_format: 'kg',
        avg_reps_per_set: 0,
        avg_weight_per_set: 0,
        avg_weight_per_rep: 0,
        weight_per_muscle_group: {},
        weight_per_muscle: {},
        reps_per_muscle_group: {},
        reps_per_muscle: {},
        sets_per_muscle_group: {},
        sets_per_muscle: {},
      };
    }

    // ==========================================================================
    // ATOMIC TRANSACTION: Archive + Update Status + Clear Lock
    // ==========================================================================
    const archiveRef = firestore.collection('users').doc(userId).collection('workouts').doc();

    const result = await firestore.runTransaction(async (tx) => {
      const activeRef = firestore.collection('users').doc(userId).collection('active_workouts').doc(workout_id);
      const lockRef = firestore.collection('users').doc(userId).collection('meta').doc('active_workout_state');

      // Read workout inside transaction
      const workoutSnap = await tx.get(activeRef);
      if (!workoutSnap.exists) {
        throw { httpCode: 404, code: 'NOT_FOUND', message: 'Active workout not found' };
      }

      const currentWorkout = workoutSnap.data();

      // Guard: if already completed, skip
      if (currentWorkout.status !== 'in_progress') {
        return { already_completed: true };
      }

      const now = admin.firestore.FieldValue.serverTimestamp();

      // 1. Create archived workout in workouts collection
      const archived = {
        id: archiveRef.id,  // Needed for iOS Workout model decoding
        user_id: userId,
        name: active.name || null,
        source_template_id: active.source_template_id || null,
        source_routine_id: active.source_routine_id || null,
        created_at: active.created_at || now,
        start_time: active.start_time || now,
        end_time: now,
        exercises: normalizedExercises,
        notes: active.notes || null,
        analytics
      };

      tx.set(archiveRef, archived);

      // 2. Update active workout status to completed
      tx.update(activeRef, {
        status: 'completed',
        end_time: now,
        updated_at: now
      });

      // 3. Clear lock document
      tx.set(lockRef, {
        active_workout_id: null,
        status: 'completed',
        updated_at: now
      });

      return { workout_id: archiveRef.id, archived: true };
    });

    if (result.already_completed) {
      return ok(res, { workout_id: workout_id, archived: false, message: 'Already completed' });
    }

    console.log(`Completed workout ${workout_id}, archived as ${result.workout_id}, lock cleared`);

    return ok(res, result);
  } catch (error) {
    console.error('complete-active-workout error:', error);
    return fail(res, 'INTERNAL', 'Failed to complete active workout', { message: error.message }, 500);
  }
}

exports.completeActiveWorkout = onRequest(
  { invoker: 'public' },
  requireFlexibleAuth(completeActiveWorkoutHandler)
);
