/**
 * =============================================================================
 * get-planning-context.js - Agent Context Aggregation
 * =============================================================================
 *
 * PURPOSE:
 * Composite read that provides the agent with full user context in ONE call.
 * This reduces tool sprawl and network round-trips for the planning agent.
 *
 * ARCHITECTURE CONTEXT:
 * ┌────────────────────────────────────────────────────────────────────────────┐
 * │ AGENT CONTEXT LOADING                                                      │
 * │                                                                            │
 * │ Agent (Planner/Coach)                                                      │
 * │   │                                                                        │
 * │   ▼ tool_get_planning_context()                                           │
 * │   │                                                                        │
 * │   ▼ client.py → HTTP POST                                                 │
 * │   │                                                                        │
 * │   ▼ get-planning-context.js (THIS FILE)                                   │
 * │   │                                                                        │
 * │   ▼ Returns composite:                                                     │
 * │   ┌─────────────────────────────────────────────────────────────────────┐ │
 * │   │ {                                                                   │ │
 * │   │   user: { profile, attributes },                                   │ │
 * │   │   activeRoutine: { name, template_ids, cursor },                   │ │
 * │   │   nextWorkout: { templateId, templateIndex, template },            │ │
 * │   │   templates: [{ id, name, analytics, exerciseCount }],             │ │
 * │   │   recentWorkoutsSummary: [{ id, end_time, total_volume }],         │ │
 * │   │   strengthSummary: [{ id, name, weight, reps, e1rm }]             │ │
 * │   │ }                                                                   │ │
 * │   └─────────────────────────────────────────────────────────────────────┘ │
 * └────────────────────────────────────────────────────────────────────────────┘
 *
 * PAYLOAD CONTROL FLAGS:
 * - includeTemplates: boolean (default true) - include routine template metadata
 * - includeTemplateExercises: boolean (default false) - include full exercise arrays
 * - includeRecentWorkouts: boolean (default true) - include workout summary
 * - workoutLimit: number (default 20) - max workouts to return
 *
 * FIRESTORE READS:
 * - users/{uid} - User profile
 * - users/{uid}/user_attributes/{uid} - User preferences
 * - users/{uid}/routines/{activeRoutineId} - Active routine
 * - users/{uid}/templates/{templateId} - Routine templates
 * - users/{uid}/workouts - Recent workout history
 *
 * CALLED BY:
 * - Agent: tool_get_planning_context() in planner_agent.py
 * - Agent: tool_get_training_context() in coach_agent.py
 *   → adk_agent/canvas_orchestrator/app/libs/tools_canvas/client.py
 *
 * RELATED FILES:
 * - get-next-workout.js: Standalone next workout endpoint
 * - ../user/get-user.js: Standalone user profile endpoint
 * - ../routines/get-next-workout.js: Used by iOS (simpler response)
 *
 * UNUSED CODE CHECK: ✅ No unused code in this file
 *
 * =============================================================================
 */

const admin = require('firebase-admin');
const { requireFlexibleAuth } = require('../auth/middleware');
const { ok, fail } = require('../utils/response');
const { getAuthenticatedUserId } = require('../utils/auth-helpers');

const firestore = admin.firestore();

/**
 * Compute strength summary from recent workouts (no extra Firestore reads).
 * Extracts per-exercise max performance (best e1RM) from workout data already fetched.
 * Returns top 15 exercises sorted by e1RM descending (~0.5KB).
 *
 * @param {Array} workouts - recentWorkoutsSummary array with exercises[].sets[]
 * @returns {Array<{id, name, weight, reps, e1rm}>}
 */
