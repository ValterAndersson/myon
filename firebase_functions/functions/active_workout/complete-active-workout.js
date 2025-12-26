const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');
const { ok, fail } = require('../utils/response');

const db = new FirestoreHelper();
const admin = require('firebase-admin');
const AnalyticsCalc = require('../utils/analytics-calculator');

async function completeActiveWorkoutHandler(req, res) {
  try {
    if (req.method !== 'POST') {
      return res.status(405).json({ success: false, error: 'Method Not Allowed' });
    }
    const userId = req.user?.uid || req.auth?.uid;
    if (!userId) return res.status(401).json({ success: false, error: 'Unauthorized' });

    const { workout_id } = req.body || {};
    if (!workout_id) return fail(res, 'INVALID_ARGUMENT', 'Missing workout_id', null, 400);

    const parent = `users/${userId}/active_workouts`;
    // Load active doc
    const active = await db.getDocument(parent, workout_id);
    if (!active) return fail(res, 'NOT_FOUND', 'Active workout not found', null, 404);

    // Archive minimal workout (analytics TBD)
    const archiveParent = `users/${userId}/workouts`;
    // Normalize sets: map weight -> weight_kg for archived representation
    const normalizedExercises = (active.exercises || []).map(ex => ({
      ...ex,
      sets: (ex.sets || []).map(s => ({
        ...s,
        weight_kg: s.weight,
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

    const archived = {
      user_id: userId,
      source_template_id: active.source_template_id || null,
      source_routine_id: active.source_routine_id || null,  // Added for routine cursor tracking
      created_at: active.created_at || new Date(),
      start_time: active.start_time || new Date(),
      end_time: new Date(),
      exercises: normalizedExercises,
      notes: active.notes || null,
      analytics
    };
    const archivedId = await db.addDocument(archiveParent, archived);

    await db.updateDocument(parent, workout_id, { status: 'completed', end_time: new Date(), updated_at: new Date() });
    return ok(res, { workout_id: archivedId, archived: true });
  } catch (error) {
    console.error('complete-active-workout error:', error);
    return fail(res, 'INTERNAL', 'Failed to complete active workout', { message: error.message }, 500);
  }
}

exports.completeActiveWorkout = onRequest(requireFlexibleAuth(completeActiveWorkoutHandler));
