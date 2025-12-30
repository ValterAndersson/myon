/**
 * =============================================================================
 * start-active-workout.js - Begin Live Workout Session
 * =============================================================================
 *
 * PURPOSE:
 * Creates a new active_workout document when user starts exercising.
 * This is the ENTRY POINT for the live workout execution flow.
 *
 * ACTIVE WORKOUT LIFECYCLE:
 * ┌─────────────────────────────────────────────────────────────────────────┐
 * │ 1. START (this file)                                                   │
 * │    User taps "Start Workout" → Creates active_workout doc              │
 * │    Status: in_progress, exercises: []                                  │
 * │                                                                         │
 * │ 2. LOG SETS (log-set.js / apply-action.js LOG_SET)                     │
 * │    User completes sets → Appends to exercises[], updates totals        │
 * │    May add new exercises via add-exercise.js                           │
 * │    May swap exercises via swap-exercise.js                             │
 * │                                                                         │
 * │ 3. COMPLETE (complete-active-workout.js)                               │
 * │    User finishes workout → Copies to workouts collection               │
 * │    Status: completed, triggers routine cursor update                   │
 * └─────────────────────────────────────────────────────────────────────────┘
 *
 * FIRESTORE WRITES:
 * - Creates: users/{uid}/active_workouts/{workoutId}
 *   - status: "in_progress"
 *   - plan: Exercise plan from session_plan card (optional)
 *   - source_template_id: Template this workout is based on (for analytics)
 *   - source_routine_id: Routine this workout belongs to (for cursor tracking)
 *   - exercises: [] (populated by log-set)
 *   - totals: { sets: 0, reps: 0, volume: 0, stimulus_score: 0 }
 *   - start_time: serverTimestamp()
 *
 * ROUTINE CONTEXT FLOW:
 * When starting a workout from a routine:
 * 1. iOS passes source_routine_id and source_template_id in request
 * 2. These are stored on the active_workout doc
 * 3. On completion, workout-routine-cursor.js trigger updates routine.cursor
 *
 * CALLED BY:
 * - iOS: ActiveWorkoutManager.startWorkout()
 *   → MYON2/MYON2/Services/ActiveWorkoutManager.swift
 * - iOS: CanvasService.startActiveWorkout()
 *   → MYON2/MYON2/Services/CanvasService.swift
 *
 * RELATED FILES:
 * - log-set.js: Add completed sets to the workout
 * - add-exercise.js: Add exercises mid-workout
 * - swap-exercise.js: Replace an exercise
 * - complete-active-workout.js: Finish and persist workout
 * - ../triggers/workout-routine-cursor.js: Updates routine cursor on completion
 *
 * =============================================================================
 */

const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');
const { ok, fail } = require('../utils/response');
const admin = require('firebase-admin');

const db = new FirestoreHelper();

async function startActiveWorkoutHandler(req, res) {
  try {
    if (req.method !== 'POST') {
      return res.status(405).json({ success: false, error: 'Method Not Allowed' });
    }

    const userId = req.user?.uid || req.auth?.uid;
    if (!userId) return fail(res, 'UNAUTHENTICATED', 'Unauthorized', null, 401);

    const plan = req.body?.plan || null;
    // Accept source_template_id and source_routine_id from request
    // These capture the routine context at workout start time
    const sourceTemplateId = req.body?.source_template_id || null;
    const sourceRoutineId = req.body?.source_routine_id || null;

    const workout = {
      id: null,
      user_id: userId,
      status: 'in_progress',
      source_template_id: sourceTemplateId,
      source_routine_id: sourceRoutineId,  // Added for routine cursor tracking
      notes: null,
      plan: plan || null,
      current: null,
      exercises: [],
      totals: { sets: 0, reps: 0, volume: 0, stimulus_score: 0 },
      start_time: admin.firestore.FieldValue.serverTimestamp(),
      end_time: null,
    };

    const collectionPath = `users/${userId}/active_workouts`;
    const workoutId = await db.addDocument(collectionPath, workout);

    return ok(res, { workout_id: workoutId, active_workout_doc: { ...workout, id: workoutId } });
  } catch (error) {
    console.error('start-active-workout error:', error);
    return fail(res, 'INTERNAL', 'Failed to start active workout', { message: error.message }, 500);
  }
}

exports.startActiveWorkout = onRequest(requireFlexibleAuth(startActiveWorkoutHandler));