function buildStrengthSummary(workouts) {
  const exercises = new Map();

  for (const w of workouts) {
    for (const ex of (w.exercises || [])) {
      const id = ex.exercise_id;
      if (!id) continue;

      let bestE1rm = 0, maxWeight = 0, bestReps = 0;
      for (const s of (ex.sets || [])) {
        const wt = s.weight_kg || 0;
        const reps = s.reps || 0;
        if (wt <= 0) continue;
        if (wt > maxWeight) { maxWeight = wt; bestReps = reps; }
        if (reps > 0 && reps <= 12) {
          bestE1rm = Math.max(bestE1rm, wt * (1 + reps / 30));
        }
      }

      if (maxWeight <= 0) continue;
      const prev = exercises.get(id);
      if (!prev || bestE1rm > (prev.e1rm || 0)) {
        exercises.set(id, {
          name: ex.name,
          weight: maxWeight,
          reps: bestReps,
          e1rm: Math.round(bestE1rm * 10) / 10 || null,
        });
      }
    }
  }

  return Array.from(exercises.entries())
    .map(([id, d]) => ({ id, ...d }))
    .filter(e => e.e1rm > 0)
    .sort((a, b) => b.e1rm - a.e1rm)
    .slice(0, 15);
}

async function getPlanningContextHandler(req, res) {
  // Dual auth: prefer req.auth.uid, fallback to body.userId for API key
  const callerUid = getAuthenticatedUserId(req);
  if (!callerUid) {
    return fail(res, 'UNAUTHENTICATED', 'Authentication required', null, 401);
  }

  // Parse flags from body or query
  const body = req.body || {};
  const includeTemplates = body.includeTemplates !== false; // default true
  const includeTemplateExercises = body.includeTemplateExercises === true; // default false
  const includeRecentWorkouts = body.includeRecentWorkouts !== false; // default true
  const workoutLimit = parseInt(body.workoutLimit) || 20;

  try {
    const result = {
      user: null,
      activeRoutine: null,
      nextWorkout: null,
      templates: [],
      recentWorkoutsSummary: null
    };

    // 1. Get user profile and attributes (handle missing user gracefully)
    const userDoc = await firestore.collection('users').doc(callerUid).get();
    const user = userDoc.exists ? userDoc.data() : {};

    // Get user attributes
    const attrsDoc = await firestore.collection('users').doc(callerUid).collection('user_attributes').doc(callerUid).get();
    // Strip sensitive internal fields before including in agent context
    const { subscription_original_transaction_id, subscription_app_account_token,
      apple_authorization_code, subscription_environment, ...safeUser } = user;
    result.user = {
      id: callerUid,
      ...safeUser,
      attributes: attrsDoc.exists ? attrsDoc.data() : null
    };

    // Derive weight_unit from user attributes for agent consumption
    const attrs = attrsDoc.exists ? attrsDoc.data() : {};
    result.weight_unit = attrs.weight_format === 'pounds' ? 'lbs' : 'kg';

    // 2. Get active routine if exists
    if (user.activeRoutineId) {
      const routineDoc = await firestore.collection('users').doc(callerUid).collection('routines').doc(user.activeRoutineId).get();
      
      if (routineDoc.exists) {
        const routine = { id: routineDoc.id, ...routineDoc.data() };
        // Normalize to template_ids
        routine.template_ids = routine.template_ids || routine.templateIds || [];
        result.activeRoutine = routine;

        // 3. Compute next workout
        const templateIds = routine.template_ids;
        if (templateIds.length > 0) {
          let nextTemplateId;
          let nextTemplateIndex;
          let selectionMethod;

          // Primary: use cursor
          if (routine.last_completed_template_id && templateIds.includes(routine.last_completed_template_id)) {
            const lastIndex = templateIds.indexOf(routine.last_completed_template_id);
            nextTemplateIndex = (lastIndex + 1) % templateIds.length;
            nextTemplateId = templateIds[nextTemplateIndex];
            selectionMethod = 'cursor';
          } else {
            // Fallback: scan recent workouts
            const workoutsSnapshot = await firestore.collection('users').doc(callerUid)
              .collection('workouts')
              .orderBy('end_time', 'desc')
              .limit(50)
              .get();
            
            const workouts = workoutsSnapshot.docs.map(d => ({ id: d.id, ...d.data() }));
            const templateSet = new Set(templateIds);
            const lastMatch = workouts.find(w => w.source_template_id && templateSet.has(w.source_template_id));

            if (lastMatch) {
              const lastIndex = templateIds.indexOf(lastMatch.source_template_id);
              if (lastIndex >= 0) {
                nextTemplateIndex = (lastIndex + 1) % templateIds.length;
                nextTemplateId = templateIds[nextTemplateIndex];
                selectionMethod = 'history_scan';
              }
            }

            if (!nextTemplateId) {
              nextTemplateIndex = 0;
              nextTemplateId = templateIds[0];
              selectionMethod = 'default_first';
            }
          }

          result.nextWorkout = {
            templateId: nextTemplateId,
            templateIndex: nextTemplateIndex,
            templateCount: templateIds.length,
            selectionMethod
          };
        }

        // 4. Get templates if requested
        if (includeTemplates && templateIds.length > 0) {
          const templateDocs = await Promise.all(
            templateIds.map(tid => 
              firestore.collection('users').doc(callerUid).collection('templates').doc(tid).get()
            )
          );

          result.templates = templateDocs
            .filter(doc => doc.exists)
            .map(doc => {
              const template = { id: doc.id, ...doc.data() };
              
              if (!includeTemplateExercises) {
                // Return metadata only (reduce payload)
                return {
                  id: template.id,
                  name: template.name,
                  description: template.description,
                  analytics: template.analytics,
                  created_at: template.created_at,
                  updated_at: template.updated_at,
                  exerciseCount: template.exercises?.length || 0
                };
              }
              return template;
            });

          // If next workout template is in the list and we didn't include exercises,
          // fetch full template for the next workout
          if (!includeTemplateExercises && result.nextWorkout?.templateId) {
            const nextTemplateDoc = await firestore.collection('users').doc(callerUid)
              .collection('templates').doc(result.nextWorkout.templateId).get();
            if (nextTemplateDoc.exists) {
              result.nextWorkout.template = { id: nextTemplateDoc.id, ...nextTemplateDoc.data() };
            }
          }
        }
      }
    }

    // 5. Get recent workouts summary if requested
    if (includeRecentWorkouts) {
      const workoutsSnapshot = await firestore.collection('users').doc(callerUid)
        .collection('workouts')
        .orderBy('end_time', 'desc')
        .limit(workoutLimit)
        .get();

      result.recentWorkoutsSummary = workoutsSnapshot.docs.map(doc => {
        const w = doc.data();
        return {
          id: doc.id,
          source_template_id: w.source_template_id,
          source_routine_id: w.source_routine_id,
          end_time: w.end_time,
          total_sets: w.analytics?.total_sets,
          total_volume: w.analytics?.total_weight,
          // Include per-exercise performance data so the agent can answer
          // "how did I do yesterday?" with actual reps, weights, and RIR
          exercises: (w.exercises || []).slice(0, 15).map(ex => {
            const allSets = ex.sets || [];
            const workingSets = allSets.filter(s => s.type !== 'warmup' && s.is_completed !== false);
            return {
              name: ex.name || ex.exercise_name,
              exercise_id: ex.exercise_id || null,
              working_sets: workingSets.length,
              sets: workingSets.map(s => ({
                reps: s.reps || 0,
                weight_kg: s.weight_kg || 0,
                rir: s.rir ?? null,
              })),
            };
          })
        };
      });
    }

    // 6. Compute strength summary from workout data (no extra reads)
    result.strengthSummary = buildStrengthSummary(result.recentWorkoutsSummary || []);

    return ok(res, result);

  } catch (error) {
    console.error('get-planning-context function error:', error);
    return fail(res, 'INTERNAL', 'Failed to get planning context', { message: error.message }, 500);
  }
}

exports.getPlanningContext = requireFlexibleAuth(getPlanningContextHandler);
