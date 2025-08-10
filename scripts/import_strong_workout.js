#!/usr/bin/env node

/*
Usage:
  node scripts/import_strong_workout.js --file /abs/path/to/workout.txt --user USER_ID [--yes] [--default-warmup-rir 3] [--tz Europe/Oslo]

Requirements:
  - Set GOOGLE_APPLICATION_CREDENTIALS to a service account JSON with Firestore access
  - npm install firebase-admin

Behavior:
  - Parses a text file in Strong export format (see sample in task)
  - Tries to match each exercise title to an exercise from /exercises
  - Proposes mappings and lets you accept/edit before writing
  - Prompts for any missing RIR values (or uses --default-warmup-rir)
  - Writes the workout to users/{userId}/workouts with correct schema
*/

const fs = require('fs');
const path = require('path');
const readline = require('readline');
const admin = require('firebase-admin');

// Initialize Firebase Admin
if (!admin.apps.length) {
  admin.initializeApp();
}
const db = admin.firestore();

// -------------- CLI ARGS --------------
function parseArgs(argv) {
  const args = {};
  for (let i = 2; i < argv.length; i++) {
    const arg = argv[i];
    if (arg.startsWith('--')) {
      const key = arg.replace(/^--/, '');
      const next = argv[i + 1];
      if (!next || next.startsWith('--')) {
        args[key] = true;
      } else {
        args[key] = next;
        i++;
      }
    }
  }
  return args;
}

const args = parseArgs(process.argv);
const filePath = args.file;
const userId = args.user;
const autoYes = Boolean(args.yes);
const defaultWarmupRir = args['default-warmup-rir'] !== undefined ? parseInt(args['default-warmup-rir'], 10) : undefined;
const analyticsMode = (args.analytics || 'local').toLowerCase(); // 'local' | 'cloud' | 'none'
const tz = args.tz || process.env.TZ || 'UTC';

if (!filePath || !userId) {
  console.error('Missing required args.');
  console.error('Example: node scripts/import_strong_workout.js --file /abs/path/workout.txt --user USER_ID [--yes] [--default-warmup-rir 3] [--tz Europe/Oslo]');
  process.exit(1);
}

// -------------- UTILITIES --------------
function toNumberLocaleFlexible(str) {
  if (typeof str !== 'string') return NaN;
  const s = str.trim().replace(/\s/g, '').replace(',', '.');
  const num = Number(s);
  return Number.isFinite(num) ? num : NaN;
}

function normalizeName(name) {
  if (!name) return '';
  let n = name.toLowerCase();
  n = n.replace(/\([^)]*\)/g, ''); // remove parenthetical content
  n = n.replace(/[^a-z0-9\s]/g, ' ');
  n = n.replace(/\s+/g, ' ').trim();
  return n;
}

function levenshtein(a, b) {
  if (a === b) return 0;
  const alen = a.length;
  const blen = b.length;
  if (alen === 0) return blen;
  if (blen === 0) return alen;
  const v0 = new Array(blen + 1).fill(0);
  const v1 = new Array(blen + 1).fill(0);
  for (let i = 0; i <= blen; i++) v0[i] = i;
  for (let i = 0; i < alen; i++) {
    v1[0] = i + 1;
    for (let j = 0; j < blen; j++) {
      const cost = a[i] === b[j] ? 0 : 1;
      v1[j + 1] = Math.min(v1[j] + 1, v0[j + 1] + 1, v0[j] + cost);
    }
    for (let j = 0; j <= blen; j++) v0[j] = v1[j];
  }
  return v1[blen];
}

function rpeToRir(rpe) {
  const mapping = { 10: 0, 9: 1, 8: 2, 7: 3, 6: 4 };
  return mapping[rpe] ?? null;
}

function parseDateTimeLine(line, tz) {
  // Examples to support:
  // "Monday 4. August 2025 at 17.08 until 18:10"
  // "Monday 4 August 2025 at 17:08 until 18:10"
  const months = {
    january: 1, february: 2, march: 3, april: 4, may: 5, june: 6,
    july: 7, august: 8, september: 9, october: 10, november: 11, december: 12
  };
  const regex = /([0-9]{1,2})\.?\s+([A-Za-z]+)\s+([0-9]{4}).*?at\s+([0-9]{1,2})[\.:]([0-9]{2})\s+until\s+([0-9]{1,2})[:\.]([0-9]{2})/i;
  const m = line.match(regex);
  if (!m) return { start: null, end: null };
  const day = parseInt(m[1], 10);
  const monthName = m[2].toLowerCase();
  const year = parseInt(m[3], 10);
  const sh = parseInt(m[4], 10);
  const sm = parseInt(m[5], 10);
  const eh = parseInt(m[6], 10);
  const em = parseInt(m[7], 10);
  const month = months[monthName];
  if (!month) return { start: null, end: null };

  // Build Date objects in the provided tz if available; otherwise, assume local
  // Node Date has no built-in IANA TZ construction; we will build in local and treat as that tz.
  // Accept that Firestore will store as Timestamp; ensure order is correct.
  const start = new Date(year, month - 1, day, sh, sm, 0);
  const end = new Date(year, month - 1, day, eh, em, 0);
  return { start, end };
}

