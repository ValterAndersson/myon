# Security Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix all CRITICAL and HIGH security vulnerabilities identified in the pre-launch security audit, without regressing existing functionality.

**Architecture:** Layered defense — Firestore rules (data layer), auth helper (function layer), webhook verification (payment layer), API key rotation (infra layer). Each task is self-contained and independently deployable.

**Tech Stack:** Firebase Functions (Node.js 22), Firestore Security Rules, `@apple/app-store-server-library`, Zod validation

**Testing strategy:** Each task includes a manual smoke test against the emulator. Run `npm test` after every task to catch regressions. Never deploy multiple tasks at once — deploy after each task passes.

**Branch:** `fix/security-hardening` (from current `feat/weight-unit-preference` or `main`)

---

## Task 1: Firestore Security Rules — Lock Down Root Collections

**Why:** Currently, anyone with the Firebase config (public in the iOS binary) can directly read/write ALL root-level collections AND subscription fields on user documents. This is the single most critical vulnerability — it enables instant free premium, exercise catalog corruption, and job queue manipulation.

**Regression risk:** LOW — Rules only restrict client SDK access. All Cloud Functions use Admin SDK (which bypasses rules). The iOS app reads user subcollections via client SDK (owner-scoped, already permitted). The iOS `SubscriptionService.syncToFirestore()` writes subscription fields directly — this WILL break and must be handled in Task 7.

**Files:**
- Modify: `firebase_functions/firestore.rules`

**Step 1: Update Firestore rules**

Replace `firebase_functions/firestore.rules` with:

```javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {

    // ================================================================
    // USER-SCOPED COLLECTIONS
    // ================================================================
    match /users/{uid} {

      // Subscription fields that ONLY Admin SDK / webhook may write.
      // Used by both create and update rules below.
      function isSubscriptionField(key) {
        return key in [
          'subscription_tier',
          'subscription_override',
          'subscription_status',
          'subscription_product_id',
          'subscription_original_transaction_id',
          'subscription_app_account_token',
          'subscription_auto_renew_enabled',
          'subscription_in_grace_period',
          'subscription_updated_at',
          'subscription_environment',
          'subscription_expires_at'
        ];
      }

      // User profile document — owner can read.
      allow read: if request.auth != null && request.auth.uid == uid;

      // Create: allow owner, but block subscription fields in initial data.
      // resource.data is null on create, so we check keys() not diff().
      allow create: if request.auth != null && request.auth.uid == uid
        && !request.resource.data.keys().hasAny([
              'subscription_tier',
              'subscription_override',
              'subscription_status',
              'subscription_product_id',
              'subscription_original_transaction_id',
              'subscription_app_account_token',
              'subscription_auto_renew_enabled',
              'subscription_in_grace_period',
              'subscription_updated_at',
              'subscription_environment',
              'subscription_expires_at'
            ]);

      // Update: allow owner, but block changes to subscription fields.
      // diff().affectedKeys() only contains keys that actually changed.
      allow update: if request.auth != null && request.auth.uid == uid
        && !request.resource.data.diff(resource.data).affectedKeys()
            .hasAny([
              'subscription_tier',
              'subscription_override',
              'subscription_status',
              'subscription_product_id',
              'subscription_original_transaction_id',
              'subscription_app_account_token',
              'subscription_auto_renew_enabled',
              'subscription_in_grace_period',
              'subscription_updated_at',
              'subscription_environment',
              'subscription_expires_at'
            ]);

      // Delete: only via Admin SDK (account deletion flow)
      allow delete: if false;

      // Exercise usage stats: owner read, Admin SDK writes only
      match /exercise_usage_stats/{statId} {
        allow read: if request.auth != null && request.auth.uid == uid;
        allow write: if false;
      }

      // Canvas: read-only for owner, Functions-only writes
      match /canvases/{canvasId} {
        allow read: if request.auth != null && request.auth.uid == uid;
        allow write: if false;
      }
      match /canvases/{canvasId}/{document=**} {
        allow read: if request.auth != null && request.auth.uid == uid;
        allow write: if false;
      }

      // Conversations: owner read; root doc + artifacts are function-only
      match /conversations/{conversationId} {
        allow read: if request.auth != null && request.auth.uid == uid;
        allow write: if false;

        match /messages/{messageId} {
          allow read: if request.auth != null && request.auth.uid == uid;
          allow write: if request.auth != null && request.auth.uid == uid;
        }
        match /artifacts/{artifactId} {
          allow read: if request.auth != null && request.auth.uid == uid;
          allow write: if false;
        }
      }

      // Agent sessions & recommendations: read-only, function-managed
      match /agent_sessions/{sessionId} {
        allow read: if request.auth != null && request.auth.uid == uid;
        allow write: if false;
      }
      match /agent_recommendations/{docId} {
        allow read: if request.auth != null && request.auth.uid == uid;
        allow write: if false;
      }

      // Subscription events: read-only audit log
      match /subscription_events/{eventId} {
        allow read: if request.auth != null && request.auth.uid == uid;
        allow write: if false;
      }

      // All other user subcollections: owner read/write
      // (workouts, templates, routines, set_facts, weekly_stats, etc.)
      match /{collection}/{document=**} {
        allow read: if request.auth != null && request.auth.uid == uid;
        allow write: if request.auth != null && request.auth.uid == uid
          && collection != "canvases"
          && collection != "exercise_usage_stats"
          && collection != "conversations"
          && collection != "agent_sessions"
          && collection != "agent_recommendations"
          && collection != "subscription_events";
      }
    }

    // ================================================================
    // ROOT COLLECTIONS (shared/global data)
    // ================================================================

    // Exercise catalog — anyone can read, only Admin SDK writes
    match /exercises/{exerciseId} {
      allow read: if true;
      allow write: if false;
    }

    // Exercise aliases — anyone can read, only Admin SDK writes
    match /exercise_aliases/{aliasSlug} {
      allow read: if true;
      allow write: if false;
    }

    // Internal collections — Admin SDK only
    match /catalog_jobs/{jobId} {
      allow read, write: if false;
    }
    match /training_analysis_jobs/{jobId} {
      allow read, write: if false;
    }
    match /cache/{cacheKey} {
      allow read: if true;
      allow write: if false;
    }
    match /idempotency/{key} {
      allow read, write: if false;
    }
    match /exercises_backup/{exerciseId} {
      allow read, write: if false;
    }
    match /processed_webhook_notifications/{notificationId} {
      allow read, write: if false;
    }

    // Deny-all fallback for unmatched paths
    match /{document=**} {
      allow read, write: if false;
    }
  }
}
```

