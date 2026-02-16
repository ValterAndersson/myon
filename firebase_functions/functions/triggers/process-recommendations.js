/**
 * =============================================================================
 * process-recommendations.js - Recommendation Processing Triggers
 * =============================================================================
 *
 * PURPOSE:
 * Process training analysis insights and weekly reviews into actionable
 * template/routine changes, with optional auto-pilot execution.
 *
 * TRIGGERS:
 * 1. onAnalysisInsightCreated - Firestore trigger on users/{userId}/analysis_insights/{insightId}
 * 2. onWeeklyReviewCreated - Firestore trigger on users/{userId}/weekly_reviews/{reviewId}
 * 3. expireStaleRecommendations - Scheduled function (daily) to expire old pending recommendations
 *
 * DATA FLOW:
 * Analysis Insight/Weekly Review → Filter actionable recommendations →
 * Check premium → Check active routine → Match exercises → Compute changes →
 * Create agent_recommendations doc → If auto-pilot, apply changes
 *
 * FIRESTORE WRITES:
 * - Creates: users/{uid}/agent_recommendations/{id}
 * - Updates: users/{uid}/templates/{id} (if auto-pilot enabled)
 *
 * =============================================================================
 */

const { onDocumentCreated } = require('firebase-functions/v2/firestore');
const { onSchedule } = require('firebase-functions/v2/scheduler');
const admin = require('firebase-admin');
const logger = require('firebase-functions/logger');
const { applyChangesToTarget } = require('../agents/apply-progression');

// ---------------------------------------------------------------------------
// Triggers
// ---------------------------------------------------------------------------

/**
 * Firestore trigger on analysis insights.
 * Fires when post-workout analysis creates a new insight document.
 */
const onAnalysisInsightCreated = onDocumentCreated(
  {
    document: 'users/{userId}/analysis_insights/{insightId}',
    region: 'us-central1',
  },
  async (event) => {
    const userId = event.params.userId;
    const insightId = event.params.insightId;
    const insight = event.data.data();

    logger.info('[onAnalysisInsightCreated] Processing insight', { userId, insightId });

    try {
      // Extract actionable recommendations from insight
      const recommendations = insight.recommendations || [];
      const actionable = recommendations
        .filter(rec => rec.confidence >= 0.7 && ['progression', 'deload', 'volume_adjust'].includes(rec.type))
        .map(rec => ({
          type: rec.type,
          target: rec.target,
          suggestedWeight: rec.suggested_weight ?? null,
          rationale: rec.action || 'Auto-generated from post-workout analysis',
          confidence: rec.confidence,
        }));

      if (actionable.length === 0) {
        logger.info('[onAnalysisInsightCreated] No actionable recommendations', { userId, insightId });
        return;
      }

      await processActionableRecommendations(userId, 'post_workout', {
        insight_id: insightId,
        workout_id: insight.workout_id,
        workout_date: insight.workout_date,
      }, actionable);
    } catch (error) {
      logger.error('[onAnalysisInsightCreated] Error processing insight', {
        userId,
        insightId,
        error: error.message,
        stack: error.stack,
      });
      // Don't throw - trigger should not retry on non-transient errors
    }
  }
);

/**
 * Firestore trigger on weekly reviews.
 * Fires when weekly review analysis creates a new review document.
 */
const onWeeklyReviewCreated = onDocumentCreated(
  {
    document: 'users/{userId}/weekly_reviews/{reviewId}',
    region: 'us-central1',
  },
  async (event) => {
    const userId = event.params.userId;
    const reviewId = event.params.reviewId;
    const review = event.data.data();

    logger.info('[onWeeklyReviewCreated] Processing review', { userId, reviewId });

    try {
      // Extract actionable items: progressions + deloads (skip swaps)
      const progressionCandidates = review.progression_candidates || [];
      const stalledExercises = (review.stalled_exercises || [])
        .filter(ex => ex.suggested_action === 'deload');

      const actionable = [
        ...progressionCandidates.map(pc => ({
          type: 'progression',
          target: pc.exercise_name,
          suggestedWeight: pc.suggested_weight ?? null,
          rationale: pc.rationale || 'Auto-generated from weekly review',
          confidence: pc.confidence || 0.8,
        })),
        ...stalledExercises.map(se => ({
          type: 'deload',
          target: se.exercise_name,
          suggestedWeight: null,
          rationale: se.rationale || 'Stall detected — deload recommended',
          confidence: 0.7,
        })),
      ];

      if (actionable.length === 0) {
        logger.info('[onWeeklyReviewCreated] No actionable recommendations', { userId, reviewId });
        return;
      }

      await processActionableRecommendations(userId, 'weekly_review', {
        review_id: reviewId,
        week_ending: review.week_ending,
      }, actionable);
    } catch (error) {
      logger.error('[onWeeklyReviewCreated] Error processing review', {
        userId,
        reviewId,
        error: error.message,
        stack: error.stack,
      });
    }
  }
);

/**
 * Scheduled function to expire stale pending recommendations.
 * Runs daily to mark recommendations older than 7 days as expired.
 */
