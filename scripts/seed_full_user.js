'use strict';

// Full-user seed:
// - Create a unique user id
// - Upsert user_attributes (preferences + profile)
// - Create 3 templates with 5 exercises each (full body)
// - Create a routine referencing those templates; set active
// - Seed ~12 workouts over 6 weeks with slight load progression; reference templates
// - Run analytics controller

const API_BASE_URL = 'https://us-central1-myon-53d85.cloudfunctions.net';
const API_KEY = process.env.MYON_API_KEY;
if (!API_KEY) { console.error('Set MYON_API_KEY env var'); process.exit(1); }

function randomId(len = 6) {
  const alphabet = 'abcdefghijklmnopqrstuvwxyz0123456789';
  let s = '';
  for (let i = 0; i < len; i++) s += alphabet[Math.floor(Math.random() * alphabet.length)];
  return s;
}

function iso(date) {
  return (date instanceof Date ? date : new Date(date)).toISOString();
}

function daysAgo(n) {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - n);
  return d;
}

async function httpJson(method, path, body) {
  const url = `${API_BASE_URL.replace(/\/$/, '')}/${path.replace(/^\//, '')}`;
  const res = await fetch(url, {
    method,
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': API_KEY,
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  let json;
  try { json = text ? JSON.parse(text) : {}; } catch (e) { throw new Error(`Non-JSON response from ${path}: ${text}`); }
  if (!res.ok || json?.success === false) {
    const err = json?.error || json;
    throw new Error(`HTTP ${res.status} ${res.statusText} at ${path}: ${typeof err === 'string' ? err : JSON.stringify(err)}`);
  }
  return json;
}

async function upsertAttributes(uid) {
  const attributes = {
    timezone: 'UTC',
    weight_format: 'kilograms',
    height_format: 'centimeter',
    week_starts_on_monday: true,
    locale: 'en-US',
    fitness_goal: 'hypertrophy',
    fitness_level: 'intermediate',
    equipment_preference: 'barbell,dumbbell,cable,bodyweight',
    height: 180,
    weight: 80,
    workouts_per_week_goal: 4,
  };
  return httpJson('POST', 'upsertUserAttributes', { userId: uid, attributes });
}

async function fetchExercises(limit = 100) {
  const url = `${API_BASE_URL.replace(/\/$/, '')}/getExercises?limit=${limit}`;
  const res = await fetch(url, { headers: { 'X-API-Key': API_KEY } });
  const json = await res.json();
  if (!res.ok || json?.success === false) throw new Error(`Failed to fetch exercises: ${JSON.stringify(json)}`);
  return json?.data?.items || [];
}

function pickDistinct(exercises, count) {
  const arr = exercises.slice(0);
  const out = [];
  while (arr.length && out.length < count) {
    const idx = Math.floor(Math.random() * arr.length);
    out.push(arr.splice(idx, 1)[0]);
  }
  return out;
}

async function createTemplate(uid, name, exList) {
  const exercises = exList.map((ex, i) => ({
    exercise_id: ex.id,
    position: i,
    sets: [
      { reps: 10, rir: 2, weight: 40 },
      { reps: 8, rir: 2, weight: 45 },
    ],
  }));
  const body = { userId: uid, template: { name, description: `${name} (seeded)`, exercises } };
  const resp = await httpJson('POST', 'createTemplate', body);
  const t = resp?.data?.template || resp?.data || resp;
  return t?.id || t?.templateId;
}

async function createRoutineAndActivate(uid, name, templateIds) {
  const routineResp = await httpJson('POST', 'createRoutine', { userId: uid, routine: { name, description: `${name} (seeded)`, template_ids: templateIds, frequency: 3 } });
  const routineId = routineResp?.data?.routineId || routineResp?.data?.routine?.id || routineResp?.data?.id || routineResp?.routineId || routineResp?.id;
  await httpJson('POST', 'setActiveRoutine', { userId: uid, routineId });
  return routineId;
}

function buildWorkoutFromTemplate(uid, templateExercises, baseDay, progressionIdx) {
  const start = new Date(baseDay);
  start.setUTCHours(18, 0, 0, 0);
  const end = new Date(start.getTime() + 60 * 60 * 1000);
  const exercises = templateExercises.map((ex, i) => ({
    exercise_id: ex.exercise_id,
    name: ex.name || null,
    position: i,
    sets: [
      { reps: 10, rir: 2, weight_kg: 40 + i * 2 + progressionIdx, type: 'working set', is_completed: true },
      { reps: 8, rir: 1, weight_kg: 45 + i * 2 + progressionIdx, type: 'working set', is_completed: true },
    ],
  }));
  return { userId: uid, workout: { start_time: iso(start), end_time: iso(end), notes: `Seeded from template (wk prog ${progressionIdx})`, exercises } };
}

async function upsertWorkout(payload) {
  const resp = await httpJson('POST', 'upsertWorkout', payload);
  return resp?.data || resp;
}

async function runAnalytics(uid) {
  return httpJson('POST', 'runAnalyticsForUser', { userId: uid });
}

async function main() {
  const uid = `seeded_user_${randomId(6)}`;
  console.log('Seeding full user:', uid);

  const attrs = await upsertAttributes(uid);
  console.log('Attributes upserted:', attrs);

  const catalog = await fetchExercises(150);
  if (catalog.length < 15) throw new Error('Not enough exercises in catalog to build 3x5 templates');

  const t1 = pickDistinct(catalog, 5);
  const t2 = pickDistinct(catalog.filter(e => !t1.find(x => x.id === e.id)), 5);
  const t3 = pickDistinct(catalog.filter(e => !t1.find(x => x.id === e.id) && !t2.find(x => x.id === e.id)), 5);

  const tpl1Id = await createTemplate(uid, 'Full Body A', t1);
  const tpl2Id = await createTemplate(uid, 'Full Body B', t2);
  const tpl3Id = await createTemplate(uid, 'Full Body C', t3);
  console.log('Templates:', tpl1Id, tpl2Id, tpl3Id);

  const routineId = await createRoutineAndActivate(uid, 'Full Body (3x week)', [tpl1Id, tpl2Id, tpl3Id]);
  console.log('Routine created & activated:', routineId);

  // Pull back templates to get canonical exercise list for workouts
  // For simplicity, reuse the local structures we built
  const tplStructs = [t1, t2, t3].map(list => list.map((e, i) => ({ exercise_id: e.id, position: i })));

  // Seed ~12 sessions over ~6 weeks, rotating templates A/B/C with progression
  const workouts = [];
  for (let i = 0; i < 12; i++) {
    const days = 3 + i * 3; // every ~3 days ~6 weeks
    const tplIdx = i % 3;
    const baseDay = daysAgo(days);
    const payload = buildWorkoutFromTemplate(uid, tplStructs[tplIdx], baseDay, i);
    const res = await upsertWorkout(payload);
    workouts.push(res);
  }
  console.log(`Workouts seeded: ${workouts.length}`);

  const analytics = await runAnalytics(uid);
  console.log('Analytics controller result:', analytics);

  console.log('Done. User:', uid, 'Templates:', [tpl1Id, tpl2Id, tpl3Id], 'Routine:', routineId);
}

main().catch((err) => {
  console.error('Seed full user failed:', err?.message || err);
  process.exit(1);
});


