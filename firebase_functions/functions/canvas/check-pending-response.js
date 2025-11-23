const functions = require('firebase-functions');
const admin = require('firebase-admin');
const { verifyApiKey } = require('../auth/middleware');

/**
 * Check for pending user responses to agent questions
 * Called by the agent to poll for user responses
 */
exports.checkPendingResponse = functions.https.onRequest(async (req, res) => {
  res.set('Access-Control-Allow-Origin', '*');
  res.set('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.set('Access-Control-Allow-Headers', 'Content-Type, Authorization');
  
  if (req.method === 'OPTIONS') {
    return res.status(204).send('');
  }

  // Verify API key (agent-to-function call)
  const apiKeyValid = await verifyApiKey(req, res);
  if (!apiKeyValid) return;

  const { userId, canvasId } = req.body;
  
  if (!userId || !canvasId) {
    return res.status(400).json({
      success: false,
      error: 'Missing userId or canvasId'
    });
  }

  try {
    // Query pending_responses subcollection for unprocessed responses
    const pendingRef = admin.firestore()
      .collection(`users/${userId}/canvases/${canvasId}/pending_responses`)
      .where('processed', '==', false)
      .orderBy('created_at', 'asc')
      .limit(1);
    
    const snapshot = await pendingRef.get();
    
    if (snapshot.empty) {
      return res.json({
        success: true,
        data: {
          has_response: false
        }
      });
    }

    // Get the first pending response
    const doc = snapshot.docs[0];
    const responseData = doc.data();
    
    // Mark as processed
    await doc.ref.update({
      processed: true,
      processed_at: admin.firestore.FieldValue.serverTimestamp()
    });
    
    return res.json({
      success: true,
      data: {
        has_response: true,
        response: responseData.response,
        card_id: responseData.card_id,
        response_id: doc.id
      }
    });
    
  } catch (error) {
    functions.logger.error('[checkPendingResponse] error', error);
    return res.status(500).json({
      success: false,
      error: error.message
    });
  }
});
