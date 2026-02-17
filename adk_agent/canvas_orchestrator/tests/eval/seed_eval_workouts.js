#!/usr/bin/env node
/**
 * Seed two eval test workouts into Firestore for the active_workout eval cases.
 *
 * Usage:
 *   GOOGLE_APPLICATION_CREDENTIALS=~/.config/povver/myon-53d85-firebase-adminsdk-fbsvc-ca7beb1435.json \
 *     node tests/eval/seed_eval_workouts.js
 *
 * Creates:
 *   - eval-push-day: matches SAMPLE_WORKOUT_BRIEF (6/18 sets done)
 *   - eval-pull-day: matches LATE_WORKOUT_BRIEF (14/18 sets done)
 *
 * Idempotent: safe to run multiple times.
 */

const admin = require('firebase-admin');

const SA_PATH = process.env.GOOGLE_APPLICATION_CREDENTIALS
  || require('path').join(require('os').homedir(), '.config/povver/myon-53d85-firebase-adminsdk-fbsvc-ca7beb1435.json');

admin.initializeApp({ credential: admin.credential.cert(SA_PATH) });
const db = admin.firestore();

const USER_ID = 'Y4SJuNPOasaltF7TuKm1QCT7JIA3';
const now = admin.firestore.Timestamp.now();

// Helper: create a set object
function makeSet(id, { reps, weight, rir, status = 'planned', setType = 'working' }) {
  const set = { id, set_type: setType, reps, weight, rir, status, tags: {} };
  if (status === 'planned') {
    // Planned sets have target values
    set.target_reps = reps;
    set.target_weight = weight;
    set.target_rir = rir;
  }
  return set;
}

// =============================================================================
// PUSH DAY — matches SAMPLE_WORKOUT_BRIEF (6/18 sets done)
// =============================================================================
const pushDay = {
  id: 'eval-push-day',
  user_id: USER_ID,
  name: 'Push Day',
  status: 'in_progress',
  source_template_id: null,
  source_routine_id: null,
  notes: null,
  plan: null,
  current: { exercise_instance_id: 'ex-bench-001', set_index: 2 },
  start_time: now,
  created_at: now,
  updated_at: now,
  version: 1,
  totals: { sets: 6, reps: 48, volume: 4800 },
  exercises: [
    {
      instance_id: 'ex-bench-001',
      exercise_id: 'bench_press__bench-press',
      name: 'Bench Press (Barbell)',
      position: 0,
      sets: [
        makeSet('set-bench-001', { reps: 8, weight: 100, rir: 2, status: 'done' }),
        makeSet('set-bench-002', { reps: 8, weight: 100, rir: 2, status: 'done' }),
        makeSet('set-bench-003', { reps: 8, weight: 100, rir: 2, status: 'planned' }),
        makeSet('set-bench-004', { reps: 8, weight: 100, rir: 2, status: 'planned' }),
      ],
    },
    {
      instance_id: 'ex-incline-002',
      exercise_id: 'incline_bench_press__incline-bench-press',
      name: 'Incline Bench Press (Dumbbell)',
      position: 1,
      sets: [
        makeSet('set-inc-001', { reps: 10, weight: 32, rir: 2, status: 'planned' }),
        makeSet('set-inc-002', { reps: 10, weight: 32, rir: 2, status: 'planned' }),
        makeSet('set-inc-003', { reps: 10, weight: 32, rir: 2, status: 'planned' }),
      ],
    },
    {
      instance_id: 'ex-fly-003',
      exercise_id: 'chest_fly__chest-fly-cable',
      name: 'Chest Fly (Cable)',
      position: 2,
      sets: [
        makeSet('set-fly-001', { reps: 12, weight: 15, rir: 2, status: 'planned' }),
        makeSet('set-fly-002', { reps: 12, weight: 15, rir: 2, status: 'planned' }),
        makeSet('set-fly-003', { reps: 12, weight: 15, rir: 2, status: 'planned' }),
      ],
    },
    {
      instance_id: 'ex-lat-004',
      exercise_id: 'lateral_raise__lateral-raise-dumbbell',
      name: 'Lateral Raise (Dumbbell)',
      position: 3,
      sets: [
        makeSet('set-lat-001', { reps: 15, weight: 10, rir: 2, status: 'planned' }),
        makeSet('set-lat-002', { reps: 15, weight: 10, rir: 2, status: 'planned' }),
        makeSet('set-lat-003', { reps: 15, weight: 10, rir: 2, status: 'planned' }),
      ],
    },
    {
      instance_id: 'ex-tri-005',
      exercise_id: 'overhead_triceps_extension__overhead-triceps-extension-cable',
      name: 'Overhead Triceps Extension (Cable)',
      position: 4,
      sets: [
        makeSet('set-tri-001', { reps: 12, weight: 20, rir: 2, status: 'planned' }),
        makeSet('set-tri-002', { reps: 12, weight: 20, rir: 2, status: 'planned' }),
      ],
    },
    {
      instance_id: 'ex-fp-006',
      exercise_id: 'face_pull__face-pull-cable',
      name: 'Face Pull (Cable)',
      position: 5,
      sets: [
        makeSet('set-fp-001', { reps: 15, weight: 12.5, rir: 2, status: 'planned' }),
        makeSet('set-fp-002', { reps: 15, weight: 12.5, rir: 2, status: 'planned' }),
      ],
    },
  ],
};

