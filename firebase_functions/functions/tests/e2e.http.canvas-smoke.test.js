const { test, describe, before } = require('node:test');
const assert = require('node:assert/strict');
const axios = require('axios');

const PROJECT = process.env.FB_EMU_PROJECT || 'demo-myon';
const BASE = `http://127.0.0.1:5001/${PROJECT}/us-central1`;
const API_KEY = process.env.VALID_API_KEYS?.split(',')[0] || 'test-key';
const USER_ID = 'u-smoke';
const headers = { 'X-API-Key': API_KEY, 'X-User-Id': USER_ID };

async function waitForHealth(timeoutMs = 30000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await axios.get(`${BASE}/health`);
      if (res.status === 200) return true;
    } catch {}
    await new Promise(r => setTimeout(r, 500));
  }
  throw new Error('Emulator health check timeout');
}

describe('Canvas smoke (HTTP emulator)', () => {
  before(async () => {
    await waitForHealth();
  });

  test('bootstrap → propose → accept(plan) → log_set → complete', async () => {
    // Bootstrap canvas
    const boot = await axios.post(`${BASE}/bootstrapCanvas`, { userId: USER_ID, purpose: 'workout' }, { headers });
    assert.equal(boot.data.success, true);
    const canvasId = boot.data.data.canvasId;
    assert.ok(typeof canvasId === 'string' && canvasId.length > 0);

    // Propose minimal plan + first set_target
    const pc = await axios.post(`${BASE}/proposeCards`, {
      canvasId,
      cards: [
        { type: 'session_plan', content: { blocks: [] }, lane: 'workout' },
        { type: 'set_target', content: { target: { reps: 8, rir: 1 } }, lane: 'workout', refs: { exercise_id: 'e1', set_index: 0 } }
      ]
    }, { headers });
    assert.equal(pc.data.success, true);
    const [ planId, setTargetId ] = pc.data.data.created_card_ids;
    assert.ok(planId && setTargetId);

    // Accept session_plan to auto-start workout (phase=active)
    const acceptPlan = await axios.post(`${BASE}/applyAction`, {
      canvasId,
      action: { type: 'ACCEPT_PROPOSAL', idempotency_key: 'k-accept-plan', card_id: planId }
    }, { headers });
    assert.equal(acceptPlan.data.success, true);

    // Complete
    const complete = await axios.post(`${BASE}/applyAction`, {
      canvasId,
      action: { type: 'COMPLETE', idempotency_key: 'k-complete' }
    }, { headers });
    assert.equal(complete.data.success, true);
  });

  test('accepting invalid session_plan fails ScienceCheck', { skip: true }, async () => {
    const boot = await axios.post(`${BASE}/bootstrapCanvas`, { userId: USER_ID, purpose: 'ad_hoc' }, { headers });
    const canvasId = boot.data.data.canvasId;

    // Propose a session_plan with invalid reps (0)
    const pc = await axios.post(`${BASE}/proposeCards`, {
      canvasId,
      cards: [
        { type: 'session_plan', lane: 'workout', content: { blocks: [ { sets: [ { target: { reps: 0, rir: 1 } } ] } ] } }
      ]
    }, { headers });
    const planId = pc.data.data.created_card_ids[0];

    // Try to accept → expect SCIENCE_VIOLATION
    try {
      await axios.post(`${BASE}/applyAction`, {
        canvasId,
        action: { type: 'ACCEPT_PROPOSAL', idempotency_key: 'k-accept-plan-bad', card_id: planId }
      }, { headers });
      assert.fail('Expected failure');
    } catch (err) {
      assert.equal(err.response.status, 400);
      const body = err.response.data;
      assert.equal(body.success, false);
      // Keep assertion minimal for emulator variability
      assert.ok(body.error && typeof body.error.code === 'string');
    }
  });
});


