const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');
const { getAuthenticatedUserId } = require('../utils/auth-helpers');

const db = new FirestoreHelper();

async function updatePreferencesHandler(req, res) {
  try {
    if (req.method !== 'POST') {
      return res.status(405).json({ success: false, error: 'Method Not Allowed' });
    }
    const userId = getAuthenticatedUserId(req);
    if (!userId) return res.status(400).json({ success: false, error: 'Missing userId' });

    const prefs = req.body?.preferences || {};
    const { timezone, weight_format, height_format, week_starts_on_monday, locale } = prefs;

    // Write into user_attributes/{uid} as canonical store; keep minimal mirrors on users/{uid} if present
    const updates = {};
    if (timezone !== undefined) updates.timezone = timezone;
    if (weight_format !== undefined) updates.weight_format = weight_format;
    if (height_format !== undefined) updates.height_format = height_format;
    if (week_starts_on_monday !== undefined) updates.week_starts_on_monday = !!week_starts_on_monday;
    if (locale !== undefined) updates.locale = locale;

    if (Object.keys(updates).length === 0) {
      return res.status(400).json({ success: false, error: 'No preference fields provided' });
    }

    await db.upsertDocumentInSubcollection('users', userId, 'user_attributes', userId, updates);

    // Optional mirrors for backwards compat
    const userMirror = {};
    if (timezone !== undefined) userMirror.timezone = timezone;
    if (week_starts_on_monday !== undefined) userMirror.week_starts_on_monday = !!week_starts_on_monday;
    if (Object.keys(userMirror).length > 0) {
      await db.upsertDocument('users', userId, userMirror);
    }

    return res.status(200).json({ success: true, data: { updated: Object.keys(updates) } });
  } catch (error) {
    console.error('update-preferences error:', error);
    return res.status(500).json({ success: false, error: 'Failed to update preferences' });
  }
}

exports.updateUserPreferences = onRequest(requireFlexibleAuth(updatePreferencesHandler));