**Step 2: Smoke test**

Test locally against emulator:
```bash
cd firebase_functions
firebase emulators:start --only firestore
```

Verify:
- Authenticated user CAN **create** their own `users/{uid}` doc (signup flow)
- Authenticated user CAN **update** non-subscription fields on their own doc
- Authenticated user CANNOT write `subscription_tier` to their own doc (create or update)
- Authenticated user CANNOT **delete** their own doc directly
- Authenticated user CANNOT read another user's doc
- Unauthenticated user CAN read `exercises` (by design for exercise catalog)
- Unauthenticated user CANNOT write to `exercises`
- Authenticated user CAN read/write their own `workouts`, `templates`, `routines`

**Step 3: Deploy rules only**

```bash
cd firebase_functions
firebase deploy --only firestore:rules
```

**Step 4: Run existing tests**

```bash
cd firebase_functions/functions && npm test
```
Expected: All existing tests pass (they use Admin SDK which bypasses rules).

**Step 5: Commit**

```bash
git add firebase_functions/firestore.rules
git commit -m "security: lock down Firestore rules — protect root collections and subscription fields"
```

---

## Task 2: Create `getAuthenticatedUserId()` Helper

**Why:** 16 endpoints derive userId from client input instead of the auth token. We need a single helper that enforces the correct pattern based on auth lane (Bearer vs API key), then update all vulnerable endpoints to use it.

**Regression risk:** MEDIUM — This changes how userId is derived in many endpoints. The key insight: `withApiKey` endpoints are agent-only (userId from client is correct). `requireFlexibleAuth` endpoints need to enforce token-based userId for Bearer lane. We must NOT break the agent system which legitimately passes userId via API key.