function detectSetType(label, bracketType) {
  // label like 'W1' or 'Set 1'
  if (label && /^w\d+/i.test(label)) return 'Warm-up';
  if (bracketType) {
    const t = bracketType.trim().toLowerCase();
    if (t.includes('warm')) return 'Warm-up';
    if (t.includes('fail')) return 'Failure';
    if (t.includes('drop')) return 'Drop Set';
  }
  return 'Working Set';
}

function extractLinkFromText(text) {
  const m = text.match(/https?:\/\/\S+/);
  return m ? m[0] : null;
}

// -------------- PARSER --------------
function parseStrongTxt(content) {
  const lines = content.split(/\r?\n/);

  let title = '';
  let startEndParsed = false;
  let startTime = null;
  let endTime = null;

  const exercises = [];
  let current = null;

  for (let i = 0; i < lines.length; i++) {
    const raw = lines[i];
    const line = raw.trim();
    if (i === 0) {
      title = line;
      continue;
    }
    if (!startEndParsed && line.length > 0) {
      const { start, end } = parseDateTimeLine(line, tz);
      if (start && end) {
        startTime = start;
        endTime = end;
        startEndParsed = true;
        continue;
      }
    }

    if (line.length === 0) {
      // empty line separates blocks
      continue;
    }

    // Start of a new exercise: a line with no colon and not a set line
    const isSetLine = /^(w\d+|set\s*\d+)\s*:/i.test(line);
    if (!isSetLine && !/^https?:\/\//i.test(line)) {
      // Commit previous exercise if present
      if (current) exercises.push(current);
      current = { title: line, sets: [] };
      continue;
    }

    // Set lines
    if (isSetLine && current) {
      // Examples:
      // W1: 24 kg × 12 [Warm-up]
      // Set 1: 44 kg × 8 @ 6
      // Set 4: 22 kg × 10 @ 10 [Failure]
      const match = line.match(/^(w\d+|set\s*\d+):\s*(.+)$/i);
      if (!match) continue;
      const label = match[1];
      const rest = match[2];

      // Extract bracket type e.g., [Warm-up] or [Failure]
      let bracketType = null;
      const bracketMatch = rest.match(/\[(.*?)\]/);
      if (bracketMatch) bracketType = bracketMatch[1];

      // Extract RPE e.g., @ 7
      let rpe = null;
      const rpeMatch = rest.match(/@\s*([0-9]+(\.[0-9])?)/);
      if (rpeMatch) rpe = Math.round(parseFloat(rpeMatch[1]));

      // Extract weight and reps: "24 kg × 12" or "2,5 kg × 15"
      // Normalize multiplication sign variants (×, x)
      const normalized = rest.replace(/×/g, 'x').replace(/✕/g, 'x');
      const wr = normalized.match(/([0-9][0-9\.,]*)\s*(kg|lb|lbs)?\s*[xX]\s*([0-9]+)/);
      if (!wr) {
        continue;
      }
      const weightRaw = wr[1];
      const unit = (wr[2] || 'kg').toLowerCase();
      const reps = parseInt(wr[3], 10);
      let weight = toNumberLocaleFlexible(weightRaw);
      if (!Number.isFinite(weight)) weight = 0;
      if (unit === 'lb' || unit === 'lbs') {
        weight = weight * 0.45359237;
      }

      const type = detectSetType(label, bracketType);
      const rir = rpe !== null ? rpeToRir(rpe) : null;

      current.sets.push({
        label,
        reps,
        weightKg: Number(weight.toFixed(3)),
        rir, // may be null, will be resolved later
        type,
        isCompleted: true
      });
    }
  }

  if (current) exercises.push(current);

  // Also capture a link if present anywhere
  const link = extractLinkFromText(content);

  return { title, startTime, endTime, exercises, link };
}

