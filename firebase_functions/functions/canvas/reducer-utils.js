function ensurePhase(mutState, requiredPhase, onError) {
  if (mutState.phase !== requiredPhase) throw onError();
}

function validateSetActual(actual) {
  if (typeof actual?.reps !== 'number' || actual.reps < 0) return { ok: false, code: 'SCIENCE_VIOLATION', message: 'Invalid reps' };
  if (typeof actual?.rir !== 'number' || actual.rir < 0 || actual.rir > 5) return { ok: false, code: 'SCIENCE_VIOLATION', message: 'Invalid RIR' };
  return { ok: true };
}

function isAnalysisReplacementTarget(card) {
  return card?.lane === 'analysis' && typeof card?.refs?.topic_key === 'string' && card.refs.topic_key.length > 0;
}

module.exports = {
  ensurePhase,
  validateSetActual,
  isAnalysisReplacementTarget,
  /**
   * Given current cards and an accepted set_target card, return ids to expire
   * to maintain a single active target per (exercise_id, set_index).
   */
  computeUniqueSetTargetResolution(cards, acceptedCard) {
    if (!acceptedCard || acceptedCard.type !== 'set_target') return [];
    const ex = acceptedCard?.refs?.exercise_id;
    const idx = acceptedCard?.refs?.set_index;
    if (ex == null || idx == null) return [];
    const colliding = [];
    for (const c of cards) {
      if (!c || c.id === acceptedCard.id) continue;
      if (c.type !== 'set_target') continue;
      const status = c.status;
      if (status !== 'active' && status !== 'accepted' && status !== 'proposed') continue;
      if (c?.refs?.exercise_id === ex && c?.refs?.set_index === idx) {
        colliding.push(c.id);
      }
    }
    return colliding;
  },
};


