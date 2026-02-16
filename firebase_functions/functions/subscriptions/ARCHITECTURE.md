# Subscriptions Module Architecture

Handles Apple App Store subscription verification, premium access gates, and subscription lifecycle management.

## Files

| File | Path | Purpose |
|------|------|---------|
| `subscription-gate.js` | `utils/subscription-gate.js` | `isPremiumUser(userId)` — shared premium check |
| `app-store-webhook.js` | `subscriptions/app-store-webhook.js` | App Store Server Notifications V2 handler |

---

## subscription-gate.js (`utils/subscription-gate.js`)

Single reusable function for premium access checks. Direct Firestore read (not cached — subscription status must be fresh).

**Export:** `isPremiumUser(userId)` → `Promise<boolean>`

**Logic (in order):**
1. `subscription_override === 'premium'` → `true` (admin override)
2. `subscription_tier === 'premium'` → `true` (active subscription)
3. Otherwise → `false`

**Usage:**
```javascript
const { isPremiumUser } = require('../utils/subscription-gate');

const hasPremium = await isPremiumUser(userId);
if (!hasPremium) {
  // deny access
}
```

**Design decision:** Checks `subscription_tier` (denormalized field set by webhook), not `subscription_status + subscription_expires_at`. This keeps the gate check simple — the webhook is responsible for setting tier correctly based on status transitions.

---

## app-store-webhook.js

**HTTP Endpoint:** `POST /appStoreWebhook` (v2 `onRequest`, NO auth middleware)

**Why no auth:** Apple calls this URL directly with a signed JWS payload. The webhook URL itself serves as the access control. JWS signature verification (via Apple root certs) provides payload authenticity.

**Current state:** JWS payloads are base64-decoded without signature verification (dev mode). Production requires placing Apple root certificates in `subscriptions/certs/` and switching to `SignedDataVerifier.verifyAndDecodeNotification()` from `@apple/app-store-server-library`.

### Apple Root Certificates

Download from https://www.apple.com/certificateauthority/ and place in `subscriptions/certs/`:
- `AppleRootCA-G3.cer`
- `AppleRootCA-G2.cer`

### Notification Type → Status Mapping

| Notification Type | Subtype | subscription_status | subscription_tier |
|---|---|---|---|
| `SUBSCRIBED` | (offerType=1) | `trial` | `premium` |
| `SUBSCRIBED` | (else) | `active` | `premium` |
| `DID_RENEW` | — | `active` | `premium` |
| `DID_FAIL_TO_RENEW` | `GRACE_PERIOD` | `grace_period` | `premium` |
| `DID_FAIL_TO_RENEW` | (else) | `expired` | `free` |
| `EXPIRED` | any | `expired` | `free` |
| `GRACE_PERIOD_EXPIRED` | — | `expired` | `free` |
| `REFUND` | — | `expired` | `free` |
| `REVOKE` | — | `expired` | `free` |
| `DID_CHANGE_RENEWAL_STATUS` | — | *(unchanged)* | *(unchanged)* |

`DID_CHANGE_RENEWAL_STATUS` only updates `subscription_auto_renew_enabled`.

### User Lookup

`appAccountToken` is a deterministic UUID v5 derived from the Firebase UID (same algorithm on iOS and server). Apple preserves it across all transactions.

1. Query `users` where `subscription_app_account_token == token`
2. Fallback: query where `subscription_original_transaction_id == txnId`

### Post-Update Actions

- Calls `invalidateProfileCache(userId)` from `user/get-user.js` to bust the 24h profile cache
- Logs event to `users/{uid}/subscription_events/{auto-id}`
- Always returns HTTP 200 (Apple retries non-200s indefinitely)

---

## Premium-Gated Endpoints

| Endpoint | Gate Point | Error Format |
|---|---|---|
| `streamAgentNormalized` | `stream-agent-normalized.js:896` | SSE `{ type: 'error', error: { code: 'PREMIUM_REQUIRED' } }` |
| Training analysis jobs | `triggers/weekly-analytics.js:506,676` | Job not enqueued (silent) |

**Streaming gate:** After auth resolves userId, calls `isPremiumUser(userId)`. Emits SSE error event (not HTTP error) because the endpoint uses SSE format. Free analytics (weekly_stats, set_facts, rollups) still run — only LLM analysis jobs are gated.

---

## Firestore Schema

### `users/{uid}` — Subscription Fields

| Field | Type | Description |
|---|---|---|
| `subscription_status` | string | `free` / `trial` / `active` / `expired` / `grace_period` |
| `subscription_tier` | string | `free` / `premium` (denormalized for fast gate checks) |
| `subscription_override` | string? | `'premium'` for admin override, `null` otherwise |
| `subscription_product_id` | string? | App Store product ID |
| `subscription_original_transaction_id` | string? | Apple's original transaction ID |
| `subscription_app_account_token` | string? | UUID v5 from Firebase UID |
| `subscription_expires_at` | Timestamp? | Subscription expiration date |
| `subscription_auto_renew_enabled` | boolean | Auto-renewal status |
| `subscription_in_grace_period` | boolean | Billing grace period active |
| `subscription_updated_at` | Timestamp | Last update timestamp |
| `subscription_environment` | string? | `Sandbox` / `Production` |

### `users/{uid}/subscription_events/{auto-id}`

Audit log of webhook notifications for debugging/compliance.

---

## Cross-References

- **Tier 1 Docs:** `docs/SYSTEM_ARCHITECTURE.md`, `docs/FIRESTORE_SCHEMA.md`
- **iOS:** `Povver/Povver/Services/SubscriptionService.swift` (StoreKit 2)
- **iOS:** `Povver/Povver/Models/SubscriptionStatus.swift` (client-side enums)
- **Admin Scripts:** `scripts/migrate_existing_users_to_premium.js`, `scripts/set_subscription_override.js`
