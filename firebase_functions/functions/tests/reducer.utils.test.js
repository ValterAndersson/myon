const { test, describe } = require('node:test');
const assert = require('node:assert/strict');
const { ensurePhase, validateSetActual, isAnalysisReplacementTarget } = require('../canvas/reducer-utils');

describe('Reducer utils', () => {
  test('ensurePhase throws when phase mismatches', () => {
    const state = { phase: 'planning' };
    assert.throws(() => ensurePhase(state, 'active', () => ({ http: 409 })));
  });

  test('validateSetActual bounds', () => {
    assert.equal(validateSetActual({ reps: 8, rir: 1 }).ok, true);
    assert.equal(validateSetActual({ reps: -1, rir: 1 }).ok, false);
    assert.equal(validateSetActual({ reps: 8, rir: 10 }).ok, false);
  });

  test('isAnalysisReplacementTarget guards by lane and topic_key', () => {
    assert.equal(isAnalysisReplacementTarget({ lane: 'analysis', refs: { topic_key: 'x' } }), true);
    assert.equal(isAnalysisReplacementTarget({ lane: 'workout', refs: { topic_key: 'x' } }), false);
    assert.equal(isAnalysisReplacementTarget({ lane: 'analysis' }), false);
  });
});


