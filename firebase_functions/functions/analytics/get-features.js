const { onRequest } = require('firebase-functions/v2/https');
const admin = require('firebase-admin');
const { ok, fail } = require('../utils/response');
const { requireFlexibleAuth } = require('../auth/middleware');

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
        const d = new Date(dateString);
        const day = d.getUTCDay();
        const diff = day; // Sunday start
        d.setUTCDate(d.getUTCDate() - diff);
        d.setUTCHours(0, 0, 0, 0);
        return d.toISOString().split('T')[0];
      }
    }
  } catch (_) {}
  return getWeekStartMonday(dateString);
}

function slopeOf(points) {
  if (!Array.isArray(points) || points.length < 2) return 0;
  const first = points[0];
  const last = points[points.length - 1];
  return (last - first) / (points.length - 1);
}

async function handler(req, res) {
  try {
    if (req.method !== 'POST') {
      return res.status(405).json({ success: false, error: 'Method Not Allowed' });
    }
    const uid = req.body?.userId || req.auth?.uid || req.user?.uid;
    if (!uid) return fail(res, 'INVALID_ARGUMENT', 'Missing userId', null, 400);

    const mode = String(req.body?.mode || 'weekly').toLowerCase();
    // Modes:
    // - 'weekly': last N weeks (default)
    // - 'week': specific weekId (yyyy-mm-dd start)
    // - 'range': [startIso, endIso] week-aligned
    // - 'daily': recent N days of per-exercise points (low granularity, recent only)
    const weeks = Math.max(1, Math.min(52, Number(req.body?.weeks || 6)));
    const weekId = typeof req.body?.weekId === 'string' ? req.body.weekId : null;
    const rangeStart = typeof req.body?.start === 'string' ? req.body.start : null;
    const rangeEnd = typeof req.body?.end === 'string' ? req.body.end : null;
    const days = Math.max(1, Math.min(120, Number(req.body?.days || 56))); // for daily mode
    const exerciseIds = Array.isArray(req.body?.exerciseIds) ? req.body.exerciseIds.slice(0, 50) : [];
    const muscles = Array.isArray(req.body?.muscles) ? req.body.muscles.slice(0, 50) : [];

    // Build week ids
    const nowIso = new Date().toISOString();
    const startOfThisWeek = await getWeekStartForUser(uid, nowIso);
    const base = new Date(startOfThisWeek + 'T00:00:00.000Z');
    let weekIds = [];
    if (mode === 'weekly') {
      for (let i = 0; i < weeks; i++) {
        const d = new Date(base);
        d.setUTCDate(d.getUTCDate() - 7 * i);
        weekIds.push(d.toISOString().split('T')[0]);
      }
    } else if (mode === 'week' && weekId) {
      weekIds = [weekId];
    } else if (mode === 'range' && rangeStart && rangeEnd) {
      const start = new Date(rangeStart + 'T00:00:00.000Z');
      const end = new Date(rangeEnd + 'T00:00:00.000Z');
      // align to user week starts
      const alignedStart = new Date(await getWeekStartForUser(uid, start.toISOString()));
      for (let d = new Date(alignedStart); d <= end; d.setUTCDate(d.getUTCDate() + 7)) {
        weekIds.push(d.toISOString().split('T')[0]);
      }
    }

    // Fetch rollups for requested weeks
    const rollupsCol = db.collection('users').doc(uid).collection('analytics_rollups');
    const rollups = [];
    if (weekIds.length) {
      await Promise.all(weekIds.map(async (wid) => {
        const snap = await rollupsCol.doc(wid).get();
        if (snap.exists) rollups.push({ id: wid, ...snap.data() });
      }));
    }

    // Optionally fetch per-muscle weekly series for requested muscles
    const seriesMuscle = {};
    if (muscles.length && weekIds.length) {
      await Promise.all(muscles.map(async (m) => {
        const doc = await db.collection('users').doc(uid).collection('analytics_series_muscle').doc(m).get();
        if (!doc.exists) return;
        const weeksMap = doc.data().weeks || {};
        const arr = weekIds.map((wid) => ({ week: wid, sets: weeksMap[wid]?.sets || 0, volume: weeksMap[wid]?.volume || 0 }));
        seriesMuscle[m] = arr;
      }));
    }

    // Optionally fetch per-exercise daily points for requested exercises (last ~8 weeks by date)
    const seriesExercise = {};
    if (exerciseIds.length) {
      const cutoff = new Date(base);
      const numDays = mode === 'daily' ? days : Math.max(days, 56);
      cutoff.setUTCDate(cutoff.getUTCDate() - numDays);
      const cutoffStr = cutoff.toISOString().split('T')[0];
      await Promise.all(exerciseIds.map(async (exId) => {
        const doc = await db.collection('users').doc(uid).collection('analytics_series_exercise').doc(exId).get();
        if (!doc.exists) return;
        const byDay = doc.data().points_by_day || {};
        const days = Object.keys(byDay).filter((k) => k >= cutoffStr).sort();
        const e1rmSeries = days.map((d) => byDay[d]?.e1rm || 0);
        const volSeries = days.map((d) => byDay[d]?.vol || 0);
        seriesExercise[exId] = {
          days,
          e1rm: e1rmSeries,
          vol: volSeries,
          e1rm_slope: slopeOf(e1rmSeries),
          vol_slope: slopeOf(volSeries),
        };
      }));
    }

    return ok(res, {
      userId: uid,
      mode,
      period_weeks: mode === 'weekly' ? weeks : undefined,
      weekIds: weekIds.length ? weekIds : undefined,
      range: mode === 'range' ? { start: rangeStart, end: rangeEnd } : undefined,
      daily_window_days: mode === 'daily' ? days : undefined,
      rollups,
      series_muscle: seriesMuscle,
      series_exercise: seriesExercise,
      schema_version: 2,
    });
  } catch (e) {
    console.error('get-features error', e);
    return fail(res, 'INTERNAL', 'Failed to fetch analytics features', { message: e.message }, 500);
  }
}

exports.getAnalyticsFeatures = onRequest(requireFlexibleAuth(handler));


