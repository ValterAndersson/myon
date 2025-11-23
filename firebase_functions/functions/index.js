// Alias ops
const { upsertAlias } = require('./aliases/upsert-alias');
const { deleteAlias } = require('./aliases/delete-alias');
// Suggestions/Refine
const { suggestFamilyVariant } = require('./exercises/suggest-family-variant');
const { suggestAliases } = require('./exercises/suggest-aliases');
const { refineExercise } = require('./exercises/refine-exercise');
const { searchAliases } = require('./exercises/search-aliases');
const functions = require('firebase-functions');
const admin = require('firebase-admin');

// Initialize admin if not already initialized
if (!admin.apps.length) {
  admin.initializeApp();
}

// Middleware
const { withApiKey } = require('./auth/middleware');
const { getServiceToken } = require('./auth/exchange-token');

// Health Check
const { health } = require('./health/health');

// User Operations
const { getUser } = require('./user/get-user');
const { updateUser } = require('./user/update-user');
const { getUserPreferences } = require('./user/get-preferences');
const { updateUserPreferences } = require('./user/update-preferences');
const { upsertUserAttributes } = require('./user/upsert-attributes');

// Workout Operations  
const { getUserWorkouts } = require('./workouts/get-user-workouts');
const { getWorkout } = require('./workouts/get-workout');
const { upsertWorkout } = require('./workouts/upsert-workout');

// Template Operations
const { getUserTemplates } = require('./templates/get-user-templates');
const { getTemplate } = require('./templates/get-template');
const { createTemplate } = require('./templates/create-template');
const { updateTemplate } = require('./templates/update-template');
const { deleteTemplate } = require('./templates/delete-template');

// Routine Operations
const { getUserRoutines } = require('./routines/get-user-routines');
const { getRoutine } = require('./routines/get-routine');
const { createRoutine } = require('./routines/create-routine');
const { updateRoutine } = require('./routines/update-routine');
const { deleteRoutine } = require('./routines/delete-routine');
const { getActiveRoutine } = require('./routines/get-active-routine');
const { setActiveRoutine } = require('./routines/set-active-routine');

// Exercise Operations
const { getExercises } = require('./exercises/get-exercises');
const { getExercise } = require('./exercises/get-exercise');
const { searchExercises } = require('./exercises/search-exercises');
const { upsertExercise } = require('./exercises/upsert-exercise');
const { approveExercise } = require('./exercises/approve-exercise');
const { ensureExerciseExists } = require('./exercises/ensure-exercise-exists');
const { resolveExercise } = require('./exercises/resolve-exercise');
const { mergeExercises } = require('./exercises/merge-exercises');
const { backfillNormalizeFamily } = require('./exercises/backfill-normalize-family');
const { backupExercises } = require('./maintenance/backup-exercises');
const { repointAlias } = require('./maintenance/repoint-alias');
const { repointShorthandAliases } = require('./maintenance/repoint-shorthand-aliases');
const { normalizeCatalog } = require('./exercises/normalize-catalog');
const { listFamilies } = require('./exercises/list-families');
const { normalizeCatalogPage } = require('./exercises/normalize-catalog-page');

// Active Workout Operations
const { proposeSession } = require('./active_workout/propose-session');
const { startActiveWorkout } = require('./active_workout/start-active-workout');
const { getActiveWorkout } = require('./active_workout/get-active-workout');
const { prescribeSet } = require('./active_workout/prescribe-set');
const { logSet } = require('./active_workout/log-set');
const { scoreSet } = require('./active_workout/score-set');
const { addExercise } = require('./active_workout/add-exercise');
const { swapExercise } = require('./active_workout/swap-exercise');
const { completeActiveWorkout } = require('./active_workout/complete-active-workout');
const { cancelActiveWorkout } = require('./active_workout/cancel-active-workout');
const { noteActiveWorkout } = require('./active_workout/note-active-workout');

// Memory Operations