**Files:**
- Create: `firebase_functions/functions/utils/auth-helpers.js`
- Test: `firebase_functions/functions/tests/auth-helpers.test.js`

**Step 1: Write the test**

```javascript
// tests/auth-helpers.test.js
const { test, describe } = require('node:test');
const assert = require('node:assert/strict');
const { getAuthenticatedUserId } = require('../utils/auth-helpers');

describe('getAuthenticatedUserId', () => {
  test('Bearer lane: returns uid from decoded token', () => {
    const req = {
      auth: { uid: 'token-user-123' },       // decoded Firebase token
      body: { userId: 'attacker-user-456' },  // attacker tries IDOR
      query: { userId: 'attacker-user-789' },
    };
    assert.equal(getAuthenticatedUserId(req), 'token-user-123');
  });

  test('Bearer lane via req.user: returns uid from decoded token', () => {
    const req = {
      user: { uid: 'token-user-123' },
      body: { userId: 'attacker-user-456' },
    };
    assert.equal(getAuthenticatedUserId(req), 'token-user-123');
  });

  test('API key lane: returns userId from body', () => {
    const req = {
      auth: { type: 'api_key', uid: undefined },
      body: { userId: 'agent-target-user' },
      query: {},
    };
    assert.equal(getAuthenticatedUserId(req), 'agent-target-user');
  });

  test('API key lane: returns uid from X-User-Id header (via auth.uid)', () => {
    const req = {
      auth: { type: 'api_key', uid: 'header-user-123' },
      body: {},
      query: {},
    };
    assert.equal(getAuthenticatedUserId(req), 'header-user-123');
  });

  test('API key lane: returns userId from query', () => {
    const req = {
      auth: { type: 'api_key', uid: undefined },
      body: {},
      query: { userId: 'query-user-123' },
    };
    assert.equal(getAuthenticatedUserId(req), 'query-user-123');
  });

  test('No auth: returns null', () => {
    const req = { body: { userId: 'attacker' }, query: {} };
    assert.equal(getAuthenticatedUserId(req), null);
  });

  test('Bearer lane: ignores query userId', () => {
    const req = {
      auth: { uid: 'real-user' },
      query: { userId: 'fake-user' },
      body: {},
    };
    assert.equal(getAuthenticatedUserId(req), 'real-user');
  });

  test('API key lane: empty string userId returns null', () => {
    const req = {
      auth: { type: 'api_key', uid: undefined },
      body: { userId: '' },
      query: {},
    };
    assert.equal(getAuthenticatedUserId(req), null);
  });

  test('API key lane: whitespace-only userId returns null', () => {
    const req = {
      auth: { type: 'api_key', uid: undefined },
      body: { userId: '   ' },
      query: {},
    };
    assert.equal(getAuthenticatedUserId(req), null);
  });
});
```

**Step 2: Run test to verify it fails**

```bash
cd firebase_functions/functions && node --test tests/auth-helpers.test.js
```
Expected: FAIL — module not found

**Step 3: Write the helper**

```javascript
// utils/auth-helpers.js
/**
 * Safely extract userId from request based on auth lane.
 *
 * Bearer lane (Firebase ID token):
 *   userId comes from the verified token ONLY. Client-provided userId
 *   in body/query is IGNORED to prevent IDOR attacks.
 *
 * API key lane (service-to-service):
 *   userId comes from X-User-Id header (via req.auth.uid) or
 *   req.body.userId / req.query.userId. The caller is a trusted
 *   service (agent system) that has been authenticated by API key.
 *
 * @param {Object} req - Express request with auth middleware applied
 * @returns {string|null} - Authenticated userId or null
 */
function getAuthenticatedUserId(req) {
  // 1. Check for decoded Firebase token (set by requireAuth or requireFlexibleAuth Bearer path)
  if (req.user?.uid) return req.user.uid;

  // 2. Check req.auth (set by requireFlexibleAuth or withApiKey)
  if (req.auth) {
    // API key lane: trusted service caller provides userId
    if (req.auth.type === 'api_key') {
      const candidate = req.auth.uid || req.body?.userId || req.query?.userId || null;
      // Validate non-empty string to prevent null/empty bypass
      if (candidate && typeof candidate === 'string' && candidate.trim()) {
        return candidate.trim();
      }
      return null;
    }
    // Bearer lane: uid from verified token ONLY
    if (req.auth.uid) return req.auth.uid;
  }

  return null;
}

module.exports = { getAuthenticatedUserId };
```

