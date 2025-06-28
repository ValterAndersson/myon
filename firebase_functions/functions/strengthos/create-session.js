const functions = require('firebase-functions');
const admin = require('firebase-admin');
const axios = require('axios');
const { auth, baseURL } = require('./config');

/**
 * Create a new StrengthOS session
 * This is a Firebase Callable function (onCall)
 */
const createStrengthOSSession = functions.https.onCall(async (request, context) => {
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

    try {
        // For ADK agents deployed to Agent Engine, sessions are managed automatically
        // We'll generate a session ID client-side that will be used with the Agent Engine
        const sessionId = `${authInfo.uid}_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        
        console.log(`Created session ID: ${sessionId} for user: ${authInfo.uid}`);
        
        return { sessionId };
    } catch (error) {
        console.error('Error creating session:', error.response?.data || error.message);
        throw new functions.https.HttpsError('internal', 'Failed to create session');
    }
});

module.exports = { createStrengthOSSession }; 