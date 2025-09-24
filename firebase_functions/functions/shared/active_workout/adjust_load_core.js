const admin = require('firebase-admin');

async function adjustLoadCore(tx, params) {
  const { uid, workout_id, exercise_id, set_index, delta_kg } = params;
  const workoutRef = admin.firestore().collection(`users/${uid}/active_workouts`).doc(workout_id);
  const snap = await tx.get(workoutRef);
  if (!snap.exists) throw { http: 404, code: 'NOT_FOUND', message: 'Workout not found' };

  const now = admin.firestore.FieldValue.serverTimestamp();
  const eventsRef = workoutRef.collection('events').doc();
  tx.set(eventsRef, {
    type: 'load_adjusted',
    payload: { exercise_id, set_index, delta_kg },
    created_at: now,
  });
  tx.update(workoutRef, { updated_at: now });
  return { event_id: eventsRef.id };
}

module.exports = { adjustLoadCore };