**Step 4: Run test to verify it passes**

```bash
cd firebase_functions/functions && node --test tests/auth-helpers.test.js
```
Expected: 9/9 PASS

**Step 5: Run all tests**

```bash
cd firebase_functions/functions && npm test
```
Expected: All existing tests still pass.

**Step 6: Commit**

```bash
git add firebase_functions/functions/utils/auth-helpers.js firebase_functions/functions/tests/auth-helpers.test.js
git commit -m "security: add getAuthenticatedUserId helper to prevent IDOR attacks"
```

---

## Task 3: Fix IDOR in `requireFlexibleAuth` Endpoints

**Why:** 8 endpoints using `requireFlexibleAuth` fall back to client-provided userId when Bearer token is used.

**Regression risk:** MEDIUM — Must preserve the API key lane (agent system) while locking down Bearer lane (iOS app). Test with both lanes after each file change.

**Files to modify (each is a sub-step — modify, test, continue):**

1. `firebase_functions/functions/routines/get-routine.js` (line 18)
2. `firebase_functions/functions/routines/get-user-routines.js` (line 18)
3. `firebase_functions/functions/routines/get-next-workout.js` (line 67)
4. `firebase_functions/functions/routines/patch-routine.js` (line 28)
5. `firebase_functions/functions/templates/get-template.js` (line 16)
6. `firebase_functions/functions/templates/patch-template.js` (line 26)
7. `firebase_functions/functions/templates/create-template-from-plan.js` (line 26)
8. `firebase_functions/functions/agents/get-planning-context.js` (line ~118)

**Pattern for each file:**

Replace:
```javascript
const userId = req.auth?.uid || req.query.userId || req.body?.userId;
// or
const callerUid = req.auth?.uid || req.body.userId;
```

With:
```javascript
const { getAuthenticatedUserId } = require('../utils/auth-helpers');
// ...
const userId = getAuthenticatedUserId(req);
if (!userId) return fail(res, 'UNAUTHENTICATED', 'Authentication required', null, 401);
```

**Step 1: Read each file first**

Before modifying, read each file to identify:
- The exact variable name used (e.g., `userId`, `callerUid`, `uid`)
- The exact userId derivation pattern on that line
- All downstream references to that variable — rename consistently

**Important:** Some files use `callerUid` instead of `userId`. When replacing, update ALL references to use `userId` consistently, OR keep the original variable name and assign from `getAuthenticatedUserId(req)`. The `require` statement must go at the **top of the file** with other imports, not inline in the handler.

**Step 2: Fix all 8 files**

For each file:
1. Add `const { getAuthenticatedUserId } = require('../utils/auth-helpers');` at the top with other imports (or `../../utils/auth-helpers` for nested paths)
2. Replace the userId derivation line
3. Ensure the `if (!userId)` guard exists right after
4. Update any downstream variable name references if the original used a different name

**Step 3: Run all tests**

```bash
cd firebase_functions/functions && npm test
```
Expected: All pass.

**Step 4: Smoke test via emulator**

```bash
cd firebase_functions && npm run serve
```

Test that agent system (API key) still works:
```bash
curl -X POST http://127.0.0.1:5001/demo-myon/us-central1/getRoutine \
  -H "X-API-Key: myon-agent-key-2024" \
  -H "Content-Type: application/json" \
  -d '{"userId": "test-user", "routineId": "test-routine"}'
```
Expected: 200 or 404 (not 401)

Test that Bearer token user CANNOT pass different userId:
```bash
# This should use the token's uid, NOT the body userId
curl -X POST http://127.0.0.1:5001/demo-myon/us-central1/getRoutine \
  -H "Authorization: Bearer VALID_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"userId": "different-user", "routineId": "test-routine"}'
```
Expected: Returns data for the token's user, NOT "different-user"

