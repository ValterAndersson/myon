const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');
const { ok, fail } = require('../utils/response');
const admin = require('firebase-admin');

const db = new FirestoreHelper();

// --- Lightweight normalizers (low-risk) ---
function _kebabToken(s) {
  return String(s || '').trim().toLowerCase().replace(/[_\s]+/g, '-');
}

function _uniqueArray(arr) {
  return Array.from(new Set((arr || []).filter(Boolean)));
}

function normalizeMovement(mv) {
  if (!mv || typeof mv !== 'object') return mv;
  const typeMap = {
    'hip hinge': 'hinge',
    hinge: 'hinge',
    push: 'push',
    pull: 'pull',
    squat: 'squat',
    carry: 'carry',
    rotate: 'rotate',
    rotation: 'rotate',
    power: 'power',
    explosive: 'power',
    accessory: 'accessory',
    other: 'other',
  };
  const splitMap = {
    upper: 'upper',
    lower: 'lower',
    'lower-body': 'lower',
    lower_body: 'lower',
    full: 'full',
    'full-body': 'full',
    full_body: 'full',
  };
  const out = { ...mv };
  if (mv.type) {
    const key = String(mv.type).trim().toLowerCase();
    out.type = typeMap[key] || key;
  }
  if (mv.split) {
    const key = String(mv.split).trim().toLowerCase();
    out.split = splitMap[key] || key;
  }
  return out;
}

function normalizeMetadata(md) {
  if (!md || typeof md !== 'object') return md;
  const levelMap = { beginner: 'beginner', intermediate: 'intermediate', advanced: 'advanced' };
  const planeMap = { sagittal: 'sagittal', frontal: 'frontal', transverse: 'transverse' };
  const out = { ...md };
  if (md.level) {
    const k = String(md.level).trim().toLowerCase();
    out.level = levelMap[k] || k;
  }
  if (md.plane_of_motion) {
    const p = String(md.plane_of_motion).trim().toLowerCase();
    out.plane_of_motion = planeMap[p] || p;
  }
  if (typeof md.unilateral !== 'undefined') {
    out.unilateral = Boolean(md.unilateral);
  }
  return out;
}

function normalizeEquipment(eq) {
  if (!Array.isArray(eq)) return eq;
  return _uniqueArray(eq.map(_kebabToken));
}

function normalizeStimulusTags(tags) {
  if (!Array.isArray(tags)) return tags;
  return _uniqueArray(tags.map(t => String(t || '').trim().toLowerCase()).filter(Boolean));
}

function normalizeStringList(arr) {
  if (!Array.isArray(arr)) return arr;
  return _uniqueArray(arr.map(s => String(s || '').trim()).filter(Boolean));
}

function normalizeMuscles(muscles) {
  if (!muscles || typeof muscles !== 'object') return muscles;
  const out = { ...muscles };
  // category: array of strings only
  if (typeof muscles.category === 'string') {
    out.category = [muscles.category];
  } else if (muscles.category && !Array.isArray(muscles.category) && typeof muscles.category === 'object') {
    // If a map was provided, collect its values into a flat string array
    const vals = [];
    for (const k of Object.keys(muscles.category || {})) {
      const v = muscles.category[k];
      if (Array.isArray(v)) vals.push(...v);
      else if (typeof v === 'string') vals.push(v);
    }
    out.category = _uniqueArray(vals);
  }
  if (Array.isArray(muscles.category)) {
    out.category = _uniqueArray(muscles.category);
  }
  // contribution: map of muscle -> number in [0,1], sum to 1.0
  if (muscles.contribution && typeof muscles.contribution === 'object') {
    const raw = muscles.contribution;
    const keys = Object.keys(raw);
    let values = keys.map(k => Number(raw[k]));
    const anyGtOne = values.some(v => v > 1);
    if (anyGtOne) values = values.map(v => v / 100);
    let sum = values.reduce((a, b) => a + (isFinite(b) ? b : 0), 0);
    if (sum <= 0) {
      out.contribution = muscles.contribution; // keep original if invalid
    } else {
      const normalized = {};
      keys.forEach((k, i) => {
        const val = values[i] / sum;
        normalized[k] = Math.round(val * 1000) / 1000; // 3 decimals
      });
      out.contribution = normalized;
    }
  }
  return out;
}

function normalizePatch(payload) {
  const p = { ...payload };
  if (p.movement) p.movement = normalizeMovement(p.movement);
  if (p.metadata) p.metadata = normalizeMetadata(p.metadata);
  if (p.equipment) p.equipment = normalizeEquipment(p.equipment);
  if (p.stimulus_tags) p.stimulus_tags = normalizeStimulusTags(p.stimulus_tags);
  if (p.coaching_cues) p.coaching_cues = normalizeStringList(p.coaching_cues);
  if (p.muscles) p.muscles = normalizeMuscles(p.muscles);
  if (p.category && typeof p.category === 'string') p.category = String(p.category).trim().toLowerCase();
  return p;
}

async function refineExerciseHandler(req, res) {
  try {
    if (req.method !== 'POST') return fail(res, 'METHOD_NOT_ALLOWED', 'Method Not Allowed', null, 405);
    const userId = req.user?.uid || req.auth?.uid || 'service';

    const { exercise_id, updates } = req.body || {};
    if (!exercise_id || !updates) return fail(res, 'INVALID_ARGUMENT', 'exercise_id and updates required');

    // Minimal validation/normalization; agent should pass structured fields
    const payload = {};
    if (updates.name) payload.name = String(updates.name).trim();
    if (updates.movement) payload.movement = updates.movement;
    if (updates.equipment) payload.equipment = updates.equipment;
    if (updates.muscles) payload.muscles = updates.muscles;
    if (updates.metadata) payload.metadata = updates.metadata;
    if (updates.execution_notes) payload.execution_notes = updates.execution_notes;
    if (updates.common_mistakes) payload.common_mistakes = updates.common_mistakes;
    if (updates.programming_use_cases) payload.programming_use_cases = updates.programming_use_cases;
    if (updates.coaching_cues) payload.coaching_cues = updates.coaching_cues;
    if (updates.stimulus_tags) payload.stimulus_tags = updates.stimulus_tags;
    if (updates.category) payload.category = updates.category;

    // If target is merged, route update to canonical parent
    const current = await db.getDocument('exercises', exercise_id);
    const targetId = current?.merged_into || exercise_id;
    const normalized = normalizePatch(payload);
    normalized.updated_at = admin.firestore.FieldValue.serverTimestamp();
    await db.updateDocument('exercises', targetId, normalized);
    return ok(res, { exercise_id: targetId, updated: true, redirected_from: current?.merged_into ? exercise_id : undefined });
  } catch (error) {
    console.error('refine-exercise error:', error);
    return fail(res, 'INTERNAL', 'Failed to refine exercise', { message: error.message }, 500);
  }
}

exports.refineExercise = onRequest(requireFlexibleAuth(refineExerciseHandler));