// StrengthOS Operations
const { createStrengthOSSession } = require('./strengthos/create-session');
const { listStrengthOSSessions } = require('./strengthos/list-sessions');
const { deleteStrengthOSSession } = require('./strengthos/delete-session');
const { queryStrengthOS } = require('./strengthos/query-strengthos');
const { queryStrengthOSv2 } = require('./strengthos/query-strengthos-v2');
const { streamAgentNormalizedHandler } = require('./strengthos/stream-agent-normalized');
const { requireFlexibleAuth } = require('./auth/middleware');
const { upsertProgressReport, getProgressReports } = require('./strengthos/progress-reports');
// Canvas Operations
const { applyAction } = require('./canvas/apply-action');
const { proposeCards } = require('./canvas/propose-cards');
const { expireProposals } = require('./canvas/expire-proposals');
const { expireProposalsScheduledHandler } = require('./canvas/expire-proposals-scheduled');
const { bootstrapCanvas } = require('./canvas/bootstrap-canvas');
const { emitEvent } = require('./canvas/emit-event');
const { checkPendingResponse } = require('./canvas/check-pending-response');
const { respondToAgent } = require('./canvas/respond-to-agent');
const { purgeCanvas } = require('./canvas/purge-canvas');

// Analytics
const { runAnalyticsForUser } = require('./analytics/controller');
const { analyticsCompactionScheduled, compactAnalyticsForUser } = require('./analytics/compaction');
const { publishWeeklyJob } = require('./analytics/publish-weekly-job');
const { getAnalyticsFeatures } = require('./analytics/get-features');
const { recalculateWeeklyForUser } = require('./analytics/recalculate-weekly-for-user');
// Agents
const { invokeCanvasOrchestrator } = require('./agents/invoke-canvas-orchestrator');

// Firestore Triggers
const {
  onTemplateCreated,
  onTemplateUpdated,
  onWorkoutCreated
} = require('./triggers/muscle-volume-calculations');
const {
  onWorkoutCompleted,
  onWorkoutCreatedWithEnd,
  onWorkoutDeleted,
  weeklyStatsRecalculation,
  manualWeeklyStatsRecalculation,
  onWorkoutCreatedWeekly,
  onWorkoutFinalizedForUser
} = require('./triggers/weekly-analytics');

// Export all functions as Firebase HTTPS functions
exports.health = functions.https.onRequest(health);

// User Operations
exports.getUser = functions.https.onRequest((req, res) => withApiKey(getUser)(req, res));
exports.updateUser = functions.https.onRequest((req, res) => withApiKey(updateUser)(req, res));
exports.getUserPreferences = functions.https.onRequest((req, res) => withApiKey(getUserPreferences)(req, res));
exports.updateUserPreferences = functions.https.onRequest((req, res) => withApiKey(updateUserPreferences)(req, res));
exports.upsertUserAttributes = functions.https.onRequest((req, res) => withApiKey(upsertUserAttributes)(req, res));

// Workout Operations
exports.getUserWorkouts = functions.https.onRequest((req, res) => withApiKey(getUserWorkouts)(req, res));
exports.getWorkout = functions.https.onRequest((req, res) => withApiKey(getWorkout)(req, res));
exports.upsertWorkout = functions.https.onRequest((req, res) => requireFlexibleAuth(upsertWorkout)(req, res));

// Template Operations
exports.getUserTemplates = functions.https.onRequest((req, res) => withApiKey(getUserTemplates)(req, res));
exports.getTemplate = functions.https.onRequest((req, res) => withApiKey(getTemplate)(req, res));
exports.createTemplate = functions.https.onRequest((req, res) => withApiKey(createTemplate)(req, res));
exports.updateTemplate = functions.https.onRequest((req, res) => withApiKey(updateTemplate)(req, res));
exports.deleteTemplate = functions.https.onRequest((req, res) => withApiKey(deleteTemplate)(req, res));

// Routine Operations
exports.getUserRoutines = functions.https.onRequest((req, res) => withApiKey(getUserRoutines)(req, res));
exports.getRoutine = functions.https.onRequest((req, res) => withApiKey(getRoutine)(req, res));
exports.createRoutine = functions.https.onRequest((req, res) => withApiKey(createRoutine)(req, res));
exports.updateRoutine = functions.https.onRequest((req, res) => withApiKey(updateRoutine)(req, res));
exports.deleteRoutine = functions.https.onRequest((req, res) => withApiKey(deleteRoutine)(req, res));
exports.getActiveRoutine = functions.https.onRequest((req, res) => withApiKey(getActiveRoutine)(req, res));
exports.setActiveRoutine = functions.https.onRequest((req, res) => withApiKey(setActiveRoutine)(req, res));