**Step 5: Commit**

```bash
git add firebase_functions/functions/routines/ firebase_functions/functions/templates/ firebase_functions/functions/agents/
git commit -m "security: fix IDOR in requireFlexibleAuth endpoints — enforce token-based userId"
```

---

## Task 4: Remove Hardcoded API Key Fallback

**Why:** `myon-agent-key-2024` is hardcoded in 6 files. If the repo is ever exposed (or the binary reverse-engineered), this key grants full API access as any user.

**Regression risk:** LOW — The key is already set via `VALID_API_KEYS` env var in production. We're only removing the fallback. The emulator tests use this key, so we need to set it in the emulator env.

**Files:**
- Modify: `firebase_functions/functions/auth/middleware.js` (lines 96-101)
- Modify: `firebase_functions/.env` (create if not exists — for emulator only)

**Step 1: Remove hardcoded fallback**

In `middleware.js`, replace lines 96-101:
```javascript
  // Prefer environment-driven rotation; allow emulator fallback
  const envApiKeys = process.env.VALID_API_KEYS;
  const emulator = process.env.FUNCTIONS_EMULATOR === 'true' || process.env.FIREBASE_EMULATOR_HUB;
  // Allow a safe default in environments where secrets aren't attached yet (e.g., fresh staging) — must be rotated regularly.
  const fallbackKeys = emulator ? 'myon-agent-key-2024' : 'myon-agent-key-2024';
  const apiKeysString = envApiKeys || process.env.MYON_API_KEY || fallbackKeys;
```

With:
```javascript
  const apiKeysString = process.env.VALID_API_KEYS || process.env.MYON_API_KEY;
  if (!apiKeysString) {
    const { logger } = require('firebase-functions');
    logger.error('[middleware] FATAL: No API keys configured. Set VALID_API_KEYS env var.');
    res.status(500).json({ success: false, error: 'Server configuration error' });
    return null;
  }
```

**Step 2: Set up emulator env var**

Create or update `firebase_functions/.env` (Firebase emulators automatically load this file when present):
```
VALID_API_KEYS=myon-agent-key-2024
```

Verify `.env` is in `.gitignore` (it should be — contains secrets). If not, add it.

Also check if tests set the env var. If `npm test` uses `VALID_API_KEYS` from the environment, you may need to add it to a test setup script or `.env.test`.

**Step 3: Run tests**

```bash
cd firebase_functions/functions && npm test
```
Expected: Pass. If tests fail with 500 "Server configuration error", set the env var before running:
```bash
VALID_API_KEYS=test-key-for-ci cd firebase_functions/functions && npm test
```

**Step 4: Commit**

```bash
git add firebase_functions/functions/auth/middleware.js
git commit -m "security: remove hardcoded API key fallback — require env var"
```

**Step 5: Post-deploy action (manual)**

After deploying, verify `VALID_API_KEYS` is set in Cloud Functions runtime:
```bash
firebase functions:config:get
# OR check GCP Secret Manager / env vars in Cloud Console
```

Generate a new strong API key and rotate:
1. Generate: `openssl rand -base64 32`
2. Set new key in Cloud Functions env **alongside** old key (comma-separated): `VALID_API_KEYS=NEW_KEY,myon-agent-key-2024`
3. Deploy functions
4. Update agent system env (Vertex AI) to use new key
5. Verify agent system works with new key
6. Remove old key: `VALID_API_KEYS=NEW_KEY`
7. Deploy functions again

---

## Task 5: App Store Webhook JWS Verification

**Why:** The webhook currently base64-decodes Apple's JWS payload without verifying the signature. Anyone who knows the webhook URL can forge subscription notifications.

**Regression risk:** MEDIUM — If Apple's cert verification is too strict or the certs are wrong, legitimate webhooks will be rejected. In production, missing certs cause webhook rejection (fail secure). In emulator, insecure fallback is used for testing.

