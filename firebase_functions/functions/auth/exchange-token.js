const functions = require('firebase-functions');
const { logger } = require('firebase-functions');
const admin = require('firebase-admin');
const {GoogleAuth} = require('google-auth-library');

/**
 * Get service account access token for authenticated users.
 * iOS app calls this to get a GCP access token for Vertex AI Agent Engine.
 * Security: Requires valid Firebase ID token.
 */
exports.getServiceToken = functions.https.onRequest(async (req, res) => {
  // Security headers (no CORS — iOS native only, no browser clients)
  res.set('X-Content-Type-Options', 'nosniff');
  res.set('X-Frame-Options', 'DENY');

  if (req.method === 'OPTIONS') {
    return res.status(204).send('');
  }

  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const idToken = req.headers.authorization?.split('Bearer ')[1];

  if (!idToken) {
    return res.status(401).json({ error: 'Unauthorized', message: 'No token provided' });
  }

  try {
    const decodedToken = await admin.auth().verifyIdToken(idToken);
    const userId = decodedToken.uid;

    const auth = new GoogleAuth({
      // Least-privilege: only Vertex AI access, not full cloud-platform
      scopes: ['https://www.googleapis.com/auth/aiplatform']
    });
    const client = await auth.getClient();
    const tokenResponse = await client.getAccessToken();
    const accessToken = tokenResponse.token || tokenResponse;

    logger.info('[exchange-token] token_issued', { userId });

    res.json({
      accessToken,
      expiryDate: Date.now() + (3600 * 1000),
      userId,
    });
  } catch (error) {
    logger.warn('[exchange-token] token_failed', {
      error_code: error.code || 'unknown',
      ip: req.ip,
    });

    if (error.code === 'auth/id-token-expired') {
      return res.status(401).json({ error: 'Token expired', message: 'ID token has expired' });
    } else if (error.code?.startsWith('auth/')) {
      return res.status(401).json({ error: 'Invalid token', message: 'Authentication failed' });
    }

    return res.status(500).json({ error: 'Internal error', message: 'Failed to get access token' });
  }
}); 