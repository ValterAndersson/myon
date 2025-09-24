const admin = require('firebase-admin');

/**
 * Core logic to log a set into an active workout.
 * Minimal extraction for Phase 1; extend with more invariants later.
 */
async function logSetCore(tx, params) {
  const { uid, workout_id, exercise_id, set_index, actual } = params;
  if (!uid) throw new Error('Missing uid');
  const parentCollection = `users/${uid}/active_workouts`;
  const workoutRef = admin.firestore().collection(parentCollection).doc(workout_id);
  const workoutSnap = await tx.get(workoutRef);
  if (!workoutSnap.exists) throw { http: 404, code: 'NOT_FOUND', message: 'Workout not found' };

  const now = admin.firestore.FieldValue.serverTimestamp();
  const eventsRef = workoutRef.collection('events').doc();
  tx.set(eventsRef, {
    type: 'set_performed',
    payload: { exercise_id, set_index, actual },
    created_at: now,
  });

  tx.update(workoutRef, { updated_at: now });
  return { event_id: eventsRef.id };
}

module.exports = { logSetCore };