// -------------- INTERACTIVE --------------
function createInterface() {
  return readline.createInterface({ input: process.stdin, output: process.stdout });
}

function askQuestion(rl, question) {
  return new Promise((resolve) => rl.question(question, resolve));
}

async function resolveMissingRir(rl, sets, fallbackWarmupRir) {
  for (const s of sets) {
    if (s.rir === null || s.rir === undefined) {
      if (s.type === 'Warm-up' && Number.isInteger(fallbackWarmupRir)) {
        s.rir = fallbackWarmupRir;
        continue;
      }
      const answer = await askQuestion(rl, `Missing RIR for ${s.type} ${s.reps} reps @ ${s.weightKg}kg. Enter RIR (0-4): `);
      const val = parseInt(answer, 10);
      if (!Number.isFinite(val) || val < 0 || val > 4) {
        console.log('Invalid RIR. Defaulting to 2.');
        s.rir = 2;
      } else {
        s.rir = val;
      }
    }
  }
}

function scoreExerciseName(targetNorm, exercise) {
  const candNorm = normalizeName(exercise.name || '');
  const dist = levenshtein(targetNorm, candNorm);
  return { exercise, dist };
}

function pickTopMatches(targetTitle, allExercises, topN = 5) {
  const targetNorm = normalizeName(targetTitle);
  const scored = allExercises.map(ex => scoreExerciseName(targetNorm, ex));
  scored.sort((a, b) => a.dist - b.dist);
  return scored.slice(0, topN).map(s => s.exercise);
}

async function mapExercises(rl, parsedExercises, allExercises) {
  const mappings = [];
  for (let i = 0; i < parsedExercises.length; i++) {
    const pe = parsedExercises[i];
    console.log(`\nExercise ${i + 1}: "${pe.title}"`);
    const candidates = pickTopMatches(pe.title, allExercises, 5);
    candidates.forEach((c, idx) => {
      console.log(`  [${idx + 1}] ${c.name} (id: ${c.id})`);
    });
    console.log('  [s] Search by text');
    console.log('  [x] Abort import');

    let choice = '1';
    if (!autoYes) {
      choice = await askQuestion(rl, `Choose mapping [1-${candidates.length}] (Enter to accept #1): `);
    }

    if (choice.toLowerCase() === 'x') {
      throw new Error('Aborted by user.');
    }

    let selected = null;
    if (choice.toLowerCase() === 's') {
      const term = await askQuestion(rl, 'Enter search term: ');
      const termNorm = term.trim().toLowerCase();
      const filtered = allExercises.filter(ex =>
        (ex.name || '').toLowerCase().includes(termNorm)
      ).slice(0, 10);
      if (filtered.length === 0) {
        console.log('No matches. Using best guess.');
        selected = candidates[0];
      } else {
        filtered.forEach((c, idx) => console.log(`  [${idx + 1}] ${c.name} (id: ${c.id})`));
        let pick = '1';
        if (!autoYes) pick = await askQuestion(rl, `Choose mapping [1-${filtered.length}] (Enter to accept #1): `);
        const pickIdx = Math.max(1, Math.min(parseInt(pick || '1', 10), filtered.length)) - 1;
        selected = filtered[pickIdx];
      }
    } else {
      const idx = Math.max(1, Math.min(parseInt(choice || '1', 10), candidates.length)) - 1;
      selected = candidates[idx];
    }

    mappings.push({ parsedTitle: pe.title, exercise: selected });
  }
  return mappings;
}

function defaultExerciseAnalytics() {
  return {
    total_sets: 0,
    total_reps: 0,
    total_weight: 0,
    weight_format: 'kg',
    avg_reps_per_set: 0,
    avg_weight_per_set: 0,
    avg_weight_per_rep: 0,
    weight_per_muscle_group: {},
    weight_per_muscle: {},
    reps_per_muscle_group: {},
    reps_per_muscle: {},
    sets_per_muscle_group: {},
    sets_per_muscle: {}
  };
}

function defaultWorkoutAnalytics() {
  return {
    total_sets: 0,
    total_reps: 0,
    total_weight: 0,
    weight_format: 'kg',
    avg_reps_per_set: 0,
    avg_weight_per_set: 0,
    avg_weight_per_rep: 0,
    weight_per_muscle_group: {},
    weight_per_muscle: {},
    reps_per_muscle_group: {},
    reps_per_muscle: {},
    sets_per_muscle_group: {},
    sets_per_muscle: {}
  };
}

