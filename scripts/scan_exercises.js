/**
 * One-off diagnostic script: Scan exercise documents for name/schema issues.
 *
 * Usage:
 *   GOOGLE_APPLICATION_CREDENTIALS=../myon-53d85-firebase-adminsdk-fbsvc-ca7beb1435.json node scripts/scan_exercises.js
 */

const admin = require('firebase-admin');
admin.initializeApp({ projectId: 'myon-53d85' });
const db = admin.firestore();

async function main() {
  const snap = await db.collection('exercises').get();

  console.log('=== TOTAL EXERCISES:', snap.size, '===\n');

  const nameIssues = [];
  const nameOk = [];
  const statusCounts = {};
  const idFormats = { doubleUnderscore: 0, dash: 0, other: 0 };
  const schemaIssues = [];

  snap.forEach(doc => {
    const data = doc.data();
    const name = data.name || '';
    const status = data.status || '(no status)';
    statusCounts[status] = (statusCounts[status] || 0) + 1;

    // Check doc ID format
    if (doc.id.includes('__')) idFormats.doubleUnderscore++;
    else if (doc.id.includes('-')) idFormats.dash++;
    else idFormats.other++;

    // Check if name looks like a slug/ID
    const looksLikeSlug = /^[a-z0-9_-]+$/.test(name) && (name.includes('-') || name.includes('_'));
    const hasSpaces = name.includes(' ');
    const allLower = name === name.toLowerCase();

    if (looksLikeSlug || (name.length > 3 && !hasSpaces && allLower)) {
      nameIssues.push({
        docId: doc.id,
        name: name,
        name_slug: data.name_slug,
        family_slug: data.family_slug,
        equipment: data.equipment,
        hasDescription: Boolean(data.description && data.description.length > 0),
        hasExecNotes: Boolean(data.execution_notes && data.execution_notes.length > 0),
        musclesPrimary: (data.muscles && data.muscles.primary) || data.primary_muscles || [],
      });
    } else {
      nameOk.push({ docId: doc.id, name: name });
    }

    // Schema checks
    const issues = [];
    if (!data.muscles && !data.primary_muscles) issues.push('no_muscles');
    if (data.primary_muscles && !data.muscles) issues.push('legacy_muscle_schema');
    if (!data.movement) issues.push('no_movement');
    if (!data.metadata) issues.push('no_metadata');
    if (!data.execution_notes || data.execution_notes.length === 0) issues.push('no_execution_notes');
    if (!data.description) issues.push('no_description');
    if (!data.equipment || data.equipment.length === 0) issues.push('no_equipment');
    if (data.coaching_cues && data.coaching_cues.length > 0) issues.push('has_coaching_cues');
    if (data.tips && data.tips.length > 0) issues.push('has_tips');
    // Check for deprecated top-level fields
    if (data.instructions) issues.push('has_deprecated_instructions');
    if (data.created_at) issues.push('has_deprecated_created_at');

    if (issues.length > 0) {
      schemaIssues.push({ docId: doc.id, name: name, issues: issues });
    }
  });

  console.log('=== DOC ID FORMAT DISTRIBUTION ===');
  console.log(JSON.stringify(idFormats, null, 2));

  console.log('\n=== STATUS DISTRIBUTION ===');
  console.log(JSON.stringify(statusCounts, null, 2));

  console.log('\n=== EXERCISES WITH SLUG-LIKE NAMES:', nameIssues.length, '===');
  for (const ex of nameIssues) {
    console.log(JSON.stringify(ex));
  }

  console.log('\n=== EXERCISES WITH PROPER NAMES:', nameOk.length, '===');
  for (const ex of nameOk.slice(0, 50)) {
    console.log('  ' + ex.docId + ' -> "' + ex.name + '"');
  }
  if (nameOk.length > 50) {
    console.log('  ... and', nameOk.length - 50, 'more');
  }

  // Schema issue summary
  const issueCounts = {};
  for (const s of schemaIssues) {
    for (const i of s.issues) {
      issueCounts[i] = (issueCounts[i] || 0) + 1;
    }
  }
  console.log('\n=== SCHEMA ISSUE COUNTS ===');
  console.log(JSON.stringify(issueCounts, null, 2));

  console.log('\n=== EXERCISES WITH SCHEMA ISSUES:', schemaIssues.length, '/', snap.size, '===');
  for (const s of schemaIssues.slice(0, 30)) {
    console.log('  ' + s.docId + ': ' + s.issues.join(', '));
  }
  if (schemaIssues.length > 30) {
    console.log('  ... and', schemaIssues.length - 30, 'more');
  }
}

main().then(() => process.exit(0)).catch(e => { console.error(e); process.exit(1); });