**Files:**
- Modify: `firebase_functions/functions/subscriptions/app-store-webhook.js`
- Create: `firebase_functions/functions/subscriptions/certs/` (download Apple root certs)

**Step 1: Download Apple root certificates**

```bash
mkdir -p firebase_functions/functions/subscriptions/certs
cd firebase_functions/functions/subscriptions/certs
curl -o AppleRootCA-G3.cer https://www.apple.com/certificateauthority/AppleRootCA-G3.cer
curl -o AppleRootCA-G2.cer https://www.apple.com/certificateauthority/AppleRootCA-G2.cer
```

Verify the certs downloaded correctly (non-zero file size):
```bash
ls -la firebase_functions/functions/subscriptions/certs/
```

**Step 2: Implement JWS verification**

Replace the `decodeJWSPayload` function in `app-store-webhook.js`:

```javascript
const { SignedDataVerifier, Environment } = require('@apple/app-store-server-library');
const fs = require('fs');
const path = require('path');

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
  logger.error('[webhook] verifier_init_failed — webhooks will be rejected in production', {
    error: String(err?.message || err),
  });
}

/**
 * Verify and decode JWS notification from Apple.
 * In production: rejects if verifier unavailable (fail secure).
 * In emulator: falls back to insecure decode for testing.
 */
async function decodeAndVerifyNotification(signedPayload) {
  if (verifier) {
    try {
      return await verifier.verifyAndDecodeNotification(signedPayload);
    } catch (err) {
      logger.error('[webhook] jws_verification_failed', {
        error: String(err?.message || err),
      });
      return null;  // Reject unverified payloads
    }
  }

  // Verifier unavailable
  const isEmulator = process.env.FUNCTIONS_EMULATOR === 'true';
  if (isEmulator) {
    logger.warn('[webhook] jws_insecure_fallback — emulator only', {
      warning: 'Apple root certs not loaded. Using insecure base64 decode.',
    });
    return decodeJWSPayloadInsecure(signedPayload);
  }

  // Production: fail secure — reject the webhook
  logger.error('[webhook] verifier unavailable in production — rejecting webhook', {
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
```

Then update the handler to use the new function (replace `decodeJWSPayload` calls with `await decodeAndVerifyNotification`).

**Step 3: Add replay protection**

In the webhook handler, after decoding but before processing:

```javascript
// Check for duplicate notification
const notificationUUID = notification.notificationUUID;
if (notificationUUID) {
  const processedRef = db.collection('processed_webhook_notifications').doc(notificationUUID);
  const processedSnap = await processedRef.get();
  if (processedSnap.exists) {
    logger.info('[webhook] duplicate_skipped', { notification_uuid: notificationUUID });
    return res.status(200).json({ ok: true });
  }
}

// ... process notification ...

// After successful processing, mark as processed (with 90-day TTL for cleanup)
if (notificationUUID) {
  const ttlDate = new Date();
  ttlDate.setDate(ttlDate.getDate() + 90);
  await db.collection('processed_webhook_notifications').doc(notificationUUID).set({
    notification_type: notificationType,
    processed_at: admin.firestore.FieldValue.serverTimestamp(),
    expires_at: admin.firestore.Timestamp.fromDate(ttlDate),
  });
}
```

**Note:** Set up a Firestore TTL policy on the `processed_webhook_notifications` collection using the `expires_at` field to auto-delete old entries. This prevents unbounded growth.

**Step 4: Decode signedTransactionInfo and signedRenewalInfo with verification**

Also update the inner JWS decoding for `signedTransactionInfo` and `signedRenewalInfo` to use the verifier's `verifyAndDecodeTransaction()` and `verifyAndDecodeRenewalInfo()` methods. In emulator mode, fall back to insecure decode for these too.

**Step 5: Test**

Send a test webhook to the emulator to verify the insecure fallback works (certs won't verify in emulator since Apple won't sign test payloads).

```bash
cd firebase_functions/functions && npm test
```

**Step 6: Commit**

```bash
git add firebase_functions/functions/subscriptions/
git commit -m "security: implement JWS verification for App Store webhook + replay protection"
```

---

## Task 6: Input Validation Hardening

