const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');
const { ok, fail } = require('../utils/response');

const db = new FirestoreHelper();

/**
 * Firebase Function: Get Next Workout
 * 
 * Determines which template to use for the next workout based on routine rotation.
 * 
 * Algorithm:
 * 1. Get active routine from user.activeRoutineId
 * 2. Primary: Use cursor fields (last_completed_template_id) for O(1) lookup
 * 3. Fallback: Scan last N workouts and find matching source_template_id
 * 4. Return the next template in rotation order
 * 
 * Deterministic fallback rules:
 * - No active routine → return null with reason
 * - Empty template_ids → return null with reason  
 * - No matching history → return first template
 * - Last template removed → return first template
 * - Normal case → return template_ids[(lastIndex + 1) % length]
 */
async function getNextWorkoutHandler(req, res) {
  // Dual auth: prefer req.auth.uid, fallback to body.userId for API key
  const userId = req.auth?.uid || req.query.userId || req.body?.userId;
  if (!userId) {
    return fail(res, 'INVALID_ARGUMENT', 'Missing userId parameter', null, 400);
  }

  try {
    // 1. Get user and check for active routine
    const user = await db.getDocument('users', userId);
    if (!user) {
      return fail(res, 'NOT_FOUND', 'User not found', null, 404);
    }

    if (!user.activeRoutineId) {
      return ok(res, { 
        template: null, 
        routine: null,
        reason: 'no_active_routine',
        message: 'No active routine set'
      });
    }

    // 2. Get the active routine
    const routine = await db.getDocumentFromSubcollection('users', userId, 'routines', user.activeRoutineId);
    if (!routine) {
      return ok(res, { 
        template: null, 
        routine: null,
        reason: 'routine_not_found',
        message: 'Active routine not found'
      });
    }

    // Canonical field is template_ids, fallback to templateIds for legacy
    const templateIds = routine.template_ids || routine.templateIds || [];
    if (templateIds.length === 0) {
      return ok(res, { 
        template: null, 
        routine,
        reason: 'empty_routine',
        message: 'Routine has no templates'
      });
    }

    // 3. Determine next template using cursor or fallback
    let nextTemplateId;
    let nextTemplateIndex;
    let selectionMethod;

    // Primary: Use cursor field if available
    if (routine.last_completed_template_id && templateIds.includes(routine.last_completed_template_id)) {
      const lastIndex = templateIds.indexOf(routine.last_completed_template_id);
      nextTemplateIndex = (lastIndex + 1) % templateIds.length;
      nextTemplateId = templateIds[nextTemplateIndex];
      selectionMethod = 'cursor';
    } else {
      // Fallback: Scan last N workouts
      const N = 50;
      const workouts = await db.getDocumentsFromSubcollection('users', userId, 'workouts', {
        orderBy: { field: 'end_time', direction: 'desc' },
        limit: N
      });

      const templateSet = new Set(templateIds);
      const lastMatchingWorkout = workouts.find(w => 
        w.source_template_id && templateSet.has(w.source_template_id)
      );

      if (lastMatchingWorkout) {
        const lastIndex = templateIds.indexOf(lastMatchingWorkout.source_template_id);
        if (lastIndex >= 0) {
          nextTemplateIndex = (lastIndex + 1) % templateIds.length;
          nextTemplateId = templateIds[nextTemplateIndex];
          selectionMethod = 'history_scan';
        }
      }

      // If still no match, start at first template
      if (!nextTemplateId) {
        nextTemplateIndex = 0;
        nextTemplateId = templateIds[0];
        selectionMethod = 'default_first';
      }
    }

    // 4. Fetch the next template with analytics
    const template = await db.getDocumentFromSubcollection('users', userId, 'templates', nextTemplateId);
    if (!template) {
      // Template referenced in routine doesn't exist - fall back to first available
      for (let i = 0; i < templateIds.length; i++) {
        const fallbackTemplate = await db.getDocumentFromSubcollection('users', userId, 'templates', templateIds[i]);
        if (fallbackTemplate) {
          return ok(res, { 
            template: fallbackTemplate, 
            routine,
            templateIndex: i,
            templateCount: templateIds.length,
            selectionMethod: 'fallback_first_available',
            warning: `Original next template ${nextTemplateId} not found`
          });
        }
      }
      return ok(res, { 
        template: null, 
        routine,
        reason: 'no_valid_templates',
        message: 'None of the routine templates exist'
      });
    }

    return ok(res, { 
      template, 
      routine,
      templateIndex: nextTemplateIndex,
      templateCount: templateIds.length,
      selectionMethod
    });

  } catch (error) {
    console.error('get-next-workout function error:', error);
    return fail(res, 'INTERNAL', 'Failed to get next workout', { message: error.message }, 500);
  }
}

exports.getNextWorkout = onRequest(requireFlexibleAuth(getNextWorkoutHandler));
