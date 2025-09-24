const { test, describe } = require('node:test');
const assert = require('node:assert/strict');
const { validateApplyActionRequest } = require('../canvas/validators');

describe('UNDO action schema', () => {
  test('UNDO shape valid', () => {
    const req = { canvasId: 'c', action: { type: 'UNDO', idempotency_key: 'k' } };
    assert.equal(validateApplyActionRequest(req).valid, true);
  });
});


