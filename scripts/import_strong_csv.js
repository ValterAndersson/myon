'use strict';

/**
 * Import workouts from Strong app CSV and upsert into MYON for an existing user.
 *
 * Usage:
 *   node scripts/import_strong_csv.js <USER_ID> [CSV_PATH] [OPTIONS]
 *
 * Options:
 *   --interactive    Prompt for exercise disambiguation when multiple matches found
 *   --cleanup        Clean up duplicate workouts before importing
 *   --dry-run        Show what would be imported without making changes
 *
 * Examples:
 *   node scripts/import_strong_csv.js abc123 strong.csv --interactive
 *   node scripts/import_strong_csv.js abc123 --cleanup
 */

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const readline = require('readline');

let admin = null;
let firestore = null;

// CLI flags
const args = process.argv.slice(2);
const FLAGS = {
  interactive: args.includes('--interactive'),
  cleanup: args.includes('--cleanup'),
  dryRun: args.includes('--dry-run'),
};
const positionalArgs = args.filter(a => !a.startsWith('--'));

function getFirestore() {
  if (!admin) {
    try {
      admin = require('firebase-admin');
    } catch (e) {
      try {
        const functionsDir = path.resolve(__dirname, 'firebase_functions', 'functions');
        admin = require(require.resolve('firebase-admin', { paths: [functionsDir] }));
      } catch (err) {
        throw new Error('firebase-admin is required. Install it or run from functions dir.');
      }
    }
    if (!admin.apps.length) {
      admin.initializeApp({
        projectId: process.env.GOOGLE_CLOUD_PROJECT || 'myon-53d85',
      });
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

// =============================================================================
// CSV PARSING
// =============================================================================

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
  return new Date(dateStr.replace(' ', 'T'));
}

function parseExerciseName(raw) {
  const m = raw.match(/^(.*?)(?:\s*\((.*)\))?$/);
  const base = (m && m[1]) ? m[1].trim() : raw.trim();
  const equipRaw = (m && m[2]) ? m[2].trim() : '';
  const equipment = equipRaw ? equipRaw.split(/-|,/).map(s => s.trim()).filter(Boolean) : [];
  return { base, equipment };
}

function deriveRIR(rpeStr) {
  const rpe = toNumber(rpeStr);
  if (!Number.isFinite(rpe)) return 2;
  let rir;
  if (rpe >= 9.5) rir = 0;
  else if (rpe >= 9.0) rir = 1;
  else if (rpe >= 8.5) rir = 1;
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

// =============================================================================
// INTERACTIVE PROMPTS
// =============================================================================

let rl = null;

function getReadline() {
  if (!rl) {
    rl = readline.createInterface({
      input: process.stdin,
      output: process.stdout,
    });
  }
  return rl;
}

function closeReadline() {
  if (rl) {
    rl.close();
    rl = null;
  }
}

async function prompt(question) {
  return new Promise((resolve) => {
    getReadline().question(question, (answer) => {
      resolve(answer.trim());
    });
  });
}

async function promptChoice(message, options) {
  console.log(`\n${message}`);
  options.forEach((opt, i) => {
    console.log(`  [${i + 1}] ${opt.label}`);
  });

  while (true) {
    const answer = await prompt(`Choice [1-${options.length}]: `);
    const num = parseInt(answer, 10);
    if (num >= 1 && num <= options.length) {
      return options[num - 1];
    }
    // Default to first option on empty input
    if (answer === '') {
      return options[0];
    }
    console.log(`Please enter a number between 1 and ${options.length}`);
  }
}

// =============================================================================
// EXERCISE RESOLUTION
// =============================================================================

async function searchExercises(query, limit = 10) {
  // Try API first
  try {
    const url = `${API_BASE_URL}/searchExercises?query=${encodeURIComponent(query)}&limit=${limit}`;
    const res = await fetch(url, { headers: { 'X-API-Key': API_KEY } });
    const json = await res.json();
    const apiResults = json?.data?.items || [];
    if (apiResults.length > 0) {
      console.log(`    [API] Found ${apiResults.length} results for: "${query}"`);
      return apiResults;
    }
    console.log(`    [API] No results for: "${query}" - trying Firestore`);
  } catch (e) {
    console.log(`    [API] Error searching: ${e.message} - trying Firestore`);
  }

  // Fallback: Search Firestore directly
  return searchExercisesFirestore(query, limit);
}

async function searchExercisesFirestore(query, limit = 10) {
  try {
    const db = getFirestore();
    const normalizedQuery = query.toLowerCase().trim();

    // Parse out equipment from query if present (e.g., "Preacher Curl (Barbell)" -> "preacher curl")
    const baseQuery = normalizedQuery.replace(/\s*\([^)]*\)\s*$/, '').trim();

    // Try multiple slug formats
    const slugVariants = [
      baseQuery.replace(/[^a-z0-9]+/g, '_'),      // preacher_curl
      baseQuery.replace(/[^a-z0-9]+/g, '-'),      // preacher-curl
      baseQuery.replace(/\s+/g, '_').replace(/[^a-z0-9_]/g, ''), // preacher_curl (preserving underscores)
    ];

    // Strategy 1: Search by family_slug with multiple formats
    for (const slug of slugVariants) {
      const familySnap = await db.collection('exercises')
        .where('family_slug', '==', slug)
        .limit(limit)
        .get();

      if (!familySnap.empty) {
        console.log(`    [Firestore] Found ${familySnap.size} results by family_slug: ${slug}`);
        return familySnap.docs.map(d => ({ id: d.id, ...d.data() }));
      }
    }

    // Strategy 2: Try partial family_slug match (first two words)
    const words = baseQuery.split(/\s+/);
    if (words.length > 1) {
      const partialSlugs = [
        words.slice(0, 2).join('_'),
        words.slice(0, 2).join('-'),
        words[0] + '_' + words[1],
      ];

      for (const slug of partialSlugs) {
        const partialSnap = await db.collection('exercises')
          .where('family_slug', '==', slug)
          .limit(limit)
          .get();

        if (!partialSnap.empty) {
          console.log(`    [Firestore] Found ${partialSnap.size} results by partial slug: ${slug}`);
          return partialSnap.docs.map(d => ({ id: d.id, ...d.data() }));
        }
      }
    }

    // Strategy 3: Search by name_slug
    for (const slug of slugVariants) {
      const nameSnap = await db.collection('exercises')
        .where('name_slug', '==', slug)
        .limit(limit)
        .get();

      if (!nameSnap.empty) {
        console.log(`    [Firestore] Found ${nameSnap.size} results by name_slug: ${slug}`);
        return nameSnap.docs.map(d => ({ id: d.id, ...d.data() }));
      }
    }

    // Strategy 4: Client-side search through all exercises (last resort)
    if (baseQuery.length >= 3) {
      console.log(`    [Firestore] Falling back to client-side search for: "${baseQuery}"`);
      const allSnap = await db.collection('exercises').get();
      const results = [];
      const queryWords = baseQuery.split(/\s+/);

      for (const doc of allSnap.docs) {
        const data = doc.data();
        const name = (data.name || '').toLowerCase();
        const nameBase = name.replace(/\s*\([^)]*\)\s*$/, '').trim(); // Strip equipment
        const familySlugDoc = (data.family_slug || '').toLowerCase();
        const nameSlugDoc = (data.name_slug || '').toLowerCase();

        // Check various matching strategies
        let matched = false;

        // Exact base name match
        if (nameBase === baseQuery) {
          matched = true;
        }
        // Name contains query
        else if (name.includes(baseQuery)) {
          matched = true;
        }
        // Query contains base name
        else if (baseQuery.includes(nameBase) && nameBase.length >= 5) {
          matched = true;
        }
        // All query words present in name
        else if (queryWords.length >= 2 && queryWords.every(w => name.includes(w))) {
          matched = true;
        }
        // Slug matching
        else if (slugVariants.some(s => familySlugDoc === s || nameSlugDoc.includes(s))) {
          matched = true;
        }

        if (matched) {
          results.push({ id: doc.id, ...data });
          if (results.length >= limit) break;
        }
      }

      if (results.length > 0) {
        console.log(`    [Firestore] Client-side search found ${results.length} results`);
      }
      return results;
    }

    return [];
  } catch (e) {
    console.warn('Firestore search failed:', e.message);
    return [];
  }
}

async function getExercisesByFamily(familySlug) {
  try {
    const db = getFirestore();
    const snap = await db.collection('exercises')
      .where('family_slug', '==', familySlug)
      .get();
    return snap.docs.map(d => ({ id: d.id, ...d.data() }));
  } catch (e) {
    return [];
  }
}

// =============================================================================
// CREATE NEW EXERCISE
// =============================================================================

function generateSlug(name) {
  return name
    .toLowerCase()
    .replace(/[()]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

function generateFamilySlug(baseName) {
  return baseName
    .toLowerCase()
    .replace(/[()]/g, '')
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '');
}

function deriveCategory(name, equipment) {
  const lower = name.toLowerCase();
  // Compound movements
  if (/deadlift|squat|bench\s*press|overhead\s*press|row|pull.?up|chin.?up|dip|lunge/.test(lower)) {
    return 'compound';
  }
  // Isolation movements
  if (/curl|extension|raise|fly|flye|kickback|pushdown|pullover/.test(lower)) {
    return 'isolation';
  }
  return 'compound'; // Default to compound
}

function deriveMovement(name) {
  const lower = name.toLowerCase();

  // Movement type
  let type = 'other';
  if (/press|push/.test(lower)) type = 'press';
  else if (/pull|row|curl/.test(lower)) type = 'pull';
  else if (/squat|lunge|leg\s*press/.test(lower)) type = 'squat';
  else if (/deadlift|hip\s*hinge|rdl|romanian/.test(lower)) type = 'hinge';
  else if (/raise|fly|flye|lateral/.test(lower)) type = 'raise';
  else if (/extension|curl/.test(lower)) type = 'isolation';

  // Split
  let split = 'full_body';
  if (/bench|chest|fly|flye|push.?up|dip|tricep|shoulder|press|raise|pull.?up|chin.?up|row|lat|bicep|curl/.test(lower)) {
    split = 'upper';
  } else if (/squat|leg|lunge|calf|hamstring|quad|glute|deadlift|hip/.test(lower)) {
    split = 'lower';
  } else if (/ab|core|crunch|plank/.test(lower)) {
    split = 'core';
  }

  return { type, split };
}

async function createNewExercise(strongName, equipment) {
  const db = getFirestore();

  // Parse the name
  const { base } = parseExerciseName(strongName);

  // Build canonical name with equipment
  const canonicalName = equipment.length > 0
    ? `${base} (${equipment.map(e => e.charAt(0).toUpperCase() + e.slice(1).toLowerCase()).join(', ')})`
    : base;

  // Generate identifiers
  const nameSlug = generateSlug(canonicalName);
  const familySlug = generateFamilySlug(base);
  const docId = `${familySlug}__${nameSlug}`;

  // Build the exercise document with proper schema
  const now = new Date();
  const exerciseDoc = {
    name: canonicalName,
    name_slug: nameSlug,
    family_slug: familySlug,
    variant_key: equipment.length > 0 ? `equipment:${equipment[0].toLowerCase()}` : null,
    category: deriveCategory(canonicalName, equipment),
    equipment: equipment.map(e => e.toLowerCase()),
    metadata: {
      level: 'intermediate',
      plane_of_motion: null,
      unilateral: false,
    },
    movement: deriveMovement(canonicalName),
    muscles: {
      primary: [],
      secondary: [],
      category: [],
      contribution: {},
    },
    description: '',
    execution_notes: [],
    common_mistakes: [],
    programming_use_cases: [],
    stimulus_tags: [],
    suitability_notes: [],
    coaching_cues: [],
    tips: [],
    // Mark as needing enrichment
    _import_source: 'strong_csv_import',
    _needs_enrichment: true,
    created_at: now,
    updated_at: now,
  };

  // Check if already exists
  const existingDoc = await db.collection('exercises').doc(docId).get();
  if (existingDoc.exists) {
    console.log(`  [=] Exercise already exists: ${docId}`);
    return { id: docId, created: false };
  }

  // Create the exercise
  if (!FLAGS.dryRun) {
    await db.collection('exercises').doc(docId).set(exerciseDoc);
    console.log(`  [+] Created new exercise: ${canonicalName} (${docId})`);

    // Queue enrichment job
    await queueEnrichmentJob(docId, canonicalName);
  } else {
    console.log(`  [+] Would create exercise: ${canonicalName} (${docId})`);
  }

  return { id: docId, created: true };
}

async function queueEnrichmentJob(exerciseId, exerciseName) {
  const db = getFirestore();

  const jobId = `import-enrich-${exerciseId}-${Date.now()}`;
  const now = new Date();

  const job = {
    id: jobId,
    type: 'CATALOG_ENRICH_FIELD',
    queue: 'priority',  // High priority for imported exercises
    status: 'queued',
    priority: 200,  // Higher than normal (100)
    mode: 'apply',  // Actually apply the enrichment
    created_at: now,
    updated_at: now,
    run_after: now,
    attempts: 0,
    max_attempts: 3,
    exercise_doc_ids: [exerciseId],
    enrichment_spec: {
      source: 'strong_csv_import',
      exercise_name: exerciseName,
      enrich_all: true,  // Enrich all missing fields
    },
    result_summary: null,
    error: null,
  };

  if (!FLAGS.dryRun) {
    await db.collection('catalog_jobs').doc(jobId).set(job);
    console.log(`  [>] Queued enrichment job: ${jobId}`);
  } else {
    console.log(`  [>] Would queue enrichment job for: ${exerciseName}`);
  }
}

function normalizeForMatching(str) {
  return str.toLowerCase()
    .replace(/[^a-z0-9]/g, '')
    .replace(/dumbbell|dumbell|db/g, 'dumbbell')
    .replace(/barbell|bb/g, 'barbell')
    .replace(/cable/g, 'cable')
    .replace(/machine/g, 'machine');
}

function scoreMatch(strongName, strongEquip, exercise) {
  let score = 0;
  const exName = (exercise.name || '').toLowerCase();
  const exEquip = (exercise.equipment || []).map(e => e.toLowerCase());
  const strongBase = normalizeForMatching(strongName);

  // Name similarity
  if (exName.includes(strongBase) || strongBase.includes(normalizeForMatching(exName.split('(')[0]))) {
    score += 50;
  }

  // Equipment match
  for (const eq of strongEquip) {
    const normEq = normalizeForMatching(eq);
    if (exEquip.some(e => normalizeForMatching(e).includes(normEq) || normEq.includes(normalizeForMatching(e)))) {
      score += 30;
    }
  }

  // Exact equipment match bonus
  if (strongEquip.length > 0 && exEquip.length > 0) {
    const strongEquipNorm = strongEquip.map(normalizeForMatching).sort().join(',');
    const exEquipNorm = exEquip.map(normalizeForMatching).sort().join(',');
    if (strongEquipNorm === exEquipNorm) {
      score += 20;
    }
  }

  return score;
}

async function resolveExerciseInteractive(cache, strongName, strongEquip, userId, sessionMappings, createdExercises) {
  const cacheKey = `${strongName}|${strongEquip.join(',')}`;

  // Check session cache first
  if (cache.has(cacheKey)) return cache.get(cacheKey);
  if (sessionMappings.has(strongName)) {
    const mapped = sessionMappings.get(strongName);
    cache.set(cacheKey, mapped);
    return mapped;
  }

  // Search for candidates
  const { base, equipment: parsedEquip } = parseExerciseName(strongName);
  const effectiveEquip = strongEquip.length > 0 ? strongEquip : parsedEquip;
  const candidates = await searchExercises(base, 10);

  // No matches found - create new exercise
  if (candidates.length === 0) {
    console.log(`  [!] No matches found for "${strongName}" - creating new exercise`);
    const result = await createNewExercise(strongName, effectiveEquip);
    if (result.created) createdExercises.add(result.id);
    cache.set(cacheKey, result.id);
    sessionMappings.set(strongName, result.id);
    return result.id;
  }

  // Score and sort candidates
  const scored = candidates.map(c => ({
    ...c,
    score: scoreMatch(base, effectiveEquip, c),
  })).sort((a, b) => b.score - a.score);

  // If best match has high confidence (>70) and is significantly better than second, auto-select
  if (scored[0].score >= 70 && (!scored[1] || scored[0].score - scored[1].score >= 20)) {
    console.log(`  [*] Auto-matched "${strongName}" -> "${scored[0].name}" (score: ${scored[0].score})`);
    cache.set(cacheKey, scored[0].id);
    return scored[0].id;
  }

  // Interactive mode: prompt user
  if (FLAGS.interactive) {
    const options = scored.slice(0, 5).map(c => ({
      label: `${c.name} [${(c.equipment || []).join(', ')}] (score: ${c.score})`,
      value: c.id,
    }));
    options.push({ label: 'Create new exercise in catalog', value: 'CREATE_NEW' });

    const choice = await promptChoice(
      `Multiple matches for "${strongName}":`,
      options
    );

    // Handle "Create new" option
    if (choice.value === 'CREATE_NEW') {
      const result = await createNewExercise(strongName, effectiveEquip);
      if (result.created) createdExercises.add(result.id);
      sessionMappings.set(strongName, result.id);
      cache.set(cacheKey, result.id);
      return result.id;
    }

    // Remember for this session (same Strong name -> same choice)
    sessionMappings.set(strongName, choice.value);
    cache.set(cacheKey, choice.value);
    return choice.value;
  }

  // Non-interactive: use best match if score is decent
  if (scored[0].score >= 50) {
    console.log(`  [?] Best guess for "${strongName}" -> "${scored[0].name}" (score: ${scored[0].score})`);
    cache.set(cacheKey, scored[0].id);
    return scored[0].id;
  }

  // Low confidence - create new exercise instead of skipping
  console.log(`  [!] Low confidence for "${strongName}" - creating new exercise`);
  const result = await createNewExercise(strongName, effectiveEquip);
  if (result.created) createdExercises.add(result.id);
  cache.set(cacheKey, result.id);
  sessionMappings.set(strongName, result.id);
  return result.id;
}

// =============================================================================
// DUPLICATE CLEANUP
// =============================================================================

async function cleanupDuplicateWorkouts(userId, dryRun = false) {
  console.log('\n--- Cleaning up duplicate workouts ---');

  const db = getFirestore();
  const workoutsRef = db.collection('users').doc(userId).collection('workouts');
  const snap = await workoutsRef.get();

  if (snap.empty) {
    console.log('No workouts found.');
    return { deleted: 0, kept: 0 };
  }

  // Group by source_meta.key (our dedup key)
  const byKey = new Map();
  for (const doc of snap.docs) {
    const data = doc.data();
    const key = data?.source_meta?.key;
    if (!key) continue; // Only process imported workouts

    if (!byKey.has(key)) {
      byKey.set(key, []);
    }
    byKey.get(key).push({
      id: doc.id,
      createTime: doc.createTime?.toMillis() || 0,
      data,
    });
  }

  let deleted = 0;
  let kept = 0;

  for (const [key, docs] of byKey.entries()) {
    if (docs.length <= 1) {
      kept += docs.length;
      continue;
    }

    // Sort by creation time, keep the oldest
    docs.sort((a, b) => a.createTime - b.createTime);
    const [keep, ...remove] = docs;

    console.log(`  Key: ${key}`);
    console.log(`    Keeping: ${keep.id} (created ${new Date(keep.createTime).toISOString()})`);

    for (const dup of remove) {
      console.log(`    Removing: ${dup.id} (created ${new Date(dup.createTime).toISOString()})`);
      if (!dryRun) {
        await workoutsRef.doc(dup.id).delete();
      }
      deleted++;
    }
    kept++;
  }

  console.log(`\nDuplicate cleanup: ${deleted} removed, ${kept} kept${dryRun ? ' (dry-run)' : ''}`);
  return { deleted, kept };
}

// =============================================================================
// MAIN IMPORT
// =============================================================================

async function main() {
  const userId = positionalArgs[0];
  const csvPath = positionalArgs[1] || path.resolve(process.cwd(), 'strong_workouts.csv');

  if (!userId) {
    console.error('Usage: node scripts/import_strong_csv.js <USER_ID> [CSV_PATH] [OPTIONS]');
    console.error('');
    console.error('Options:');
    console.error('  --interactive    Prompt for exercise disambiguation');
    console.error('  --cleanup        Clean up duplicate workouts before importing');
    console.error('  --dry-run        Show what would be imported without making changes');
    process.exit(1);
  }

  console.log('Strong CSV Import');
  console.log('==================');
  console.log(`User ID:      ${userId}`);
  console.log(`Interactive:  ${FLAGS.interactive}`);
  console.log(`Dry-run:      ${FLAGS.dryRun}`);

  // Cleanup mode
  if (FLAGS.cleanup) {
    await cleanupDuplicateWorkouts(userId, FLAGS.dryRun);
    if (!positionalArgs[1]) {
      // Just cleanup, no import
      closeReadline();
      return;
    }
  }

  if (!fs.existsSync(csvPath)) {
    console.error('CSV file not found:', csvPath);
    process.exit(1);
  }

  console.log(`CSV file:     ${csvPath}`);
  console.log('');

  await ensureUserDoc(userId);

  const content = fs.readFileSync(csvPath, 'utf8');
  const rows = parseCSV(content);
  if (!rows.length) {
    console.log('No rows parsed. Exiting.');
    closeReadline();
    return;
  }

  const groups = groupByWorkout(rows);
  console.log(`Workouts to import: ${groups.size}\n`);

  const exerciseCache = new Map();
  const sessionMappings = new Map(); // Remember user choices for this session
  const createdExercises = new Set(); // Track newly created exercises
  let imported = 0;
  let skipped = 0;

  // Pre-fetch existing workouts for dedup
  const db = getFirestore();
  const existingKeys = new Set();
  try {
    const workoutsSnap = await db.collection('users').doc(userId).collection('workouts').get();
    for (const doc of workoutsSnap.docs) {
      const key = doc.data()?.source_meta?.key;
      if (key) existingKeys.add(key);
    }
    console.log(`Found ${existingKeys.size} existing imported workouts\n`);
  } catch (e) {
    console.warn('Could not fetch existing workouts:', e.message);
  }

  for (const [, bundle] of groups) {
    const { rows: wrows, meta } = bundle;
    const start = parseStrongDate(meta.dateStr);
    const duration = toNumber(wrows[0]['Duration (sec)']) || 3600;
    const end = new Date(start.getTime() + duration * 1000);
    const workoutNotes = (wrows.find(r => r['Workout Notes']) || {})['Workout Notes'] || '';

    // Build dedup key
    const roundedStart = new Date(Math.floor(start.getTime() / (10 * 60 * 1000)) * (10 * 60 * 1000));
    const normalizedName = (meta.name || '').trim();
    const importKey = `${roundedStart.toISOString()}|${normalizedName}`;

    // Skip if already exists
    if (existingKeys.has(importKey)) {
      console.log(`[SKIP] "${meta.name}" @ ${meta.dateStr} (already imported)`);
      skipped++;
      continue;
    }

    // Group by exercise name
    const byEx = new Map();
    for (const r of wrows) {
      const exName = r['Exercise Name'];
      if (!exName) continue;
      if (!byEx.has(exName)) byEx.set(exName, []);
      byEx.get(exName).push(r);
    }

    console.log(`\n[IMPORT] "${meta.name}" @ ${meta.dateStr}`);

    const exercises = [];
    for (const [exName, srows] of byEx.entries()) {
      const { base, equipment } = parseExerciseName(exName);

      const exId = await resolveExerciseInteractive(
        exerciseCache, exName, equipment, userId, sessionMappings, createdExercises
      );

      if (!exId) {
        // This shouldn't happen anymore since we create new exercises
        console.log(`  [!] Failed to resolve or create: ${exName}`);
        continue;
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

      if (sets.length === 0) continue;
      exercises.push({ exercise_id: exId, name: base, position: exercises.length, sets });
    }

    if (exercises.length === 0) {
      console.log(`  [!] Skipping - no resolvable exercises`);
      skipped++;
      continue;
    }

    // Build digest for ID
    const digestObj = {
      dateBucket: roundedStart.toISOString(),
      name: meta.name,
      ex: exercises.map(e => ({ id: e.exercise_id, sets: e.sets.map(s => [s.reps, s.weight_kg, s.type]) })),
    };
    const digest = crypto.createHash('sha1').update(JSON.stringify(digestObj)).digest('hex');

    const payload = {
      userId,
      workout: {
        id: `imp:strong:${digest}`,
        start_time: iso(start),
        end_time: iso(end),
        notes: `Strong import — ${meta.name}${workoutNotes ? ' — ' + workoutNotes : ''}`,
        source_meta: { source: 'strong_csv', key: importKey, digest },
        exercises,
      },
    };

    if (FLAGS.dryRun) {
      console.log(`  [DRY-RUN] Would import ${exercises.length} exercises`);
      imported++;
    } else {
      try {
        await httpJson('POST', 'upsertWorkout', payload);
        console.log(`  [OK] Imported ${exercises.length} exercises`);
        imported++;
        existingKeys.add(importKey); // Track for dedup within this run
      } catch (e) {
        console.error(`  [ERROR] ${e.message}`);
      }
    }
  }

  // Summary
  console.log('\n==================');
  console.log('IMPORT SUMMARY');
  console.log('==================');
  console.log(`Total workouts:  ${groups.size}`);
  console.log(`Imported:        ${imported}`);
  console.log(`Skipped:         ${skipped}`);
  console.log(`New exercises:   ${createdExercises.size}`);

  if (createdExercises.size > 0) {
    console.log(`\nNewly created exercises (queued for enrichment):`);
    for (const exId of createdExercises) {
      console.log(`  + ${exId}`);
    }
  }

  if (sessionMappings.size > 0) {
    console.log(`\nExercise mappings used:`);
    for (const [strong, exId] of sessionMappings.entries()) {
      const isNew = createdExercises.has(exId);
      console.log(`  "${strong}" -> ${exId}${isNew ? ' (NEW)' : ''}`);
    }
  }

  closeReadline();

  // Run analytics
  if (!FLAGS.dryRun && imported > 0) {
    console.log('\nRunning analytics controller...');
    try {
      const run = await httpJson('POST', 'runAnalyticsForUser', { userId });
      console.log('Analytics result:', run?.data || run);
    } catch (e) {
      console.warn('Analytics controller failed:', e.message);
    }
  }
}

main().catch(err => {
  closeReadline();
  console.error('Import failed:', err?.message || err);
  process.exit(1);
});
