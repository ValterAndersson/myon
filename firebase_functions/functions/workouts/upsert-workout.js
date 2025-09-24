const { onRequest } = require('firebase-functions/v2/https');
const admin = require('firebase-admin');
const { requireFlexibleAuth } = require('../auth/middleware');
const { ok, fail } = require('../utils/response');
const AnalyticsCalc = require('../utils/analytics-calculator');

if (!admin.apps.length) {
  admin.initializeApp();
}

function toTimestamp(value) {
  if (!value) return null;
  if (value instanceof Date) return admin.firestore.Timestamp.fromDate(value);
  if (typeof value === 'number') return admin.firestore.Timestamp.fromMillis(value);
  if (typeof value === 'string') {
    const d = new Date(value);
    if (!isNaN(d.getTime())) return admin.firestore.Timestamp.fromDate(d);
  }
  return null;
}

function normalizeExercises(rawExercises, defaultCompleted = true) {
  const list = Array.isArray(rawExercises) ? rawExercises : [];
  return list.map(ex => {
    const sets = Array.isArray(ex.sets) ? ex.sets : [];
    const normSets = sets.map(s => {
      // Prefer explicit kg; accept weight/weight_lbs and convert when unit provided
      let weightKg = null;
      if (typeof s.weight_kg === 'number') {
        weightKg = s.weight_kg;
      } else if (typeof s.weight === 'number') {
        const unit = (s.unit || s.weight_unit || 'kg').toLowerCase();
        weightKg = unit === 'lbs' || unit === 'pounds' ? +(s.weight / 2.2046226218).toFixed(3) : s.weight;
      } else if (typeof s.weight_lbs === 'number') {
        weightKg = +(s.weight_lbs / 2.2046226218).toFixed(3);
      }
      return {
        id: s.id || null,
        reps: typeof s.reps === 'number' ? s.reps : 0,
        rir: typeof s.rir === 'number' ? s.rir : 0,
        type: s.type || 'working set',
        weight_kg: typeof weightKg === 'number' ? weightKg : 0,
        is_completed: s.is_completed !== undefined ? !!s.is_completed : !!defaultCompleted,
      };
    });
    return {
      exercise_id: String(ex.exercise_id || ex.exerciseId || ''),
      name: ex.name || null,
      position: typeof ex.position === 'number' ? ex.position : null,
      sets: normSets,
    };
  });
}

async function upsertWorkoutHandler(req, res) {
  try {
    if (req.method !== 'POST') {
      return res.status(405).json({ success: false, error: 'Method Not Allowed' });
    }

    const auth = req.user || req.auth || {};
    // Determine target user
    let uid = auth.uid;
    if (!uid) {
      uid = req.get('X-User-Id') || req.headers['x-user-id'] || req.body?.userId;
    }
    if (!uid) return fail(res, 'INVALID_ARGUMENT', 'Missing userId (header X-User-Id or body.userId)', null, 400);

    const body = req.body || {};
    const input = body.workout || body;
    if (!input || !Array.isArray(input.exercises)) {
      return fail(res, 'INVALID_ARGUMENT', 'workout.exercises array is required', null, 400);
    }

    const db = admin.firestore();
    const col = db.collection('users').doc(String(uid)).collection('workouts');

    // Times
    const startTs = toTimestamp(input.start_time) || toTimestamp(input.startTime);
    const endTs = toTimestamp(input.end_time) || toTimestamp(input.endTime);
    if (!endTs) return fail(res, 'INVALID_ARGUMENT', 'end_time is required (ISO string or millis)', null, 400);

    const exercises = normalizeExercises(input.exercises, true);

    // Compute analytics synchronously to ensure weekly stats triggers run on create
    let workoutAnalytics = null;
    let updatedExercises = exercises;
    try {
      const calc = await AnalyticsCalc.calculateWorkoutAnalytics({ exercises });
      workoutAnalytics = calc.workoutAnalytics;
      updatedExercises = calc.updatedExercises || exercises;
    } catch (e) {
      // Fallback minimal analytics
      const totals = exercises.reduce((acc, ex) => {
        const sets = ex.sets || [];
        const reps = sets.reduce((s, v) => s + (v.reps || 0), 0);
        const vol = sets.reduce((s, v) => s + ((v.weight_kg || 0) * (v.reps || 0)), 0);
        return { sets: acc.sets + sets.length, reps: acc.reps + reps, vol: acc.vol + vol };
      }, { sets: 0, reps: 0, vol: 0 });
      workoutAnalytics = {
        total_sets: totals.sets,
        total_reps: totals.reps,
        total_weight: totals.vol,
        weight_format: 'kg',
        avg_reps_per_set: totals.sets > 0 ? totals.reps / totals.sets : 0,
        avg_weight_per_set: totals.sets > 0 ? totals.vol / totals.sets : 0,
        avg_weight_per_rep: totals.reps > 0 ? totals.vol / totals.reps : 0,
        weight_per_muscle_group: {},
        weight_per_muscle: {},
        reps_per_muscle_group: {},
        reps_per_muscle: {},
        sets_per_muscle_group: {},
        sets_per_muscle: {},
      };
    }

    // Select id semantics
    let docId = input.id ? String(input.id) : null;
    const docRef = docId ? col.doc(docId) : col.doc();
    docId = docRef.id;

    // Payload
    const payload = {
      id: docId,
      user_id: String(uid),
      source_template_id: input.source_template_id || input.template_id || null,
      created_at: startTs || admin.firestore.FieldValue.serverTimestamp(),
      start_time: startTs || admin.firestore.FieldValue.serverTimestamp(),
      end_time: endTs,
      notes: input.notes || null,
      source_meta: input.source_meta || input.sourceMeta || null,
      exercises: updatedExercises,
      analytics: input.analytics || workoutAnalytics,
    };

    // Create or update
    const existing = await docRef.get();
    if (existing.exists) {
      await docRef.set(payload, { merge: true });
    } else {
      await docRef.set(payload, { merge: false });
    }

    return ok(res, { workout_id: docId, created: !existing.exists, user_id: uid });
  } catch (error) {
    console.error('upsert-workout error:', error);
    return fail(res, 'INTERNAL', 'Failed to upsert workout', { message: error.message }, 500);
  }
}

exports.upsertWorkout = onRequest(requireFlexibleAuth(upsertWorkoutHandler));


