# Auth — Module Architecture

Authentication middleware for Firebase Functions. Provides three authentication strategies used across all endpoints.

## File Inventory

| File | Purpose |
|------|---------|
| `middleware.js` | All auth middleware: `withApiKey`, `requireFlexibleAuth`, `requireAuth`, and low-level verifiers |
| `exchange-token.js` | `getServiceToken` — exchanges credentials for GCP service account tokens (used for Vertex AI calls) |

## Authentication Strategies

| Middleware | User ID Source | Use Case | Wrapped In |
|-----------|---------------|----------|------------|
| `withApiKey` | `req.body.userId` or `req.query.userId` (trusted) | Agent/service-to-service calls | `index.js` |
| `requireFlexibleAuth` | Bearer → `req.auth.uid`; API key → `req.body.userId` | Endpoints called by both iOS and agents | `index.js` |
| `requireAuth` | `req.auth.uid` only | iOS-only endpoints (strict) | `index.js` |

## Security Model

**Bearer Lane (Firebase Auth Token):**
- Used by iOS app
- `userId` derived from `req.auth.uid` ONLY
- Client-provided `userId` in request body is IGNORED
- Prevents cross-user data access

**Service Lane (API Key):**
- Used by agent system and service-to-service calls
- `userId` from `req.body.userId` or `req.query.userId` (trusted)
- Authenticated via `X-API-Key` header against `VALID_API_KEYS` env var

**Why Bearer endpoints never trust request params:**
If a Bearer endpoint accepted `userId` from the request body, any authenticated user could read/write another user's data by providing a different `userId`. The middleware enforces that Bearer-authenticated requests always derive `userId` from the verified Firebase Auth token.

## Cross-References

- All endpoint wrappers in `index.js` use these middleware functions
- CORS headers are set by `requireFlexibleAuth` and `withApiKey` (not by individual handlers)
- Auth patterns documented in `docs/SYSTEM_ARCHITECTURE.md` (Authentication Lanes section)
