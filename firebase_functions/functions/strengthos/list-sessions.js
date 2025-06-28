const functions = require('firebase-functions');
const admin = require('firebase-admin');
const axios = require('axios');
const { auth, baseURL } = require('./config');

/**
 * List StrengthOS sessions for a user
 * This is a Firebase Callable function (onCall)
 */
const listStrengthOSSessions = functions.https.onCall(async (request, context) => {
    // Debug logging
    console.log('listStrengthOSSessions called');
    
    // In v2 functions, the structure might be different
    // Check if we're dealing with a wrapped request
    let data, authInfo;
    
    if (request && request.auth && request.data) {
        // V2 structure: request contains both auth and data
        authInfo = request.auth;
        data = request.data;
        console.log('Using V2 structure - auth from request.auth');
    } else if (context && context.auth) {
        // V1 structure: separate data and context
        authInfo = context.auth;
        data = request;
        console.log('Using V1 structure - auth from context.auth');
    } else {
        console.error('No auth found in request or context');
        // Don't stringify the entire request/context as it may contain circular references
        console.log('request keys:', Object.keys(request || {}));
        console.log('context keys:', Object.keys(context || {}));
        throw new functions.https.HttpsError('unauthenticated', 'User must be authenticated');
    }
    
    console.log('Auth found, uid:', authInfo.uid);

    try {
        const client = await auth.getClient();
        const accessToken = await client.getAccessToken();

        // First try ADK's list_sessions method
        try {
            console.log('Calling Vertex AI with list_sessions method');
            const response = await axios.post(
                `${baseURL}:query`,
                {
                    class_method: "list_sessions",
                    input: {
                        user_id: authInfo.uid
                    }
                },
                {
                    headers: {
                        'Authorization': `Bearer ${accessToken.token}`,
                        'Content-Type': 'application/json'
                    }
                }
            );

            console.log('Vertex AI response:', response.data);
            
            // ADK returns sessions array directly
            const sessions = response.data.sessions || response.data || [];
            // Extract session IDs if sessions are objects
            const sessionIds = Array.isArray(sessions) 
                ? sessions.map(s => typeof s === 'string' ? s : (s.session_id || s.id || s))
                : [];
            return { sessionIds };
        } catch (listError) {
            console.log('Error calling Vertex AI:', listError.response?.status, listError.response?.data || listError.message);
            
            // If list_sessions is not available, return empty array
            // The agent might handle sessions internally
            if (listError.response?.status === 400 || listError.response?.status === 404) {
                console.log('list_sessions method not found, returning empty array');
                return { sessionIds: [] };
            }
            
            throw listError;
        }
    } catch (error) {
        console.error('Error listing sessions:', error.response?.data || error.message);
        
        // If 404 or no sessions, return empty array
        if (error.response?.status === 404) {
            return { sessionIds: [] };
        }
        
        throw new functions.https.HttpsError('internal', 'Failed to list sessions');
    }
});

module.exports = { listStrengthOSSessions }; 