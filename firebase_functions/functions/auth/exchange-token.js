const functions = require('firebase-functions');
const admin = require('firebase-admin');
const {GoogleAuth} = require('google-auth-library');

/**
 * Get service account access token for authenticated users
 * 
 * This function provides authenticated Firebase users with a GCP access token
 * from the Cloud Function's service account. This allows the iOS app to call
 * GCP services (like Agent Engine) on behalf of the user without exposing
 * service account credentials.
 * 
 * Security: User must be authenticated with Firebase to call this function
 */
exports.getServiceToken = functions.https.onRequest(async (req, res) => {
  console.log('Get service token endpoint called');
  
  // Set CORS headers
  res.set('Access-Control-Allow-Origin', '*');
  res.set('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.set('Access-Control-Allow-Headers', 'Authorization, Content-Type');
  
  // Handle preflight OPTIONS request
  if (req.method === 'OPTIONS') {
    console.log('Handling CORS preflight');
    return res.status(204).send('');
  }
  
  // Only allow POST requests
  if (req.method !== 'POST') {
    console.log('Method not allowed:', req.method);
    return res.status(405).json({ 
      error: 'Method not allowed', 
      message: 'Only POST requests are allowed' 
    });
  }
  
  // Extract the Firebase ID token from Authorization header
  const idToken = req.headers.authorization?.split('Bearer ')[1];
  
  if (!idToken) {
    console.log('No token provided in Authorization header');
    return res.status(401).json({ 
      error: 'Unauthorized', 
      message: 'No token provided' 
    });
  }
  
  try {
    // Verify the Firebase ID token
    console.log('Verifying Firebase ID token...');
    const decodedToken = await admin.auth().verifyIdToken(idToken);
    const userId = decodedToken.uid;
    console.log('Token verified for user:', userId);
    
    // Get service account token
    const auth = new GoogleAuth({
      scopes: ['https://www.googleapis.com/auth/cloud-platform']
    });
    
    console.log('Getting service account access token...');
    const client = await auth.getClient();
    const tokenResponse = await client.getAccessToken();
    
    // Extract the token
    const accessToken = tokenResponse.token || tokenResponse;
    console.log('Access token obtained');
    
    // Return the service account's access token
    res.json({
      accessToken: accessToken,
      expiryDate: Date.now() + (3600 * 1000), // 1 hour from now
      userId: userId
    });
    
  } catch (error) {
    console.error('Error:', error.message);
    
    if (error.code === 'auth/id-token-expired') {
      return res.status(401).json({ 
        error: 'Token expired', 
        message: 'ID token has expired' 
      });
    } else if (error.code?.startsWith('auth/')) {
      return res.status(401).json({ 
        error: 'Invalid token', 
        message: 'Authentication failed' 
      });
    }
    
    // Internal server error for other issues
    return res.status(500).json({ 
      error: 'Internal error', 
      message: 'Failed to get access token' 
    });
  }
}); 