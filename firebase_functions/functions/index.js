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

// Workout Operations  
const { getUserWorkouts } = require('./workouts/get-user-workouts');
const { getWorkout } = require('./workouts/get-workout');

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

// Memory Operations


// StrengthOS Operations
const { createStrengthOSSession } = require('./strengthos/create-session');
const { listStrengthOSSessions } = require('./strengthos/list-sessions');
const { deleteStrengthOSSession } = require('./strengthos/delete-session');
const { queryStrengthOS } = require('./strengthos/query-strengthos');
const { queryStrengthOSv2 } = require('./strengthos/query-strengthos-v2');
const { streamAgentNormalizedHandler } = require('./strengthos/stream-agent-normalized');
const { requireFlexibleAuth } = require('./auth/middleware');

// Firestore Triggers
const {
  onTemplateCreated,
  onTemplateUpdated,
  onWorkoutCreated
} = require('./triggers/muscle-volume-calculations');
const {
  onWorkoutCompleted,
  onWorkoutDeleted,
  weeklyStatsRecalculation,
  manualWeeklyStatsRecalculation
} = require('./triggers/weekly-analytics');

// Export all functions as Firebase HTTPS functions
exports.health = functions.https.onRequest(health);

// User Operations
exports.getUser = functions.https.onRequest((req, res) => withApiKey(getUser)(req, res));
exports.updateUser = functions.https.onRequest((req, res) => withApiKey(updateUser)(req, res));

// Workout Operations
exports.getUserWorkouts = functions.https.onRequest((req, res) => withApiKey(getUserWorkouts)(req, res));
exports.getWorkout = functions.https.onRequest((req, res) => withApiKey(getWorkout)(req, res));

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

// Memory Operations


// StrengthOS Operations (Callable functions - authenticated via Firebase Auth)
exports.createStrengthOSSession = createStrengthOSSession;
exports.listStrengthOSSessions = listStrengthOSSessions;
exports.deleteStrengthOSSession = deleteStrengthOSSession;
exports.queryStrengthOS = queryStrengthOS;
exports.queryStrengthOSv2 = queryStrengthOSv2;
exports.streamAgentNormalized = functions.https.onRequest(requireFlexibleAuth(streamAgentNormalizedHandler));

// Auth Operations
exports.getServiceToken = getServiceToken;

// Firestore Triggers (these don't need API key middleware)
exports.onTemplateCreated = onTemplateCreated;
exports.onTemplateUpdated = onTemplateUpdated;
exports.onWorkoutCreated = onWorkoutCreated;
exports.onWorkoutCompleted = onWorkoutCompleted;
exports.onWorkoutDeleted = onWorkoutDeleted;

// Scheduled Functions
exports.weeklyStatsRecalculation = weeklyStatsRecalculation;

// Callable Functions
exports.manualWeeklyStatsRecalculation = manualWeeklyStatsRecalculation;
