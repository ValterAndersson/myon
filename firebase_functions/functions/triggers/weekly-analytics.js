const { onDocumentUpdated, onDocumentDeleted } = require('firebase-functions/v2/firestore');
const admin = require('firebase-admin');

if (!admin.apps.length) {
  admin.initializeApp();
}

const db = admin.firestore();

function getWeekStart(dateString) {
  const date = new Date(dateString);
  const day = date.getUTCDay();
  const diff = (day + 6) % 7;
  date.setUTCDate(date.getUTCDate() - diff);
  date.setUTCHours(0, 0, 0, 0);
  return date.toISOString().split('T')[0];
}

function mergeMetrics(target = {}, source = {}, increment = 1) {
  for (const [key, value] of Object.entries(source)) {
    const current = target[key] || 0;
    const updated = current + value * increment;
    if (updated === 0) {
      delete target[key];
    } else {
      target[key] = updated;
    }
  }
}

async function updateWeeklyStats(userId, weekId, analytics, increment = 1) {
  const ref = db
    .collection('users')
    .doc(userId)
    .collection('analytics')
    .collection('weekly_stats')
    .doc(weekId);

  await db.runTransaction(async (tx) => {
    const snap = await tx.get(ref);
    const data = snap.exists
      ? snap.data()
      : {
          workouts: 0,
          total_sets: 0,
          total_reps: 0,
          total_weight: 0,
          weight_per_muscle_group: {},
          weight_per_muscle: {},
          reps_per_muscle_group: {},
          reps_per_muscle: {},
          sets_per_muscle_group: {},
          sets_per_muscle: {},
        };

    data.workouts += increment;
    data.total_sets +=
      (analytics.total_sets || analytics.totalSets || 0) * increment;
    data.total_reps +=
      (analytics.total_reps || analytics.totalReps || 0) * increment;
    data.total_weight +=
      (analytics.total_weight || analytics.totalWeight || 0) * increment;

    mergeMetrics(
      data.weight_per_muscle_group,
      analytics.weight_per_muscle_group || analytics.weightPerMuscleGroup || {},
      increment
    );
    mergeMetrics(
      data.weight_per_muscle,
      analytics.weight_per_muscle || analytics.weightPerMuscle || {},
      increment
    );
    mergeMetrics(
      data.reps_per_muscle_group,
      analytics.reps_per_muscle_group || analytics.repsPerMuscleGroup || {},
      increment
    );
    mergeMetrics(
      data.reps_per_muscle,
      analytics.reps_per_muscle || analytics.repsPerMuscle || {},
      increment
    );
    mergeMetrics(
      data.sets_per_muscle_group,
      analytics.sets_per_muscle_group || analytics.setsPerMuscleGroup || {},
      increment
    );
    mergeMetrics(
      data.sets_per_muscle,
      analytics.sets_per_muscle || analytics.setsPerMuscle || {},
      increment
    );

    data.updated_at = admin.firestore.FieldValue.serverTimestamp();
    tx.set(ref, data, { merge: true });
  });
}

exports.onWorkoutCompleted = onDocumentUpdated(
  'users/{userId}/workouts/{workoutId}',
  async (event) => {
    const before = event.data.before.data();
    const after = event.data.after.data();
    if (!after || !after.completedAt) return null;
    if (before && before.completedAt === after.completedAt) return null;

    const analytics = after.analytics;
    if (!analytics) return null;

    const weekId = getWeekStart(after.completedAt);
    await updateWeeklyStats(event.params.userId, weekId, analytics, 1);
    return { success: true, weekId };
  }
);

exports.onWorkoutDeleted = onDocumentDeleted(
  'users/{userId}/workouts/{workoutId}',
  async (event) => {
    const workout = event.data.data();
    if (!workout || !workout.completedAt || !workout.analytics) return null;
    const weekId = getWeekStart(workout.completedAt);
    await updateWeeklyStats(event.params.userId, weekId, workout.analytics, -1);
    return { success: true, weekId };
  }
);