**Why:** Missing upper bounds on weight values, array sizes, and string lengths enable data corruption and DoS.

**Regression risk:** LOW — We're adding upper bounds to existing Zod schemas. Legitimate data will never hit these limits (1000kg weight, 50 exercises per workout, 100 sets per exercise).

**Files:**
- Modify: `firebase_functions/functions/utils/validators.js`

**Step 1: Read validators.js**

Read the file first to locate existing schemas and understand current validation patterns.

**Step 2: Add upper bounds to schemas**

Add to `LogSetSchemaV2`:
```javascript
weight: z.number().nonnegative().max(1000).nullable(), // 1000kg = beyond any human capacity
```

Add max counts to `TemplateSchema` (if exists) or add new:
```javascript
const MAX_EXERCISES_PER_WORKOUT = 50;
const MAX_SETS_PER_EXERCISE = 100;
const MAX_NAME_LENGTH = 200;
const MAX_NOTES_LENGTH = 5000;
```

Apply these constants to any `z.array()` schemas for exercises and sets.

**Step 3: Run tests**

```bash
cd firebase_functions/functions && npm test
```

**Step 4: Commit**

```bash
git add firebase_functions/functions/utils/validators.js
git commit -m "security: add upper bounds to input validation — weight, array sizes, string lengths"
```

---

## Task 7: Fix iOS Subscription Sync (Adapt to Firestore Rules)

**Why:** Task 1's Firestore rules block client writes to subscription fields. The iOS `SubscriptionService.syncToFirestore()` method writes `subscription_tier`, `subscription_status` directly — it will start failing silently after rules deploy.

**Regression risk:** HIGH if not done — subscription UI will break. LOW if done correctly — we route through a new Cloud Function.

**Approach:** Create a minimal Cloud Function `syncSubscriptionStatus` that the iOS app calls with StoreKit transaction data. The function validates and writes subscription fields using Admin SDK (bypasses rules). The webhook remains authoritative for downgrades — this function only accepts positive entitlements as a fast-path for UI responsiveness.

**Race condition note:** If StoreKit cache on iOS reports "active" while webhook simultaneously reports "expired", this function rejects the stale iOS sync (tier must be 'premium', status must be active/trial/grace_period). The webhook always wins for downgrades since it writes via Admin SDK unconditionally. Brief positive overwrite from iOS is acceptable — webhook will correct within seconds.

**Files:**
- Create: `firebase_functions/functions/subscriptions/sync-subscription-status.js`
- Modify: `firebase_functions/functions/index.js` (add export)
- Modify: `Povver/Povver/Services/SubscriptionService.swift` (call function instead of direct write)

**Step 1: Create the Cloud Function**

```javascript
// subscriptions/sync-subscription-status.js
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
```

**Step 2: Add to index.js**

```javascript
const { syncSubscriptionStatus } = require('./subscriptions/sync-subscription-status');
exports.syncSubscriptionStatus = syncSubscriptionStatus;
```

**Step 3: Update iOS SubscriptionService**

In `SubscriptionService.swift`, replace the direct Firestore write in `syncToFirestore()` with an API call to the new function:

```swift
private func syncToFirestore() async {
    guard let userId = Auth.auth().currentUser?.uid else { return }
    let state = subscriptionState

    // Only sync positive entitlements (same guard as before)
    guard state.tier == .premium else { return }

    do {
        try await ApiClient.shared.postJSON("syncSubscriptionStatus", body: [
            "status": state.status.rawValue,
            "tier": state.tier.rawValue,
            "autoRenewEnabled": state.autoRenewEnabled,
            "inGracePeriod": state.inGracePeriod,
            "productId": state.productId as Any,
        ])
    } catch {
        // Non-critical — webhook is authoritative
        DebugLogger.shared.warn("Subscription sync failed: \(error.localizedDescription)")
    }
}
```

**Step 4: Test**

- Verify the Cloud Function works via emulator
- Verify the iOS app compiles and subscription flow works
- Verify direct Firestore write to subscription fields is BLOCKED by rules

**Step 5: Commit**

