'use strict';

// Minimal seed: create a test user (via preferences upsert) and upsert one workout.
// Requires Node 18+ (global fetch). No env vars needed; values are hardcoded below.

const API_BASE_URL = 'https://us-central1-myon-53d85.cloudfunctions.net';
const API_KEY = process.env.MYON_API_KEY;
if (!API_KEY) { console.error('Set MYON_API_KEY env var'); process.exit(1); }

function randomId(len = 6) {
  const alphabet = 'abcdefghijklmnopqrstuvwxyz0123456789';
  let s = '';
  for (let i = 0; i < len; i++) s += alphabet[Math.floor(Math.random() * alphabet.length)];
  return s;
}

const TEST_UID = `seeded_user_${randomId(6)}`;

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

function iso(date) {
  return (date instanceof Date ? date : new Date(date)).toISOString();
}

function daysAgo(n) {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - n);
  return d;
}

async function ensureUser(uid) {
  const preferences = {
    timezone: 'UTC',
    week_starts_on_monday: true,
    weight_format: 'kilograms',
    height_format: 'centimeter',
  };
  const resp = await httpJson('POST', 'updateUserPreferences', { userId: uid, preferences });
  return resp?.data || resp;
}

async function fetchExercises(limit = 50) {
  const url = `${API_BASE_URL.replace(/\/$/, '')}/getExercises?limit=${limit}`;
  const res = await fetch(url, { headers: { 'X-API-Key': API_KEY } });
  const json = await res.json();
  if (!res.ok || json?.success === false) {
    throw new Error(`Failed to fetch exercises: ${JSON.stringify(json)}`);
  }
  const items = json?.data?.items || [];
  return items;
}

function buildWorkoutPayloadAt(uid, exercises, date, variation = 0) {
  const chosen = exercises.slice(0, 2);
  if (chosen.length === 0) throw new Error('No exercises available to seed');

  const start = new Date(date);
  start.setUTCHours(17, 15, 0, 0);
  const end = new Date(start.getTime() + (45 + (variation % 3) * 5) * 60 * 1000);

  const exPayload = chosen.map((ex, idx) => ({
    exercise_id: ex.id,
    name: ex.name || null,
    position: idx,
    sets: [
      { reps: 10, rir: 2, weight_kg: 40 + idx * 5 + variation, type: 'working set', is_completed: true },
      { reps: 8, rir: 1, weight_kg: 45 + idx * 5 + variation, type: 'working set', is_completed: true },
    ],
  }));

  return {
    userId: uid,
    workout: {
      start_time: iso(start),
      end_time: iso(end),
      notes: `Seeded workout (simple) — ${start.toISOString().slice(0,10)}`,
      exercises: exPayload,
    },
  };
}

async function upsertWorkoutsOverWeeks(uid, count = 8) {
  const exercises = await fetchExercises(50);
  const results = [];
  for (let i = 0; i < count; i++) {
    const days = 2 + i * 2; // every ~2 days over ~2-3 weeks
    const payload = buildWorkoutPayloadAt(uid, exercises, daysAgo(days), i);
    const resp = await httpJson('POST', 'upsertWorkout', payload);
    results.push(resp?.data || resp);
  }
  return results;
}

async function runAnalytics(uid) {
  const resp = await httpJson('POST', 'runAnalyticsForUser', { userId: uid });
  return resp?.data || resp;
}

async function main() {
  console.log(`Seeding simple data to ${API_BASE_URL} for user ${TEST_UID} ...`);
  const ensure = await ensureUser(TEST_UID);
  console.log('User ensured (preferences updated):', ensure);

  const upserts = await upsertWorkoutsOverWeeks(TEST_UID, 8);
  console.log(`Workouts upserted: ${upserts.length}`);

  const analytics = await runAnalytics(TEST_UID);
  console.log('Analytics controller result:', analytics);

  console.log('Done. User:', TEST_UID);
}

main().catch((err) => {
  console.error('Seed failed:', err?.message || err);
  process.exit(1);
});


