const admin = require('firebase-admin');
const { toSlug, buildAliasSlugs, uniqueArray } = require('./strings');

function computeFamilySlug(name) {
  const s = (name || '').toLowerCase();
  if (!s.trim()) return '';
  // Canonical families in priority order
  const families = [
    // Lower body core
    { key: 'squat', rx: /\b(front squat|back squat|zercher|overhead squat|squat(?! jump))\b/ },
    { key: 'deadlift', rx: /\b(deadlift|romanian deadlift|\brdl\b|sumo deadlift)\b/ },
    { key: 'hip_thrust', rx: /\b(hip thrust|glute bridge)\b/ },
    { key: 'lunge_split_squat', rx: /\b(bulgarian split squat|split squat|lunge)\b/ },
    // Pressing families
    { key: 'bench_press', rx: /\b(bench press|incline bench|decline bench|flat dumbbell press|incline dumbbell press)\b/ },
    { key: 'overhead_press', rx: /\b(overhead press|military press|shoulder press|push press|strict press|standing overhead press|seated overhead press)\b/ },
    // Rowing families (separate common modes)
    { key: 'barbell_row', rx: /\b(bent over row|barbell row|pendlay)\b/ },
    { key: 'seated_row', rx: /\b(seated cable row|seated row)\b/ },
    { key: 't_bar_row', rx: /\b(t\-?bar row)\b/ },
    // Vertical pulls
    { key: 'lat_pulldown', rx: /\b(lat pull\s?down|pulldown)\b/ },
    { key: 'pull_up', rx: /\b(pull\s?up|chin\s?up|muscle up)\b/ },
    // Isolation / accessories
    { key: 'biceps_curl', rx: /\b(biceps curl|hammer curl|curl(?!.*wrist)|preacher curl)\b/ },
    { key: 'wrist_curl', rx: /\b(wrist curl|reverse wrist curl)\b/ },
    { key: 'triceps_extension', rx: /\b(triceps extension|overhead triceps extension|skullcrusher|lying triceps extension)\b/ },
    { key: 'lateral_raise', rx: /\b(lateral raise|side raise)\b/ },
    { key: 'rear_delt_fly', rx: /\b(rear delt fly|reverse fly|face pull)\b/ },
    { key: 'chest_fly', rx: /\b(pec deck|flye|chest fly)\b/ },
    { key: 'calf_raise', rx: /\b(calf raise)\b/ },
    { key: 'leg_extension', rx: /\b(leg extension)\b/ },
    { key: 'leg_curl', rx: /\b(leg curl|hamstring curl|lying leg curl|seated leg curl)\b/ },
    { key: 'shrug', rx: /\b(shrug)\b/ },
    // Core
    { key: 'crunch_core', rx: /\b(crunch|sit\s?up|leg raise|hanging raise)\b/ },
    { key: 'anti_rotation_core', rx: /\b(pallof|anti\-rotation|plank|rollout)\b/ },
    // Carries
    { key: 'carry', rx: /\b(farmer|yoke walk|carry)\b/ },
  ];
  for (const f of families) {
    if (f.rx.test(s)) return f.key;
  }
  // Fallback: use last noun-ish token from slug minus common qualifiers
  const qualifiers = new Set(['barbell','dumbbell','machine','cable','band','bench','bodyweight','smith','incline','decline','seated','standing','lying','flat','close','reverse','wide','narrow','overhead','landmine','t','chest','supported']);
  const slug = toSlug(s);
  const tokens = slug.split('-').filter(Boolean);
  for (let i = tokens.length - 1; i >= 0; i--) {
    const t = tokens[i];
    if (!qualifiers.has(t)) return t;
  }
  return tokens[0] || '';
}

