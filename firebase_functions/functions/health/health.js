const { onRequest } = require('firebase-functions/v2/https');

// Simple health check endpoint for AI agents
async function healthHandler(req, res) {
  // Add CORS headers
  res.set('Access-Control-Allow-Origin', '*');
  res.set('Access-Control-Allow-Methods', 'GET, OPTIONS');
  res.set('Access-Control-Allow-Headers', 'Content-Type');
  
  // Handle preflight requests
  if (req.method === 'OPTIONS') {
    return res.status(200).send();
  }

  const response = {
    success: true,
    status: 'healthy',
    timestamp: new Date().toISOString(),
    version: '1.0.0',
    services: {
      firebase: 'online',
      firestore: 'online'
    },
    endpoints: {
      getUserAI: '/getUserAI',
      health: '/health'
    }
  };

  return res.status(200).json(response);
}

// Export the health check function (no auth required)
exports.health = onRequest(healthHandler); 