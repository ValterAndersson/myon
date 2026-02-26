/**
 * =============================================================================
 * upsert-workout.js - Create or Update Workout with Analytics & Set Facts
 * =============================================================================
 *
 * PURPOSE:
 * Upserts a completed workout document with full analytics computation and
 * set_facts/series generation inline. Used primarily by import scripts
 * (e.g., Strong CSV import) but can be used for any workout upsert.
 *
 * KEY FEATURES:
 * - Normalizes exercises and sets (weight conversion, defaults)
 * - Computes full analytics using analytics-calculator.js
 * - Handles set_facts generation inline (not via triggers)
 * - Handles series updates inline (series_exercises, series_muscle_groups, etc.)
 * - Cleans up old set_facts/series on re-import (idempotent updates)
 * - Sets set_facts_synced_at flag to prevent duplicate trigger processing
 *
 * UPSERT FLOW:
 * ┌─────────────────────────────────────────────────────────────────────────┐
 * │ 1. Validate input                                                       │
 * │ 2. Normalize exercises (weight → weight_kg, defaults)                   │
 * │ 3. Compute analytics via AnalyticsCalc                                  │
 * │ 4. If updating existing workout:                                        │
 * │    a. Delete old set_facts for this workout_id                          │
 * │    b. Revert old series contributions (sign=-1)                         │
 * │ 5. Write workout document                                               │
 * │ 6. Generate and write new set_facts                                     │
 * │ 7. Update series (sign=+1)                                              │
 * │ 8. Set set_facts_synced_at timestamp                                    │
 * └─────────────────────────────────────────────────────────────────────────┘
 *
 * CALLED BY:
 * - scripts/import_strong_csv.js
 * - Any admin script needing to bulk-import workouts
 *
 * NOT EXPOSED TO:
 * - AI agents (uses requireFlexibleAuth, not agent-accessible)
 *
 * =============================================================================
 */

const { onRequest } = require('firebase-functions/v2/https');
const admin = require('firebase-admin');
const { requireFlexibleAuth } = require('../auth/middleware');
const { ok, fail } = require('../utils/response');
const AnalyticsCalc = require('../utils/analytics-calculator');
const { getAuthenticatedUserId } = require('../utils/auth-helpers');
const {
  generateSetFactsForWorkout,
  writeSetFactsInChunks,
  updateSeriesForWorkout,
} = require('../training/set-facts-generator');
const { CAPS } = require('../utils/caps');

if (!admin.apps.length) {
  admin.initializeApp();
}

const db = admin.firestore();

/**
 * Convert various date formats to Firestore Timestamp
 */
function toTimestamp(value) {
  if (!value) return null;
  if (value instanceof admin.firestore.Timestamp) return value;
  if (value instanceof Date) return admin.firestore.Timestamp.fromDate(value);
  if (typeof value === 'number') return admin.firestore.Timestamp.fromMillis(value);
  if (typeof value === 'string') {
    const d = new Date(value);
    if (!isNaN(d.getTime())) return admin.firestore.Timestamp.fromDate(d);
  }
  return null;
}

/**
 * Normalize exercises array with proper weight_kg conversion and defaults
 */
function normalizeExercises(rawExercises, defaultCompleted = true) {
  const list = Array.isArray(rawExercises) ? rawExercises : [];
  return list.map(ex => {
    const sets = Array.isArray(ex.sets) ? ex.sets : [];
    const normSets = sets.map(s => {
      // Prefer explicit kg; accept weight/weight_lbs and convert when unit provided
      let weightKg = null;
      if (typeof s.weight_kg === 'number') {
        weightKg = s.weight_kg;
      } else if (typeof s.weight === 'number') {
        const unit = (s.unit || s.weight_unit || 'kg').toLowerCase();
        weightKg = unit === 'lbs' || unit === 'pounds' ? +(s.weight / 2.2046226218).toFixed(3) : s.weight;
      } else if (typeof s.weight_lbs === 'number') {
        weightKg = +(s.weight_lbs / 2.2046226218).toFixed(3);
      }
      return {
        id: s.id || null,
        reps: typeof s.reps === 'number' ? s.reps : 0,
        rir: typeof s.rir === 'number' ? s.rir : null,
        type: s.type || 'working set',
        weight_kg: typeof weightKg === 'number' ? weightKg : 0,
        is_completed: s.is_completed !== undefined ? !!s.is_completed : !!defaultCompleted,
      };
    });
    return {
      exercise_id: String(ex.exercise_id || ex.exerciseId || ''),
      name: ex.name || null,
      position: typeof ex.position === 'number' ? ex.position : null,
      sets: normSets,
    };
  });
}

/**
 * Delete all set_facts for a specific workout
 */
async function deleteSetFactsForWorkout(userId, workoutId) {
  const setFactsQuery = db.collection('users').doc(userId)
    .collection('set_facts')
    .where('workout_id', '==', workoutId);
  
  const snapshot = await setFactsQuery.get();
  if (snapshot.empty) return 0;
  
  // Delete in batches
  const batchSize = CAPS.FIRESTORE_BATCH_LIMIT || 500;
  const docs = snapshot.docs;
  
  for (let i = 0; i < docs.length; i += batchSize) {
    const chunk = docs.slice(i, i + batchSize);
    const batch = db.batch();
    for (const doc of chunk) {
      batch.delete(doc.ref);
    }
    await batch.commit();
  }
  
  return snapshot.size;
}

/**
 * Main upsert handler
 */
