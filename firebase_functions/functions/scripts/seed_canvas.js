/*
  Seed canvas data for a user using proposeCards (service-only).
  Usage:
    node functions/scripts/seed_canvas.js <USER_ID> <CANVAS_ID> [BASE_URL]

  Notes:
  - Requires API key header 'X-API-Key'. Set env MYON_API_KEY (defaults to 'myon-agent-key-2024').
  - Do NOT run from the iOS app. This is a developer-only seeding tool.
*/
const axios = require('axios');

async function main() {
  const [,, userId, canvasId, baseUrlArg] = process.argv;
  if (!userId || !canvasId) {
    console.error('Usage: node functions/scripts/seed_canvas.js <USER_ID> <CANVAS_ID> [BASE_URL]');
    process.exit(1);
  }
  const base = baseUrlArg || 'https://us-central1-myon-53d85.cloudfunctions.net';
  const apiKey = process.env.MYON_API_KEY || 'myon-agent-key-2024';

  const url = `${base}/proposeCards`;
  const headers = {
    'Content-Type': 'application/json',
    'X-API-Key': apiKey,
    'X-User-Id': userId,
  };

  const payload = {
    canvasId,
    cards: [
      // Minimal session plan
      { type: 'session_plan', lane: 'workout', content: { blocks: [] } },
      // Visualization placeholder
      { type: 'visualization', lane: 'analysis', content: { chart_type: 'line', spec_format: 'vega_lite', spec: {} } },
      // Instruction/analysis task placeholder
      { type: 'analysis_task', lane: 'analysis', content: {} }
    ]
  };

  try {
    const res = await axios.post(url, payload, { headers });
    console.log('Seed success:', res.data);
  } catch (e) {
    if (e.response) {
      console.error('Seed error:', e.response.status, e.response.data);
    } else {
      console.error('Seed error:', e.message);
    }
    process.exit(2);
  }
}

main();


