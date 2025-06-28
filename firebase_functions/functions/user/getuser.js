const { onRequest } = require('firebase-functions/v2/https');
const admin = require('firebase-admin');
const { requireAuth } = require('../auth/middleware');

// Handler function for getting user data
async function getUserHandler(req, res) {
  const userId = req.query.userId || req.body?.userId;

  if (!userId) {
    return res.status(400).json({ success: false, error: 'Missing userId' });
  }

  try {
    const doc = await admin.firestore().collection('users').doc(userId).get();
    if (!doc.exists) {
      return res.status(404).json({ success: false, error: 'User not found' });
    }

    return res.status(200).json({ 
      success: true, 
      data: doc.data(), 
      requestedBy: req.user.email // Available from auth middleware
    });
  } catch (error) {
    console.error('getUser error:', error);
    return res.status(500).json({ success: false, error: error.message });
  }
}

// Export the function wrapped with authentication
exports.getUser = onRequest(requireAuth(getUserHandler));