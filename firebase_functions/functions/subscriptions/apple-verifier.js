/**
 * apple-verifier.js - Shared Apple JWS verification utilities
 *
 * Extracts the SignedDataVerifier initialization from app-store-webhook.js
 * so it can be reused by sync-subscription-status.js for transaction verification.
 *
 * Production: verifies JWS signatures using Apple root certificates (fail secure).
 * Emulator: falls back to insecure decode for testing.
 */
'use strict';

const { SignedDataVerifier, Environment } = require('@apple/app-store-server-library');
const { logger } = require('firebase-functions');
const fs = require('fs');
const path = require('path');

const APPLE_BUNDLE_ID = 'com.povver.Povver';

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
    true, // enableOnlineChecks
    environment,
    APPLE_BUNDLE_ID,
    null  // appAppleId (optional)
  );
} catch (err) {
  verifierError = err;
  const logFn = typeof logger !== 'undefined' ? logger.error : console.error;
  logFn('[apple-verifier] init_failed', { error: String(err?.message || err) });
}

/**
 * Decode JWS payload without verification — EMULATOR ONLY.
 */
function decodeJWSPayloadInsecure(signedPayload) {
  try {
    const parts = signedPayload.split('.');
    if (parts.length !== 3) throw new Error('Invalid JWS format');
    return JSON.parse(Buffer.from(parts[1], 'base64').toString('utf-8'));
  } catch (error) {
    logger.error('[apple-verifier] jws_decode_failed', {
      error: String(error?.message || error),
    });
    return null;
  }
}

/**
 * Verify and decode a signed transaction from Apple.
 * Returns decoded transaction object or null if verification fails.
 */
async function verifySignedTransaction(signedTransactionInfo) {
  if (verifier) {
    try {
      return await verifier.verifyAndDecodeSignedTransaction(signedTransactionInfo);
    } catch (err) {
      logger.error('[apple-verifier] transaction_verification_failed', {
        error: String(err?.message || err),
      });
      return null;
    }
  }

  const isEmulator = process.env.FUNCTIONS_EMULATOR === 'true';
  if (isEmulator) {
    logger.warn('[apple-verifier] insecure_fallback — emulator only');
    return decodeJWSPayloadInsecure(signedTransactionInfo);
  }

  logger.error('[apple-verifier] verifier unavailable in production', {
    init_error: String(verifierError?.message || 'unknown'),
  });
  return null;
}

/**
 * Verify and decode a signed notification from Apple.
 * Returns decoded notification object or null if verification fails.
 */
async function verifySignedNotification(signedPayload) {
  if (verifier) {
    try {
      return await verifier.verifyAndDecodeNotification(signedPayload);
    } catch (err) {
      logger.error('[apple-verifier] notification_verification_failed', {
        error: String(err?.message || err),
      });
      return null;
    }
  }

  const isEmulator = process.env.FUNCTIONS_EMULATOR === 'true';
  if (isEmulator) {
    logger.warn('[apple-verifier] insecure_fallback — emulator only');
    return decodeJWSPayloadInsecure(signedPayload);
  }

  logger.error('[apple-verifier] verifier unavailable in production', {
    init_error: String(verifierError?.message || 'unknown'),
  });
  return null;
}

module.exports = {
  verifySignedTransaction,
  verifySignedNotification,
  decodeJWSPayloadInsecure,
  APPLE_BUNDLE_ID,
};
