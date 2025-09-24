const { test, describe } = require('node:test');
const assert = require('node:assert/strict');
const { validateApplyActionRequest, validateProposeCardsRequest } = require('../canvas/validators');

// This is a golden flow contract test at the schema/delta level (no Firestore IO)
describe('Golden E2E flow (contract-level)', () => {
  test('plan→accept→log_set→complete shapes', () => {
    // ADD_INSTRUCTION
    let req = { canvasId: 'c', action: { type: 'ADD_INSTRUCTION', idempotency_key: 'k1', payload: { text: 'upper body today' } } };
    assert.equal(validateApplyActionRequest(req).valid, true);

    // Agent proposes session plan + set_target
    let pc = { canvasId: 'c', cards: [ { type: 'session_plan', content: { blocks: [] }, lane: 'workout' }, { type: 'set_target', content: { target: { reps: 8, rir: 1 } }, lane: 'workout', refs: { exercise_id: 'e', set_index: 0 } } ] };
    assert.equal(validateProposeCardsRequest(pc).valid, true);

    // ACCEPT_PROPOSAL (set_target)
    req = { canvasId: 'c', action: { type: 'ACCEPT_PROPOSAL', idempotency_key: 'k2', card_id: 'card_set_target' } };
    assert.equal(validateApplyActionRequest(req).valid, true);

    // LOG_SET
    req = { canvasId: 'c', action: { type: 'LOG_SET', idempotency_key: 'k3', payload: { workout_id: 'w', exercise_id: 'e', set_index: 0, actual: { reps: 8, rir: 1, weight: 60 } } } };
    assert.equal(validateApplyActionRequest(req).valid, true);

    // COMPLETE
    req = { canvasId: 'c', action: { type: 'COMPLETE', idempotency_key: 'k4' } };
    assert.equal(validateApplyActionRequest(req).valid, true);
  });
});