async function upsertWorkoutHandler(req, res) {
  try {
    if (req.method !== 'POST') {
      return res.status(405).json({ success: false, error: 'Method Not Allowed' });
    }

    const auth = req.user || req.auth || {};
    // Determine target user
    const uid = getAuthenticatedUserId(req);
    if (!uid) return fail(res, 'INVALID_ARGUMENT', 'Missing userId (header X-User-Id or body.userId)', null, 400);

    const body = req.body || {};
    const input = body.workout || body;
    if (!input || !Array.isArray(input.exercises)) {
      return fail(res, 'INVALID_ARGUMENT', 'workout.exercises array is required', null, 400);
    }

    const col = db.collection('users').doc(String(uid)).collection('workouts');

    // Times
    const startTs = toTimestamp(input.start_time) || toTimestamp(input.startTime);
    const endTs = toTimestamp(input.end_time) || toTimestamp(input.endTime);
    if (!endTs) return fail(res, 'INVALID_ARGUMENT', 'end_time is required (ISO string or millis)', null, 400);

    const exercises = normalizeExercises(input.exercises, true);

    // Compute analytics synchronously to ensure weekly stats triggers run on create
    let workoutAnalytics = null;
    let updatedExercises = exercises;
    try {
      const calc = await AnalyticsCalc.calculateWorkoutAnalytics({ exercises });
      workoutAnalytics = calc.workoutAnalytics;
      updatedExercises = calc.updatedExercises || exercises;
    } catch (e) {
      console.warn('Analytics calculation failed, using fallback:', e.message);
      // Fallback minimal analytics
      const totals = exercises.reduce((acc, ex) => {
        const sets = ex.sets || [];
        const reps = sets.reduce((s, v) => s + (v.reps || 0), 0);
        const vol = sets.reduce((s, v) => s + ((v.weight_kg || 0) * (v.reps || 0)), 0);
        return { sets: acc.sets + sets.length, reps: acc.reps + reps, vol: acc.vol + vol };
      }, { sets: 0, reps: 0, vol: 0 });
      workoutAnalytics = {
        total_sets: totals.sets,
        total_reps: totals.reps,
        total_weight: totals.vol,
        weight_format: 'kg',
        avg_reps_per_set: totals.sets > 0 ? totals.reps / totals.sets : 0,
        avg_weight_per_set: totals.sets > 0 ? totals.vol / totals.sets : 0,
        avg_weight_per_rep: totals.reps > 0 ? totals.vol / totals.reps : 0,
        weight_per_muscle_group: {},
        weight_per_muscle: {},
        reps_per_muscle_group: {},
        reps_per_muscle: {},
        sets_per_muscle_group: {},
        sets_per_muscle: {},
      };
    }

    // Select id semantics
    let docId = input.id ? String(input.id) : null;
    const docRef = docId ? col.doc(docId) : col.doc();
    docId = docRef.id;

    // Check if existing workout
    const existing = await docRef.get();
    const isUpdate = existing.exists;

    // If updating, clean up old set_facts and revert series
    if (isUpdate) {
      const existingData = existing.data();
      
      // Delete old set_facts
      const deletedCount = await deleteSetFactsForWorkout(String(uid), docId);
      if (deletedCount > 0) {
        console.log(`Deleted ${deletedCount} old set_facts for workout ${docId}`);
      }
      
      // Revert old series contributions
      if (existingData && existingData.exercises && existingData.end_time) {
        try {
          const existingWorkout = { ...existingData, id: docId };
          await updateSeriesForWorkout(db, String(uid), existingWorkout, -1);
          console.log(`Reverted old series for workout ${docId}`);
        } catch (e) {
          console.warn('Failed to revert old series (continuing):', e.message);
        }
      }
    }

    // Payload
    const payload = {
      id: docId,
      user_id: String(uid),
      name: input.name || (isUpdate ? (existing.data()?.name || null) : null),
      source_template_id: input.source_template_id || input.template_id || null,
      created_at: isUpdate ? existing.data()?.created_at : (startTs || admin.firestore.FieldValue.serverTimestamp()),
      start_time: startTs || admin.firestore.FieldValue.serverTimestamp(),
      end_time: endTs,
      notes: input.notes || null,
      source_meta: input.source_meta || input.sourceMeta || null,
      exercises: updatedExercises,
      analytics: input.analytics || workoutAnalytics,
      // Flag to indicate set_facts were handled by upsertWorkout (prevents duplicate trigger processing)
      set_facts_synced_at: admin.firestore.FieldValue.serverTimestamp(),
    };

    // Write workout document
    await docRef.set(payload, { merge: false });

    // Generate and write new set_facts
    const workoutWithId = { ...payload, id: docId, end_time: endTs };
    try {
      const setFacts = generateSetFactsForWorkout({
        userId: String(uid),
        workout: workoutWithId,
      });
      
      if (setFacts.length > 0) {
        await writeSetFactsInChunks(db, String(uid), setFacts);
        console.log(`Wrote ${setFacts.length} set_facts for workout ${docId}`);
        
        // Update series
        await updateSeriesForWorkout(db, String(uid), workoutWithId, 1);
        console.log(`Updated series for workout ${docId}`);
      }
    } catch (e) {
      console.error('Failed to generate set_facts/series (workout saved, analytics may be incomplete):', e.message);
    }

    return ok(res, { 
      workout_id: docId, 
      created: !isUpdate, 
      user_id: uid,
      set_facts_synced: true,
    });
  } catch (error) {
    console.error('upsert-workout error:', error);
    return fail(res, 'INTERNAL', 'Failed to upsert workout', { message: error.message }, 500);
  }
}

exports.upsertWorkout = onRequest(
  { invoker: 'public' },
  requireFlexibleAuth(upsertWorkoutHandler)
);
