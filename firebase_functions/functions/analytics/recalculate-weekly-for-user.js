const { onRequest } = require('firebase-functions/v2/https');
const admin = require('firebase-admin');
const { requireFlexibleAuth } = require('../auth/middleware');
const { ok, fail } = require('../utils/response');

if (!admin.apps.length) {
  admin.initializeApp();
}

const db = admin.firestore();

function getWeekStartSunday(dateString) {
  const date = new Date(dateString);
  const day = date.getUTCDay();
  const diff = day;
  date.setUTCDate(date.getUTCDate() - diff);
  date.setUTCHours(0, 0, 0, 0);
  return date.toISOString().split('T')[0];
}

function getWeekStartMonday(dateString) {
  const date = new Date(dateString);
  const day = date.getUTCDay();
  const diff = day === 0 ? 6 : day - 1;
  date.setUTCDate(date.getUTCDate() - diff);
  date.setUTCHours(0, 0, 0, 0);
  return date.toISOString().split('T')[0];
}

async function getWeekStartForUser(userId, dateString) {
  try {
    const userDoc = await db.collection('users').doc(userId).get();
    if (userDoc.exists) {
      const userData = userDoc.data();
      const weekStartsOnMonday = userData.week_starts_on_monday !== undefined ? userData.week_starts_on_monday : true;
      return weekStartsOnMonday ? getWeekStartMonday(dateString) : getWeekStartSunday(dateString);
    }
  } catch (e) {
    console.warn('getWeekStartForUser: falling back to Monday start', e?.message || e);
  }
  return getWeekStartMonday(dateString);
}

function mergeMetrics(target = {}, source = {}, increment = 1) {
  if (!source || typeof source !== 'object') return;
  for (const [key, value] of Object.entries(source)) {
    if (typeof value !== 'number') continue;
    const current = target[key] || 0;
    const updated = current + value * increment;
    if (updated === 0) delete target[key]; else target[key] = updated;
  }
}

async function recalcAllWeeksForUser(userId, startDate, endDate) {
  // Aggregate workouts by weekId
  const aggregates = new Map();
  const col = db.collection('users').doc(userId).collection('workouts');
  let query = col.orderBy('end_time', 'asc');
  if (startDate) query = query.startAt(admin.firestore.Timestamp.fromDate(new Date(startDate)));
  // Note: endDate filter applied after fetch to avoid index complexity

  let lastDoc = null;
  let total = 0;
  while (true) {
    let q = query.limit(500);
    if (lastDoc) q = q.startAfter(lastDoc);
    const snap = await q.get();
    if (snap.empty) break;
    for (const doc of snap.docs) {
      const w = doc.data();
      if (!w || !w.end_time || !w.analytics) continue;
      const endIso = w.end_time.toDate ? w.end_time.toDate().toISOString() : String(w.end_time);
      if (endDate && new Date(endIso) > new Date(endDate)) continue;
      const weekId = await getWeekStartForUser(userId, endIso);
      if (!aggregates.has(weekId)) {
        aggregates.set(weekId, {
          workouts: 0,
          total_sets: 0,
          total_reps: 0,
          total_weight: 0,
          weight_per_muscle_group: {},
          weight_per_muscle: {},
          reps_per_muscle_group: {},
          reps_per_muscle: {},
          sets_per_muscle_group: {},
          sets_per_muscle: {},
        });
      }
      const agg = aggregates.get(weekId);
      agg.workouts += 1;
      agg.total_sets += w.analytics.total_sets || 0;
      agg.total_reps += w.analytics.total_reps || 0;
      agg.total_weight += w.analytics.total_weight || 0;
      mergeMetrics(agg.weight_per_muscle_group, w.analytics.weight_per_muscle_group || {}, 1);
      mergeMetrics(agg.weight_per_muscle, w.analytics.weight_per_muscle || {}, 1);
      mergeMetrics(agg.reps_per_muscle_group, w.analytics.reps_per_muscle_group || {}, 1);
      mergeMetrics(agg.reps_per_muscle, w.analytics.reps_per_muscle || {}, 1);
      mergeMetrics(agg.sets_per_muscle_group, w.analytics.sets_per_muscle_group || {}, 1);
      mergeMetrics(agg.sets_per_muscle, w.analytics.sets_per_muscle || {}, 1);
      total += 1;
    }
    lastDoc = snap.docs[snap.docs.length - 1];
    if (snap.size < 500) break;
  }

  // Write weekly_stats
  const writes = [];
  for (const [weekId, data] of aggregates.entries()) {
    const ref = db.collection('users').doc(userId).collection('weekly_stats').doc(weekId);
    data.updated_at = admin.firestore.FieldValue.serverTimestamp();
    data.recalculated_at = admin.firestore.FieldValue.serverTimestamp();
    writes.push(ref.set(data, { merge: true }));
  }
  if (writes.length) await Promise.allSettled(writes);

  return { weeks: aggregates.size, workouts: total };
}

async function handler(req, res) {
  try {
    if (req.method !== 'POST') {
      return res.status(405).json({ success: false, error: 'Method Not Allowed' });
    }
    const userId = req.body?.userId || req.auth?.uid || req.user?.uid;
    if (!userId) return fail(res, 'INVALID_ARGUMENT', 'Missing userId', null, 400);
    const { startDate, endDate } = req.body || {};
    const result = await recalcAllWeeksForUser(userId, startDate, endDate);
    return ok(res, { userId, ...result });
  } catch (e) {
    console.error('recalculate-weekly-for-user error', e);
    return fail(res, 'INTERNAL', 'Failed to recalc weekly stats', { message: e.message }, 500);
  }
}

exports.recalculateWeeklyForUser = onRequest(requireFlexibleAuth(handler));


