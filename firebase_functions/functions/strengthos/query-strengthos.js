const { onCall } = require('firebase-functions/v2/https');
const { logger } = require('firebase-functions');
const functions = require('firebase-functions');
const axios = require('axios');
const { GoogleAuth } = require('google-auth-library');
const { VERTEX_AI_CONFIG } = require('./config');

exports.queryStrengthOS = onCall(async (request) => {
  try {
    logger.info('[queryStrengthOS] Starting request processing', {
      userId: request.auth?.uid,
      hasData: !!request.data,
      hasSessionId: !!request.data?.sessionId,
      hasMessage: !!request.data?.message
    });
    
    // Get the ID token for authentication
    const auth = new GoogleAuth({
      scopes: ['https://www.googleapis.com/auth/cloud-platform']
    });
    const token = await auth.getAccessToken();
    
    // Get user ID with fallback for testing
    const userId = request.auth?.uid || "test-user-123";
    
    // Get session ID - if it's a new conversation, let ADK create the session
    const inputSessionId = request.data?.sessionId || null;
    
    // Build the streamQuery endpoint URL
    const streamQueryUrl = `https://${VERTEX_AI_CONFIG.location}-aiplatform.googleapis.com/v1/projects/${VERTEX_AI_CONFIG.projectId}/locations/${VERTEX_AI_CONFIG.location}/reasoningEngines/${VERTEX_AI_CONFIG.agentId}:streamQuery`;
    
    logger.info('[queryStrengthOS] Making streamQuery request', {
      url: streamQueryUrl,
      userId: userId,
      sessionId: inputSessionId,
      messageLength: request.data?.message?.length
    });
    
    // Prepare the request payload according to AdkApp pattern
    const payload = {
      class_method: "stream_query",
      input: {
        message: request.data?.message || "",
        user_id: userId
      }
    };
    
    // Only add session_id if it's provided and looks valid
    if (inputSessionId && typeof inputSessionId === 'string' && inputSessionId.length > 0) {
      payload.input.session_id = inputSessionId;
    }
    
    logger.info('[queryStrengthOS] Request payload', {
      hasSessionId: !!payload.input.session_id,
      sessionId: payload.input.session_id,
      userId: payload.input.user_id
    });
    
    // Make the request and handle as text response
    const response = await axios({
      method: 'post',
      url: streamQueryUrl,
      data: payload,
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      },
      responseType: 'text',
      transformResponse: [(data) => data],
      timeout: 30000,
      maxRedirects: 0,
      validateStatus: (status) => status >= 200 && status < 500
    });

    logger.info('[queryStrengthOS] Response received', {
      status: response.status,
      dataType: typeof response.data,
      hasData: !!response.data,
      dataLength: response.data?.length
    });
    
    // Parse the streaming response
    let fullResponse = '';
    let sessionId = inputSessionId; // Default to input session
    let extractedSessionId = null;
    
    if (response.data && typeof response.data === 'string') {
      const lines = response.data.split('\n').filter(line => line.trim());
      
      logger.info('[queryStrengthOS] Processing response lines', {
        lineCount: lines.length
      });
      
      for (const line of lines) {
        try {
          const data = JSON.parse(line);
          
          // Look for model responses with text
          if (data.content && data.content.parts && data.content.role === 'model') {
            for (const part of data.content.parts) {
              if (part.text) {
                fullResponse += part.text;
              }
            }
          }
          
          // Look for session ID in actions (this is where AdkApp puts it)
          if (data.actions && data.actions.session_id) {
            extractedSessionId = data.actions.session_id;
            logger.info('[queryStrengthOS] Found session ID in actions', { 
              sessionId: extractedSessionId 
            });
          }
          
          // Also check if it's in the top-level session_id field
          if (data.session_id) {
            extractedSessionId = data.session_id;
            logger.info('[queryStrengthOS] Found session ID at top level', { 
              sessionId: extractedSessionId 
            });
          }
        } catch (e) {
          logger.debug('[queryStrengthOS] Could not parse line', { 
            error: e.message,
            line: line.substring(0, 100) 
          });
        }
      }
      
      // Use extracted session ID if found, otherwise keep the input
      if (extractedSessionId) {
        sessionId = extractedSessionId;
      }
    }
    
    logger.info('[queryStrengthOS] Parsed response', {
      responseLength: fullResponse.length,
      finalSessionId: sessionId,
      sessionIdSource: extractedSessionId ? 'extracted' : 'input'
    });
    
    // If we got no response and no session was provided, it might be the first message
    if (!fullResponse && !inputSessionId) {
      logger.info('[queryStrengthOS] No response on first message, checking if session was created');
      // The session might have been created but no response generated
      // In this case, we should have a session ID in the response
      if (!sessionId || sessionId === inputSessionId) {
        fullResponse = "Hello! I'm your StrengthOS fitness assistant. How can I help you with your fitness journey today?";
      }
    }
    
    // If we still have no response, return a helpful message
    if (!fullResponse) {
      logger.warn('[queryStrengthOS] No response parsed from agent', {
        inputSessionId: inputSessionId,
        extractedSessionId: extractedSessionId
      });
      fullResponse = "I apologize, but I'm having trouble maintaining our conversation. Could you please try rephrasing your question?";
    }
    
    // Return the response in the format expected by iOS app
    return {
      response: fullResponse,
      sessionId: sessionId || ""
    };
    
  } catch (error) {
    logger.error('[queryStrengthOS] Error querying StrengthOS', {
      error: error.message,
      stack: error.stack,
      response: error.response?.data
    });
    
    // Throw Firebase error so iOS app can handle it properly
    throw new functions.https.HttpsError(
      'internal', 
      error.response?.data?.message || error.message || 'Failed to query StrengthOS'
        );
  }
}); 