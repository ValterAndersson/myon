/**
 * sync-subscription-status.js - Route iOS subscription sync through Cloud Function
 *
 * Why: Task 1's Firestore rules block client writes to subscription fields.
 * iOS SubscriptionService.syncToFirestore() previously wrote directly to Firestore.
 * This function provides a secure write path for positive entitlements only.
 *
 * Security:
 * - Bearer lane only (userId from verified Firebase token)
 * - Rejects API key auth (only iOS app should call this)
 * - Only accepts positive entitlements (tier=premium, status in active/trial/grace_period)
 * - Webhook remains authoritative for downgrades (client never writes tier=free)
 *
 * Called by: iOS SubscriptionService after StoreKit entitlement check
 */
const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');
const { logger } = require('firebase-functions');
const admin = require('firebase-admin');
const { ok, fail } = require('../utils/response');

const db = admin.firestore();

async function syncSubscriptionStatusHandler(req, res) {
  if (req.method !== 'POST') {
    return res.status(405).json({ success: false, error: 'Method Not Allowed' });
  }

  // Bearer lane only — userId from verified token
  const userId = req.auth?.uid;
  if (!userId || req.auth?.type === 'api_key') {
    return fail(res, 'UNAUTHENTICATED', 'Bearer token required', null, 401);
  }

  const { status, tier, autoRenewEnabled, inGracePeriod, productId } = req.body;

  // Only allow syncing POSITIVE entitlements from client
  // (webhook is authoritative for downgrades; client sync is a courtesy for faster UI)
  if (tier !== 'premium') {
    return fail(res, 'INVALID_ARGUMENT',
      'Client sync only allowed for positive entitlements', null, 400);
  }

  const allowedStatuses = ['active', 'trial', 'grace_period'];
  if (!allowedStatuses.includes(status)) {
    return fail(res, 'INVALID_ARGUMENT',
      'Client sync only allowed for active statuses', null, 400);
  }

  try {
    const userRef = db.collection('users').doc(userId);
    await userRef.update({
      subscription_status: status,
      subscription_tier: tier,
      subscription_auto_renew_enabled: autoRenewEnabled || false,
      subscription_in_grace_period: inGracePeriod || false,
      subscription_product_id: productId || null,
      subscription_updated_at: admin.firestore.FieldValue.serverTimestamp(),
    });

    logger.info('[syncSubscriptionStatus] synced', { userId, tier, status });
    return ok(res, { synced: true });
  } catch (error) {
    logger.error('[syncSubscriptionStatus] error', { userId, error: error.message });
    return fail(res, 'INTERNAL', 'Failed to sync subscription', null, 500);
  }
}

const fn = onRequest(
  { timeoutSeconds: 10, memory: '256MiB' },
  requireFlexibleAuth(syncSubscriptionStatusHandler)
);

module.exports = { syncSubscriptionStatus: fn };
