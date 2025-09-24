const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const FirestoreHelper = require('../utils/firestore-helper');

const db = new FirestoreHelper();

async function getPreferencesHandler(req, res) {
  try {
    const userId = req.query.userId || req.body?.userId || req.user?.uid || req.auth?.uid;
    if (!userId) return res.status(400).json({ success: false, error: 'Missing userId' });

    const [user, attrs] = await Promise.all([
      db.getDocument('users', userId),
      db.getDocumentFromSubcollection('users', userId, 'user_attributes', userId)
    ]);

    if (!user) return res.status(404).json({ success: false, error: 'User not found' });

    const tz = user.timezone || attrs?.timezone || null;
    const weightFormat = attrs?.weight_format || user.weightFormat || 'kilograms';
    const heightFormat = attrs?.height_format || user.heightFormat || 'centimeter';
    const weekStartsMonday = (attrs?.week_starts_on_monday ?? user.week_starts_on_monday ?? false);

    const preferences = {
      timezone: tz,
      weight_format: weightFormat,
      height_format: heightFormat,
      week_starts_on_monday: !!weekStartsMonday,
      first_day_of_week: weekStartsMonday ? 'monday' : 'sunday',
      weight_unit: weightFormat === 'pounds' ? 'lbs' : 'kg',
      height_unit: heightFormat === 'feet' ? 'ft' : 'cm',
      locale: user.locale || attrs?.locale || null
    };

    return res.status(200).json({ success: true, data: preferences });
  } catch (error) {
    console.error('get-preferences error:', error);
    return res.status(500).json({ success: false, error: 'Failed to get preferences' });
  }
}

exports.getUserPreferences = onRequest(requireFlexibleAuth(getPreferencesHandler));


