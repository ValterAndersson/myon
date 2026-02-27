/**
 * app-store-webhook.js - Handle App Store Server Notifications V2
 *
 * Webhook receives signed notifications from Apple when subscription status changes
 * (purchase, renewal, refund, expiration, etc.).
 *
 * Security:
 * - NO auth middleware — Apple calls this URL directly with a signed JWS payload
 * - JWS signature verification using Apple root certificates (production)
 * - Replay protection via notificationUUID tracking (90-day TTL)
 * - Always returns 200 (Apple retries non-200s indefinitely)
 * - Fail-secure: rejects webhooks if verifier unavailable in production
 * - Emulator: falls back to insecure decode for testing
 *
 * Apple Root Certificates:
 * Located in subscriptions/certs/:
 *   - AppleRootCA-G3.cer
 *   - AppleRootCA-G2.cer
 * Downloaded from https://www.apple.com/certificateauthority/
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
const { SignedDataVerifier, Environment } = require('@apple/app-store-server-library');
const fs = require('fs');
const path = require('path');

const db = admin.firestore();

// Apple bundle ID (used for JWS verification)
const APPLE_BUNDLE_ID = 'com.povver.Povver';

// Eagerly initialize verifier at module load — fail fast if certs are missing
let verifier = null;
let verifierError = null;
try {
  const certsDir = path.join(__dirname, 'certs');
  const rootCerts = [
    fs.readFileSync(path.join(certsDir, 'AppleRootCA-G3.cer')),
    fs.readFileSync(path.join(certsDir, 'AppleRootCA-G2.cer')),
  ];
  const environment = process.env.APP_STORE_ENVIRONMENT === 'Sandbox'
    ? Environment.SANDBOX
    : Environment.PRODUCTION;
  verifier = new SignedDataVerifier(
    rootCerts,
    true,  // enableOnlineChecks
    environment,
    APPLE_BUNDLE_ID,
    null   // appAppleId (optional)
  );
} catch (err) {
  verifierError = err;
  // Logger may not be available at module load; use console as fallback
  const logFn = typeof logger !== 'undefined' ? logger.error : console.error;
  logFn('[webhook] verifier_init_failed — webhooks will be rejected in production', {
    error: String(err?.message || err),
  });
}

/**
 * Verify and decode JWS notification from Apple.
 * Production: rejects if verifier unavailable (fail secure).
 * Emulator: falls back to insecure decode for testing.
 */
async function decodeAndVerifyNotification(signedPayload) {
  if (verifier) {
    try {
      return await verifier.verifyAndDecodeNotification(signedPayload);
    } catch (err) {
      logger.error('[webhook] jws_verification_failed', {
        error: String(err?.message || err),
      });
      return null;
    }
  }

  const isEmulator = process.env.FUNCTIONS_EMULATOR === 'true';
  if (isEmulator) {
    logger.warn('[webhook] jws_insecure_fallback — emulator only');
    return decodeJWSPayloadInsecure(signedPayload);
  }

  logger.error('[webhook] verifier unavailable in production — rejecting webhook', {
    init_error: String(verifierError?.message || 'unknown'),
  });
  return null;
}

/**
 * Verify and decode JWS transaction info from Apple.
 * Production: rejects if verifier unavailable (fail secure).
 * Emulator: falls back to insecure decode for testing.
 */
async function decodeAndVerifyTransaction(signedTransactionInfo) {
  if (verifier) {
    try {
      return await verifier.verifyAndDecodeSignedTransaction(signedTransactionInfo);
    } catch (err) {
      logger.error('[webhook] jws_transaction_verification_failed', {
        error: String(err?.message || err),
      });
      return null;
    }
  }

  const isEmulator = process.env.FUNCTIONS_EMULATOR === 'true';
  if (isEmulator) {
    logger.warn('[webhook] jws_transaction_insecure_fallback — emulator only');
    return decodeJWSPayloadInsecure(signedTransactionInfo);
  }

  logger.error('[webhook] verifier unavailable in production — rejecting transaction', {
    init_error: String(verifierError?.message || 'unknown'),
  });
  return null;
}

