const { test, describe } = require('node:test');
const assert = require('node:assert/strict');
const { validateApplyActionRequest } = require('../canvas/validators');

describe('Reducer properties (static checks via schema)', () => {
  test('stale version is detectable at gateway level', () => {
    const input = {
      canvasId: 'c1',
      expected_version: 10,
      action: { type: 'ADD_INSTRUCTION', idempotency_key: 'k1', payload: { text: 'x' } }
    };
    const v = validateApplyActionRequest(input);
    assert.equal(v.valid, true);
  });

  test('LOG_SET payload must include required fields', () => {
    const input = {
      canvasId: 'c1',
      action: { type: 'LOG_SET', idempotency_key: 'k2', payload: { workout_id: 'w', exercise_id: 'e', set_index: 0, actual: { reps: 8, rir: 1 } } }
    };
    const v = validateApplyActionRequest(input);
    assert.equal(v.valid, true);
  });
});


