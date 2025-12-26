/**
 * create-routine-from-draft.js
 * 
 * Creates a routine and templates from a routine draft in the canvas.
 * This is the single write path for saving routine drafts.
 * 
 * Flow:
 * 1. Load routine_summary card and all referenced session_plan cards
 * 2. For each day: create new template or patch existing (if source_template_id exists)
 * 3. Create new routine or patch existing (if source_routine_id exists)
 * 4. Mark all draft cards as accepted
 */

const admin = require('firebase-admin');
const { convertPlanToTemplate } = require('../utils/plan-to-template-converter');

/**
 * Creates a routine from a canvas draft.
 * 
 * @param {string} userId - The user ID
 * @param {string} canvasId - The canvas ID containing the draft
 * @param {string} draftId - The draft_id from routine_summary.meta.draftId
 * @param {Object} options - Optional settings
 * @param {boolean} options.setActive - Whether to set as active routine (default: true)
 * @returns {Object} { routineId, templateIds, isUpdate }
 */
async function createRoutineFromDraftCore(userId, canvasId, draftId, options = {}) {
  const { setActive = true } = options;
  const db = admin.firestore();
  const { FieldValue } = admin.firestore;
  const now = FieldValue.serverTimestamp();

  const canvasPath = `users/${userId}/canvases/${canvasId}`;
  
  // 1. Find the routine_summary card by draftId
  const summaryQuery = db.collection(`${canvasPath}/cards`)
    .where('type', '==', 'routine_summary')
    .where('meta.draftId', '==', draftId)
    .limit(1);
  
  const summarySnap = await summaryQuery.get();
  if (summarySnap.empty) {
    throw { http: 404, code: 'NOT_FOUND', message: `Draft not found: ${draftId}` };
  }
  
  const summaryDoc = summarySnap.docs[0];
  const summary = summaryDoc.data();
  const summaryContent = summary.content || {};
  const groupId = summary.meta?.groupId;
  
  // Validate summary has workouts
  if (!Array.isArray(summaryContent.workouts) || summaryContent.workouts.length === 0) {
    throw { http: 400, code: 'INVALID_ARGUMENT', message: 'Draft has no workouts' };
  }
  
  // 2. Load all referenced session_plan cards in order from workouts[]
  const templateIds = [];
  const dayCards = [];
  
  for (const workout of summaryContent.workouts) {
    if (!workout.card_id) {
      // Placeholder day - skip or error?
      if (workout.generate) {
        throw { http: 400, code: 'INCOMPLETE_DRAFT', message: `Day ${workout.day} has not been generated yet` };
      }
      continue;
    }
    
    const cardRef = db.doc(`${canvasPath}/cards/${workout.card_id}`);
    const cardSnap = await cardRef.get();
    
    if (!cardSnap.exists) {
      throw { http: 404, code: 'NOT_FOUND', message: `Day card not found: ${workout.card_id}` };
    }
    
    const cardData = cardSnap.data();
    dayCards.push({ ref: cardRef, data: cardData, workout });
  }
  
  // 3. For each day card: create or update template
  const templatesPath = `users/${userId}/templates`;
  
  for (const { ref: dayCardRef, data: dayCard, workout } of dayCards) {
    const sourceTemplateId = dayCard.meta?.sourceTemplateId;
    
    // Convert session_plan to template format
    const templateData = convertPlanToTemplate({
      title: workout.title || dayCard.content?.title || 'Workout',
      blocks: dayCard.content?.blocks || [],
      estimated_duration: workout.estimated_duration || dayCard.content?.estimated_duration_minutes,
    });
    
    if (sourceTemplateId) {
      // Update existing template
      const templateRef = db.doc(`${templatesPath}/${sourceTemplateId}`);
      const templateSnap = await templateRef.get();
      
      if (templateSnap.exists) {
        await templateRef.update({
          name: templateData.name,
          exercises: templateData.exercises,
          analytics: null, // Will be recomputed by trigger
          updated_at: now,
        });
        templateIds.push(sourceTemplateId);
        console.log('[createRoutineFromDraft] updated template', { templateId: sourceTemplateId });
      } else {
        // Source template doesn't exist, create new
        const newTemplateRef = db.collection(templatesPath).doc();
        await newTemplateRef.set({
          id: newTemplateRef.id,
          user_id: userId,
          ...templateData,
          created_at: now,
          updated_at: now,
        });
        templateIds.push(newTemplateRef.id);
        console.log('[createRoutineFromDraft] created template (source missing)', { templateId: newTemplateRef.id });
      }
    } else {
      // Create new template
      const newTemplateRef = db.collection(templatesPath).doc();
      await newTemplateRef.set({
        id: newTemplateRef.id,
        user_id: userId,
        ...templateData,
        created_at: now,
        updated_at: now,
      });
      templateIds.push(newTemplateRef.id);
      console.log('[createRoutineFromDraft] created template', { templateId: newTemplateRef.id });
    }
  }
  
  // 4. Create or update routine
  const routinesPath = `users/${userId}/routines`;
  const sourceRoutineId = summary.meta?.sourceRoutineId;
  let routineId;
  let isUpdate = false;
  
  const routineData = {
    name: summaryContent.name || 'My Routine',
    description: summaryContent.description || null,
    frequency: summaryContent.frequency || templateIds.length,
    template_ids: templateIds,
    updated_at: now,
  };
  
  if (sourceRoutineId) {
    // Update existing routine
    const routineRef = db.doc(`${routinesPath}/${sourceRoutineId}`);
    const routineSnap = await routineRef.get();
    
    if (routineSnap.exists) {
      await routineRef.update(routineData);
      routineId = sourceRoutineId;
      isUpdate = true;
      console.log('[createRoutineFromDraft] updated routine', { routineId });
    } else {
      // Source routine doesn't exist, create new
      const newRoutineRef = db.collection(routinesPath).doc();
      await newRoutineRef.set({
        id: newRoutineRef.id,
        user_id: userId,
        ...routineData,
        created_at: now,
      });
      routineId = newRoutineRef.id;
      console.log('[createRoutineFromDraft] created routine (source missing)', { routineId });
    }
  } else {
    // Create new routine
    const newRoutineRef = db.collection(routinesPath).doc();
    await newRoutineRef.set({
      id: newRoutineRef.id,
      user_id: userId,
      ...routineData,
      created_at: now,
    });
    routineId = newRoutineRef.id;
    console.log('[createRoutineFromDraft] created routine', { routineId });
  }
  
  // 5. Set as active routine if requested
  if (setActive && routineId) {
    const userRef = db.doc(`users/${userId}`);
    await userRef.update({ activeRoutineId: routineId });
    console.log('[createRoutineFromDraft] set active routine', { routineId });
  }
  
  // 6. Mark all draft cards as accepted
  const batch = db.batch();
  
  // Mark summary as accepted
  batch.update(summaryDoc.ref, { status: 'accepted', updated_at: now });
  
  // Mark all day cards as accepted
  for (const { ref } of dayCards) {
    batch.update(ref, { status: 'accepted', updated_at: now });
  }
  
  await batch.commit();
  console.log('[createRoutineFromDraft] marked cards accepted', { 
    summaryId: summaryDoc.id, 
    dayCardCount: dayCards.length 
  });
  
  return {
    routineId,
    templateIds,
    isUpdate,
    summaryCardId: summaryDoc.id,
  };
}

module.exports = { createRoutineFromDraftCore };