/**
 * Verify and decode JWS renewal info from Apple.
 * Production: rejects if verifier unavailable (fail secure).
 * Emulator: falls back to insecure decode for testing.
 */
async function decodeAndVerifyRenewalInfo(signedRenewalInfo) {
  if (verifier) {
    try {
      return await verifier.verifyAndDecodeRenewalInfo(signedRenewalInfo);
    } catch (err) {
      logger.error('[webhook] jws_renewal_verification_failed', {
        error: String(err?.message || err),
      });
      return null;
    }
  }

  const isEmulator = process.env.FUNCTIONS_EMULATOR === 'true';
  if (isEmulator) {
    logger.warn('[webhook] jws_renewal_insecure_fallback — emulator only');
    return decodeJWSPayloadInsecure(signedRenewalInfo);
  }

  logger.error('[webhook] verifier unavailable in production — rejecting renewal info', {
    init_error: String(verifierError?.message || 'unknown'),
  });
  return null;
}

// Insecure decode — emulator-only fallback
function decodeJWSPayloadInsecure(signedPayload) {
  try {
    const parts = signedPayload.split('.');
    if (parts.length !== 3) throw new Error('Invalid JWS format');
    return JSON.parse(Buffer.from(parts[1], 'base64').toString('utf-8'));
  } catch (error) {
    logger.error('[webhook] jws_decode_failed', {
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

    // Verify and decode outer notification
    const notification = await decodeAndVerifyNotification(signedPayload);
    if (!notification) {
      logger.error('[webhook] notification_verification_failed');
      return res.status(200).json({ ok: true });
    }

    const { notificationType, subtype, data, notificationUUID } = notification;

    // Replay protection: check if notification was already processed
    if (notificationUUID) {
      const processedRef = db.collection('processed_webhook_notifications').doc(notificationUUID);
      const processedSnap = await processedRef.get();
      if (processedSnap.exists) {
        logger.info('[webhook] duplicate_skipped', { notification_uuid: notificationUUID });
        return res.status(200).json({ ok: true });
      }
    }

    logger.info('subscription_event_received', {
      event: 'subscription_event_received',
      notification_type: notificationType,
      subtype: subtype || null,
      notification_uuid: notificationUUID || null,
    });

    // Verify and decode signedTransactionInfo (appAccountToken lives here, not in data)
    let transactionInfo = null;
    if (data?.signedTransactionInfo) {
      transactionInfo = await decodeAndVerifyTransaction(data.signedTransactionInfo);
    }

    // Verify and decode signedRenewalInfo for auto-renew status
    let renewalInfo = null;
    if (data?.signedRenewalInfo) {
      renewalInfo = await decodeAndVerifyRenewalInfo(data.signedRenewalInfo);
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

    // Log event for debugging/compliance (180-day TTL — configure Firestore TTL policy on expires_at)
    const eventTtlDate = new Date();
    eventTtlDate.setDate(eventTtlDate.getDate() + 180);
    await db.collection(`users/${userId}/subscription_events`).add({
      notification_type: notificationType,
      subtype: subtype || null,
      subscription_status: update.subscription_status || null,
      subscription_tier: update.subscription_tier || null,
      app_account_token: appAccountToken,
      original_transaction_id: originalTransactionId,
      environment: data?.environment || null,
      created_at: admin.firestore.FieldValue.serverTimestamp(),
      expires_at: admin.firestore.Timestamp.fromDate(eventTtlDate),
    });

    // Record processed notification for replay protection (90-day TTL)
    if (notificationUUID) {
      const ttlDate = new Date();
      ttlDate.setDate(ttlDate.getDate() + 90);
      await db.collection('processed_webhook_notifications').doc(notificationUUID).set({
        notification_type: notificationType,
        processed_at: admin.firestore.FieldValue.serverTimestamp(),
        expires_at: admin.firestore.Timestamp.fromDate(ttlDate),
      });
    }

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

exports.appStoreWebhook = onRequest({ maxInstances: 10 }, handleAppStoreWebhook);