const expireStaleRecommendations = onSchedule(
  {
    schedule: 'every day 00:00',
    timeZone: 'UTC',
    region: 'us-central1',
  },
  async () => {
    logger.info('[expireStaleRecommendations] Starting sweep');

    try {
      const db = admin.firestore();
      const sevenDaysAgo = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000);

      const querySnapshot = await db.collectionGroup('agent_recommendations')
        .where('state', '==', 'pending_review')
        .where('created_at', '<', admin.firestore.Timestamp.fromDate(sevenDaysAgo))
        .get();

      if (querySnapshot.empty) {
        logger.info('[expireStaleRecommendations] No stale recommendations found');
        return;
      }

      // Firestore batch limit is 500 — chunk if needed
      const docs = querySnapshot.docs;
      const BATCH_LIMIT = 500;
      let expiredCount = 0;

      for (let i = 0; i < docs.length; i += BATCH_LIMIT) {
        const chunk = docs.slice(i, i + BATCH_LIMIT);
        const batch = db.batch();

        for (const doc of chunk) {
          batch.update(doc.ref, {
            state: 'expired',
            state_history: admin.firestore.FieldValue.arrayUnion({
              from: 'pending_review',
              to: 'expired',
              at: new Date().toISOString(),
              by: 'system',
              note: 'TTL expired (7 days)',
            }),
          });
          expiredCount++;
        }

        await batch.commit();
      }

      logger.info('[expireStaleRecommendations] Sweep complete', { expiredCount });
    } catch (error) {
      logger.error('[expireStaleRecommendations] Error during sweep', {
        error: error.message,
        stack: error.stack,
      });
    }
  }
);

// ---------------------------------------------------------------------------
// Shared processing logic
// ---------------------------------------------------------------------------

/**
 * Core recommendation processing shared by both triggers.
 * Reads user prefs, resolves exercises against active routine templates,
 * deduplicates against existing pending recs, and creates new recommendations.
 *
 * @param {string} userId
 * @param {string} triggerType - 'post_workout' | 'weekly_review'
 * @param {Object} triggerContext - Trigger-specific context (insight_id, review_id, etc.)
 * @param {Array} actionable - Normalized actionable items: [{ type, target, suggestedWeight, rationale, confidence }]
 */
