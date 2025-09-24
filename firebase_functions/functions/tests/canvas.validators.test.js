const { test, describe } = require('node:test');
const assert = require('node:assert/strict');
const { validateApplyActionRequest, validateProposeCardsRequest } = require('../canvas/validators');

describe('Canvas validators', () => {
  test('applyAction valid ADD_INSTRUCTION', () => {
    const input = {
      canvasId: 'c1',
      expected_version: 0,
      action: { type: 'ADD_INSTRUCTION', idempotency_key: 'k1', payload: { text: 'Analyze' } }
    };
    const v = validateApplyActionRequest(input);
    assert.equal(v.valid, true);
  });

  test('applyAction requires card_id for ACCEPT_PROPOSAL', () => {
    const input = { canvasId: 'c1', action: { type: 'ACCEPT_PROPOSAL', idempotency_key: 'k1' } };
    const v = validateApplyActionRequest(input);
    assert.equal(v.valid, false);
  });

  test('proposeCards minimal', () => {
    const input = { canvasId: 'c1', cards: [ { type: 'analysis_task', content: { what: 'compute' } } ] };
    const v = validateProposeCardsRequest(input);
    assert.equal(v.valid, true);
  });
  test('set_target content shape', () => {
    const input = { canvasId: 'c1', cards: [ { type: 'set_target', lane: 'workout', refs: { exercise_id: 'e', set_index: 0 }, content: { target: { reps: 8, rir: 1 } } } ] };
    const v = validateProposeCardsRequest(input);
    assert.equal(v.valid, true);
  });
  test('agent_stream content shape', () => {
    const input = { canvasId: 'c1', cards: [ { type: 'agent_stream', content: { steps: [{ text: 'loading' }], status: 'running' } } ] };
    const v = validateProposeCardsRequest(input);
    assert.equal(v.valid, true);
  });
  test('clarify-questions content shape', () => {
    const input = { canvasId: 'c1', cards: [ { type: 'clarify-questions', content: { prompt: 'help?', questions: [{ id: 'q1', text: 'Which day?' }] } } ] };
    const v = validateProposeCardsRequest(input);
    assert.equal(v.valid, true);
  });
  test('list content shape', () => {
    const input = { canvasId: 'c1', cards: [ { type: 'list', content: { title: 'Options', items: [{ id: '1' }] } } ] };
    const v = validateProposeCardsRequest(input);
    assert.equal(v.valid, true);
  });
  test('inline-info content shape', () => {
    const input = { canvasId: 'c1', cards: [ { type: 'inline-info', content: { headline: 'Note', body: 'Body' } } ] };
    const v = validateProposeCardsRequest(input);
    assert.equal(v.valid, true);
  });
  test('proposal-group content shape', () => {
    const input = { canvasId: 'c1', cards: [ { type: 'proposal-group', content: { groupId: 'g1', title: 'Bundle' } } ] };
    const v = validateProposeCardsRequest(input);
    assert.equal(v.valid, true);
  });
  test('routine-overview content shape', () => {
    const input = { canvasId: 'c1', cards: [ { type: 'routine-overview', content: { title: 'PPL', split: 'PPL', days: 3 } } ] };
    const v = validateProposeCardsRequest(input);
    assert.equal(v.valid, true);
  });

  test('ACCEPT_ALL payload shape', () => {
    const input = { canvasId: 'c1', action: { type: 'ACCEPT_ALL', idempotency_key: 'k', payload: { group_id: 'g1' } } };
    const v = validateApplyActionRequest(input);
    assert.equal(v.valid, true);
  });

  test('SWAP payload shape', () => {
    const input = { canvasId: 'c1', action: { type: 'SWAP', idempotency_key: 'k3', payload: { workout_id: 'w', exercise_id: 'e1', replacement_exercise_id: 'e2' } } };
    const v = validateApplyActionRequest(input);
    assert.equal(v.valid, true);
  });

  test('ADJUST_LOAD payload shape', () => {
    const input = { canvasId: 'c1', action: { type: 'ADJUST_LOAD', idempotency_key: 'k4', payload: { workout_id: 'w', exercise_id: 'e', set_index: 0, delta_kg: 2.5 } } };
    const v = validateApplyActionRequest(input);
    assert.equal(v.valid, true);
  });

  test('REORDER_SETS payload shape', () => {
    const input = { canvasId: 'c1', action: { type: 'REORDER_SETS', idempotency_key: 'k5', payload: { workout_id: 'w', exercise_id: 'e', order: [2,0,1] } } };
    const v = validateApplyActionRequest(input);
    assert.equal(v.valid, true);
  });

  test('EDIT_SET payload shape valid', () => {
    const input = { canvasId: 'c1', action: { type: 'EDIT_SET', idempotency_key: 'k6', payload: { workout_id: 'w', exercise_id: 'e', set_index: 0, target: { reps: 8, rir: 1, weight: 60 } } } };
    const v = validateApplyActionRequest(input);
    assert.equal(v.valid, true);
  });

  test('EDIT_SET payload invalid without target', () => {
    const input = { canvasId: 'c1', action: { type: 'EDIT_SET', idempotency_key: 'k7', payload: { workout_id: 'w', exercise_id: 'e', set_index: 0 } } };
    const v = validateApplyActionRequest(input);
    assert.equal(v.valid, false);
  });

  test('proposeCards requires cards array', () => {
    const input = { canvasId: 'c1', cards: [] };
    const v = validateProposeCardsRequest(input);
    assert.equal(v.valid, false);
  });
});