function computeVariantKey(exercise) {
  const name = String(exercise?.name || '').toLowerCase();
  const fam = computeFamilySlug(name);
  let variant = '';
  const includes = (rx) => rx.test(name);

  if (fam === 'deadlift') {
    if (includes(/sumo/)) variant = 'sumo';
    else if (includes(/romanian|\brdl\b/)) variant = 'romanian';
    else if (includes(/stiff[-\s]?leg/)) variant = 'stiff_leg';
    else if (includes(/trap\s?bar|hex\s?bar/)) variant = 'trap_bar';
    else if (includes(/deficit/)) variant = 'deficit';
    else variant = 'conventional';
  } else if (fam === 'squat') {
    if (includes(/front/)) variant = 'front';
    else if (includes(/back/)) variant = 'back';
    else if (includes(/zercher/)) variant = 'zercher';
    else if (includes(/overhead/)) variant = 'overhead';
    else variant = 'bodyweight_or_unspecified';
  } else if (fam === 'bench_press') {
    if (includes(/incline/)) variant = 'incline';
    else if (includes(/decline/)) variant = 'decline';
    else variant = includes(/dumbbell/) ? 'flat_dumbbell' : 'flat_barbell';
  } else if (fam === 'overhead_press') {
    if (includes(/push\s?press/)) variant = 'push_press';
    else if (includes(/military|strict/)) variant = 'strict';
    else variant = includes(/seated/) ? 'seated' : 'standing';
  } else if (fam === 'barbell_row') {
    if (includes(/pendlay/)) variant = 'pendlay';
    else variant = 'bent_over';
  } else if (fam === 'seated_row') {
    variant = 'cable_seated';
  } else if (fam === 't_bar_row') {
    variant = 't_bar';
  } else if (fam === 'lunge_split_squat') {
    if (includes(/bulgarian/)) variant = 'bulgarian_split_squat';
    else if (includes(/split squat/)) variant = 'split_squat';
    else variant = 'lunge';
  } else if (fam === 'lat_pulldown') {
    if (includes(/close|v[-\s]?bar/)) variant = 'close_grip';
    else if (includes(/wide/)) variant = 'wide_grip';
    else variant = 'neutral';
  } else if (fam === 'pull_up') {
    if (includes(/chin/)) variant = 'chin_up';
    else if (includes(/muscle/)) variant = 'muscle_up';
    else variant = 'pull_up';
  } else if (fam === 'triceps_extension') {
    variant = includes(/overhead/) ? 'overhead' : includes(/lying|skull/) ? 'lying' : 'cable_pushdown_or_other';
  } else if (fam === 'biceps_curl') {
    if (includes(/hammer/)) variant = 'hammer';
    else if (includes(/preacher/)) variant = 'preacher';
    else variant = includes(/dumbbell/) ? 'dumbbell' : includes(/barbell/) ? 'barbell' : 'other';
  }

  // Compose minimal variant key used for merge-grouping
  return variant ? `variant:${variant}` : 'variant:default';
}

async function reserveAliasesTransaction(db, aliasSlugs, exerciseId, familySlug) {
  const aliasColl = db.collection('exercise_aliases');
  const slugs = uniqueArray(aliasSlugs || []);
  const now = admin.firestore.FieldValue.serverTimestamp();
  return await db.runTransaction(async (tx) => {
    for (const slug of slugs) {
      const ref = aliasColl.doc(slug);
      const snap = await tx.get(ref);
      if (snap.exists) {
        const existing = snap.data();
        if (existing.exercise_id && existing.exercise_id !== exerciseId) {
          // Conflict: another exercise owns this alias
          throw new Error(`ALIAS_CONFLICT:${slug}:${existing.exercise_id}`);
        }
      }
      const payload = {
        alias_slug: slug,
        exercise_id: exerciseId,
        family_slug: familySlug || null,
        updated_at: now,
      };
      if (!snap?.exists) {
        payload.created_at = now;
      }
      tx.set(ref, payload, { merge: true });
    }
    return true;
  });
}

async function transferAliases(db, fromAliasSlugs, targetExerciseId, familySlug) {
  const aliasColl = db.collection('exercise_aliases');
  const now = admin.firestore.FieldValue.serverTimestamp();
  const slugs = uniqueArray(fromAliasSlugs || []);
  const batch = db.batch();
  for (const slug of slugs) {
    const ref = aliasColl.doc(slug);
    batch.set(ref, {
      alias_slug: slug,
      exercise_id: targetExerciseId,
      family_slug: familySlug || null,
      updated_at: now,
    }, { merge: true });
  }
  await batch.commit();
}

async function reserveAliasesNonTxn(db, aliasSlugs, exerciseId, familySlug) {
  const aliasColl = db.collection('exercise_aliases');
  const slugs = uniqueArray(aliasSlugs || []);
  const now = admin.firestore.FieldValue.serverTimestamp();
  const conflicts = [];
  for (const slug of slugs) {
    const ref = aliasColl.doc(slug);
    try {
      await ref.create({
        alias_slug: slug,
        exercise_id: exerciseId,
        family_slug: familySlug || null,
        created_at: now,
        updated_at: now,
      });
    } catch (e) {
      try {
        const snap = await ref.get();
        if (snap.exists) {
          const data = snap.data() || {};
          if (data.exercise_id && data.exercise_id !== exerciseId) {
            conflicts.push(`ALIAS_CONFLICT:${slug}:${data.exercise_id}`);
          } else {
            await ref.set({ exercise_id: exerciseId, family_slug: familySlug || null, updated_at: now }, { merge: true });
          }
        }
      } catch (e2) {
        conflicts.push(`ALIAS_ERROR:${slug}:${String(e2.message || e2)}`);
      }
    }
  }
  return conflicts;
}

module.exports = {
  computeFamilySlug,
  computeVariantKey,
  reserveAliasesTransaction,
  reserveAliasesNonTxn,
  transferAliases,
  buildAliasSlugs,
  toSlug,
  uniqueArray,
};

