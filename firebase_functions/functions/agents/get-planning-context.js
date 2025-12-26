const admin = require('firebase-admin');
const { requireFlexibleAuth } = require('../auth/middleware');
const { ok, fail } = require('../utils/response');

const firestore = admin.firestore();

/**
 * Firebase Function: Get Planning Context
 * 
 * Composite read for the planning agent. Returns user profile, active routine,
 * templates, next workout, and recent workouts summary in one call.
 * 
 * Flags for payload control:
 * - includeTemplates: boolean (default true) - include routine templates
 * - includeTemplateExercises: boolean (default false) - include full exercise arrays
 * - includeRecentWorkouts: boolean (default true) - include workout summary
 * - workoutLimit: number (default 20) - max workouts to return
 * 
 * This reduces tool sprawl by combining multiple reads into one composite.
 */
async function getPlanningContextHandler(req, res) {
  // Dual auth: prefer req.auth.uid, fallback to body.userId for API key
  const callerUid = req.auth?.uid || req.body?.userId || req.query?.userId;
  if (!callerUid) {
    return fail(res, 'INVALID_ARGUMENT', 'Missing userId parameter', null, 400);
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
    result.user = {
      id: callerUid,
      ...user,
      attributes: attrsDoc.exists ? attrsDoc.data() : null
    };

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
          exercise_count: w.exercises?.length
        };
      });
    }

    return ok(res, result);

  } catch (error) {
    console.error('get-planning-context function error:', error);
    return fail(res, 'INTERNAL', 'Failed to get planning context', { message: error.message }, 500);
  }
}

exports.getPlanningContext = requireFlexibleAuth(getPlanningContextHandler);