// Exercise Operations
exports.getExercises = functions.https.onRequest((req, res) => withApiKey(getExercises)(req, res));
exports.getExercise = functions.https.onRequest((req, res) => withApiKey(getExercise)(req, res));
exports.searchExercises = functions.https.onRequest((req, res) => withApiKey(searchExercises)(req, res));
exports.upsertExercise = functions.https.onRequest((req, res) => withApiKey(upsertExercise)(req, res));
exports.approveExercise = functions.https.onRequest((req, res) => withApiKey(approveExercise)(req, res));
exports.ensureExerciseExists = functions.https.onRequest((req, res) => withApiKey(ensureExerciseExists)(req, res));
exports.resolveExercise = functions.https.onRequest((req, res) => withApiKey(resolveExercise)(req, res));
exports.mergeExercises = functions.https.onRequest((req, res) => withApiKey(mergeExercises)(req, res));
exports.backfillNormalizeFamily = functions.https.onRequest((req, res) => withApiKey(backfillNormalizeFamily)(req, res));
exports.backupExercises = functions.https.onRequest((req, res) => withApiKey(backupExercises)(req, res));
exports.repointAlias = functions.https.onRequest((req, res) => withApiKey(repointAlias)(req, res));
exports.repointShorthandAliases = functions.https.onRequest((req, res) => withApiKey(repointShorthandAliases)(req, res));
exports.upsertAlias = functions.https.onRequest((req, res) => withApiKey(upsertAlias)(req, res));
exports.deleteAlias = functions.https.onRequest((req, res) => withApiKey(deleteAlias)(req, res));
exports.suggestFamilyVariant = functions.https.onRequest((req, res) => withApiKey(suggestFamilyVariant)(req, res));
exports.suggestAliases = functions.https.onRequest((req, res) => withApiKey(suggestAliases)(req, res));
exports.refineExercise = functions.https.onRequest((req, res) => withApiKey(refineExercise)(req, res));
exports.searchAliases = functions.https.onRequest((req, res) => withApiKey(searchAliases)(req, res));
exports.normalizeCatalog = functions.https.onRequest((req, res) => withApiKey(normalizeCatalog)(req, res));
exports.listFamilies = functions.https.onRequest((req, res) => withApiKey(listFamilies)(req, res));
exports.normalizeCatalogPage = functions.https.onRequest((req, res) => withApiKey(normalizeCatalogPage)(req, res));

// Active Workout Operations
exports.proposeSession = functions.https.onRequest((req, res) => requireFlexibleAuth(proposeSession)(req, res));
exports.startActiveWorkout = functions.https.onRequest((req, res) => requireFlexibleAuth(startActiveWorkout)(req, res));
exports.getActiveWorkout = functions.https.onRequest((req, res) => requireFlexibleAuth(getActiveWorkout)(req, res));
exports.prescribeSet = functions.https.onRequest((req, res) => requireFlexibleAuth(prescribeSet)(req, res));
exports.logSet = functions.https.onRequest((req, res) => requireFlexibleAuth(logSet)(req, res));
exports.scoreSet = functions.https.onRequest((req, res) => requireFlexibleAuth(scoreSet)(req, res));
exports.addExercise = functions.https.onRequest((req, res) => requireFlexibleAuth(addExercise)(req, res));
exports.swapExercise = functions.https.onRequest((req, res) => requireFlexibleAuth(swapExercise)(req, res));
exports.completeActiveWorkout = functions.https.onRequest((req, res) => requireFlexibleAuth(completeActiveWorkout)(req, res));
exports.cancelActiveWorkout = functions.https.onRequest((req, res) => requireFlexibleAuth(cancelActiveWorkout)(req, res));
exports.noteActiveWorkout = functions.https.onRequest((req, res) => requireFlexibleAuth(noteActiveWorkout)(req, res));

// Memory Operations


