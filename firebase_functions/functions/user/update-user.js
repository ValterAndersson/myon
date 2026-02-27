const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');
const { invalidateProfileCache } = require('./get-user');

const db = new FirestoreHelper();

/**
 * Firebase Function: Update User
 * 
 * Description: Updates user preferences, goals, and settings.
 * AI can use this to update user preferences based on workout analysis.
 */
async function updateUserHandler(req, res) {
  const { userId, userData } = req.body;
  
  if (!userId) {
    return res.status(400).json({
      success: false,
      error: 'Missing userId',
      usage: 'Provide userId in request body'
    });
  }
  
  if (!userData || Object.keys(userData).length === 0) {
    return res.status(400).json({
      success: false,
      error: 'Missing userData',
      usage: 'Provide userData object with fields to update'
    });
  }

  try {
    // Check if user exists
    const existingUser = await db.getDocument('users', userId);
    if (!existingUser) {
      return res.status(404).json({
        success: false,
        error: 'User not found',
        userId: userId
      });
    }

    // Validate and sanitize user data
    const allowedFields = [
      'displayName', 'preferences', 'goals', 'fitnessLevel', 
      'equipment', 'activeRoutineId', 'notifications', 'aiSettings'
    ];
    
    const sanitizedData = {};
    Object.keys(userData).forEach(key => {
      if (allowedFields.includes(key)) {
        sanitizedData[key] = userData[key];
      }
    });

    if (Object.keys(sanitizedData).length === 0) {
      return res.status(400).json({
        success: false,
        error: 'No valid fields to update',
        allowedFields: allowedFields
      });
    }

    // Update user
    await db.updateDocument('users', userId, sanitizedData);
    
    // Invalidate the profile cache so next read gets fresh data
    await invalidateProfileCache(userId);
    
    // Get updated user data
    const updatedUser = await db.getDocument('users', userId);

    return res.status(200).json({
      success: true,
      data: updatedUser,
      updatedFields: Object.keys(sanitizedData),
      metadata: {
        function: 'update-user',
        userId: userId,
        updatedAt: new Date().toISOString(),
        authType: req.auth?.type || 'firebase',
        source: req.auth?.source || 'user_app'
      }
    });

  } catch (error) {
    console.error('update-user function error:', error);
    return res.status(500).json({
      success: false,
      error: 'Failed to update user',
    });
  }
}

// Export Firebase Function
exports.updateUser = onRequest(requireFlexibleAuth(updateUserHandler));
