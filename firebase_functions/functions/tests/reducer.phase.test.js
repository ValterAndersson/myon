const { test, describe } = require('node:test');
const assert = require('node:assert/strict');
const { validateApplyActionRequest } = require('../canvas/validators');

describe('Reducer phase actions (schema level)', () => {
  test('PAUSE/RESUME/COMPLETE allowed types', () => {
    const pause = { canvasId: 'c', action: { type: 'PAUSE', idempotency_key: 'k' } };
    assert.equal(validateApplyActionRequest(pause).valid, true);

    const resume = { canvasId: 'c', action: { type: 'RESUME', idempotency_key: 'k2' } };
    assert.equal(validateApplyActionRequest(resume).valid, true);

    const complete = { canvasId: 'c', action: { type: 'COMPLETE', idempotency_key: 'k3' } };
    assert.equal(validateApplyActionRequest(complete).valid, true);
  });
});