function buildWorkoutDocument({ userId, parsed, mappings, forcedId }) {
  const now = new Date();
  const start = parsed.startTime || now;
  const end = parsed.endTime || now;

  const exercises = parsed.exercises.map((pe, idx) => {
    const mapping = mappings.find(m => m.parsedTitle === pe.title);
    const exerciseId = mapping?.exercise?.id || null;
    if (!exerciseId) {
      throw new Error(`Exercise mapping missing for "${pe.title}". Aborting.`);
    }
    const name = mapping?.exercise?.name || pe.title;
    const sets = pe.sets.map(s => ({
      id: `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
      reps: s.reps,
      rir: s.rir,
      type: s.type,
      weight_kg: s.weightKg,
      is_completed: Boolean(s.isCompleted)
    }));

    return {
      id: `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
      exercise_id: exerciseId,
      name,
      position: idx,
      sets,
      analytics: analyticsMode === 'local' ? defaultExerciseAnalytics() : undefined
    };
  });

  const notesParts = [];
  if (parsed.title) notesParts.push(`Imported: ${parsed.title}`);
  if (parsed.link) notesParts.push(`Source: ${parsed.link}`);

  const workout = {
    id: forcedId || undefined,
    user_id: userId,
    source_template_id: null,
    created_at: admin.firestore.Timestamp.fromDate(now),
    updated_at: admin.firestore.Timestamp.fromDate(now),
    start_time: admin.firestore.Timestamp.fromDate(start),
    end_time: admin.firestore.Timestamp.fromDate(end),
    exercises,
    notes: notesParts.length ? notesParts.join(' | ') : null,
    analytics: analyticsMode === 'local' ? defaultWorkoutAnalytics() : undefined
  };

  return workout;
}

function printWorkoutSummary(workout) {
  console.log('\nProposed workout to import:');
  console.log(`- User: ${workout.user_id}`);
  console.log(`- Start: ${workout.start_time.toDate().toISOString()}`);
  console.log(`- End:   ${workout.end_time.toDate().toISOString()}`);
  if (workout.notes) console.log(`- Notes: ${workout.notes}`);
  console.log(`- Exercises: ${workout.exercises.length}`);
  workout.exercises.forEach((ex, i) => {
    const working = ex.sets.filter(s => s.is_completed && /working|failure|drop/i.test(s.type)).length;
    const warmups = ex.sets.filter(s => s.is_completed && /warm/i.test(s.type)).length;
    console.log(`  ${i + 1}. ${ex.name} (id: ${ex.exercise_id || 'UNMAPPED'}) - sets: ${ex.sets.length} (working ~${working}, warm-ups ~${warmups})`);
  });
}

async function main() {
  // Read file
  const abs = path.isAbsolute(filePath) ? filePath : path.join(process.cwd(), filePath);
  const content = fs.readFileSync(abs, 'utf8');
  const parsed = parseStrongTxt(content);

  // Fetch exercises
  console.log('Fetching exercises from Firestore...');
  const snap = await db.collection('exercises').get();
  const allExercises = snap.docs.map(d => ({ id: d.id, ...d.data() }));
  if (allExercises.length === 0) {
    console.error('No exercises found in /exercises. Aborting.');
    process.exit(1);
  }

  // Map exercises
  const rl = createInterface();
  const mappings = await mapExercises(rl, parsed.exercises, allExercises);

  // Resolve missing RIRs per set
  for (const pe of parsed.exercises) {
    await resolveMissingRir(rl, pe.sets, defaultWarmupRir);
  }

  // Build workout doc (defer id until we create a docRef)
  const draftWorkout = buildWorkoutDocument({ userId, parsed, mappings });

  // Show summary and confirm
  printWorkoutSummary(draftWorkout);
  let proceed = true;
  if (!autoYes) {
    const answer = await askQuestion(rl, 'Proceed with import? [y/N]: ');
    proceed = /^y(es)?$/i.test((answer || '').trim());
  }
  rl.close();

  if (!proceed) {
    console.log('Aborted.');
    process.exit(1);
  }

  // Create doc with explicit id so `id` field exists in document
  const workoutsColl = db.collection('users').doc(userId).collection('workouts');
  const docRef = workoutsColl.doc();
  const workoutDoc = buildWorkoutDocument({ userId, parsed, mappings, forcedId: docRef.id });
  await docRef.set(workoutDoc, { merge: false });
  console.log(`Imported workout with id: ${docRef.id}`);
  console.log('Note: analytics will be computed/updated by Cloud Functions shortly after creation.');
}

main().catch(err => {
  console.error(err);
  process.exit(1);
});