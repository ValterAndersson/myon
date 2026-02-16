const admin = require('firebase-admin');

/**
 * Check if a user has premium access.
 *
 * Checks in this order:
 * 1. subscription_override === 'premium' (admin override)
 * 2. subscription_tier === 'premium' (active subscription)
 *
 * @param {string} userId - The user ID to check
 * @returns {Promise<boolean>} - True if user has premium access
 */
async function isPremiumUser(userId) {
  if (!userId) {
    return false;
  }

  try {
    const db = admin.firestore();
    const userDoc = await db.collection('users').doc(userId).get();

    if (!userDoc.exists) {
      return false;
    }

    const userData = userDoc.data();

    // Check override first (admin grants)
    if (userData.subscription_override === 'premium') {
      return true;
    }

    // Check subscription tier
    if (userData.subscription_tier === 'premium') {
      return true;
    }

    return false;
  } catch (error) {
    console.error(`Error checking premium status for user ${userId}:`, error);
    return false;
  }
}

module.exports = { isPremiumUser };
