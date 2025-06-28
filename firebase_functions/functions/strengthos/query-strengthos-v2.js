const { onCall } = require('firebase-functions/v2/https');
const { logger } = require('firebase-functions');
const functions = require('firebase-functions');
const axios = require('axios');
const { GoogleAuth } = require('google-auth-library');
const { VERTEX_AI_CONFIG } = require('./config');

/**
 * Enhanced StrengthOS query function with proper ADK session management
 */
exports.queryStrengthOSv2 = onCall(async (request) => {
  try {
    logger.info('[queryStrengthOSv2] Starting request', {
      userId: request.auth?.uid,
      hasSessionId: !!request.data?.sessionId,
      action: request.data?.action || 'query'
    });
    
    // Get authentication token
    const auth = new GoogleAuth({
      scopes: ['https://www.googleapis.com/auth/cloud-platform']
    });
    const token = await auth.getAccessToken();
    
    // Get user ID
    const userId = request.auth?.uid || "test-user-123";
    
    // Handle different actions
    const action = request.data?.action || 'query';
    
    switch (action) {
      case 'createSession':
        return await createSession(userId, token);
      
      case 'listSessions':
        return await listSessions(userId, token);
      
      case 'query':
      default:
        return await queryWithSession(userId, request.data, token);
    }
    
  } catch (error) {
    logger.error('[queryStrengthOSv2] Error', {
      error: error.message,
      stack: error.stack
    });
    
    throw new functions.https.HttpsError(
      'internal',
      error.message || 'Failed to process request'
    );
  }
});

/**
 * Create a new session for the user
 */
async function createSession(userId, token) {
  logger.info('[createSession] Creating new session', { userId });
  
  const url = `https://${VERTEX_AI_CONFIG.location}-aiplatform.googleapis.com/v1/projects/${VERTEX_AI_CONFIG.projectId}/locations/${VERTEX_AI_CONFIG.location}/reasoningEngines/${VERTEX_AI_CONFIG.agentId}:query`;
  
  const response = await axios.post(url, {
    class_method: "create_session",
    input: {
      user_id: userId,
      state: {
        "user:id": userId
      }
    }
  }, {
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    }
  });
  
  const sessionId = response.data?.output?.id || 
                   response.data?.output?.session_id || 
                   response.data?.id;
  
  logger.info('[createSession] Session created', { sessionId });
  
  return {
    sessionId: sessionId,
    message: "New session created"
  };
}

/**
 * List all sessions for a user
 */
async function listSessions(userId, token) {
  logger.info('[listSessions] Listing sessions', { userId });
  
  const url = `https://${VERTEX_AI_CONFIG.location}-aiplatform.googleapis.com/v1/projects/${VERTEX_AI_CONFIG.projectId}/locations/${VERTEX_AI_CONFIG.location}/reasoningEngines/${VERTEX_AI_CONFIG.agentId}:query`;
  
  const response = await axios.post(url, {
    class_method: "list_sessions",
    input: {
      user_id: userId
    }
  }, {
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    }
  });
  
  return {
    sessions: response.data?.output || []
  };
}

/**
 * Query with session management
 */
async function queryWithSession(userId, data, token) {
  let sessionId = data?.sessionId;
  const message = data?.message || "";
  
  // If no session ID provided, create a new session first
  if (!sessionId) {
    logger.info('[queryWithSession] No session ID provided, creating new session');
    const sessionResult = await createSession(userId, token);
    sessionId = sessionResult.sessionId;
  }
  
  logger.info('[queryWithSession] Querying with session', {
    userId,
    sessionId,
    messageLength: message.length
  });
  
  // Make the stream query request
  const streamUrl = `https://${VERTEX_AI_CONFIG.location}-aiplatform.googleapis.com/v1/projects/${VERTEX_AI_CONFIG.projectId}/locations/${VERTEX_AI_CONFIG.location}/reasoningEngines/${VERTEX_AI_CONFIG.agentId}:streamQuery`;
  
  const payload = {
    class_method: "stream_query",
    input: {
      user_id: userId,
      session_id: sessionId,
      message: message
    }
  };
  
  const response = await axios({
    method: 'post',
    url: streamUrl,
    data: payload,
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    responseType: 'text',
    transformResponse: [(data) => data],
    timeout: 30000
  });
  
  // Parse the streaming response
  let fullResponse = '';
  let hasContent = false;
  
  if (response.data && typeof response.data === 'string') {
    const lines = response.data.split('\n').filter(line => line.trim());
    
    for (const line of lines) {
      try {
        const data = JSON.parse(line);
        
        // Extract text from model responses
        if (data.content && data.content.parts && data.content.role === 'model') {
          for (const part of data.content.parts) {
            if (part.text) {
              fullResponse += part.text;
              hasContent = true;
            }
          }
        }
      } catch (e) {
        // Skip non-JSON lines
      }
    }
  }
  
  // If no response content, provide a fallback
  if (!fullResponse && !hasContent) {
    logger.warn('[queryWithSession] No response content', { sessionId });
    fullResponse = "I'm here to help with your fitness journey. What would you like to know?";
  }
  
  logger.info('[queryWithSession] Query complete', {
    sessionId,
    responseLength: fullResponse.length
  });
  
  return {
    response: fullResponse,
    sessionId: sessionId
  };
} 