/**
 * =============================================================================
 * get-next-workout.js - Routine Cursor Resolution
 * =============================================================================
 *
 * PURPOSE:
 * Determines which template to use for the next workout based on routine rotation.
 * This is the READ endpoint that agents and iOS use to get the next scheduled workout.
 *
 * ARCHITECTURE CONTEXT:
 * ┌────────────────────────────────────────────────────────────────────────────┐
 * │ ROUTINE ROTATION SYSTEM                                                    │
 * │                                                                            │
 * │ Routine (3-day PPL):                                                       │
 * │   template_ids: [push_id, pull_id, legs_id]                               │
 * │   last_completed_template_id: push_id  (cursor position)                  │
 * │                                                                            │
 * │ get-next-workout.js logic:                                                 │
 * │   1. Find last_completed_template_id in template_ids                       │
 * │   2. Return template_ids[(lastIndex + 1) % length]                         │
 * │   3. For above example: returns pull_id                                    │
 * │                                                                            │
 * │ After completing pull workout:                                             │
 * │   workout-routine-cursor.js updates:                                       │
 * │   last_completed_template_id: pull_id                                      │
 * │                                                                            │
 * │ Next call to get-next-workout returns: legs_id                             │
 * └────────────────────────────────────────────────────────────────────────────┘
 *
 * SELECTION METHODS:
 * - cursor: O(1) lookup using routine.last_completed_template_id
 * - history_scan: O(N) fallback scanning last 50 workouts
 * - default_first: No history, start with first template
 * - fallback_first_available: Referenced template missing, use first valid
 *
 * RESPONSE SHAPE:
 * {
 *   template: { id, name, exercises, analytics },
 *   routine: { id, name, template_ids },
 *   templateIndex: 1,          // Position in rotation (0-based)
 *   templateCount: 3,          // Total templates in routine
 *   selectionMethod: "cursor"  // How we determined next template
 * }
 *
 * CALLED BY:
 * - iOS: RoutinesViewModel.fetchNextWorkout()
 * - iOS: CanvasService.getNextWorkout()
 * - Agent: planner_tools.py → tool_get_next_workout()
 *   → adk_agent/canvas_orchestrator/app/agents/tools/planner_tools.py
 *
 * RELATED FILES:
 * - create-routine-from-draft.js: Creates routines with template_ids
 * - ../triggers/workout-routine-cursor.js: Updates cursor on completion
 * - ../active_workout/complete-active-workout.js: Triggers cursor update
 *
 * =============================================================================
 */

const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');
const { ok, fail } = require('../utils/response');
const { getAuthenticatedUserId } = require('../utils/auth-helpers');

const db = new FirestoreHelper();
async function getNextWorkoutHandler(req, res) {
  // Dual auth: prefer req.auth.uid, fallback to body.userId for API key
  const userId = getAuthenticatedUserId(req);
  if (!userId) {
    return fail(res, 'UNAUTHENTICATED', 'Authentication required', null, 401);
  }

  try {
    // 1. Get user and check for active routine
    const user = await db.getDocument('users', userId);
    
    // If no user doc or no activeRoutineId, return gracefully
    if (!user || !user.activeRoutineId) {
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
