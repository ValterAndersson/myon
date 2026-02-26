const { onRequest } = require('firebase-functions/v2/https');

const { ok } = require('../utils/response');

// Simple health check endpoint for AI agents
async function healthHandler(req, res) {
  res.set('X-Content-Type-Options', 'nosniff');

  if (req.method === 'OPTIONS') {
    return res.status(204).send();
  }

  return ok(res, {
    status: 'healthy',
    timestamp: new Date().toISOString(),
    version: '1.0.0',
    services: { firebase: 'online', firestore: 'online' },
  });
}

// Export the health check function (no auth required)
exports.health = onRequest(healthHandler); 