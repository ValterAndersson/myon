# Recommendations Module Architecture

> **Tier 2 Documentation**: Module-level architecture for agent recommendation review endpoints.

---

## Purpose

The recommendations module provides HTTP endpoints for users to review and act on agent-generated training recommendations. Agent recommendations are created automatically by background triggers when training analysis identifies actionable progression opportunities.

---

## File Structure

```
recommendations/
├── ARCHITECTURE.md              # This file (Tier 2 docs)
└── review-recommendation.js     # Review endpoint (accept/reject recommendations)
```

---

## Entry Points

### `POST /reviewRecommendation`

**File**: `review-recommendation.js`
**Auth**: v2 `onRequest` with `requireFlexibleAuth` (Bearer lane)
**Region**: `us-central1`

User-facing endpoint to accept or reject pending agent recommendations.

**Request**:
```json
{
  "recommendationId": "string",
  "action": "accept" | "reject"
}
```

**Response (accept)**:
```json
{
  "success": true,
  "data": {
    "status": "applied",
    "result": {
      "template_id": "...",
      "changes_applied": 3
    }
  }
}
```

**Response (reject)**:
```json
{
  "success": true,
  "data": {
    "status": "rejected"
  }
}
```

---

## Authentication Pattern

### v2 onRequest with requireFlexibleAuth (Bearer Lane)

This module uses the **Bearer lane** authentication pattern:

```javascript
const { onRequest } = require('firebase-functions/v2/https');
const { requireFlexibleAuth } = require('../auth/middleware');

const reviewRecommendation = onRequest(
  { cors: true, region: 'us-central1' },
  requireFlexibleAuth(async (req, res) => {
    const userId = req.auth.uid; // ALWAYS from auth token, never client-provided
    // ...
  })
);
```

**Security invariant**: `userId` is derived exclusively from `req.auth.uid`. Any client-provided `userId` parameters are ignored. This prevents cross-user data access.

Pattern reference: `firebase_functions/functions/training/get-analysis-summary.js`

---

## Accept Flow (Scope-Dependent)

1. **Auth**: Extract `userId` from `req.auth.uid` (never trust client)
2. **Premium gate**: Call `isPremiumUser(userId)` from `utils/subscription-gate.js`
   - If not premium → return `403 PREMIUM_REQUIRED`
3. **Read recommendation**: `users/{uid}/agent_recommendations/{recommendationId}`
4. **Validate state**: Must be `pending_review`
   - If not → return `409 INVALID_STATE`
5. **Branch on `scope`**:
   - **`exercise`**: Acknowledge only — set `state = 'acknowledged'`, no template mutation
   - **`routine`**: Acknowledge only — set `state = 'acknowledged'`, no template mutation (muscle_balance recs)
   - **`template`**: Proceed to freshness check + apply (steps 6-8)
6. **Freshness check** (template-scoped only):
   - Read target template
   - For each change, verify `change.from === resolvePathValue(currentTemplate, change.path)`
   - Skip comparison when `change.from === null` (new field being added — no baseline)
   - If any mismatch → return `409 STALE_RECOMMENDATION` with details
7. **Apply changes**: Call `applyChangesToTarget()` from `agents/apply-progression.js`
8. **Update recommendation**:
   - `state = 'applied'`
   - `applied_by = 'user'`
   - `applied_at = serverTimestamp()`
   - `result = { template_id, changes_applied }`
   - Append to `state_history`: `{ from: 'pending_review', to: 'applied', at, by: 'user' }`
9. **Return**: `ok(res, { status: 'applied', result })` or `ok(res, { status: 'acknowledged' })`

### Freshness Check Rationale

The freshness check prevents applying stale recommendations when the user has manually edited the template between recommendation creation and review. Without this check:
- User gets recommendation "increase bench press from 80kg to 82kg"
- User manually edits template to 85kg
- User accepts recommendation → template would revert to 82kg (data loss)

With freshness check:
- Change expects `from: 80kg`, but current value is 85kg
- Return `409 STALE_RECOMMENDATION` with mismatch details
- User sees clear error: "Template has changed since recommendation was created"

---

## Reject Flow

1. **Auth**: Extract `userId` from `req.auth.uid`
2. **Premium gate**: Same `isPremiumUser()` check
3. **Validate state**: Must be `pending_review`
4. **Update recommendation**:
   - `state = 'rejected'`
   - Append to `state_history`: `{ from: 'pending_review', to: 'rejected', at, by: 'user' }`
5. **Return**: `ok(res, { status: 'rejected' })`

---

## Error Codes

