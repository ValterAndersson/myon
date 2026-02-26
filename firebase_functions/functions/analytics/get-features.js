const { onRequest } = require('firebase-functions/v2/https');
const admin = require('firebase-admin');
const { ok, fail } = require('../utils/response');
const { requireFlexibleAuth } = require('../auth/middleware');
const { getAuthenticatedUserId } = require('../utils/auth-helpers');

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

function parseWeekDate(weekId) {
  if (!weekId) return null;
  const date = new Date(`${weekId}T00:00:00.000Z`);
  return Number.isNaN(date.getTime()) ? null : date;
}

function attachFatigueMetrics(rollups) {
  if (!Array.isArray(rollups) || !rollups.length) return;
  const indexed = rollups
    .map((rollup) => ({
      rollup,
      weekDate: parseWeekDate(rollup.id || rollup.week_id),
    }))
    .filter((item) => item.weekDate);

  indexed.sort((a, b) => a.weekDate - b.weekDate);

  const history = new Map();
  for (const entry of indexed) {
    const currentLoads = entry.rollup.intensity?.load_per_muscle || {};
    const currentGroupLoads = entry.rollup.intensity?.load_per_muscle_group || {};
    const muscles = new Set([
      ...history.keys(),
      ...Object.keys(currentLoads),
    ]);
    entry.rollup.intensity = entry.rollup.intensity || {};
    entry.rollup.intensity.group_loads = currentGroupLoads;
    const fatiguePerMuscle = {};
    let systemicAcute = 0;
    let systemicChronicAccum = 0;
    let systemicChronicContrib = 0;

    for (const muscle of muscles) {
      const load = currentLoads[muscle] || 0;
      const previous = history.get(muscle) || [];
      const chronicWindow = previous.slice(-4);
      const chronic = chronicWindow.length
        ? chronicWindow.reduce((sum, val) => sum + val, 0) / chronicWindow.length
        : null;
      const fatigueScore = chronic !== null ? load - chronic : null;
      const acwr = chronic && chronic > 0 ? load / chronic : null;

      fatiguePerMuscle[muscle] = {
        acute: load,
        chronic,
        fatigue_score: fatigueScore,
        acwr,
      };

      systemicAcute += load;
      if (chronic !== null) {
        systemicChronicAccum += chronic;
        systemicChronicContrib += 1;
      }

      const nextHistory = previous.concat(load);
      if (nextHistory.length > 8) nextHistory.shift();
      history.set(muscle, nextHistory);
    }

    const systemicChronic = systemicChronicContrib > 0 ? systemicChronicAccum : null;

    entry.rollup.fatigue = {
      muscles: fatiguePerMuscle,
      systemic: {
        acute: systemicAcute,
        chronic: systemicChronic,
        fatigue_score: systemicChronic !== null ? systemicAcute - systemicChronic : null,
        acwr: systemicChronic && systemicChronic > 0 ? systemicAcute / systemicChronic : null,
      },
    };
  }
}

function addSummaries(rollups, topN = 8) {
  if (!Array.isArray(rollups)) return;
  for (const rollup of rollups) {
    const intensity = rollup.intensity || {};
    const groupLoads = Object.entries(intensity.load_per_muscle_group || {});
    const muscleLoads = Object.entries(intensity.load_per_muscle || {});
    const toSummary = (entries, hardMap = {}, lowMap = {}) =>
      entries
        .map(([key, load]) => ({
          key,
          load,
          hard_sets: hardMap[key] || 0,
          low_rir_sets: lowMap[key] || 0,
        }))
        .filter((item) => item.load > 0 || item.hard_sets > 0 || item.low_rir_sets > 0)
        .sort((a, b) => {
          if (b.load !== a.load) return b.load - a.load;
          if (b.hard_sets !== a.hard_sets) return b.hard_sets - a.hard_sets;
          return b.low_rir_sets - a.low_rir_sets;
        })
        .slice(0, topN);

    rollup.summary = {
      muscle_groups: toSummary(
        groupLoads,
        intensity.hard_sets_per_muscle_group || {},
        intensity.low_rir_sets_per_muscle_group || {}
      ),
      muscles: toSummary(
        muscleLoads,
        intensity.hard_sets_per_muscle || {},
        intensity.low_rir_sets_per_muscle || {}
      ),
    };
  }
}

async function handler(req, res) {
  try {
    if (req.method !== 'POST') {
      return res.status(405).json({ success: false, error: 'Method Not Allowed' });
    }
    const uid = getAuthenticatedUserId(req);
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
        if (snap.exists) {
          const data = snap.data() || {};
          rollups.push({
            id: wid,
            ...data,
            intensity: {
              hard_sets_total: data.hard_sets_total || 0,
              low_rir_sets_total: data.low_rir_sets_total || 0,
              hard_sets_per_muscle: data.hard_sets_per_muscle || {},
              low_rir_sets_per_muscle: data.low_rir_sets_per_muscle || {},
              load_per_muscle: data.load_per_muscle || {},
              hard_sets_per_muscle_group: data.hard_sets_per_muscle_group || {},
              low_rir_sets_per_muscle_group: data.low_rir_sets_per_muscle_group || {},
              load_per_muscle_group: data.load_per_muscle_group || {},
            },
            cadence: {
              sessions: data.workouts || 0,
            },
          });
        }
      }));
      attachFatigueMetrics(rollups);
      addSummaries(rollups);
    }

    // Optionally fetch per-muscle weekly series for requested muscles
    const seriesMuscle = {};
    if (muscles.length && weekIds.length) {
      await Promise.all(muscles.map(async (m) => {
        const doc = await db.collection('users').doc(uid).collection('analytics_series_muscle').doc(m).get();
        if (!doc.exists) return;
        const weeksMap = doc.data().weeks || {};
        const arr = weekIds.map((wid) => ({
          week: wid,
          sets: weeksMap[wid]?.sets || 0,
          volume: weeksMap[wid]?.volume || 0,
          hard_sets: weeksMap[wid]?.hard_sets || 0,
          load: weeksMap[wid]?.load || 0,
          low_rir_sets: weeksMap[wid]?.low_rir_sets || 0,
        }));
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
      schema_version: 3,
    });
  } catch (e) {
    console.error('get-features error', e);
    return fail(res, 'INTERNAL', 'Failed to fetch analytics features', { message: e.message }, 500);
  }
}

exports.getAnalyticsFeatures = onRequest(requireFlexibleAuth(handler));


