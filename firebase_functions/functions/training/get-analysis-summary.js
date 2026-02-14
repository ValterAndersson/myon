/**
 * Analysis Summary Endpoint
 * Returns pre-computed analysis insights for coaching
 *
 * Uses onRequest (not onCall) for compatibility with HTTP clients.
 * Bearer auth (iOS + agent)
 */

const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const admin = require('firebase-admin');
const { ok, fail } = require('../utils/response');

if (!admin.apps.length) {
  admin.initializeApp();
}

const db = admin.firestore();

/**
 * Get today's date in YYYY-MM-DD format (UTC)
 */
function getTodayDateKey() {
  const now = new Date();
  return now.toISOString().split('T')[0];
}

/**
 * getAnalysisSummary
 * Returns pre-computed analysis data from multiple collections
 */
exports.getAnalysisSummary = onRequest(requireFlexibleAuth(async (req, res) => {
  try {
    // Get userId from auth (Bearer lane - trusted)
    const userId = req.auth?.uid;
    if (!userId) {
      return fail(res, 'MISSING_USER_ID', 'userId is required', null, 400);
    }

    // Parse optional params
    const sections = req.body.sections || null; // e.g. ["insights", "daily_brief"]
    const insightsLimit = req.body.limit || 5;
    const dateKey = req.body.date || getTodayDateKey();

    const validSections = ['insights', 'daily_brief', 'weekly_review'];
    const requestedSections = sections
      ? sections.filter(s => validSections.includes(s))
      : validSections;

    const now = admin.firestore.Timestamp.now();

    // Build parallel reads for only requested sections
    const reads = {};

    if (requestedSections.includes('insights')) {
      reads.insights = db.collection('users').doc(userId)
        .collection('analysis_insights')
        .where('expires_at', '>', now)
        .orderBy('expires_at', 'desc')
        .orderBy('created_at', 'desc')
        .limit(insightsLimit)
        .get();
    }

    if (requestedSections.includes('daily_brief')) {
      reads.daily_brief = db.collection('users').doc(userId)
        .collection('daily_briefs')
        .doc(dateKey)
        .get();
    }

    if (requestedSections.includes('weekly_review')) {
      reads.weekly_review = db.collection('users').doc(userId)
        .collection('weekly_reviews')
        .orderBy('created_at', 'desc')
        .limit(1)
        .get();
    }

    // Execute all reads in parallel
    const keys = Object.keys(reads);
    const snapshots = await Promise.all(keys.map(k => reads[k]));
    const results = {};
    keys.forEach((k, i) => { results[k] = snapshots[i]; });

    // Build response payload — only include requested sections
    const response = { generated_at: new Date().toISOString() };

    if (results.insights) {
      const insights = [];
      for (const doc of results.insights.docs) {
        const data = doc.data();
        insights.push({
          id: doc.id,
          type: data.type,
          workout_id: data.workout_id || null,
          workout_date: data.workout_date || null,
          summary: data.summary || '',
          highlights: data.highlights || [],
          flags: data.flags || [],
          recommendations: data.recommendations || [],
          created_at: data.created_at?.toDate?.()?.toISOString() || data.created_at,
          expires_at: data.expires_at?.toDate?.()?.toISOString() || data.expires_at,
        });
      }
      response.insights = insights;
    }

    if (results.daily_brief) {
      let dailyBrief = null;
      if (results.daily_brief.exists) {
        const data = results.daily_brief.data();
        dailyBrief = {
          date: dateKey,
          has_planned_workout: data.has_planned_workout || false,
          planned_workout: data.planned_workout || null,
          readiness: data.readiness || null,
          readiness_summary: data.readiness_summary || '',
          fatigue_flags: data.fatigue_flags || [],
          adjustments: data.adjustments || [],
          created_at: data.created_at?.toDate?.()?.toISOString() || data.created_at,
        };
      }
      response.daily_brief = dailyBrief;
    }

    if (results.weekly_review) {
      let weeklyReview = null;
      if (!results.weekly_review.empty) {
        const doc = results.weekly_review.docs[0];
        const data = doc.data();
        weeklyReview = {
          id: doc.id,
          week_ending: data.week_ending || null,
          summary: data.summary || '',
          training_load: data.training_load || {},
          muscle_balance: data.muscle_balance || [],
          exercise_trends: data.exercise_trends || [],
          progression_candidates: data.progression_candidates || [],
          stalled_exercises: data.stalled_exercises || [],
          created_at: data.created_at?.toDate?.()?.toISOString() || data.created_at,
        };
      }
      response.weekly_review = weeklyReview;
    }

    return ok(res, response);

  } catch (error) {
    console.error('Error in getAnalysisSummary:', error);
    return fail(res, 'INTERNAL_ERROR', error.message, null, 500);
  }
}));