```bash
git add firebase_functions/functions/subscriptions/sync-subscription-status.js \
       firebase_functions/functions/index.js \
       Povver/Povver/Services/SubscriptionService.swift
git commit -m "security: route iOS subscription sync through Cloud Function (Firestore rules block direct writes)"
```

---

## Task 8: Add Premium Gate to `artifactAction`

**Why:** Users can save AI-generated content (routines, templates) via `artifactAction` even after their premium subscription expires.

**Regression risk:** LOW — Only adds a check before mutation actions. Non-mutating actions (dismiss) remain available to all users.

**Files:**
- Modify: `firebase_functions/functions/artifacts/artifact-action.js`

**Step 1: Read artifact-action.js**

Read the file first to identify the action type switch statement and which actions are mutations (save_routine, save_template, start_workout) vs. non-mutations (accept, dismiss).

**Step 2: Add premium check — scoped to mutation actions only**

Inside the handler, after userId extraction and action type parsing, add the premium gate **only for mutation actions** (save_routine, save_template, start_workout). Do NOT gate dismiss or accept — free users should be able to dismiss artifacts from their UI.

```javascript
const { isPremiumUser } = require('../utils/subscription-gate');

// Premium gate — only mutation actions require premium
const premiumActions = ['save_routine', 'save_template', 'start_workout'];
if (premiumActions.includes(actionType)) {
  const hasPremium = await isPremiumUser(userId);
  if (!hasPremium) {
    return fail(res, 'PREMIUM_REQUIRED', 'Premium subscription required', null, 403);
  }
}
```

**Step 3: Test**

```bash
cd firebase_functions/functions && npm test
```

**Step 4: Commit**

```bash
git add firebase_functions/functions/artifacts/artifact-action.js
git commit -m "security: add premium gate to artifact mutation actions"
```

---

## Deployment Sequence

Deploy in this exact order to avoid breaking changes:

1. **Deploy Task 7 Cloud Function first** (`syncSubscriptionStatus`) — so iOS has a working endpoint before rules block direct writes
2. **Deploy Task 1 Firestore rules** — now subscription fields are protected, iOS uses the new function
3. **Deploy Tasks 2-6, 8** — all other security fixes (function-level changes)
4. **Submit iOS update** — with Task 7 Swift changes

If deploying in a single session:
```bash
# Step 1: Deploy new function + all function changes
cd firebase_functions/functions && npm test  # Verify all pass
firebase deploy --only functions

# Step 2: Deploy rules (after functions are live)
firebase deploy --only firestore:rules
```

**Rollback plan:** If rules deploy causes issues:
```bash
# Revert to permissive rules temporarily
git checkout HEAD~1 -- firebase_functions/firestore.rules
firebase deploy --only firestore:rules
```
Functions can be rolled back independently via the Cloud Console.

---

## Post-Deployment Verification Checklist

- [ ] iOS app can create new user accounts (signup flow)
- [ ] iOS app can update user profile (non-subscription fields)
- [ ] iOS app can still stream agent responses (premium users)
- [ ] iOS app shows paywall for free users trying to stream
- [ ] iOS app can log workout sets
- [ ] iOS app can save routines/templates
- [ ] iOS app can dismiss artifacts (free users too)
- [ ] Agent system can still call API-key endpoints
- [ ] App Store webhook still processes notifications
- [ ] Direct Firestore write to `subscription_tier` is REJECTED
- [ ] Direct Firestore write to `exercises` collection is REJECTED
- [ ] User A cannot read User B's workouts via any endpoint

---

## Out of Scope (Future Tasks)

These were identified in the audit but deferred to avoid scope creep:

- **Certificate pinning on iOS** — requires URLSession delegate changes, significant testing
- **CORS allowlist** — needs coordination with agent system origins
- **Rate limiting** — needs Redis or Cloud Armor, architectural decision
- **Agent prompt injection sanitization** — needs LLM-specific testing
- **Safety gate keyword hardening** — needs agent system changes
- **npm audit fix** — run separately, test thoroughly for breaking changes
- **Jailbreak detection** — optional, client-side only
- **Firestore TTL policy for processed_webhook_notifications** — set up via Firebase Console after Task 5 deploys