// Alias candidates (abbreviations and common synonyms) for registry seeding
function computeAliasCandidates(ex) {
  const name = String(ex?.name || '');
  const family = computeFamilySlug(name);
  const variantKey = computeVariantKey(ex) || '';
  const variant = variantKey.replace('variant:', '');
  const aliases = new Set();

  const add = (a) => { const s = toSlug(a); if (s) aliases.add(s); };

  if (family === 'deadlift') {
    add('deadlift');
    if (variant === 'romanian') { add('rdl'); add('romanian deadlift'); }
    else if (variant === 'sumo') { add('sumo deadlift'); }
    else if (variant === 'stiff_leg') { add('sldl'); add('stiff leg deadlift'); }
    else if (variant === 'trap_bar') { add('trap bar deadlift'); add('hex bar deadlift'); }
  } else if (family === 'squat') {
    if (variant === 'back') add('back squat');
    else if (variant === 'front') add('front squat');
    else if (variant === 'zercher') add('zercher squat');
    else if (variant === 'overhead') add('overhead squat');
    add('squat');
  } else if (family === 'bench_press') {
    add('bench press');
    if (variant === 'flat_dumbbell') { add('dumbbell bench press'); add('db bench'); }
    if (variant === 'incline') { add('incline bench press'); add('incline press'); }
    if (variant === 'decline') { add('decline bench press'); }
  } else if (family === 'overhead_press') {
    add('overhead press'); add('ohp');
    if (variant === 'strict') { add('military press'); add('strict press'); }
    if (variant === 'push_press') { add('push press'); }
    if (variant === 'seated') { add('seated shoulder press'); add('seated ohp'); }
  } else if (family === 'barbell_row') {
    add('barbell row'); add('bent over row'); if (variant === 'pendlay') add('pendlay row');
  } else if (family === 't_bar_row') {
    add('t-bar row'); add('tbar row');
  } else if (family === 'pull_up') {
    add('pull up'); add('pull-up'); if (variant === 'chin_up') { add('chin up'); add('chin-up'); } if (variant === 'muscle_up') { add('muscle up'); add('muscle-up'); }
  } else if (family === 'lat_pulldown') {
    add('lat pulldown'); add('pulldown');
  } else if (family === 'lunge_split_squat') {
    add('lunge'); if (variant === 'bulgarian_split_squat') add('bulgarian split squat'); if (variant === 'split_squat') add('split squat');
  }

  // Generic token-based shorthand expansions
  if (/dumbbell/i.test(name)) {
    add(name.replace(/dumbbell/ig, 'db'));
  }
  if (/barbell/i.test(name)) {
    add(name.replace(/barbell/ig, 'bb'));
  }
  if (/t-?bar/i.test(name)) {
    add(name.replace(/t-?bar/ig, 'tbar'));
  }
  // Bench specific shorthands
  if (family === 'bench_press') {
    if (/dumbbell/i.test(name)) { add('dumbbell-bench-press'); add('db-bench-press'); add('db-bench'); }
    if (/barbell/i.test(name)) { add('bb-bench-press'); add('bb-bench'); }
  }

  return Array.from(aliases);
}

module.exports.computeAliasCandidates = computeAliasCandidates;

function titleCase(str) {
  return String(str)
    .toLowerCase()
    .split(/\s+/)
    .map(w => w ? w[0].toUpperCase() + w.slice(1) : '')
    .join(' ')
    .replace(/\bOf\b|\bAnd\b/g, (m) => m.toLowerCase());
}

function canonicalizeName(rawName) {
  let name = String(rawName || '').trim();
  const original = name;
  if (!name) return { name, changed: false, aliasSlug: null };
  let lower = name.toLowerCase();

  // Hyphenated common forms → spaced words
  lower = lower.replace(/-/g, ' ');

  // Abbreviation expansions (word-boundary)
  lower = lower.replace(/\bohp\b/g, 'overhead press');
  lower = lower.replace(/\bdb\b/g, 'dumbbell');
  lower = lower.replace(/\bbb\b/g, 'barbell');
  lower = lower.replace(/\btbar\b/g, 't bar');

  // Normalize multiple spaces
  lower = lower.replace(/\s{2,}/g, ' ').trim();

  // Standardize some known phrases
  lower = lower.replace(/\bbench press\b/g, 'bench press');
  lower = lower.replace(/\boverhead press\b/g, 'overhead press');
  lower = lower.replace(/\bdumbbell bench press\b/g, 'dumbbell bench press');

  const canonical = titleCase(lower);
  const changed = canonical !== original;
  const aliasSlug = changed ? toSlug(original) : null;
  return { name: canonical, changed, aliasSlug };
}

module.exports.canonicalizeName = canonicalizeName;


