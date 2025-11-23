'use strict';

// Import workouts from Strong app CSV and upsert into MYON for an existing user.
// Usage: node scripts/import_strong_csv.js <USER_ID> [CSV_PATH]
// Notes:
// - API base and key are hardcoded for convenience.
// - Resolves exercises via resolveExercise; unmatched entries are reported and skipped.

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

let admin = null;
let firestore = null;

function getFirestore() {
  if (!admin) {
    try {
      admin = require('firebase-admin');
    } catch (e) {
      try {
        const functionsDir = path.resolve(__dirname, 'firebase_functions', 'functions');
        admin = require(require.resolve('firebase-admin', { paths: [functionsDir] }));
      } catch (err) {
        throw new Error('firebase-admin is required for dedupe lookup. Install it or run from functions dir.');
      }
    }
    if (!admin.apps.length) {
      admin.initializeApp();
    }
  }
  if (!firestore) {
    firestore = admin.firestore();
  }
  return firestore;
}

const API_BASE_URL = 'https://us-central1-myon-53d85.cloudfunctions.net';
const API_KEY = 'myon-agent-key-2024';

function iso(date) {
  return (date instanceof Date ? date : new Date(date)).toISOString();
}

async function httpJson(method, endpoint, body, extraHeaders) {
  const url = `${API_BASE_URL.replace(/\/$/, '')}/${endpoint.replace(/^\//, '')}`;
  const res = await fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json', 'X-API-Key': API_KEY, ...(extraHeaders || {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  let json;
  try { json = text ? JSON.parse(text) : {}; } catch (e) { throw new Error(`Non-JSON response from ${endpoint}: ${text}`); }
  if (!res.ok || json?.success === false) {
    const err = json?.error || json;
    throw new Error(`HTTP ${res.status} ${res.statusText} at ${endpoint}: ${typeof err === 'string' ? err : JSON.stringify(err)}`);
  }
  return json;
}

async function ensureUserDoc(userId) {
  try {
    // Create minimal user mirrors via preferences; safe no-op if exists
    await httpJson('POST', 'updateUserPreferences', {
      userId,
      preferences: {
        week_starts_on_monday: true,
        timezone: 'UTC'
      }
    });
  } catch (e) {
    console.warn('ensureUserDoc warning:', e.message);
  }
}

async function followCanonical(exerciseId) {
  try {
    const resp = await httpJson('POST', 'getExercise', { exerciseId });
    // Shapes: { success, data: { id, ... } } or nested
    const data = resp?.data || resp;
    if (data && typeof data === 'object') {
      const ex = data.exercise || data;
      if (ex && typeof ex === 'object') return ex.id || exerciseId;
    }
  } catch (_) {}
  return exerciseId;
}

// Minimal CSV parser for semicolon- or comma-delimited, double-quoted values.
function parseCSV(content) {
  const lines = content.split(/\r?\n/).filter(l => l.length > 0);
  if (lines.length === 0) return [];
  const delimiter = detectDelimiter(lines[0]);
  const header = splitLine(lines[0], delimiter);
  const rows = [];
  for (let i = 1; i < lines.length; i++) {
    const fields = splitLine(lines[i], delimiter);
    if (fields.length === 0) continue;
    const obj = {};
    for (let j = 0; j < header.length; j++) {
      obj[stripQuotes(header[j])] = stripQuotes(fields[j] || '');
    }
    rows.push(obj);
  }
  return rows;
}

function detectDelimiter(line) {
  const semi = (line.match(/;/g) || []).length;
  const comma = (line.match(/,/g) || []).length;
  if (semi === 0 && comma === 0) return ';';
  return semi >= comma ? ';' : ',';
}

function splitLine(line, delimiter = ';') {
  const out = [];
  let cur = '';
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      inQuotes = !inQuotes;
      cur += ch;
    } else if (ch === delimiter && !inQuotes) {
      out.push(cur);
      cur = '';
    } else {
      cur += ch;
    }
  }
  out.push(cur);
  return out;
}

function stripQuotes(s) {
  if (s == null) return '';
  s = String(s);
  if (s.startsWith('"') && s.endsWith('"')) return s.slice(1, -1);
  return s;
}

function toNumber(str) {
  if (!str) return null;
  const n = Number(str);
  return Number.isFinite(n) ? n : null;
}

function parseStrongDate(dateStr) {
  if (!dateStr) throw new Error('Missing Date column in CSV export.');
  // Input like: 2024-06-18 11:04:00 (local time)
  // Treat as local and convert to ISO.
  return new Date(dateStr.replace(' ', 'T'));
}

function parseExerciseName(raw) {
  // Example: "Deadlift (Barbell)" => baseName: Deadlift, equipment: [Barbell]
  const m = raw.match(/^(.*?)(?:\s*\((.*)\))?$/);
  const base = (m && m[1]) ? m[1].trim() : raw.trim();
  const equipRaw = (m && m[2]) ? m[2].trim() : '';
  // Split on '-' or ',' to get tokens; trim
  const equipment = equipRaw ? equipRaw.split(/-|,/).map(s => s.trim()).filter(Boolean) : [];
  return { base, equipment };
}

