# Utils — Module Architecture

Shared helpers used across Firebase Function endpoints. These provide consistent patterns for responses, validation, authentication, Firestore operations, rate limiting, and domain logic.

## File Inventory

| File | Purpose |
|------|---------|
| `response.js` | Response helpers: `ok(res, data)` / `fail(res, code, message, details, httpStatus)`. All endpoints use these for consistent response shape. |
| `auth-helpers.js` | `getAuthenticatedUserId(req)` — single source of truth for secure userId derivation. Prevents IDOR by enforcing token-based userId in bearer-lane. Logs IDOR attempts. |
| `validators.js` | Zod schema validation with security upper bounds (MAX_WEIGHT_KG, MAX_REPS, etc.). Used by write endpoints. |
| `rate-limiter.js` | In-memory sliding window rate limiter. Pre-configured tiers: `authLimiter` (10/min), `agentLimiter` (120/hr), `writeLimiter` (300/min). |
| `subscription-gate.js` | `isPremiumUser(userId)` — direct Firestore read for premium access checks. Checks `subscription_override` then `subscription_tier`. |
| `validation-response.js` | Validation error formatting for agent self-healing (includes attempted payload, errors, hints, expected schema) |
| `idempotency.js` | Idempotency key check and storage. Supports global, canvas-scoped, and workout-scoped (transactional) variants. |
| `active-workout-helpers.js` | Shared helpers for active workout mutations: `computeTotals`, `findExercise`, `findSet`, `findExerciseAndSet`. |
| `firestore-helper.js` | Firestore abstractions: `upsertDocument`, `upsertDocumentInSubcollection`, timestamp handling |
| `plan-to-template-converter.js` | Converts `session_plan` artifact content to a `WorkoutTemplate` document structure |
| `strings.js` | String utilities: slug generation, name normalization |
| `aliases.js` | Exercise alias management: slug lookup, alias reservation |
| `analytics-writes.js` | Analytics series write operations |
| `analytics-calculator.js` | Analytics computation: e1RM, volume, set classification |
| `muscle-taxonomy.js` | Canonical muscle groups and muscles with stable IDs |
| `workout-seed-mapper.js` | Maps seed data into workout document format |
| `caps.js` | Server-enforced caps for training analytics v2 |

## Security Utilities

### `auth-helpers.js` — IDOR Prevention

```javascript
const userId = getAuthenticatedUserId(req);
// Bearer lane: returns token-verified uid, ignores req.body.userId
// API key lane: returns req.auth.uid or req.body.userId (trusted service)
// Logs IDOR attempts when bearer client passes mismatched userId
```

Every endpoint handler must use this. Never read `req.body.userId` directly in bearer-lane endpoints.

### `rate-limiter.js` — Sliding Window

```javascript
const { agentLimiter } = require('../utils/rate-limiter');
if (!agentLimiter.check(userId)) {
  return fail(res, 'RATE_LIMITED', 'Too many requests', null, 429);
}
```

Per-instance (not distributed). Pair with `maxInstances` on v2 functions for global cost control. Denied requests do NOT consume rate limit slots.

### `validators.js` — Input Bounds

Security bounds prevent payload abuse:
- `MAX_WEIGHT_KG`: 1500, `MAX_REPS`: 500
- `MAX_EXERCISES_PER_WORKOUT`: 50, `MAX_SETS_PER_EXERCISE`: 100
- `MAX_NAME_LENGTH`: 200, `MAX_NOTES_LENGTH`: 5000

### `subscription-gate.js` — Premium Check

```javascript
const { isPremiumUser } = require('../utils/subscription-gate');
const hasPremium = await isPremiumUser(userId);
if (!hasPremium) return fail(res, 'PREMIUM_REQUIRED', '...', null, 403);
```

Direct Firestore read (not cached). Checks `subscription_override === 'premium'` first (admin override), then `subscription_tier === 'premium'`.

## Key Exports

### `response.js`
```javascript
ok(res, data, meta?)    // → { success: true, data, meta? }
fail(res, code, msg, details?, httpStatus?)  // → { success: false, error: { code, message, details? } }
```

## Cross-References

- Security invariants: `docs/SECURITY.md`
- Auth middleware: `auth/middleware.js`, `auth/ARCHITECTURE.md`
- Subscription lifecycle: `subscriptions/ARCHITECTURE.md`
- Used by all endpoint handlers across the codebase
