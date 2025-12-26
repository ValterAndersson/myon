const admin = require('firebase-admin');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');
const { ok, fail } = require('../utils/response');
const { convertPlanBlocksToTemplateExercises, validatePlanContent } = require('../utils/plan-to-template-converter');

const db = new FirestoreHelper();
const firestore = admin.firestore();

/**
 * Firebase Function: Create Template From Plan
 * 
 * Converts a session_plan card to a workout template.
 * Supports two modes:
 * - 'create': Create a new template
 * - 'update': Update an existing template's exercises
 * 
 * Features:
 * - Idempotency via key: {canvasId}:{cardId}:{mode}:{existingTemplateId}
 * - Dual auth (Firebase auth + API key)
 * - Canvas ownership verification
 * - Schema-validated conversion
 */
async function createTemplateFromPlanHandler(req, res) {
  // Dual auth: prefer req.auth.uid, fallback to body.userId for API key
  const callerUid = req.auth?.uid || req.body.userId;
  if (!callerUid) {
    return fail(res, 'UNAUTHENTICATED', 'No user identified', null, 401);
  }

  const { canvasId, cardId, name, mode, existingTemplateId } = req.body;

  // Validate required parameters
  if (!canvasId || !cardId || !name || !mode) {
    return fail(res, 'INVALID_ARGUMENT', 'Missing required parameters: canvasId, cardId, name, mode', null, 400);
  }

  if (!['create', 'update'].includes(mode)) {
    return fail(res, 'INVALID_ARGUMENT', 'mode must be "create" or "update"', null, 400);
  }

  if (mode === 'update' && !existingTemplateId) {
    return fail(res, 'INVALID_ARGUMENT', 'existingTemplateId required for update mode', null, 400);
  }

  try {
    // Idempotency check
    const idempotencyKey = `createTemplateFromPlan:${canvasId}:${cardId}:${mode}:${existingTemplateId || 'new'}`;
    const idempotencyRef = firestore.collection('users').doc(callerUid).collection('idempotency').doc(idempotencyKey);
    const idempotencyDoc = await idempotencyRef.get();
    
    if (idempotencyDoc.exists) {
      const existing = idempotencyDoc.data();
      // Return cached result
      return ok(res, { 
        templateId: existing.result, 
        mode, 
        idempotent: true,
        message: 'Operation already completed'
      });
    }

    // Verify canvas ownership
    const canvasRef = firestore.collection('users').doc(callerUid).collection('canvases').doc(canvasId);
    const canvasDoc = await canvasRef.get();
    
    if (!canvasDoc.exists) {
      return fail(res, 'NOT_FOUND', 'Canvas not found', null, 404);
    }

    const canvas = canvasDoc.data();
    // Verify ownership if meta.user_id exists
    if (canvas.meta?.user_id && canvas.meta.user_id !== callerUid) {
      return fail(res, 'PERMISSION_DENIED', 'Canvas not accessible', null, 403);
    }

    // Get the card
    const cardRef = canvasRef.collection('cards').doc(cardId);
    const cardDoc = await cardRef.get();
    
    if (!cardDoc.exists) {
      return fail(res, 'NOT_FOUND', 'Card not found', null, 404);
    }

    const card = cardDoc.data();
    if (card.type !== 'session_plan') {
      return fail(res, 'INVALID_ARGUMENT', `Card type is "${card.type}", expected "session_plan"`, null, 400);
    }

    // Validate plan content before conversion
    const validation = validatePlanContent(card.content);
    if (!validation.valid) {
      return fail(res, 'INVALID_ARGUMENT', 'Invalid plan content', { errors: validation.errors }, 400);
    }

    // Convert plan blocks to template exercises
    let exercises;
    try {
      exercises = convertPlanBlocksToTemplateExercises(card.content.blocks);
    } catch (conversionError) {
      return fail(res, 'INVALID_ARGUMENT', 'Failed to convert plan to template', { message: conversionError.message }, 400);
    }

    let templateId;

    if (mode === 'create') {
      // Create new template
      const templateData = {
        user_id: callerUid,
        name: name.trim(),
        description: card.content.coach_notes || null,
        exercises,
        source_card_id: cardId,
        source_canvas_id: canvasId,
        created_at: admin.firestore.FieldValue.serverTimestamp(),
        updated_at: admin.firestore.FieldValue.serverTimestamp()
      };

      const templateRef = await firestore.collection('users').doc(callerUid).collection('templates').add(templateData);
      templateId = templateRef.id;
      
      // Update the template with its own ID
      await templateRef.update({ id: templateId });

    } else if (mode === 'update') {
      // Verify existing template exists and belongs to user
      const existingRef = firestore.collection('users').doc(callerUid).collection('templates').doc(existingTemplateId);
      const existingDoc = await existingRef.get();
      
      if (!existingDoc.exists) {
        return fail(res, 'NOT_FOUND', 'Template not found', null, 404);
      }

      // Update template with new exercises
      await existingRef.update({
        exercises,
        updated_at: admin.firestore.FieldValue.serverTimestamp(),
        // Delete analytics so trigger will recompute
        analytics: admin.firestore.FieldValue.delete()
      });
      
      templateId = existingTemplateId;
    }

    // Record idempotency (TTL: 24 hours)
    await idempotencyRef.set({
      result: templateId,
      mode,
      created_at: admin.firestore.FieldValue.serverTimestamp(),
      expires_at: new Date(Date.now() + 24 * 60 * 60 * 1000)
    });

    return ok(res, { 
      templateId, 
      mode,
      exerciseCount: exercises.length,
      message: mode === 'create' ? 'Template created' : 'Template updated'
    });

  } catch (error) {
    console.error('create-template-from-plan function error:', error);
    return fail(res, 'INTERNAL', 'Failed to create template from plan', { message: error.message }, 500);
  }
}

exports.createTemplateFromPlan = requireFlexibleAuth(createTemplateFromPlanHandler);