function deriveRIR(rpeStr) {
  const rpe = toNumber(rpeStr);
  if (!Number.isFinite(rpe)) return 2; // default when missing
  // Discrete mapping per table, capped to max RIR = 4
  // 10 -> 0, 9.5 -> 0, 9 -> 1, 8.5 -> 1 (possibly 2), 8 -> 2, 7.5 -> 2, 7 -> 3, 5-6 -> 4
  let rir;
  if (rpe >= 9.5) rir = 0;
  else if (rpe >= 9.0) rir = 1;
  else if (rpe >= 8.5) rir = 1; // could be 2; choose conservative 1
  else if (rpe >= 8.0) rir = 2;
  else if (rpe >= 7.5) rir = 2;
  else if (rpe >= 7.0) rir = 3;
  else if (rpe >= 5.0) rir = 4;
  else rir = 4;
  if (rir > 4) rir = 4;
  if (rir < 0) rir = 0;
  return rir;
}

function sortSetOrder(a, b) {
  const toRank = (v) => {
    if (v === 'WARM_UP') return -1000;
    if (v === 'DROP_SET') return 1000;
    if (v === 'FAILURE') return 9999;
    const n = toNumber(v);
    return Number.isFinite(n) ? n : 0;
  };
  return toRank(a) - toRank(b);
}

function groupByWorkout(rows) {
  const groups = new Map();
  for (const r of rows) {
    const workoutNo = r['Workout #'];
    const dateStr = r['Date'];
    const name = r['Workout Name'];
    const key = `${workoutNo}|${dateStr}|${name}`;
    if (!groups.has(key)) {
      groups.set(key, { rows: [], meta: { no: workoutNo, dateStr, name } });
    }
    groups.get(key).rows.push(r);
  }
  return groups;
}

async function resolveExerciseCached(cache, base, equipment, userId) {
  const key = `${base}|${equipment.join(',')}`;
  if (cache.has(key)) return cache.get(key);
  // Try resolveExercise first
  try {
    const resp = await httpJson('POST', 'resolveExercise', { q: base, context: { available_equipment: equipment } });
    const best = resp?.data?.best || resp?.data?.data?.best || resp?.data?.best || resp?.best;
    if (best?.id) {
      const canonicalId = await followCanonical(best.id);
      cache.set(key, canonicalId);
      return canonicalId;
    }
  } catch (_) {}
  // Fallback: searchExercises
  try {
    const url = `${API_BASE_URL.replace(/\/$/, '')}/searchExercises?query=${encodeURIComponent(base)}&limit=5`;
    const res = await fetch(url, { headers: { 'X-API-Key': API_KEY } });
    const json = await res.json();
    const items = json?.data?.items || [];
    if (items.length) {
      const canonicalId = await followCanonical(items[0].id);
      cache.set(key, canonicalId);
      return canonicalId;
    }
  } catch (_) {}
  // Create placeholder draft as a last resort
  try {
    const ensure = await httpJson('POST', 'ensureExerciseExists', { exercise: { name: base, equipment } }, { 'X-User-Id': userId });
    const createdId = ensure?.data?.exercise_id || ensure?.exercise_id;
    if (createdId) {
      const canonicalId = await followCanonical(createdId);
      cache.set(key, canonicalId);
      return canonicalId;
    }
  } catch (_) {}
  cache.set(key, null);
  return null;
}

