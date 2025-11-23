const admin = require('firebase-admin');
const AnalyticsWrites = require('../utils/analytics-writes');
const AnalyticsCalc = require('../utils/analytics-calculator');

if (!admin.apps.length) {
  admin.initializeApp();
}

const db = admin.firestore();

function getWeekStartMonday(date) {
  const d = new Date(date);
  const day = d.getUTCDay();
  const diff = day === 0 ? 6 : day - 1;
  d.setUTCDate(d.getUTCDate() - diff);
  d.setUTCHours(0, 0, 0, 0);
  return d.toISOString().split('T')[0];
}

async function getWeekStartForUser(userId, dateString) {
  try {
    const snap = await db.collection('users').doc(userId).get();
    if (snap.exists) {
      const weekStartsOnMonday = snap.data().week_starts_on_monday !== undefined ? snap.data().week_starts_on_monday : true;
      if (!weekStartsOnMonday) {
        // Sunday start
        const d = new Date(dateString);
        const day = d.getUTCDay();
        const diff = day;
        d.setUTCDate(d.getUTCDate() - diff);
        d.setUTCHours(0, 0, 0, 0);
        return d.toISOString().split('T')[0];
      }
    }
  } catch (_) {}
  return getWeekStartMonday(dateString);
}

function estimateE1RM(weightKg, reps) {
  if (typeof weightKg !== 'number' || typeof reps !== 'number' || reps <= 0) return 0;
  if (reps === 1) return weightKg;
  return weightKg * (1 + reps / 30);
}

async function processUserAnalytics(userId, { backfillDays = 90 } = {}) {
  const stateRef = db.collection('users').doc(userId).collection('analytics_state').doc('current');
  const stateSnap = await stateRef.get();
  const state = stateSnap.exists ? stateSnap.data() : {};

  let sinceIso = null;
  if (state.last_processed_workout_at) {
    sinceIso = state.last_processed_workout_at;
  } else {
    const d = new Date();
    d.setUTCDate(d.getUTCDate() - backfillDays);
    sinceIso = d.toISOString();
  }

  const sinceTs = admin.firestore.Timestamp.fromDate(new Date(sinceIso));

  // Fetch workouts since watermark (or backfill window)
  const workoutsSnap = await db
    .collection('users').doc(userId)
    .collection('workouts')
    .where('end_time', '>=', sinceTs)
    .orderBy('end_time', 'asc')
    .get();

  let lastEndIso = sinceIso;
  for (const doc of workoutsSnap.docs) {
    const workout = doc.data();
    if (!workout || !workout.end_time) continue;
    const endIso = workout.end_time.toDate ? workout.end_time.toDate().toISOString() : workout.end_time;
    lastEndIso = endIso;

    // Ensure analytics present
    let analytics = workout.analytics;
    if (!analytics) {
      try {
        const { workoutAnalytics } = await AnalyticsCalc.calculateWorkoutAnalytics(workout);
        analytics = workoutAnalytics;
        await doc.ref.set({ analytics }, { merge: true });
      } catch (e) {
        console.warn(`processUserAnalytics: failed to compute analytics for workout ${doc.id}`, e?.message || e);
        continue;
      }
    }

    // Upsert rollups and per-muscle weekly series
    const weekId = await getWeekStartForUser(userId, endIso);
    const intensity = analytics.intensity || {};
    await AnalyticsWrites.upsertRollup(userId, weekId, {
      total_sets: analytics.total_sets,
      total_reps: analytics.total_reps,
      total_weight: analytics.total_weight,
      weight_per_muscle_group: analytics.weight_per_muscle_group || {},
      workouts: 1,
      hard_sets_total: intensity.hard_sets || 0,
      low_rir_sets_total: intensity.low_rir_sets || 0,
      hard_sets_per_muscle: intensity.hard_sets_per_muscle || {},
      low_rir_sets_per_muscle: intensity.low_rir_sets_per_muscle || {},
      load_per_muscle: intensity.load_per_muscle || {},
    }, 1);

    const setsByGroup = analytics.sets_per_muscle_group || {};
    const volByGroup = analytics.weight_per_muscle_group || {};
    const hardSetsByMuscle = intensity.hard_sets_per_muscle || {};
    const loadByMuscle = intensity.load_per_muscle || {};
    const lowRirByMuscle = intensity.low_rir_sets_per_muscle || {};
    const muscles = new Set([
      ...Object.keys(setsByGroup),
      ...Object.keys(volByGroup),
      ...Object.keys(hardSetsByMuscle),
      ...Object.keys(loadByMuscle),
      ...Object.keys(lowRirByMuscle),
    ]);
    const mWrites = [];
    for (const muscle of muscles) {
      mWrites.push(
        AnalyticsWrites.appendMuscleSeries(
          userId,
          muscle,
          weekId,
          {
            sets: setsByGroup[muscle] || 0,
            volume: volByGroup[muscle] || 0,
            hard_sets: hardSetsByMuscle[muscle] || 0,
            load: loadByMuscle[muscle] || 0,
            low_rir_sets: lowRirByMuscle[muscle] || 0,
          },
          1
        )
      );
    }
    if (mWrites.length) await Promise.allSettled(mWrites);

    // Per-exercise daily points
    const dayKey = endIso.split('T')[0];
    const exercises = Array.isArray(workout.exercises) ? workout.exercises : [];
    const perExercise = new Map();
    for (const ex of exercises) {
      const exId = ex.exercise_id;
      if (!exId || !Array.isArray(ex.sets)) continue;
      let maxE1 = 0; let vol = 0;
      for (const s of ex.sets) {
        if (!s.is_completed) continue;
        const reps = typeof s.reps === 'number' ? s.reps : 0;
        const w = typeof s.weight_kg === 'number' ? s.weight_kg : 0;
        if (reps > 0 && w > 0) {
          maxE1 = Math.max(maxE1, estimateE1RM(w, reps));
          vol += w * reps;
        }
      }
      if (maxE1 > 0 || vol > 0) {
        const curr = perExercise.get(exId) || { e1rm: 0, vol: 0 };
        curr.e1rm = Math.max(curr.e1rm, maxE1);
        curr.vol += vol;
        perExercise.set(exId, curr);
      }
    }
    const eWrites = [];
    for (const [exerciseId, point] of perExercise.entries()) {
      eWrites.push(AnalyticsWrites.appendExerciseSeries(userId, exerciseId, dayKey, point, 1));
    }
    if (eWrites.length) await Promise.allSettled(eWrites);
  }

  // Update watermark
  await AnalyticsWrites.updateWatermark(userId, { last_processed_workout_at: lastEndIso });

  // Light compaction stub: mark compaction time; real aggregation can be added incrementally
  await AnalyticsWrites.updateWatermark(userId, { last_compaction_at: new Date().toISOString() });

  return { success: true, userId, processed: workoutsSnap.size };
}

module.exports = { processUserAnalytics };