| Code | HTTP | Description | When |
|------|------|-------------|------|
| `PREMIUM_REQUIRED` | 403 | User does not have premium subscription | Premium gate fails |
| `NOT_FOUND` | 404 | Recommendation or template not found | Read fails |
| `INVALID_STATE` | 409 | Recommendation not in 'pending_review' state | Already applied/rejected/expired |
| `STALE_RECOMMENDATION` | 409 | Target template has changed since recommendation | Freshness check fails |
| `INTERNAL_ERROR` | 500 | Apply failed (e.g., Firestore write error) | `applyChangesToTarget` throws |

Error response format (via `utils/response.js`):
```json
{
  "success": false,
  "error": {
    "code": "STALE_RECOMMENDATION",
    "message": "Recommendation is stale - template has changed",
    "details": {
      "mismatches": [
        {
          "path": "exercises[0].sets[0].weight",
          "expected": 80,
          "actual": 85
        }
      ]
    }
  }
}
```

---

## Integration with apply-progression.js

This module imports shared utility functions from `agents/apply-progression.js`:

```javascript
const {
  applyChangesToTarget,
  resolvePathValue,
} = require('../agents/apply-progression');
```

### `applyChangesToTarget(db, userId, targetType, targetId, changes)`

Applies an array of changes to a template or routine document. Used by:
- `agents/apply-progression.js` (auto-pilot mode)
- `triggers/process-recommendations.js` (auto-pilot mode)
- `recommendations/review-recommendation.js` (user review mode)

**Input**:
- `db` - Firestore instance
- `userId` - User ID
- `targetType` - `"template"` or `"routine"`
- `targetId` - Template or routine document ID
- `changes` - Array of `{ path, from, to, rationale }` objects

**Output**:
```javascript
{
  template_id: "...",
  changes_applied: 3
}
```

**Behavior**:
- Reads target document
- Applies changes to deep copy using `applyChangesToObject()`
- Writes updated document with `updated_at` and `last_progression_at` timestamps
- Throws on Firestore errors (caller catches)

### `resolvePathValue(obj, path)`

Resolves a nested path like `"exercises[0].sets[0].weight"` to get a value from an object.

**Input**:
- `obj` - Object to traverse
- `path` - Dot/bracket notation path string

**Output**: Value at path, or `undefined` if not found

**Use case**: Freshness check compares expected `change.from` with `resolvePathValue(currentTemplate, change.path)`

---

## Firestore Operations

### Reads

- `users/{uid}/agent_recommendations/{id}` - Get recommendation to review
- `users/{uid}/templates/{id}` - Freshness check (accept flow only)

### Writes

- `users/{uid}/agent_recommendations/{id}` - Update state, state_history, applied_by, applied_at, result
- `users/{uid}/templates/{id}` - Apply changes (accept flow only, via `applyChangesToTarget`)

---

## State Machine

Agent recommendations follow this state machine:

```
pending_review → applied (user accepts, template-scoped)
pending_review → acknowledged (user accepts, exercise/routine-scoped)
pending_review → rejected (user rejects)
pending_review → expired (daily TTL sweep)
applied → failed (apply error during accept)
```

This endpoint handles transitions from `pending_review` to `applied` or `rejected`.

The `failed` state is a fallback when `applyChangesToTarget` throws during accept. The recommendation is updated to `failed` state with error details before returning 500 to the client.

---

## Related Components

### Triggers (create recommendations)
- `triggers/process-recommendations.js`
  - `onAnalysisInsightCreated` - Process post-workout insights
  - `onWeeklyReviewCreated` - Process weekly reviews
  - `expireStaleRecommendations` - Daily cleanup (7-day TTL)

### Auto-pilot (background apply)
- `agents/apply-progression.js`
  - `applyProgression` - Headless HTTP endpoint for agent calls
  - Shared utilities (`applyChangesToTarget`, etc.)

### Premium gate
- `utils/subscription-gate.js`
  - `isPremiumUser(userId)` - Check subscription tier

### Response helpers
- `utils/response.js`
  - `ok(res, data)` - Success response
  - `fail(res, code, message, details, httpStatus)` - Error response

---

## Testing Checklist

- [ ] Accept pending recommendation (valid state, premium user, fresh template)
- [ ] Accept returns 409 STALE_RECOMMENDATION when template changed
- [ ] Accept returns 409 INVALID_STATE when already applied/rejected/expired
- [ ] Accept returns 403 PREMIUM_REQUIRED for free users
- [ ] Reject pending recommendation (valid state, premium user)
- [ ] Reject returns 409 INVALID_STATE when already applied/rejected/expired
- [ ] Both actions return 404 when recommendation doesn't exist
- [ ] Applied recommendation updates state_history with user attribution
- [ ] Failed apply updates recommendation to failed state with error

---

## Future Enhancements

- **Batch review**: Accept/reject multiple recommendations in one request
- **Preview mode**: Show what would change without applying (dry-run)
- **Revert**: Undo applied recommendation (requires storing original values)
