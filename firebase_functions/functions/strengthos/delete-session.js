const functions = require('firebase-functions');
const admin = require('firebase-admin');
const axios = require('axios');
const { auth, baseURL } = require('./config');

/**
 * Delete a StrengthOS session
 * This is a Firebase Callable function (onCall)
 */
const deleteStrengthOSSession = functions.https.onCall(async (request, context) => {
    // Handle V1/V2 auth structure
    let data, authInfo;
    if (request && request.auth && request.data) {
        authInfo = request.auth;
        data = request.data;
    } else if (context && context.auth) {
        authInfo = context.auth;
        data = request;
    } else {
        throw new functions.https.HttpsError('unauthenticated', 'User must be authenticated');
    }

    const { sessionId } = data;
    if (!sessionId) {
        throw new functions.https.HttpsError('invalid-argument', 'sessionId is required');
    }

    try {
        // Sessions are managed by Agent Engine infrastructure
        // We'll just return success for client-side cleanup
        console.log(`Session ${sessionId} marked for deletion for user: ${authInfo.uid}`);
        
        return { success: true };
    } catch (error) {
        console.error('Error deleting session:', error.response?.data || error.message);
        throw new functions.https.HttpsError('internal', 'Failed to delete session');
    }
});

module.exports = { deleteStrengthOSSession }; 