async function main() {
  const userId = process.argv[2];
  const csvPath = process.argv[3] || path.resolve(process.cwd(), 'strong_workouts.csv');
  if (!userId) {
    console.error('Usage: node scripts/import_strong_csv.js <USER_ID> [CSV_PATH]');
    process.exit(1);
  }
  if (!fs.existsSync(csvPath)) {
    console.error('CSV file not found:', csvPath);
    process.exit(1);
  }

  console.log('Importing Strong CSV for user:', userId, 'from', csvPath);
  // Ensure Firestore shows the parent user doc so subcollections are visible
  await ensureUserDoc(userId);
  const content = fs.readFileSync(csvPath, 'utf8');
  const rows = parseCSV(content);
  if (!rows.length) {
    console.log('No rows parsed. Exiting.');
    return;
  }
  const groups = groupByWorkout(rows);
  console.log('Workouts to import:', groups.size);

  const exerciseCache = new Map();
  const unresolved = new Set();
  let imported = 0;
  // Optional manual mapping file next to CSV: same name + .map.json
  const mappingPath = csvPath + '.map.json';
  let manualMap = {};
  if (fs.existsSync(mappingPath)) {
    try { manualMap = JSON.parse(fs.readFileSync(mappingPath, 'utf8')); } catch (_) {}
  }

  for (const [, bundle] of groups) {
    const { rows: wrows, meta } = bundle;
    // Metadata
    const start = parseStrongDate(meta.dateStr);
    const duration = toNumber(wrows[0]['Duration (sec)']) || 3600;
    const end = new Date(start.getTime() + duration * 1000);
    const workoutNotes = (wrows.find(r => r['Workout Notes']) || {})['Workout Notes'] || '';

    // Group by exercise name
    const byEx = new Map();
    for (const r of wrows) {
      const exName = r['Exercise Name'];
      if (!exName) continue;
      if (!byEx.has(exName)) byEx.set(exName, []);
      byEx.get(exName).push(r);
    }

    const exercises = [];
    for (const [exName, srows] of byEx.entries()) {
      const { base, equipment } = parseExerciseName(exName);
      let exId = null;
      // Manual mapping takes precedence when provided
      if (manualMap[exName]) {
        exId = manualMap[exName];
      } else {
        exId = await resolveExerciseCached(exerciseCache, base, equipment, userId);
      }
      if (!exId) {
        unresolved.add(exName);
        continue; // skip unknown exercise to avoid touching catalog
      }
      // Sort sets by Set Order
      srows.sort((a, b) => sortSetOrder(a['Set Order'], b['Set Order']));
      const sets = [];
      for (const sr of srows) {
        const order = sr['Set Order'];
        const reps = toNumber(sr['Reps']);
        const weightKg = toNumber(sr['Weight (kg)'] ?? sr['Weight']);
        const rpe = sr['RPE'];
        const seconds = toNumber(sr['Seconds']);
        let type = 'working set';
        if (order === 'WARM_UP') type = 'warmup';
        if (order === 'DROP_SET') type = 'drop set';
        if (order === 'FAILURE') type = 'failure set';
        // Mark incomplete if reps missing or zero; still record weight if present
        const isCompleted = Number.isFinite(reps) && reps > 0;
        sets.push({
          reps: Number.isFinite(reps) ? reps : 0,
          rir: deriveRIR(rpe),
          type,
          weight_kg: Number.isFinite(weightKg) ? weightKg : 0,
          is_completed: isCompleted,
          seconds: Number.isFinite(seconds) ? seconds : undefined,
        });
      }
      // Drop empty set lists
      if (sets.length === 0) continue;
      exercises.push({ exercise_id: exId, name: base, position: exercises.length, sets });
    }

    if (exercises.length === 0) {
      console.log('Skipping workout with no resolvable exercises:', meta.name, meta.dateStr);
      continue;
    }

    // Build a dedupe digest that is resilient to small time skews: round start to 10-min buckets
    const roundedStart = new Date(Math.floor(start.getTime() / (10 * 60 * 1000)) * (10 * 60 * 1000));
    const digestObj = {
      dateBucket: roundedStart.toISOString(),
      name: meta.name,
      ex: exercises.map(e => ({ id: e.exercise_id, sets: e.sets.map(s => [s.reps, s.weight_kg, s.type]) })),
    };
    const digest = crypto.createHash('sha1').update(JSON.stringify(digestObj)).digest('hex');

    // Dedup existing workout with same import key
    const normalizedName = (meta.name || '').trim();
    const importKey = `${roundedStart.toISOString()}|${normalizedName}`;
    let existingWorkoutId = null;
    try {
      const db = getFirestore();
      const userDoc = db.collection('users').doc(userId);
      const workoutsSnap = await userDoc.collection('workouts')
        .where('source_meta.key', '==', importKey)
        .get();
      if (!workoutsSnap.empty) {
        const docs = workoutsSnap.docs.sort((a, b) => {
          const at = a.createTime?.seconds || 0;
          const bt = b.createTime?.seconds || 0;
          return at - bt;
        });
        existingWorkoutId = docs[0].id;
        const duplicates = docs.slice(1);
        if (duplicates.length) {
          await Promise.all(
            duplicates.map((doc) => doc.ref.delete().catch(() => {}))
          );
        }
      }
    } catch (e) {
      console.warn('Existing workout lookup failed (continuing):', e.message);
    }

    const payload = {
      userId,
      workout: {
        id: existingWorkoutId || `imp:strong:${digest}`,
        start_time: iso(start),
        end_time: iso(end),
        notes: `Strong import — ${meta.name}${workoutNotes ? ' — ' + workoutNotes : ''}`,
        source_meta: { source: 'strong_csv', key: importKey, digest },
        exercises,
      },
    };

    try {
      await httpJson('POST', 'upsertWorkout', payload);
      imported += 1;
    } catch (e) {
      console.error('Failed to import workout', meta.name, meta.dateStr, e.message);
    }
  }

  console.log('Imported workouts:', imported, '/', groups.size);
  if (unresolved.size) {
    console.log('Unresolved exercise names (skipped):');
    for (const n of unresolved) console.log('-', n);
  }
  console.log('Running analytics controller...');
  try {
    const run = await httpJson('POST', 'runAnalyticsForUser', { userId });
    console.log('Analytics result:', run?.data || run);
  } catch (e) {
    console.warn('Analytics controller failed:', e.message);
  }
}

main().catch(err => {
  console.error('Import failed:', err?.message || err);
  process.exit(1);
});


