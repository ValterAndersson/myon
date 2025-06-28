const admin = require('firebase-admin');
const { getAuth } = require('firebase-admin/auth');
const functions = require('firebase-functions');

/**
 * Middleware to verify Firebase ID token
 * @param {Object} req - Request object
 * @param {Object} res - Response object
 * @returns {Object|null} - Decoded token or null if authentication fails
 */
async function verifyAuth(req, res) {
  const authHeader = req.get('Authorization') || req.get('authorization');
  const idToken = authHeader?.startsWith('Bearer ') ? authHeader.slice(7) : null;

  if (!idToken) {
    res.status(401).json({ 
      success: false, 
      error: 'Missing or invalid Authorization header. Please provide Bearer token.' 
    });
    return null;
  }

  try {
    const decoded = await getAuth().verifyIdToken(idToken);
    return decoded;
  } catch (error) {
    console.error('Auth verification error:', error);
    res.status(403).json({ 
      success: false, 
      error: 'Invalid or expired token' 
    });
    return null;
  }
}

/**
 * Middleware to verify API key for 3rd party access (AI agents)
 * @param {Object} req - Request object
 * @param {Object} res - Response object
 * @returns {Object|null} - API key info or null if authentication fails
 */
async function verifyApiKey(req, res) {
  const apiKey = req.get('X-API-Key') || req.query.apiKey;
  
  if (!apiKey) {
    res.status(401).json({ 
      success: false, 
      error: 'Missing API key. Please provide X-API-Key header or apiKey query parameter.' 
    });
    return null;
  }

  try {
    // For Firebase Functions v2, use environment variables or fallback to hardcoded for testing
    const envApiKeys = process.env.VALID_API_KEYS;
    const hardcodedKeys = 'myon-agent-key-2024,backup-key-2024,dev-key-2024';
    const apiKeysString = envApiKeys || hardcodedKeys;
    const validApiKeys = apiKeysString ? apiKeysString.split(',').map(key => key.trim()) : [];
    
    // Debug logging
    console.log('🔍 API Key Debug Info:', {
      receivedApiKey: apiKey,
      envApiKeys: envApiKeys,
      apiKeysString: apiKeysString,
      validApiKeys: validApiKeys,
      hasValidKeys: validApiKeys.length > 0,
      keyMatch: validApiKeys.includes(apiKey)
    });
    
    if (validApiKeys.length === 0) {
      console.error('⚠️ No valid API keys configured!');
      res.status(500).json({ 
        success: false, 
        error: 'Server configuration error: No valid API keys configured' 
      });
      return null;
    }
    
    if (!validApiKeys.includes(apiKey)) {
      console.log('❌ API key not found in valid keys list');
      res.status(403).json({ 
        success: false, 
        error: 'Invalid API key' 
      });
      return null;
    }

    console.log('✅ API key validated successfully');
    return { 
      type: 'api_key', 
      key: apiKey,
      source: 'third_party_agent'
    };
  } catch (error) {
    console.error('🚨 API key verification error:', error);
    res.status(500).json({ 
      success: false, 
      error: 'API key verification failed: ' + error.message 
    });
    return null;
  }
}

/**
 * Flexible auth middleware that supports both Firebase Auth and API keys
 * @param {Object} req - Request object
 * @param {Object} res - Response object
 * @returns {Object|null} - Auth info or null if authentication fails
 */
async function verifyFlexibleAuth(req, res) {
  // Try Firebase Auth first
  const authHeader = req.get('Authorization') || req.get('authorization');
  if (authHeader?.startsWith('Bearer ')) {
    return await verifyAuth(req, res);
  }
  
  // Try API key authentication
  const apiKey = req.get('X-API-Key') || req.query.apiKey;
  if (apiKey) {
    return await verifyApiKey(req, res);
  }
  
  res.status(401).json({ 
    success: false, 
    error: 'Authentication required. Provide either Bearer token or X-API-Key header.' 
  });
  return null;
}

/**
 * Middleware wrapper for functions that require authentication
 * @param {Function} handler - The function handler to wrap
 * @returns {Function} - Wrapped function with auth verification
 */
function requireAuth(handler) {
  return async (req, res) => {
    const decoded = await verifyAuth(req, res);
    if (!decoded) {
      return; // Response already sent by verifyAuth
    }
    
    // Add the decoded token to request for use in handler
    req.user = decoded;
    return handler(req, res);
  };
}

/**
 * Middleware wrapper for functions that support flexible authentication
 * @param {Function} handler - The function handler to wrap
 * @returns {Function} - Wrapped function with flexible auth verification
 */
function requireFlexibleAuth(handler) {
  return async (req, res) => {
    // Add CORS headers for 3rd party access
    res.set('Access-Control-Allow-Origin', '*');
    res.set('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    res.set('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-API-Key');
    
    // Handle preflight requests
    if (req.method === 'OPTIONS') {
      return res.status(200).send();
    }
    
    const authInfo = await verifyFlexibleAuth(req, res);
    if (!authInfo) {
      return; // Response already sent by verifyFlexibleAuth
    }
    
    // Add auth info to request for use in handler
    req.auth = authInfo;
    return handler(req, res);
  };
}

const withApiKey = (handler) => {
  return async (req, res) => {
    // Set CORS headers
    res.set('Access-Control-Allow-Origin', '*');
    res.set('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    res.set('Access-Control-Allow-Headers', 'Content-Type, X-API-Key');
    
    // Handle preflight
    if (req.method === 'OPTIONS') {
      return res.status(204).send('');
    }
    
    // Check API key
    const apiKey = req.headers['x-api-key'];
    if (!apiKey || apiKey !== 'myon-agent-key-2024') {
      return res.status(401).json({
        success: false,
        error: 'Invalid or missing API key'
      });
    }
    
    // Call the actual handler
    return handler(req, res);
  };
};

module.exports = {
  verifyAuth,
  verifyApiKey,
  verifyFlexibleAuth,
  requireAuth,
  requireFlexibleAuth,
  withApiKey
}; 