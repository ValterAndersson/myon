const functions = require('firebase-functions');
const admin = require('firebase-admin');
const axios = require('axios');
const { verifyAuth } = require('../auth/middleware');

/**
 * Respond to agent with user's answer to clarify questions
 */
exports.respondToAgent = functions.https.onRequest(async (req, res) => {
  // CORS
  res.set('Access-Control-Allow-Origin', '*');
  res.set('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.set('Access-Control-Allow-Headers', 'Content-Type, Authorization');
  if (req.method === 'OPTIONS') {
    return res.status(204).send('');
  }

  // Auth
  const userId = await verifyAuth(req, res);
  if (!userId) return;

  const { canvasId, cardId, response } = req.body;
  
  if (!canvasId || !response) {
    return res.status(400).json({
      success: false,
      error: 'Missing canvasId or response'
    });
  }

  try {
    // Log the response to canvas events for traceability
    const eventRef = admin.firestore()
      .collection(`users/${userId}/canvases/${canvasId}/events`)
      .doc();
    
    await eventRef.set({
      type: 'user_response',
      payload: {
        card_id: cardId,
        response: response,
        timestamp: Date.now()
      },
      created_at: admin.firestore.FieldValue.serverTimestamp()
    });

    // Forward the response to the agent via SSE stream
    // This would typically be handled by maintaining the SSE connection
    // For now, we'll store it for the agent to pick up
    const responseRef = admin.firestore()
      .collection(`users/${userId}/canvases/${canvasId}/pending_responses`)
      .doc();
    
    await responseRef.set({
      card_id: cardId,
      response: response,
      processed: false,
      created_at: admin.firestore.FieldValue.serverTimestamp()
    });

    // Immediately prune the answered clarify card from the canvas
    try {
      const cardRef = admin.firestore().doc(`users/${userId}/canvases/${canvasId}/cards/${cardId}`);
      await cardRef.delete();

      // Remove from up_next queue
      const upNextRef = admin.firestore()
        .collection(`users/${userId}/canvases/${canvasId}/up_next`)
        .where('card_id', '==', cardId)
        .limit(10);
      const upSnap = await upNextRef.get();
      const batch = admin.firestore().batch();
      upSnap.forEach(doc => batch.delete(doc.ref));
      if (!upSnap.empty) {
        await batch.commit();
      }

      // Log pruning event for traceability
      const pruneEventRef = admin.firestore()
        .collection(`users/${userId}/canvases/${canvasId}/events`)
        .doc();
      await pruneEventRef.set({
        type: 'card_pruned',
        payload: { card_id: cardId, reason: 'answered_clarification' },
        created_at: admin.firestore.FieldValue.serverTimestamp()
      });
    } catch (pruneErr) {
      console.error('[respondToAgent] prune error:', pruneErr);
    }

    // Re-trigger the orchestrator to continue the conversation deterministically
    try {
      const invokeUrl = `https://us-central1-myon-53d85.cloudfunctions.net/invokeCanvasOrchestrator`;
      const correlationId = responseRef.id;
      const msg = `User answered clarification: ${JSON.stringify(response)}. Continue planning.`;
      await axios.post(invokeUrl, {
        userId,
        canvasId,
        message: msg,
        correlationId
      }, { timeout: 8000 });
    } catch (invokeErr) {
      console.error('[respondToAgent] invokeCanvasOrchestrator error:', invokeErr?.message || invokeErr);
    }

    return res.json({
      success: true,
      data: { response_id: responseRef.id }
    });

  } catch (error) {
    console.error('[respondToAgent] error:', error);
    return res.status(500).json({
      success: false,
      error: error.message
    });
  }
});