async function processActionableRecommendations(userId, triggerType, triggerContext, actionable) {
  const db = admin.firestore();

  // 1. Read user doc once — premium gate + auto_pilot + activeRoutineId
  const userDoc = await db.collection('users').doc(userId).get();
  if (!userDoc.exists) {
    logger.warn(`[processRecommendations] User not found`, { userId });
    return;
  }

  const userData = userDoc.data();

  // Premium gate: check override first, then tier (mirrors isPremiumUser logic)
  const isPremium = userData.subscription_override === 'premium' || userData.subscription_tier === 'premium';
  if (!isPremium) {
    logger.info(`[processRecommendations] Skipping — not premium`, { userId });
    return;
  }

  const autoPilotEnabled = userData.auto_pilot_enabled || false;
  const activeRoutineId = userData.activeRoutineId;

  if (!activeRoutineId) {
    logger.info(`[processRecommendations] No active routine`, { userId });
    return;
  }

  // 2. Get routine and templates
  const routineDoc = await db.doc(`users/${userId}/routines/${activeRoutineId}`).get();
  if (!routineDoc.exists) {
    logger.warn(`[processRecommendations] Active routine not found`, { userId, activeRoutineId });
    return;
  }

  const templateIds = routineDoc.data().template_ids || [];
  if (templateIds.length === 0) {
    logger.info(`[processRecommendations] Routine has no templates`, { userId, activeRoutineId });
    return;
  }

  // 3. Load all templates in parallel and build exercise index
  const templateSnaps = await Promise.all(
    templateIds.map(tid => db.doc(`users/${userId}/templates/${tid}`).get())
  );

  // { exercise_name_lower: { templateId, exerciseIndex, sets } }
  const exerciseIndex = {};
  for (const snap of templateSnaps) {
    if (!snap.exists) continue;
    const exercises = snap.data().exercises || [];
    exercises.forEach((ex, idx) => {
      const key = (ex.name || '').trim().toLowerCase();
      if (key) {
        exerciseIndex[key] = {
          templateId: snap.id,
          exerciseIndex: idx,
          sets: ex.sets || [],
        };
      }
    });
  }

  // 4. Get existing pending recommendations for deduplication
  const pendingSnap = await db.collection(`users/${userId}/agent_recommendations`)
    .where('state', '==', 'pending_review')
    .get();

  const pendingExercises = new Set();
  pendingSnap.forEach(doc => {
    const rec = doc.data();
    const changes = rec.recommendation?.changes || [];
    for (const change of changes) {
      const match = change.path.match(/exercises\[(\d+)\]/);
      if (match && rec.target?.template_id) {
        pendingExercises.add(`${rec.target.template_id}:${match[1]}`);
      }
    }
  });

  // 5. Process each actionable recommendation
  const { FieldValue } = admin.firestore;
  let processedCount = 0;

  for (const rec of actionable) {
    const exerciseName = rec.target || '';
    const key = exerciseName.trim().toLowerCase();

    const exerciseData = exerciseIndex[key];
    if (!exerciseData) {
      logger.info(`[processRecommendations] Exercise not found in templates`, { exerciseName, userId });
      continue;
    }

    // Deduplication check
    const pendingKey = `${exerciseData.templateId}:${exerciseData.exerciseIndex}`;
    if (pendingExercises.has(pendingKey)) {
      logger.info(`[processRecommendations] Skipping duplicate`, { exerciseName, templateId: exerciseData.templateId });
      continue;
    }

    // Compute changes
    const changes = computeProgressionChanges(exerciseData, rec.type, rec.suggestedWeight);
    if (changes.length === 0) {
      logger.info(`[processRecommendations] No valid changes`, { exerciseName });
      continue;
    }

    // Create recommendation document
    const recRef = db.collection(`users/${userId}/agent_recommendations`).doc();
    const state = autoPilotEnabled ? 'applied' : 'pending_review';
    const now = FieldValue.serverTimestamp();

    const recommendationData = {
      id: recRef.id,
      created_at: now,
      trigger: triggerType,
      trigger_context: triggerContext,
      scope: 'template',
      target: { template_id: exerciseData.templateId },
      recommendation: {
        type: rec.type,
        changes,
        summary: `${rec.type} for ${exerciseName}`,
        rationale: rec.rationale,
        confidence: rec.confidence,
      },
      state,
      state_history: [{
        from: null,
        to: state,
        at: new Date().toISOString(),
        by: 'agent',
        note: autoPilotEnabled ? 'Auto-applied' : 'Queued for review',
      }],
      applied_by: autoPilotEnabled ? 'agent' : null,
    };

    // If auto-pilot, apply changes to template
    if (autoPilotEnabled) {
      try {
        const result = await applyChangesToTarget(db, userId, 'template', exerciseData.templateId, changes);
        recommendationData.applied_at = now;
        recommendationData.result = result;
        logger.info(`[processRecommendations] Auto-applied`, {
          templateId: exerciseData.templateId,
          exerciseName,
          changeCount: changes.length,
        });
      } catch (applyError) {
        logger.error(`[processRecommendations] Apply failed`, {
          error: applyError.message,
          templateId: exerciseData.templateId,
          exerciseName,
        });
        recommendationData.state = 'failed';
        recommendationData.state_history.push({
          from: 'applied',
          to: 'failed',
          at: new Date().toISOString(),
          by: 'system',
          note: `Apply failed: ${applyError.message}`,
        });
      }
    }

    await recRef.set(recommendationData);
    // Mark as pending so later iterations in this batch don't duplicate
    pendingExercises.add(pendingKey);
    processedCount++;

    logger.info(`[processRecommendations] Created`, {
      recommendationId: recRef.id,
      exerciseName,
      state: recommendationData.state,
    });
  }

  logger.info(`[processRecommendations] Complete`, {
    userId,
    trigger: triggerType,
    actionableCount: actionable.length,
    processedCount,
  });
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Compute progression changes for an exercise.
 *
 * Rules (deterministic, not LLM):
 * - Progression (>40kg): +2.5% rounded to nearest 2.5kg, capped at +5kg
 * - Progression (≤40kg): +5% rounded to nearest 1.25kg, capped at +5kg
 * - Deload: -10% weight, same rounding
 * - Safety: min 0kg
 *
 * @param {Object} exerciseData - { templateId, exerciseIndex, sets }
 * @param {string} recommendationType - 'progression' | 'deload' | 'volume_adjust'
 * @param {number|null} suggestedWeight - Explicit weight suggestion (optional)
 * @returns {Array} Array of change objects { path, from, to, rationale }
 */
function computeProgressionChanges(exerciseData, recommendationType, suggestedWeight) {
  const changes = [];
  const sets = exerciseData.sets || [];

  for (let setIdx = 0; setIdx < sets.length; setIdx++) {
    const set = sets[setIdx];
    const currentWeight = set.weight_kg || set.weight || 0;

    let newWeight;
    if (suggestedWeight !== null && suggestedWeight !== undefined) {
      newWeight = suggestedWeight;
    } else if (recommendationType === 'deload') {
      newWeight = roundToNearest(currentWeight * 0.9, currentWeight > 40 ? 2.5 : 1.25);
    } else {
      const increment = currentWeight > 40 ? 0.025 : 0.05;
      newWeight = roundToNearest(currentWeight * (1 + increment), currentWeight > 40 ? 2.5 : 1.25);
      newWeight = Math.min(newWeight, currentWeight + 5);
    }

    if (newWeight !== currentWeight && newWeight > 0) {
      changes.push({
        path: `exercises[${exerciseData.exerciseIndex}].sets[${setIdx}].weight_kg`,
        from: currentWeight,
        to: newWeight,
        rationale: `${recommendationType}: ${currentWeight}kg → ${newWeight}kg`,
      });
    }
  }

  return changes;
}

/**
 * Round value to nearest step.
 */
function roundToNearest(value, step) {
  return Math.round(value / step) * step;
}

module.exports = {
  onAnalysisInsightCreated,
  onWeeklyReviewCreated,
  expireStaleRecommendations,
};
