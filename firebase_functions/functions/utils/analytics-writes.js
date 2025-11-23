const admin = require('firebase-admin');

if (!admin.apps.length) {
  admin.initializeApp();
}

const db = admin.firestore();
const { FieldValue } = admin.firestore;

/**
 * Append or subtract a per-exercise daily point for a user.
 * Stores points in a map keyed by ISO date to enable idempotent upserts.
 *
 * Path: users/{uid}/analytics_series_exercise/{exercise_id}
 * Doc shape:
 * {
 *   points_by_day: { 'YYYY-MM-DD': { e1rm?: number, vol?: number } },
 *   schema_version: number,
 *   updated_at: Timestamp
 * }
 */
async function appendExerciseSeries(userId, exerciseId, dateKey, point, increment = 1) {
  if (!userId || !exerciseId || !dateKey || !point) return;

  const ref = db
    .collection('users').doc(userId)
    .collection('analytics_series_exercise').doc(exerciseId);

  await db.runTransaction(async (tx) => {
    const snap = await tx.get(ref);
    const data = snap.exists ? snap.data() : { points_by_day: {}, schema_version: 1 };
    const current = data.points_by_day?.[dateKey] || {};

    const next = { ...current };
    // e1RM: on add, keep max; on subtract, leave as-is (recomputed by periodic jobs if needed)
    if (typeof point.e1rm === 'number' && increment > 0) {
      next.e1rm = Math.max(current.e1rm || 0, point.e1rm);
    }
    // Volume: add/subtract
    if (typeof point.vol === 'number') {
      const newVol = (current.vol || 0) + (point.vol * increment);
      if (newVol > 0) {
        next.vol = newVol;
      } else {
        delete next.vol;
      }
    }

    const pointsByDay = { ...(data.points_by_day || {}) };
    if (Object.keys(next).length === 0) {
      delete pointsByDay[dateKey];
    } else {
      pointsByDay[dateKey] = next;
    }

    tx.set(ref, {
      points_by_day: pointsByDay,
      schema_version: data.schema_version || 1,
      updated_at: FieldValue.serverTimestamp(),
    }, { merge: true });
  });
}

/**
 * Upsert per-muscle weekly metrics.
 * Path: users/{uid}/analytics_series_muscle/{muscle}
 * Doc shape: { weeks: { 'YYYY-MM-DD': { sets:number, volume:number, exposure?:number } } }
 */
async function appendMuscleSeries(userId, muscleKey, weekId, delta, increment = 1) {
  if (!userId || !muscleKey || !weekId || !delta) return;

  const ref = db
    .collection('users').doc(userId)
    .collection('analytics_series_muscle').doc(muscleKey);

  await db.runTransaction(async (tx) => {
    const snap = await tx.get(ref);
    const data = snap.exists ? snap.data() : { weeks: {} };
    const current = data.weeks?.[weekId] || { sets: 0, volume: 0, hard_sets: 0, load: 0, low_rir_sets: 0 };

    const next = {
      sets: current.sets + ((delta.sets || 0) * increment),
      volume: current.volume + ((delta.volume || 0) * increment),
      hard_sets: current.hard_sets + ((delta.hard_sets || 0) * increment),
      load: current.load + ((delta.load || 0) * increment),
      low_rir_sets: current.low_rir_sets + ((delta.low_rir_sets || 0) * increment),
    };

    const weeks = { ...(data.weeks || {}) };
    if (next.sets <= 0 && next.volume <= 0 && next.hard_sets <= 0 && next.low_rir_sets <= 0 && next.load <= 0) {
      delete weeks[weekId];
    } else {
      weeks[weekId] = next;
    }

    tx.set(ref, {
      weeks,
      updated_at: FieldValue.serverTimestamp(),
    }, { merge: true });
  });
}

/**
 * Upsert weekly/monthly rollups.
 * Path: users/{uid}/analytics_rollups/{periodId}
 * Doc shape: minimal denormalized metrics we can expand over time.
 */
async function upsertRollup(userId, periodId, delta, increment = 1) {
  if (!userId || !periodId || !delta) return;

  const ref = db
    .collection('users').doc(userId)
    .collection('analytics_rollups').doc(periodId);

  await db.runTransaction(async (tx) => {
    const snap = await tx.get(ref);
    const data = snap.exists ? snap.data() : {
      total_sets: 0,
      total_reps: 0,
      total_weight: 0,
      weight_per_muscle_group: {},
      workouts: 0,
      hard_sets_total: 0,
      low_rir_sets_total: 0,
      hard_sets_per_muscle: {},
      low_rir_sets_per_muscle: {},
      load_per_muscle: {},
    };

    const sign = increment >= 0 ? 1 : -1;
    if (typeof delta.total_sets === 'number') data.total_sets += delta.total_sets * sign;
    if (typeof delta.total_reps === 'number') data.total_reps += delta.total_reps * sign;
    if (typeof delta.total_weight === 'number') data.total_weight += delta.total_weight * sign;
    if (typeof delta.workouts === 'number') data.workouts += delta.workouts * sign;
    if (typeof delta.hard_sets_total === 'number') data.hard_sets_total += delta.hard_sets_total * sign;
    if (typeof delta.low_rir_sets_total === 'number') data.low_rir_sets_total += delta.low_rir_sets_total * sign;

    const mergeMap = (target, source) => {
      if (!source || typeof source !== 'object') return;
      for (const [k, v] of Object.entries(source)) {
        if (typeof v !== 'number') continue;
        const cur = target[k] || 0;
        const upd = cur + v * sign;
        if (Math.abs(upd) < 1e-6) {
          delete target[k];
        } else {
          target[k] = upd;
        }
      }
    };

    const ensureMap = (key) => {
      if (!data[key] || typeof data[key] !== 'object') {
        data[key] = {};
      }
      return data[key];
    };

    mergeMap(ensureMap('weight_per_muscle_group'), delta.weight_per_muscle_group);
    mergeMap(ensureMap('hard_sets_per_muscle'), delta.hard_sets_per_muscle);
    mergeMap(ensureMap('low_rir_sets_per_muscle'), delta.low_rir_sets_per_muscle);
    mergeMap(ensureMap('load_per_muscle'), delta.load_per_muscle);
    mergeMap(ensureMap('hard_sets_per_muscle_group'), delta.hard_sets_per_muscle_group);
    mergeMap(ensureMap('low_rir_sets_per_muscle_group'), delta.low_rir_sets_per_muscle_group);
    mergeMap(ensureMap('load_per_muscle_group'), delta.load_per_muscle_group);

    tx.set(ref, {
      ...data,
      updated_at: FieldValue.serverTimestamp(),
    }, { merge: true });
  });
}

/**
 * Update analytics watermarks/state with merge semantics.
 * Path: users/{uid}/analytics_state/current
 */
async function updateWatermark(userId, stateUpdate) {
  if (!userId || !stateUpdate) return;
  const ref = db
    .collection('users').doc(userId)
    .collection('analytics_state').doc('current');

  await ref.set({
    ...stateUpdate,
    updated_at: FieldValue.serverTimestamp(),
  }, { merge: true });
}

module.exports = {
  appendExerciseSeries,
  appendMuscleSeries,
  upsertRollup,
  updateWatermark,
};