// StrengthOS Operations (Callable functions - authenticated via Firebase Auth)
exports.createStrengthOSSession = createStrengthOSSession;
exports.listStrengthOSSessions = listStrengthOSSessions;
exports.deleteStrengthOSSession = deleteStrengthOSSession;
exports.queryStrengthOS = queryStrengthOS;
exports.queryStrengthOSv2 = queryStrengthOSv2;
exports.streamAgentNormalized = functions.https.onRequest(requireFlexibleAuth(streamAgentNormalizedHandler));
exports.upsertProgressReport = functions.https.onRequest((req, res) => withApiKey(upsertProgressReport)(req, res));
exports.getProgressReports = functions.https.onRequest((req, res) => requireFlexibleAuth(getProgressReports)(req, res));

// Canvas Operations
exports.applyAction = functions.https.onRequest((req, res) => requireFlexibleAuth(applyAction)(req, res));
exports.proposeCards = functions.https.onRequest((req, res) => withApiKey(proposeCards)(req, res));
exports.expireProposals = functions.https.onRequest((req, res) => withApiKey(expireProposals)(req, res));
exports.bootstrapCanvas = functions.https.onRequest((req, res) => requireFlexibleAuth(bootstrapCanvas)(req, res));
exports.emitEvent = functions.https.onRequest((req, res) => withApiKey(emitEvent)(req, res));
exports.checkPendingResponse = functions.https.onRequest((req, res) => withApiKey(checkPendingResponse)(req, res));
exports.respondToAgent = functions.https.onRequest((req, res) => requireFlexibleAuth(respondToAgent)(req, res));
exports.purgeCanvas = functions.https.onRequest((req, res) => requireFlexibleAuth(purgeCanvas)(req, res));
exports.runAnalyticsForUser = functions.https.onRequest((req, res) => requireFlexibleAuth(runAnalyticsForUser)(req, res));
exports.compactAnalyticsForUser = functions.https.onRequest((req, res) => requireFlexibleAuth(compactAnalyticsForUser)(req, res));
exports.publishWeeklyJob = functions.https.onRequest((req, res) => requireFlexibleAuth(publishWeeklyJob)(req, res));
exports.getAnalyticsFeatures = functions.https.onRequest((req, res) => requireFlexibleAuth(getAnalyticsFeatures)(req, res));
exports.recalculateWeeklyForUser = functions.https.onRequest((req, res) => requireFlexibleAuth(recalculateWeeklyForUser)(req, res));
// Agents
exports.invokeCanvasOrchestrator = functions.https.onRequest((req, res) => requireFlexibleAuth(invokeCanvasOrchestrator)(req, res));

// Auth Operations
exports.getServiceToken = getServiceToken;

// Firestore Triggers (these don't need API key middleware)
exports.onTemplateCreated = onTemplateCreated;
exports.onTemplateUpdated = onTemplateUpdated;
exports.onWorkoutCreated = onWorkoutCreated;
exports.onWorkoutCreatedWithEnd = onWorkoutCreatedWithEnd;
exports.onWorkoutCompleted = onWorkoutCompleted;
exports.onWorkoutDeleted = onWorkoutDeleted;
exports.onWorkoutCreatedWeekly = onWorkoutCreatedWeekly;
exports.onWorkoutFinalizedForUser = onWorkoutFinalizedForUser;

// Scheduled Functions
exports.weeklyStatsRecalculation = weeklyStatsRecalculation;
exports.analyticsCompactionScheduled = analyticsCompactionScheduled;
// Guard scheduled export for environments without scheduler helper
if (functions.pubsub && typeof functions.pubsub.schedule === 'function') {
  exports.expireProposalsScheduled = functions.pubsub.schedule('every 15 minutes').onRun(async (context) => {
    try {
      const result = await expireProposalsScheduledHandler();
      console.log('expireProposalsScheduled result', result);
    } catch (e) {
      console.error('expireProposalsScheduled error', e);
    }
    return null;
  });
} else {
  console.log('Skipping expireProposalsScheduled export: scheduler not available in current runtime');
}

// Callable Functions
exports.manualWeeklyStatsRecalculation = manualWeeklyStatsRecalculation;
