/**
 * Deep scan: Check duplicates, sample full docs, and verify iOS schema compatibility.
 *
 * Usage:
 *   GOOGLE_APPLICATION_CREDENTIALS=~/.config/povver/myon-53d85-firebase-adminsdk-fbsvc-ca7beb1435.json \
 *     node scripts/scan_exercises_deep.js
 */

const admin = require('firebase-admin');
admin.initializeApp({ projectId: 'myon-53d85' });
const db = admin.firestore();

async function main() {
  const snap = await db.collection('exercises').get();

  // 1. Duplicate name detection
  const nameMap = {};
  snap.forEach(doc => {
    const data = doc.data();
    const name = data.name || '';
    const status = data.status || 'approved';
    if (status === 'deprecated') return;

    if (nameMap[name] === undefined) nameMap[name] = [];
    nameMap[name].push(doc.id);
  });

  const dupes = Object.entries(nameMap)
    .filter(([, ids]) => ids.length > 1)
    .sort((a, b) => b[1].length - a[1].length);

  console.log('=== DUPLICATE EXERCISE NAMES:', dupes.length, '===');
  for (const [name, ids] of dupes.slice(0, 40)) {
    console.log('  "' + name + '" (' + ids.length + ' docs): ' + ids.join(', '));
  }
  if (dupes.length > 40) console.log('  ... and', dupes.length - 40, 'more');

  // 2. Sample full documents (enriched ones from the Feb 9 batch)
  console.log('\n=== SAMPLE FULL DOCUMENTS ===');
  const sampleIds = [
    'bench_press__bench-press-barbell',
    'ball_slams__ball-slams',
    'bayesian_curl__bayesian-curl',
    'reverse_fly__reverse-fly-cable',
    'cable_pull_over__cable-pull-over',
    'skullcrusher__skullcrusher-dumbbell',
    'push_up__push-up',
    'high_incline_dumbell_press__high-incline-dumbell-press',
  ];
  for (const id of sampleIds) {
    const doc = await db.collection('exercises').doc(id).get();
    if (doc.exists) {
      const data = doc.data();
      // Remove timestamps for readability
      delete data.updated_at;
      delete data.created_at;
      console.log('\n--- ' + id + ' ---');
      console.log(JSON.stringify(data, null, 2));
    } else {
      console.log('\n--- ' + id + ' --- NOT FOUND');
    }
  }

  // 3. iOS schema compatibility check
  // The iOS Exercise model expects these fields via CodingKeys:
  // name, category, description, metadata{level, plane_of_motion, unilateral},
  // movement{split, type}, equipment[], muscles{category, primary, secondary, contribution},
  // execution_notes[], common_mistakes[], programming_use_cases[],
  // stimulus_tags[], suitability_notes[], coaching_cues[], tips[], status
  console.log('\n=== iOS SCHEMA COMPATIBILITY ===');
  const iosFields = [
    'name', 'category', 'description', 'metadata', 'movement',
    'equipment', 'muscles', 'execution_notes', 'common_mistakes',
    'programming_use_cases', 'stimulus_tags', 'suitability_notes',
    'coaching_cues', 'tips', 'status'
  ];
  const fieldPresence = {};
  iosFields.forEach(f => { fieldPresence[f] = { present: 0, missing: 0 }; });

  snap.forEach(doc => {
    const data = doc.data();
    for (const field of iosFields) {
      const val = data[field];
      if (val !== undefined && val !== null) {
        fieldPresence[field].present++;
      } else {
        fieldPresence[field].missing++;
      }
    }
  });

  for (const [field, counts] of Object.entries(fieldPresence)) {
    const pct = ((counts.present / snap.size) * 100).toFixed(1);
    console.log('  ' + field.padEnd(25) + counts.present + '/' + snap.size + ' (' + pct + '%)');
  }

  // 4. Check what fields exist that iOS doesn't expect
  console.log('\n=== EXTRA FIELDS NOT IN iOS MODEL ===');
  const allFields = new Set();
  snap.forEach(doc => {
    Object.keys(doc.data()).forEach(k => allFields.add(k));
  });
  const iosFieldSet = new Set(iosFields);
  iosFieldSet.add('updated_at');
  iosFieldSet.add('created_at');
  const extra = [...allFields].filter(f => iosFieldSet.has(f) === false).sort();
  console.log('  ' + extra.join(', '));
}

main().then(() => process.exit(0)).catch(e => { console.error(e); process.exit(1); });
