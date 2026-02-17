/**
 * app-store-webhook.js - Handle App Store Server Notifications V2
 *
 * Webhook receives signed notifications from Apple when subscription status changes
 * (purchase, renewal, refund, expiration, etc.).
 *
 * Security:
 * - NO auth middleware — Apple calls this URL directly with a signed JWS payload
 * - Production MUST verify JWS signature using Apple root certificates
 * - Always returns 200 (Apple retries non-200s indefinitely)
 *
 * Apple Root Certificates:
 * Download from https://www.apple.com/certificateauthority/ and place in subscriptions/certs/:
 *   - AppleRootCA-G3.cer
 *   - AppleRootCA-G2.cer
 * Until certs are in place, the handler uses insecure base64 decode (dev only).
 *
 * User Lookup Strategy:
 * 1. subscription_app_account_token (deterministic UUID v5 from Firebase UID)
 * 2. subscription_original_transaction_id (fallback)
 *
 * Called by: Apple App Store Server → webhook URL configured in App Store Connect
 */
const { onRequest } = require('firebase-functions/v2/https');
const { logger } = require('firebase-functions');
const admin = require('firebase-admin');

const db = admin.firestore();

// Apple bundle ID (used for JWS verification when certs are in place)
const APPLE_BUNDLE_ID = 'com.povver.Povver';

/**
 * Decode JWS payload (base64 middle section).
 * In production, replace with SignedDataVerifier.verifyAndDecodeNotification()
 * from @apple/app-store-server-library after placing Apple root certs.
 */
function decodeJWSPayload(signedPayload) {
  try {
    const parts = signedPayload.split('.');
    if (parts.length !== 3) throw new Error('Invalid JWS format');
    return JSON.parse(Buffer.from(parts[1], 'base64').toString('utf-8'));
  } catch (error) {
    logger.error('jws_decode_failed', {
      event: 'jws_decode_failed',
      error: String(error?.message || error),
    });
    return null;
  }
}

/**
 * Find user by appAccountToken or originalTransactionId
 */
async function findUser(appAccountToken, originalTransactionId) {
  // Strategy 1: appAccountToken (deterministic UUID v5 from Firebase UID)
  if (appAccountToken) {
    const snap = await db.collection('users')
      .where('subscription_app_account_token', '==', appAccountToken)
      .limit(1)
      .get();
    if (!snap.empty) {
      const doc = snap.docs[0];
      return { userId: doc.id, userRef: doc.ref };
    }
  }

  // Strategy 2: originalTransactionId fallback
  if (originalTransactionId) {
    const snap = await db.collection('users')
      .where('subscription_original_transaction_id', '==', originalTransactionId)
      .limit(1)
      .get();
    if (!snap.empty) {
      const doc = snap.docs[0];
      return { userId: doc.id, userRef: doc.ref };
    }
  }

  return null;
}

/**
 * Derive subscription fields from notification type and transaction info.
 * Returns partial update object for users/{uid}.
 *
 * Notification type → status mapping:
 *   SUBSCRIBED (offerType 1 = introductory offer) → trial
 *   SUBSCRIBED (else) → active
 *   DID_RENEW → active
 *   EXPIRED / GRACE_PERIOD_EXPIRED / REFUND / REVOKE → expired, tier free
 *   DID_FAIL_TO_RENEW → grace_period (billing retry) or expired
 *   DID_CHANGE_RENEWAL_STATUS → only update auto_renew_enabled flag
 */
function buildSubscriptionUpdate(notificationType, subtype, transactionInfo, renewalInfo) {
  const now = admin.firestore.FieldValue.serverTimestamp();
  const base = { subscription_updated_at: now };

  switch (notificationType) {
    case 'SUBSCRIBED': {
      // offerType 1 = introductory offer (free trial per our App Store Connect config)
      const isTrial = transactionInfo?.offerType === 1;
      return {
        ...base,
        subscription_status: isTrial ? 'trial' : 'active',
        subscription_tier: 'premium',
        subscription_original_transaction_id: transactionInfo?.originalTransactionId || null,
        subscription_product_id: transactionInfo?.productId || null,
        subscription_auto_renew_enabled: true,
        subscription_in_grace_period: false,
      };
    }

    case 'DID_RENEW':
      return {
        ...base,
        subscription_status: 'active',
        subscription_tier: 'premium',
        subscription_auto_renew_enabled: true,
        subscription_in_grace_period: false,
      };

    case 'EXPIRED':
    case 'GRACE_PERIOD_EXPIRED':
    case 'REFUND':
    case 'REVOKE':
      return {
        ...base,
        subscription_status: 'expired',
        subscription_tier: 'free',
        subscription_auto_renew_enabled: false,
        subscription_in_grace_period: false,
      };

    case 'DID_FAIL_TO_RENEW':
      // subtype GRACE_PERIOD means billing retry is active
      if (subtype === 'GRACE_PERIOD') {
        return {
          ...base,
          subscription_status: 'grace_period',
          subscription_tier: 'premium', // still premium during grace period
          subscription_in_grace_period: true,
        };
      }
      return {
        ...base,
        subscription_status: 'expired',
        subscription_tier: 'free',
        subscription_auto_renew_enabled: false,
        subscription_in_grace_period: false,
      };

    case 'DID_CHANGE_RENEWAL_STATUS': {
      // Only update auto-renew flag — don't change status/tier
      const autoRenew = renewalInfo?.autoRenewStatus === 1;
      return {
        ...base,
        subscription_auto_renew_enabled: autoRenew,
      };
    }

    default:
      logger.warn('subscription_unhandled_type', {
        event: 'subscription_unhandled_type',
        notification_type: notificationType,
      });
      return null;
  }
}

