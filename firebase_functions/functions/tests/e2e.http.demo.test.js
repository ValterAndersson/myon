const { test, describe, before } = require('node:test');
const assert = require('node:assert/strict');
const axios = require('axios');

const PROJECT = process.env.FB_EMU_PROJECT || 'demo-myon';
const BASE = `http://127.0.0.1:5001/${PROJECT}/us-central1`;
const API_KEY = 'myon-agent-key-2024';
const USER_ID = 'u1';
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

describe('E2E emulator (HTTP)', () => {
  before(async () => {
    await waitForHealth();
  });

  test('proposeCards → accept → resume → complete', async () => {
    const canvasId = 'c1';

    // Propose cards
    const pc = await axios.post(`${BASE}/proposeCards`, {
      canvasId,
      cards: [
        { type: 'session_plan', content: { blocks: [] }, lane: 'workout' },
        { type: 'set_target', content: { target: { reps: 8, rir: 1 } }, lane: 'workout', refs: { exercise_id: 'e', set_index: 0 } }
      ]
    }, { headers });
    assert.equal(pc.data.success, true);
    const targetCardId = pc.data.data.created_card_ids[1];

    // Accept set_target
    const accept = await axios.post(`${BASE}/applyAction`, {
      canvasId,
      action: { type: 'ACCEPT_PROPOSAL', idempotency_key: 'k-accept', card_id: targetCardId }
    }, { headers });
    assert.equal(accept.data.success, true);

    // Resume to active
    const resume = await axios.post(`${BASE}/applyAction`, {
      canvasId,
      action: { type: 'RESUME', idempotency_key: 'k-resume' }
    }, { headers });
    assert.equal(resume.data.success, true);

    // Complete session
    const complete = await axios.post(`${BASE}/applyAction`, {
      canvasId,
      action: { type: 'COMPLETE', idempotency_key: 'k-complete' }
    }, { headers });
    assert.equal(complete.data.success, true);
  });
});


