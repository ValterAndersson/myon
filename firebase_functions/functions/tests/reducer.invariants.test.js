const { test, describe } = require('node:test');
const assert = require('node:assert/strict');
const { computeUniqueSetTargetResolution } = require('../canvas/reducer-utils');

describe('Reducer invariants', () => {
  test('single active set_target per (exercise,set)', () => {
    const accepted = { id: 'A', type: 'set_target', refs: { exercise_id: 'e1', set_index: 0 } };
    const cards = [
      accepted,
      { id: 'B', type: 'set_target', refs: { exercise_id: 'e1', set_index: 0 }, status: 'active' },
      { id: 'C', type: 'set_target', refs: { exercise_id: 'e1', set_index: 1 }, status: 'active' },
      { id: 'D', type: 'set_target', refs: { exercise_id: 'e2', set_index: 0 }, status: 'proposed' },
    ];
    const expireIds = computeUniqueSetTargetResolution(cards, accepted);
    assert.deepEqual(expireIds.sort(), ['B']);
  });
});