// =============================================================================
// PULL DAY — matches LATE_WORKOUT_BRIEF (14/18 sets done)
// =============================================================================
const pullDay = {
  id: 'eval-pull-day',
  user_id: USER_ID,
  name: 'Pull Day',
  status: 'in_progress',
  source_template_id: null,
  source_routine_id: null,
  notes: null,
  plan: null,
  current: { exercise_instance_id: 'ex-curl-005', set_index: 2 },
  start_time: now,
  created_at: now,
  updated_at: now,
  version: 1,
  totals: { sets: 14, reps: 160, volume: 9560 },
  exercises: [
    {
      instance_id: 'ex-row-001',
      exercise_id: 'bent_over_row__bent-over-row-barbell',
      name: 'Barbell Row (Barbell)',
      position: 0,
      sets: [
        makeSet('set-row-001', { reps: 8, weight: 80, rir: 2, status: 'done' }),
        makeSet('set-row-002', { reps: 8, weight: 80, rir: 1, status: 'done' }),
        makeSet('set-row-003', { reps: 7, weight: 80, rir: 1, status: 'done' }),
      ],
    },
    {
      instance_id: 'ex-lat-002',
      exercise_id: 'close_grip_lat_pulldown__close-grip-lat-pulldown-cable',
      name: 'Lat Pulldown (Cable)',
      position: 1,
      sets: [
        makeSet('set-lat-001p', { reps: 10, weight: 65, rir: 2, status: 'done' }),
        makeSet('set-lat-002p', { reps: 10, weight: 65, rir: 2, status: 'done' }),
        makeSet('set-lat-003p', { reps: 9, weight: 65, rir: 1, status: 'done' }),
      ],
    },
    {
      instance_id: 'ex-scr-003',
      exercise_id: 'seated_row__seated-row',
      name: 'Seated Cable Row (Cable)',
      position: 2,
      sets: [
        makeSet('set-scr-001', { reps: 12, weight: 55, rir: 2, status: 'done' }),
        makeSet('set-scr-002', { reps: 11, weight: 55, rir: 1, status: 'done' }),
        makeSet('set-scr-003', { reps: 11, weight: 55, rir: 1, status: 'done' }),
      ],
    },
    {
      instance_id: 'ex-fp-004',
      exercise_id: 'face_pull__face-pull-cable',
      name: 'Face Pull (Cable)',
      position: 3,
      sets: [
        makeSet('set-fp-001p', { reps: 15, weight: 15, rir: 2, status: 'done' }),
        makeSet('set-fp-002p', { reps: 14, weight: 15, rir: 1, status: 'done' }),
        makeSet('set-fp-003p', { reps: 13, weight: 15, rir: 1, status: 'done' }),
      ],
    },
    {
      instance_id: 'ex-curl-005',
      exercise_id: 'bicep_curl__bicep-curl-dumbbell',
      name: 'Bicep Curl (Dumbbell)',
      position: 4,
      sets: [
        makeSet('set-curl-001', { reps: 10, weight: 14, rir: 2, status: 'done' }),
        makeSet('set-curl-002', { reps: 10, weight: 14, rir: 1, status: 'done' }),
        makeSet('set-curl-003', { reps: 10, weight: 14, rir: 2, status: 'planned' }),
      ],
    },
    {
      instance_id: 'ex-ham-006',
      exercise_id: 'hammer_curl__hammer-curl-dumbbell',
      name: 'Hammer Curl (Dumbbell)',
      position: 5,
      sets: [
        makeSet('set-ham-001', { reps: 12, weight: 12, rir: 2, status: 'planned' }),
        makeSet('set-ham-002', { reps: 12, weight: 12, rir: 2, status: 'planned' }),
      ],
    },
  ],
};

async function seed() {
  const workoutsRef = db.collection('users').doc(USER_ID).collection('active_workouts');

  // Push Day
  const { id: pushId, ...pushData } = pushDay;
  await workoutsRef.doc(pushId).set(pushData);
  console.log('✓ Created eval-push-day (' + pushDay.exercises.length + ' exercises, ' +
    pushDay.exercises.reduce((a, e) => a + e.sets.length, 0) + ' sets)');

  // Pull Day
  const { id: pullId, ...pullData } = pullDay;
  await workoutsRef.doc(pullId).set(pullData);
  console.log('✓ Created eval-pull-day (' + pullDay.exercises.length + ' exercises, ' +
    pullDay.exercises.reduce((a, e) => a + e.sets.length, 0) + ' sets)');

  console.log('\nWorkout IDs:');
  console.log('  SAMPLE (Push Day): eval-push-day');
  console.log('  LATE   (Pull Day): eval-pull-day');
}

seed().then(() => process.exit(0)).catch(e => {
  console.error('Seed failed:', e.message);
  process.exit(1);
});