/**
 * Invalidate cached user profile so next agent call sees updated tier.
 * get-user.js caches user profiles for 24h — bust on subscription change.
 */
async function invalidateProfileCacheSafe(userId) {
  try {
    const { invalidateProfileCache } = require('../user/get-user');
    if (typeof invalidateProfileCache === 'function') {
      invalidateProfileCache(userId);
    }
  } catch {
    // Non-critical — cache will expire naturally
  }
}

/**
 * Main webhook handler
 */
async function handleAppStoreWebhook(req, res) {
  try {
    if (req.method !== 'POST') {
      return res.status(200).json({ ok: true });
    }

    const { signedPayload } = req.body || {};
    if (!signedPayload) {
      logger.error('subscription_missing_payload', {
        event: 'subscription_missing_payload',
      });
      return res.status(200).json({ ok: true });
    }

    // Decode outer notification
    // TODO: Replace with SignedDataVerifier.verifyAndDecodeNotification() when certs are in place
    const notification = decodeJWSPayload(signedPayload);
    if (!notification) {
      console.error('Failed to decode notification');
      return res.status(200).json({ ok: true });
    }

    const { notificationType, subtype, data } = notification;
    logger.info('subscription_event_received', {
      event: 'subscription_event_received',
      notification_type: notificationType,
      subtype: subtype || null,
    });

    // Decode signedTransactionInfo (appAccountToken lives here, not in data)
    let transactionInfo = null;
    if (data?.signedTransactionInfo) {
      transactionInfo = decodeJWSPayload(data.signedTransactionInfo);
    }

    // Decode signedRenewalInfo for auto-renew status
    let renewalInfo = null;
    if (data?.signedRenewalInfo) {
      renewalInfo = decodeJWSPayload(data.signedRenewalInfo);
    }

    // appAccountToken is inside the decoded transaction, not at the data level.
    // Normalize to lowercase — iOS writes lowercase, Apple may return either case.
    const appAccountToken = transactionInfo?.appAccountToken?.toLowerCase() || null;
    const originalTransactionId = transactionInfo?.originalTransactionId || null;

    // Find user
    const userLookup = await findUser(appAccountToken, originalTransactionId);
    if (!userLookup) {
      logger.warn('subscription_user_not_found', {
        event: 'subscription_user_not_found',
        app_account_token: appAccountToken ? '***' : null,
        has_transaction_id: !!originalTransactionId,
      });
      return res.status(200).json({ ok: true });
    }

    const { userId, userRef } = userLookup;

    // Build subscription update
    const update = buildSubscriptionUpdate(notificationType, subtype, transactionInfo, renewalInfo);
    if (!update) {
      return res.status(200).json({ ok: true });
    }

    // Add expiration date if available
    if (transactionInfo?.expiresDate) {
      update.subscription_expires_at = admin.firestore.Timestamp.fromMillis(transactionInfo.expiresDate);
    }

    // Add environment
    update.subscription_environment = data?.environment || 'Production';

    // Update user doc
    await userRef.update(update);
    logger.info('subscription_updated', {
      event: 'subscription_updated',
      notification_type: notificationType,
      subtype: subtype || null,
      user_id: userId,
      status: update.subscription_status || null,
      tier: update.subscription_tier || null,
    });

    // Invalidate profile cache
    await invalidateProfileCacheSafe(userId);

    // Log event for debugging/compliance
    await db.collection(`users/${userId}/subscription_events`).add({
      notification_type: notificationType,
      subtype: subtype || null,
      subscription_status: update.subscription_status || null,
      subscription_tier: update.subscription_tier || null,
      app_account_token: appAccountToken,
      original_transaction_id: originalTransactionId,
      environment: data?.environment || null,
      created_at: admin.firestore.FieldValue.serverTimestamp(),
    });

    return res.status(200).json({ ok: true });
  } catch (error) {
    logger.error('subscription_webhook_error', {
      event: 'subscription_webhook_error',
      error: String(error?.message || error),
    });
    // Always return 200 — Apple retries non-200s indefinitely
    return res.status(200).json({ ok: true });
  }
}

exports.appStoreWebhook = onRequest(handleAppStoreWebhook);
