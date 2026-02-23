/**
 * Backfill template_diff on a completed workout and optionally trigger analysis.
 *
 * Usage:
 *   GOOGLE_APPLICATION_CREDENTIALS=$FIREBASE_SA_KEY node scripts/backfill-template-diff.js <userId> <workoutId> [--trigger-analysis]
 */

const admin = require('firebase-admin');
admin.initializeApp();
const db = admin.firestore();
const { generateTemplateDiff } = require('../utils/template-diff-generator');

async function main() {
  const userId = process.argv[2];
  const workoutId = process.argv[3];
  const triggerAnalysis = process.argv.includes('--trigger-analysis');

  if (!userId || !workoutId) {
    console.error('Usage: node scripts/backfill-template-diff.js <userId> <workoutId> [--trigger-analysis]');
    process.exit(1);
  }

  // 1. Read the workout
  const workoutRef = db.doc(`users/${userId}/workouts/${workoutId}`);
  const workoutSnap = await workoutRef.get();
  if (!workoutSnap.exists) {
    console.error('Workout not found:', workoutId);
    process.exit(1);
  }
  const workout = workoutSnap.data();
  console.log(`Workout: ${workout.name || workoutId}`);
  console.log(`  Exercises: ${(workout.exercises || []).length}`);
  console.log(`  source_template_id: ${workout.source_template_id || 'none'}`);

  if (!workout.source_template_id) {
    console.log('No source_template_id — nothing to diff.');
    process.exit(0);
  }

  // 2. Read the template
  const templateRef = db.doc(`users/${userId}/templates/${workout.source_template_id}`);
  const templateSnap = await templateRef.get();
  if (!templateSnap.exists) {
    console.error('Template not found:', workout.source_template_id);
    process.exit(1);
  }
  const template = templateSnap.data();
  console.log(`\nTemplate: ${template.name}`);
  console.log(`  Exercises: ${(template.exercises || []).length}`);

  // 3. Show comparison
  const workoutExIds = (workout.exercises || []).map(e => e.exercise_id);
  const templateExIds = (template.exercises || []).map(e => e.exercise_id);
  console.log('\n--- Template exercises ---');
  for (const ex of template.exercises || []) {
    const inWorkout = workoutExIds.includes(ex.exercise_id);
    console.log(`  ${inWorkout ? '✓' : '✗'} ${ex.name || ex.exercise_id} (${(ex.sets || []).length} sets)`);
    for (const s of ex.sets || []) {
      console.log(`      ${s.reps}r @ ${s.weight || 0}kg rir=${s.rir ?? '-'}`);
    }
  }
  console.log('\n--- Workout exercises ---');
  for (const ex of workout.exercises || []) {
    const inTemplate = templateExIds.includes(ex.exercise_id);
    console.log(`  ${inTemplate ? '✓' : '+'} ${ex.name || ex.exercise_id} (${(ex.sets || []).length} sets)`);
    for (const s of ex.sets || []) {
      console.log(`      ${s.reps}r @ ${s.weight_kg || 0}kg rir=${s.rir ?? '-'} ${s.is_completed ? '✓' : '○'}`);
    }
  }

  // 4. Generate diff
  const diff = generateTemplateDiff(workout.exercises, template.exercises);
  console.log('\n--- Generated template_diff ---');
  console.log(JSON.stringify(diff, null, 2));

  // 5. Write diff to workout doc
  await workoutRef.update({ template_diff: diff });
  console.log('\n✓ template_diff written to workout doc');

  // 6. Write changelog entry if changes detected
  if (diff.changes_detected) {
    const changelogRef = templateRef.collection('changelog').doc();
    await changelogRef.set({
      timestamp: admin.firestore.FieldValue.serverTimestamp(),
      source: 'workout_completion',
      workout_id: workoutId,
      recommendation_id: null,
      changes: [{ field: 'exercises', operation: 'deviated', summary: diff.summary || 'User deviated from template' }],
      expires_at: new Date(Date.now() + 90 * 24 * 60 * 60 * 1000)
    });
    console.log('✓ changelog entry written');
  }

  // 7. Optionally trigger analysis
  if (triggerAnalysis) {
    await db.collection('training_analysis_jobs').add({
      type: 'POST_WORKOUT',
      status: 'queued',
      priority: 100,
      payload: {
        user_id: userId,
        workout_id: workoutId,
        window_weeks: 4,
      },
      attempts: 0,
      max_attempts: 3,
      created_at: admin.firestore.FieldValue.serverTimestamp(),
      updated_at: admin.firestore.FieldValue.serverTimestamp(),
    });
    console.log('✓ POST_WORKOUT analysis job enqueued');
  }

  console.log('\nDone.');
  process.exit(0);
}

main().catch(err => {
  console.error('Error:', err);
  process.exit(1);
});
