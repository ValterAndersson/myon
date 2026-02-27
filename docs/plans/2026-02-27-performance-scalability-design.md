# Performance & Scalability Design — Povver Platform

> **Document Purpose**: Comprehensive performance and scalability audit with ranked implementation plan. Written for LLM/agentic coding agents to execute without ambiguity.
>
> **Created**: 2026-02-27
> **Status**: Approved design, ready for implementation planning
> **Scope**: Full-stack review — iOS, Firebase Functions, Firestore, Vertex AI Agent Engine
> **Target**: Scale from current (<1k users) to 100k concurrent users

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Current Architecture Quick Reference](#current-architecture-quick-reference)
3. [Phase 1 — Emergency Fixes (Week 1)](#phase-1--emergency-fixes-week-1)
   - [1.1 SSE Proxy Connection Cap](#11-sse-proxy-connection-cap)
   - [1.2 Subscription Gate Caching](#12-subscription-gate-caching)
   - [1.3 GCP Token Caching in exchange-token](#13-gcp-token-caching-in-exchange-token)
   - [1.4 Parallelize get-planning-context Reads](#14-parallelize-get-planning-context-reads)
   - [1.5 Recommendation Listener Leak](#15-recommendation-listener-leak)
4. [Phase 2 — UX Speed (Weeks 2–3)](#phase-2--ux-speed-weeks-23)
   - [2.1 iOS App Launch Waterfall](#21-ios-app-launch-waterfall)
   - [2.2 Wire CacheManager Into Repositories](#22-wire-cachemanager-into-repositories)
   - [2.3 Server-Side Workout History Pagination](#23-server-side-workout-history-pagination)
5. [Phase 3 — Scale Infrastructure (Month 2)](#phase-3--scale-infrastructure-month-2)
   - [3.1 Async Analytics Processing (Trigger Fan-Out)](#31-async-analytics-processing-trigger-fan-out)
   - [3.2 Global Rate Limiting](#32-global-rate-limiting)
   - [3.3 Function Bundle Splitting](#33-function-bundle-splitting)
   - [3.4 Firestore TTL Policies](#34-firestore-ttl-policies)
   - [3.5 v1 to v2 Function Migration](#35-v1-to-v2-function-migration)
6. [Phase 4 — Optimization (Ongoing)](#phase-4--optimization-ongoing)
   - [4.1 Expand Fast Lane Patterns](#41-expand-fast-lane-patterns)
   - [4.2 Planning Context Caching](#42-planning-context-caching)
   - [4.3 Batch Analytics Writes](#43-batch-analytics-writes)
   - [4.4 Training Analyst Horizontal Scaling](#44-training-analyst-horizontal-scaling)
   - [4.5 iOS SSE Connection Reuse](#45-ios-sse-connection-reuse)
7. [Appendix A — Current Bottleneck Map](#appendix-a--current-bottleneck-map)
8. [Appendix B — Cost Projections](#appendix-b--cost-projections)
9. [Appendix C — File Reference Index](#appendix-c--file-reference-index)

---

## Executive Summary

### Would the system scale to 100k concurrent users today?

**No.** Three critical blockers:

1. **SSE streaming capped at 20 concurrent connections** — `streamAgentNormalized` is configured with `maxInstances: 20, concurrency: 1`. User #21 gets a 503 error. This is the single biggest blocker.

2. **Workout completion triggers write storm** — Completing one workout fires 35–45 Firestore writes synchronously (set_facts, weekly_stats, exercise_usage_stats, series, rollups). At 100k users × 3 workouts/week = 4.5M trigger writes/hour during peak.

3. **Rate limiting is per-instance, not global** — The in-memory `Map()` in `rate-limiter.js` resets on cold starts and doesn't share state across instances. A determined user can make `N × 120` agent requests/hour where N = number of function instances.

### What's already good?

- **Local-first iOS workout tracking** — Optimistic UI updates mean users never wait for Firestore during set logging. Well-architected `MutationCoordinator` pattern.
- **4-lane agent routing** — Fast Lane bypasses LLM entirely for copilot commands (`"done"`, `"8 @ 100"`). Sub-500ms latency.
- **HTTP connection pooling** — Agent-to-Firebase calls reuse TCP connections via `requests.Session()` with `HTTPAdapter(pool_connections=10, pool_maxsize=20)`.
- **Pre-computed training analysis** — Heavy analytics are pre-computed by background workers, not computed on-demand.
- **ContextVar isolation** — Per-request state isolation prevents cross-user data leaks in concurrent Vertex AI environments.

### Implementation Roadmap

| Phase | Duration | Items | Key Metric |
|-------|----------|-------|------------|
| **Phase 1: Emergency** | Week 1 | #1.1–#1.5 | SSE capacity 20→5,000; planning context 200ms→50ms |
| **Phase 2: UX Speed** | Weeks 2–3 | #2.1–#2.3 | App launch 2.5s→<500ms; Firestore reads -80% |
| **Phase 3: Scale** | Month 2 | #3.1–#3.5 | Trigger writes -80%; rate limiting global |
| **Phase 4: Optimize** | Ongoing | #4.1–#4.5 | LLM cost -10%; latency polish |

---

## Current Architecture Quick Reference

Read these docs before starting any implementation:

| Doc | Path | What It Covers |
|-----|------|----------------|
| System Architecture | `docs/SYSTEM_ARCHITECTURE.md` | Cross-layer data flows, schema contracts, auth patterns |
| Firebase Functions | `docs/FIREBASE_FUNCTIONS_ARCHITECTURE.md` | All endpoints, auth middleware, trigger documentation |
| iOS Architecture | `docs/IOS_ARCHITECTURE.md` | MVVM layers, services, repositories, views |
| Shell Agent | `docs/SHELL_AGENT_ARCHITECTURE.md` | 4-lane routing, ContextVars, tool definitions |
| Firestore Schema | `docs/FIRESTORE_SCHEMA.md` | All collections, document shapes, indexes, security rules |
| Security | `docs/SECURITY.md` | Auth model, IDOR prevention, input validation, rate limiting |

### Request Flow (Happy Path — Agent Streaming)

```
iOS App (DirectStreamingService.swift)
  │ POST /streamAgentNormalized (SSE)
  ▼
Firebase Function (stream-agent-normalized.js)
  │ 1. requireFlexibleAuth → verifyIdToken (JWT, ~5ms cached)
  │ 2. isPremiumUser(userId) → Firestore read (~30ms, NO CACHE) ← FIX #1.2
  │ 3. rateLimiter.check(userId) → in-memory Map (~0ms) ← FIX #3.2
  │ 4. getGcpToken() → cached or refresh (~10-200ms)
  │ 5. POST to Vertex AI :streamQuery (SSE)
  ▼
Vertex AI Agent Engine (agent_engine_app.py)
  │ 1. Parse context prefix → SessionContext
  │ 2. set_current_context(ctx)
  │ 3. route_request(message) → Lane routing
  │ 4. If Slow Lane: ShellAgent.run() → LLM + tools
  │    └─ tool_get_planning_context() → HTTP to Firebase → 4+ sequential Firestore reads ← FIX #1.4
  │ 5. Stream response chunks
  ▼
Firebase Function (event transformation)
  │ Parse NDJSON → transform → SSE events
  ▼
iOS App (handleIncomingStreamEvent)
```

---

## Phase 1 — Emergency Fixes (Week 1)

### 1.1 SSE Proxy Connection Cap

**Priority**: P0 — System literally cannot serve >20 concurrent agent conversations
**Severity**: CRITICAL
**Effort**: Low (configuration change)

#### Problem

The SSE streaming proxy `streamAgentNormalized` is configured with hard limits that cap the entire system at 20 concurrent agent streams:

```javascript
// File: firebase_functions/functions/index.js
// Line: ~230-233
exports.streamAgentNormalized = onRequestV2(
  { timeoutSeconds: 300, memory: '512MiB', maxInstances: 20, concurrency: 1 },
  requireFlexibleAuth(streamAgentNormalizedHandler)
);
```

- `maxInstances: 20` = Firebase will never spawn more than 20 function instances
- `concurrency: 1` = each instance handles exactly 1 request at a time
- **Result**: Maximum 20 simultaneous SSE streams across ALL users

At 100k users with even 0.5% streaming simultaneously = 500 concurrent streams needed. Current capacity handles 4% of that.

#### Fix

```javascript
// File: firebase_functions/functions/index.js
// Change the configuration:
exports.streamAgentNormalized = onRequestV2(
  {
    timeoutSeconds: 300,
    memory: '512MiB',
    maxInstances: 500,    // Was: 20. Support 500 instances.
    concurrency: 10       // Was: 1. Node.js async I/O handles 10 concurrent SSE streams per instance.
  },
  requireFlexibleAuth(streamAgentNormalizedHandler)
);
```

**Why `concurrency: 10` is safe for SSE:**
- SSE connections are I/O-bound (waiting on Vertex AI stream), not CPU-bound
- Node.js event loop handles concurrent async streams efficiently
- Each stream uses ~2–5MB memory (within 512MiB budget for 10 streams)
- The original `concurrency: 1` was overly conservative

**Capacity after fix**: 500 instances × 10 streams = **5,000 concurrent streams**

#### Files to Modify

| File | Change |
|------|--------|
| `firebase_functions/functions/index.js:~230-233` | Update `maxInstances` and `concurrency` |

#### Verification

1. Deploy the change: `cd firebase_functions/functions && npm run deploy`
2. Open 5 simultaneous agent conversations from different browser tabs
3. Verify all 5 stream without 503 errors
4. Check Cloud Console → Cloud Functions → `streamAgentNormalized` → Instances tab confirms multiple concurrent requests per instance

#### Cross-References

- SSE proxy implementation: `firebase_functions/functions/strengthos/stream-agent-normalized.js`
- iOS SSE client: `Povver/Povver/Services/DirectStreamingService.swift`
- Agent architecture: `docs/SHELL_AGENT_ARCHITECTURE.md` (section: "iOS Client Integration")

---

### 1.2 Subscription Gate Caching

**Priority**: P0 — Adds 20–50ms latency to every agent stream + every workout trigger
**Severity**: HIGH
**Effort**: Low

#### Problem

`isPremiumUser(userId)` does a fresh Firestore read on every call. No caching.

```javascript
// File: firebase_functions/functions/utils/subscription-gate.js
// Lines: 13-43
async function isPremiumUser(userId) {
  try {
    const db = admin.firestore();
    const userDoc = await db.collection('users').doc(userId).get();  // FRESH READ EVERY TIME

    if (!userDoc.exists) return false;

    const userData = userDoc.data();
    if (userData.subscription_override === 'premium') return true;
    if (userData.subscription_tier === 'premium') return true;

    return false;
  } catch (error) {
    return false;
  }
}
```

**Called from:**
- `strengthos/stream-agent-normalized.js` — Premium gate before every SSE stream
- `triggers/weekly-analytics.js:~575` — Every workout completion trigger
- `triggers/weekly-analytics.js:~752` — Every workout creation with end_time

**Impact at 100k users:**
- 500k+ unnecessary Firestore reads/week
- 20–50ms added latency to every agent stream start

#### Fix

Add a 5-minute in-memory cache. Expose an `invalidatePremiumCache(userId)` function for the subscription webhook to call.

```javascript
// File: firebase_functions/functions/utils/subscription-gate.js

const PREMIUM_CACHE_TTL_MS = 5 * 60 * 1000; // 5 minutes
const premiumCache = new Map();

async function isPremiumUser(userId) {
  // Check cache first
  const cached = premiumCache.get(userId);
  if (cached && Date.now() < cached.expiresAt) {
    return cached.isPremium;
  }

  try {
    const db = admin.firestore();
    const userDoc = await db.collection('users').doc(userId).get();

    if (!userDoc.exists) {
      premiumCache.set(userId, { isPremium: false, expiresAt: Date.now() + PREMIUM_CACHE_TTL_MS });
      return false;
    }

    const userData = userDoc.data();
    const isPremium = userData.subscription_override === 'premium' || userData.subscription_tier === 'premium';

    premiumCache.set(userId, { isPremium, expiresAt: Date.now() + PREMIUM_CACHE_TTL_MS });
    return isPremium;
  } catch (error) {
    return false;
  }
}

function invalidatePremiumCache(userId) {
  premiumCache.delete(userId);
}

module.exports = { isPremiumUser, invalidatePremiumCache };
```

**Then call `invalidatePremiumCache(userId)` from the subscription webhook:**

```javascript
// File: firebase_functions/functions/subscriptions/app-store-webhook.js
// After updating subscription fields, add:
const { invalidatePremiumCache } = require('../utils/subscription-gate');
invalidatePremiumCache(userId);
```

#### Files to Modify

| File | Change |
|------|--------|
| `firebase_functions/functions/utils/subscription-gate.js` | Add in-memory cache + invalidation export |
| `firebase_functions/functions/subscriptions/app-store-webhook.js` | Call `invalidatePremiumCache(userId)` after subscription update |

#### Verification

1. Run existing tests: `cd firebase_functions/functions && npm test`
2. Manual test: call `isPremiumUser` twice for same user, verify second call doesn't hit Firestore (check Cloud Logging)
3. Verify webhook invalidates cache correctly

#### Cross-References

- Subscription webhook: `firebase_functions/functions/subscriptions/app-store-webhook.js`
- User profile cache (reference pattern): `firebase_functions/functions/user/get-user.js:18-70` — existing 2-tier cache implementation to use as reference
- SSE proxy premium gate: `firebase_functions/functions/strengthos/stream-agent-normalized.js` (search for `isPremiumUser`)

---

### 1.3 GCP Token Caching in exchange-token

**Priority**: P0 — Adds 200–400ms to every iOS session start
**Severity**: HIGH
**Effort**: Low (copy existing pattern)

#### Problem

`exchange-token.js` fetches a fresh GCP access token on every call. The identical caching pattern already exists in `stream-agent-normalized.js` but was never applied here.

```javascript
// File: firebase_functions/functions/auth/exchange-token.js
// Current: NO caching — fresh GoogleAuth + getAccessToken() every call

// Compare with existing cache in:
// File: firebase_functions/functions/strengthos/stream-agent-normalized.js
// Lines: ~110-127 — proper token caching with 55-minute TTL
```

**Impact**: iOS calls `getServiceToken` on every conversation start. Without caching, each call pays:
- `GoogleAuth` client creation: ~50ms
- `getAccessToken()` network call: ~100–300ms
- Total: 200–400ms added to session start

#### Fix

Copy the token caching pattern from `stream-agent-normalized.js:110-127` into `exchange-token.js`:

```javascript
// File: firebase_functions/functions/auth/exchange-token.js
// Add at module level (outside handler):

let cachedGcpToken = null;
let gcpTokenExpiresAt = 0;

async function getCachedGcpToken() {
  const now = Date.now();
  // Return cached if valid (with 5-minute safety margin)
  if (cachedGcpToken && now < gcpTokenExpiresAt - (5 * 60 * 1000)) {
    return cachedGcpToken;
  }

  const auth = new GoogleAuth({ scopes: ['https://www.googleapis.com/auth/cloud-platform'] });
  const client = await auth.getClient();
  const tokenResponse = await client.getAccessToken();

  cachedGcpToken = tokenResponse.token || tokenResponse;
  gcpTokenExpiresAt = now + (55 * 60 * 1000); // 55 minutes (tokens valid for 60)

  return cachedGcpToken;
}

// Then in the handler, replace:
//   const client = await auth.getClient();
//   const tokenResponse = await client.getAccessToken();
// With:
//   const accessToken = await getCachedGcpToken();
```

#### Files to Modify

| File | Change |
|------|--------|
| `firebase_functions/functions/auth/exchange-token.js` | Add token caching (copy pattern from stream-agent-normalized.js:110-127) |

#### Verification

1. Call `getServiceToken` twice within 1 minute — second call should return instantly (check latency in Cloud Logging)
2. Verify token is valid for Vertex AI calls

#### Cross-References

- Existing token cache (reference implementation): `firebase_functions/functions/strengthos/stream-agent-normalized.js:110-127`
- Another instance of the same pattern: `firebase_functions/functions/canvas/open-canvas.js:30-42`
- iOS token consumer: `Povver/Povver/Services/DirectStreamingService.swift` — also check if iOS caches the returned token (it should cache until `expiryDate - 5min`)

---

### 1.4 Parallelize get-planning-context Reads

**Priority**: P0 — Adds 150ms+ latency to every agent planning request
**Severity**: HIGH
**Effort**: Low

#### Problem

`get-planning-context.js` performs 4+ sequential Firestore reads where they could run in parallel:

```javascript
// File: firebase_functions/functions/agents/get-planning-context.js
// Lines: ~140-262

// SEQUENTIAL (current — each awaits before next starts):
const userDoc = await firestore.collection('users').doc(callerUid).get();           // ~50ms
const attrsDoc = await firestore.collection('users').doc(callerUid)
  .collection('user_attributes').doc(callerUid).get();                               // ~50ms
// ... then routine read ...                                                         // ~50ms
// ... then template reads (Promise.all, but AFTER routine) ...                      // ~50ms
// Total: ~200ms minimum (4 sequential round-trips)

// PARALLEL (fix — all independent reads start simultaneously):
// Total: ~50ms (1 round-trip, all reads in parallel)
```

#### Fix

Restructure reads into two phases:
1. **Phase A** (parallel): User + attributes + workouts — these are independent
2. **Phase B** (depends on A): Routine + templates — needs `user.activeRoutineId` from Phase A

```javascript
// File: firebase_functions/functions/agents/get-planning-context.js
// Replace the sequential reads section (~lines 140-262) with:

// Phase A: All independent reads in parallel
const [userDoc, attrsDoc, workoutsSnapshot] = await Promise.all([
  firestore.collection('users').doc(callerUid).get(),
  firestore.collection('users').doc(callerUid)
    .collection('user_attributes').doc(callerUid).get(),
  includeRecentWorkouts
    ? firestore.collection('users').doc(callerUid)
        .collection('workouts')
        .orderBy('end_time', 'desc')
        .limit(workoutLimit)
        .get()
    : Promise.resolve(null),
]);

const user = userDoc.exists ? userDoc.data() : {};
const attributes = attrsDoc.exists ? attrsDoc.data() : {};

// Phase B: Routine + templates (depends on user.activeRoutineId from Phase A)
let routine = null;
let templates = [];

if (user.activeRoutineId) {
  const routineDoc = await firestore.collection('users').doc(callerUid)
    .collection('routines').doc(user.activeRoutineId).get();
  routine = routineDoc.exists ? { id: routineDoc.id, ...routineDoc.data() } : null;

  if (routine && routine.template_ids && includeTemplates) {
    // Use getAll for batch read (1 RPC instead of N parallel gets)
    const templateRefs = routine.template_ids.map(tid =>
      firestore.collection('users').doc(callerUid).collection('templates').doc(tid)
    );
    if (templateRefs.length > 0) {
      const templateDocs = await firestore.getAll(...templateRefs);
      templates = templateDocs
        .filter(doc => doc.exists)
        .map(doc => ({ id: doc.id, ...doc.data() }));
    }
  }
}
```

**Key improvement**: `firestore.getAll(...refs)` is a single RPC call regardless of how many refs are passed. This replaces the current `Promise.all(refs.map(r => r.get()))` pattern which creates N parallel RPCs.

#### Files to Modify

| File | Change |
|------|--------|
| `firebase_functions/functions/agents/get-planning-context.js` | Restructure sequential reads into parallel phases |

#### Verification

1. Run existing tests: `cd firebase_functions/functions && npm test`
2. Call `getPlanningContext` and compare response structure with pre-change response (should be identical)
3. Check Cloud Logging for reduced Firestore read latency

#### Cross-References

- Agent tool that calls this: `adk_agent/canvas_orchestrator/app/skills/coach_skills.py` → `get_training_context()`
- HTTP client: `adk_agent/canvas_orchestrator/app/libs/tools_common/http.py` (or `app/libs/tools_canvas/client.py`)
- Agent tools definition: `adk_agent/canvas_orchestrator/app/shell/tools.py` → `tool_get_training_context`

---

### 1.5 Recommendation Listener Leak

**Priority**: P1 — Accumulates orphaned Firestore listeners, wastes read quota
**Severity**: MEDIUM
**Effort**: Low

#### Problem

`RecommendationRepository.startListening()` is called in `MainTabsView.task` but `stopListening()` is never called anywhere. Listeners survive logout and accumulate across sessions.

```swift
// File: Povver/Povver/Repositories/RecommendationRepository.swift
// Lines: ~11-38 — startListening() creates addSnapshotListener
// stopListening() exists but is NEVER CALLED

// File: Povver/Povver/Views/MainTabsView.swift
// Line: ~140 — starts the listener on tab appearance
```

#### Fix

Call `stopListening()` in two places:

1. **On logout** — in `AuthService.signOut()` or wherever session teardown happens
2. **On ViewModel deinit** — if `RecommendationsViewModel` owns the listener lifecycle

```swift
// Option A: In AuthService.signOut() or RootView session teardown
RecommendationRepository.shared.stopListening()

// Option B: In RecommendationsViewModel (if it exists as ObservableObject)
deinit {
    RecommendationRepository.shared.stopListening()
}
```

Also audit all `addSnapshotListener` usage across the codebase to verify matching `.remove()` calls:
- Search pattern: `grep -r "addSnapshotListener" Povver/Povver/`
- Each result should have a corresponding `ListenerRegistration` stored and `.remove()` called

#### Files to Modify

| File | Change |
|------|--------|
| `Povver/Povver/Repositories/RecommendationRepository.swift` | Verify `stopListening()` removes listener correctly |
| `Povver/Povver/Views/RootView.swift` or `Services/AuthService.swift` | Call `stopListening()` on sign-out |
| `Povver/Povver/ViewModels/RecommendationsViewModel.swift` | Add cleanup in deinit |

#### Verification

1. Login → navigate to Coach tab (starts listener) → logout → login again
2. Check Firestore usage dashboard — should not see accumulating read operations from old listeners
3. Check Xcode console for Firestore listener debug messages

#### Cross-References

- Listener convention: `CLAUDE.md` → "Listener cleanup" rule
- CanvasViewModel listener pattern (correct implementation): `Povver/Povver/ViewModels/CanvasViewModel.swift:101-102`

---

## Phase 2 — UX Speed (Weeks 2–3)

### 2.1 iOS App Launch Waterfall

**Priority**: P1 — User sees blank screen for 2.5–4 seconds on every login
**Severity**: HIGH
**Effort**: Medium

#### Problem

After authentication, `RootView` blocks on sequential operations before showing `MainTabsView`:

```
Time 0ms:    User authenticates
Time 50ms:   RootView.onChange triggers
             ├─ SessionPreWarmer.preWarmIfNeeded()        [~2-3s network call]
             └─ prefetchLibraryData()                    [4 parallel endpoints:]
                 ├─ getUserTemplates()
                 ├─ getUserRoutines()
                 ├─ getNextWorkout()
                 └─ getActiveWorkout()
Time 2500ms: MainTabsView finally renders
Time 2600ms: CoachTabView.onAppear fires REDUNDANT:
             ├─ SessionPreWarmer.preWarmIfNeeded() AGAIN [debounced to 10s]
             └─ loadRecentCanvases()                    [Firestore query]
```

**Result**: 2.5–4 seconds of blank screen. On poor mobile networks: 4–6 seconds.

#### Fix (Three Parts)

**Part A: Show MainTabsView immediately with skeletons**

```swift
// File: Povver/Povver/Views/RootView.swift
// Lines: ~49-56
// Change: Don't await prefetch before showing main content.
// Show MainTabsView immediately, let each tab load its own data.

// BEFORE:
.onChange(of: authService.isAuthenticated) { _, isAuth in
    if isAuth {
        Task {
            await SessionPreWarmer.shared.preWarmIfNeeded()  // BLOCKS
            await FocusModeWorkoutService.shared.prefetchLibraryData()  // BLOCKS
        }
        flow = .main
    }
}

// AFTER:
.onChange(of: authService.isAuthenticated) { _, isAuth in
    if isAuth {
        flow = .main  // Show tabs IMMEDIATELY
        Task {
            // Fire-and-forget background prefetch
            async let _ = SessionPreWarmer.shared.preWarmIfNeeded()
            async let _ = FocusModeWorkoutService.shared.prefetchLibraryData()
        }
    }
}
```

**Part B: Remove redundant pre-warm from CoachTabView**

```swift
// File: Povver/Povver/Views/Tabs/CoachTabView.swift
// Lines: ~63-66
// REMOVE the redundant SessionPreWarmer.preWarmIfNeeded() call.
// RootView already fires it. The 10-second debounce is too short for tab switching.
```

**Part C: Remove redundant prefetch fallback from MainTabsView**

```swift
// File: Povver/Povver/Views/MainTabsView.swift
// Lines: ~138-145
// REMOVE the fallback prefetchLibraryData() call.
// RootView guarantees execution. The guard check adds complexity for no benefit.
```

**Part D (Future): Batch bootstrap endpoint**

Create `POST /getAppBootstrapData` that returns templates + routines + next workout + active workout in one round-trip instead of 4 parallel calls. This is a larger change and can be deferred to Phase 3.

#### Files to Modify

| File | Change |
|------|--------|
| `Povver/Povver/Views/RootView.swift:~49-56` | Show `.main` before awaiting prefetch |
| `Povver/Povver/Views/Tabs/CoachTabView.swift:~63-66` | Remove redundant pre-warm call |
| `Povver/Povver/Views/MainTabsView.swift:~138-145` | Remove redundant prefetch fallback |

#### Verification

1. Build and run on simulator: `xcodebuild -scheme Povver -destination 'platform=iOS Simulator,name=iPhone 16 Pro' build`
2. Login → measure time from auth success to first tab content visible
3. Should be <500ms (vs 2.5–4s before)
4. Verify all tab content still loads correctly (just asynchronously)

#### Cross-References

- Prefetch implementation: `Povver/Povver/Services/FocusModeWorkoutService.swift:1765-1790`
- Pre-warmer: `Povver/Povver/Services/SessionPreWarmer.swift`
- Tab structure: `docs/IOS_ARCHITECTURE.md` (section: "Tab Structure")

---

### 2.2 Wire CacheManager Into Repositories

**Priority**: P1 — 500+ unnecessary Firestore reads per session
**Severity**: HIGH
**Effort**: Medium

#### Problem

`CacheManager.swift` implements a proper actor-based memory+disk cache with configurable TTL. **Zero call sites reference it.** Meanwhile:

- **Exercise catalog**: `ExerciseRepository` fetches all 500+ exercises from Firestore on every Library tab visit
- **Templates**: Fetched 3x redundantly (prefetch + Library + detail views)
- **Workout history**: Full collection read on every History tab visit (no pagination — see #2.3)

```swift
// File: Povver/Povver/Services/CacheManager.swift
// Lines: 1-344
// Complete actor-based cache implementation — UNUSED

// File: Povver/Povver/Repositories/ExerciseRepository.swift
// Lines: ~13-45
// Fetches from Firestore every time — NO CACHING
```

#### Fix

Wire `CacheManager` into the three highest-volume repositories:

**Exercise Catalog (60-minute TTL — near-immutable data):**

```swift
// File: Povver/Povver/Repositories/ExerciseRepository.swift

func getExercises() async throws -> [Exercise] {
    let cacheKey = "exercises:all"
    if let cached: [Exercise] = await CacheManager.shared.get(cacheKey) {
        return cached
    }

    let exercises = try await fetchFromFirestore() // existing implementation
    await CacheManager.shared.set(cacheKey, value: exercises, ttl: 3600) // 60 min
    return exercises
}
```

**Templates (5-minute TTL — user-mutable):**

```swift
// File: Povver/Povver/Repositories/TemplateRepository.swift

func getUserTemplates(userId: String) async throws -> [WorkoutTemplate] {
    let cacheKey = "templates:\(userId)"
    if let cached: [WorkoutTemplate] = await CacheManager.shared.get(cacheKey) {
        return cached
    }

    let templates = try await fetchFromFirestore(userId: userId)
    await CacheManager.shared.set(cacheKey, value: templates, ttl: 300) // 5 min
    return templates
}

// Invalidate on mutation:
func createTemplate(_ template: WorkoutTemplate) async throws {
    // ... existing create logic ...
    await CacheManager.shared.remove("templates:\(template.userId)")
}
```

**Routines (5-minute TTL — user-mutable, same pattern as templates):**

Apply the same pattern to `RoutineRepository`.

#### Files to Modify

| File | Change |
|------|--------|
| `Povver/Povver/Repositories/ExerciseRepository.swift` | Add CacheManager reads with 60min TTL |
| `Povver/Povver/Repositories/TemplateRepository.swift` | Add CacheManager reads with 5min TTL + invalidation on mutations |
| `Povver/Povver/Repositories/RoutineRepository.swift` | Add CacheManager reads with 5min TTL + invalidation on mutations |

#### Verification

1. Open Library tab → exercises load (cache miss)
2. Navigate away and back → exercises load instantly (cache hit)
3. Create a new template → navigate to templates list → new template appears (cache invalidated)
4. Wait 6 minutes → exercises re-fetched from Firestore (TTL expired)

#### Cross-References

- CacheManager implementation: `Povver/Povver/Services/CacheManager.swift`
- Existing prefetch cache in FocusModeWorkoutService: `Povver/Povver/Services/FocusModeWorkoutService.swift` — has its own `cachedTemplates` property that should be consolidated into CacheManager

---

### 2.3 Server-Side Workout History Pagination

**Priority**: P1 — User with 200 workouts = 200 Firestore reads on every History tab visit
**Severity**: MEDIUM
**Effort**: Medium

#### Problem

`HistoryView` fetches ALL workouts from Firestore, then paginates in memory:

```swift
// File: Povver/Povver/Views/Tabs/HistoryView.swift
// Lines: ~171-198
// Fetches ENTIRE workout history, then shows 25 at a time
// "Load More" appends from in-memory cache — no actual pagination benefit

// File: Povver/Povver/Repositories/WorkoutRepository.swift
// getWorkouts() has no limit parameter — returns everything
```

#### Fix (Two Parts)

**Part A: Backend — Add cursor pagination to getUserWorkouts**

The Firebase Function `getUserWorkouts` (or `getWorkout` / `get-user-workouts.js`) needs a `limit` and `startAfter` parameter.

```javascript
// File: firebase_functions/functions/workouts/get-user-workouts.js
// Add parameters:
//   limit: number (default 25, max 100)
//   startAfter: string (workout document ID for cursor)

const limit = Math.min(parseInt(req.query.limit) || 25, 100);
const startAfter = req.query.startAfter;

let query = firestore.collection('users').doc(userId)
  .collection('workouts')
  .orderBy('end_time', 'desc')
  .limit(limit + 1); // Fetch 1 extra to determine hasMore

if (startAfter) {
  const cursorDoc = await firestore.collection('users').doc(userId)
    .collection('workouts').doc(startAfter).get();
  if (cursorDoc.exists) {
    query = query.startAfter(cursorDoc);
  }
}

const snapshot = await query.get();
const workouts = snapshot.docs.slice(0, limit).map(doc => ({ id: doc.id, ...doc.data() }));
const hasMore = snapshot.docs.length > limit;

return ok(res, { workouts, hasMore, cursor: workouts.length > 0 ? workouts[workouts.length - 1].id : null });
```

**Part B: iOS — Use cursor pagination in HistoryView**

```swift
// File: Povver/Povver/Views/Tabs/HistoryView.swift
// Replace full-collection fetch with paginated calls:

@Published var workouts: [Workout] = []
@Published var hasMore = true
@Published var cursor: String? = nil

func loadMore() async {
    guard hasMore, !isLoading else { return }
    isLoading = true

    let result = try await workoutRepository.getWorkouts(
        userId: userId,
        limit: 25,
        startAfter: cursor
    )

    workouts.append(contentsOf: result.workouts)
    hasMore = result.hasMore
    cursor = result.cursor
    isLoading = false
}
```

#### Files to Modify

| File | Change |
|------|--------|
| `firebase_functions/functions/workouts/get-user-workouts.js` | Add `limit` and `startAfter` parameters |
| `Povver/Povver/Repositories/WorkoutRepository.swift` | Add paginated `getWorkouts(limit:startAfter:)` method |
| `Povver/Povver/Views/Tabs/HistoryView.swift` | Replace full fetch with cursor-based pagination |

#### Cross-References

- Workout model: `Povver/Povver/Models/Workout.swift`
- Existing pagination pattern (reference): check if `getUserTemplates` has pagination
- Firestore schema for workouts: `docs/FIRESTORE_SCHEMA.md` (section: workouts subcollection)

---

## Phase 3 — Scale Infrastructure (Month 2)

### 3.1 Async Analytics Processing (Trigger Fan-Out)

**Priority**: P0 — Workout completion triggers 35–45 synchronous Firestore writes
**Severity**: CRITICAL
**Effort**: High

#### Problem

`onWorkoutCompleted` in `triggers/weekly-analytics.js` does massive synchronous work:

```
Workout completion trigger fires:
├── 1. Update weekly_stats/{weekId} (transaction)
├── 2. Upsert analytics_rollup/{weekId}
├── 3. Append N × muscle_weekly_series (10 writes for 10 muscle groups)
├── 4. Append M × exercise_daily_series (8 writes for 8 exercises)
├── 5. Generate set_facts (24 documents for 24 sets)
├── 6. Update series_exercises
├── 7. Check isPremiumUser (Firestore read — see #1.2)
├── 8. Enqueue training_analysis_job (if premium)
├── 9. Update exercise_usage_stats (8 transactions for 8 exercises)
└── Total: 35-45 writes, 5-15 seconds execution
```

**At 100k users × 3 workouts/week:**
- 300k trigger executions/week
- 10.5–13.5M Firestore writes/week from triggers alone
- Cost: ~$19–24/week in Firestore writes ($1,000–1,250/year)
- Trigger execution: 5–15s per workout (can timeout, causing retries and duplicate writes)

**Risk**: Firestore triggers are "at-least-once". Long-running triggers that timeout will retry, causing duplicate analytics. The current code has some idempotency but not comprehensive.

#### Fix

Replace the heavy trigger with a lightweight job enqueue. Process analytics in a background Cloud Run worker.

**Step 1: Slim trigger (enqueue only)**

```javascript
// File: firebase_functions/functions/triggers/weekly-analytics.js
// REPLACE the heavy onWorkoutCompleted with:

exports.onWorkoutCompleted = onDocumentUpdated(
  'users/{userId}/workouts/{workoutId}',
  async (event) => {
    const beforeStatus = event.data.before.data()?.status;
    const afterStatus = event.data.after.data()?.status;

    // Only fire on actual completion
    if (beforeStatus === 'completed' || afterStatus !== 'completed') return;

    const { userId, workoutId } = event.params;

    // Single write — enqueue analytics job
    await admin.firestore().collection('analytics_processing_queue').add({
      type: 'WORKOUT_ANALYTICS',
      userId,
      workoutId,
      status: 'queued',
      created_at: admin.firestore.FieldValue.serverTimestamp(),
      // Include workout snapshot to avoid re-read
      workout_snapshot: event.data.after.data(),
    });

    logger.info('[onWorkoutCompleted] Job enqueued', { userId, workoutId });
  }
);
```

**Step 2: Background worker (Cloud Run Job or Cloud Function)**

Create a new scheduled function or Cloud Run Job that polls `analytics_processing_queue` and processes jobs in batches. The worker does all the heavy analytics work that currently lives in the trigger.

**Step 3: Migrate existing analytics logic to worker**

Move the body of the current `onWorkoutCompleted` trigger into the worker, with:
- Batch writes (collect all writes, execute in a single `batch.commit()`)
- Idempotency (check if job already processed)
- Retry with exponential backoff
- Rate limiting (max N jobs/minute to prevent Firestore write spikes)

#### Files to Modify

| File | Change |
|------|--------|
| `firebase_functions/functions/triggers/weekly-analytics.js` | Replace heavy trigger with job enqueue |
| `firebase_functions/functions/workers/analytics-processor.js` | **NEW FILE** — background analytics worker |
| `firebase_functions/functions/index.js` | Export new worker function |

#### Cross-References

- Current trigger implementation: `firebase_functions/functions/triggers/weekly-analytics.js` (lines 430–788)
- Set facts generator: `firebase_functions/functions/training/set-facts-generator.js`
- Exercise usage stats: `firebase_functions/functions/triggers/weekly-analytics.js` (search for `updateExerciseUsageStats`)
- Training analysis job queue: `firebase_functions/functions/triggers/weekly-analytics.js` (search for `training_analysis_jobs`)
- Existing worker pattern (reference): `adk_agent/training_analyst/workers/analyst_worker.py`

---

### 3.2 Global Rate Limiting

**Priority**: P0 — Current in-memory rate limiter is bypassable
**Severity**: CRITICAL
**Effort**: Medium

#### Problem

See [Appendix A](#appendix-a--current-bottleneck-map) for full analysis. The `rate-limiter.js` uses a per-instance `Map()` that resets on cold starts and doesn't share state across instances.

#### Fix

Add a Firestore-based daily user cap as a circuit breaker, keeping the in-memory limiter for burst protection:

```javascript
// File: firebase_functions/functions/utils/rate-limiter.js
// Add a Firestore-based daily cap alongside the existing in-memory limiter:

async function checkDailyLimit(userId, dailyMax = 500) {
  const db = admin.firestore();
  const today = new Date().toISOString().slice(0, 10); // YYYY-MM-DD
  const ref = db.collection('rate_limits').doc(`${userId}_${today}`);

  return db.runTransaction(async (tx) => {
    const doc = await tx.get(ref);
    const count = doc.exists ? doc.data().count : 0;

    if (count >= dailyMax) {
      logger.warn('[rate_limit] Daily limit exceeded', { userId, count, dailyMax });
      return false;
    }

    tx.set(ref, {
      count: count + 1,
      userId,
      date: today,
      updated_at: admin.firestore.FieldValue.serverTimestamp()
    }, { merge: true });

    return true;
  });
}
```

Add TTL to rate_limit documents so they auto-clean:
- Set `expires_at` field to `today + 2 days`
- Configure Firestore TTL policy on `rate_limits` collection

#### Files to Modify

| File | Change |
|------|--------|
| `firebase_functions/functions/utils/rate-limiter.js` | Add `checkDailyLimit()` function |
| `firebase_functions/functions/strengthos/stream-agent-normalized.js` | Call `checkDailyLimit()` before streaming |
| `firestore.rules` | Add rules for `rate_limits` collection (admin-only writes) |

#### Cross-References

- Current rate limiter: `firebase_functions/functions/utils/rate-limiter.js`
- Where it's called: `firebase_functions/functions/strengthos/stream-agent-normalized.js` (search for `agentLimiter`)
- Security doc: `docs/SECURITY.md`

---

### 3.3 Function Bundle Splitting

**Priority**: P1 — Cold starts load 106 functions, takes 1–3 seconds
**Severity**: MEDIUM
**Effort**: High

#### Problem

All 106 functions are exported from a single `index.js`. Every cold start loads all function code, even if only one function is invoked.

#### Fix

Split into 3 deployment groups using Firebase's codebase feature:

```json
// File: firebase.json
{
  "functions": [
    {
      "source": "functions",
      "codebase": "hot",
      "predeploy": ["npm --prefix functions run lint"],
      "only": ["logSet", "getActiveWorkout", "completeCurrentSet",
               "patchActiveWorkout", "streamAgentNormalized", "startActiveWorkout",
               "completeActiveWorkout", "addExercise", "swapExercise",
               "autofillExercise", "artifactAction", "openCanvas"]
    },
    {
      "source": "functions",
      "codebase": "warm",
      "only": ["getPlanningContext", "getUser", "getUserWorkouts",
               "getUserTemplates", "getUserRoutines", "getTemplate",
               "getRoutine", "searchExercises", "getServiceToken"]
    },
    {
      "source": "functions",
      "codebase": "cold",
      "only": ["*"]  // Everything else
    }
  ]
}
```

**Note**: This requires restructuring `index.js` to support selective exports. This is a significant refactor — defer to Phase 3.

#### Files to Modify

| File | Change |
|------|--------|
| `firebase.json` | Add codebase splitting configuration |
| `firebase_functions/functions/index.js` | Restructure exports for selective loading |

---

### 3.4 Firestore TTL Policies

**Priority**: P1 — Unbounded collection growth
**Severity**: MEDIUM
**Effort**: Low-Medium

#### Problem

Several collections grow without bounds:

| Collection | Growth Rate (100k users) | Recommendation |
|------------|--------------------------|----------------|
| `set_facts` | 45 docs/user/week → 1.17B docs in 5 years | 2-year TTL |
| `workspace_entries` | 75M events/week | 30-day TTL (or remove if canvas deprecated) |
| `idempotency` (in active_workouts) | 24 docs/workout | 7-day TTL |
| `rate_limits` (new, from #3.2) | 1 doc/user/day | 2-day TTL |
| `template changelog` | Has 90-day `expires_at` but verify TTL policy is deployed | Verify |

#### Fix

1. Add `expires_at` field to documents in each collection
2. Configure Firestore TTL policy via Firebase Console or `gcloud` CLI:

```bash
gcloud firestore fields ttls update expires_at \
  --collection-group=set_facts \
  --project=myon-53d85

gcloud firestore fields ttls update expires_at \
  --collection-group=workspace_entries \
  --project=myon-53d85

gcloud firestore fields ttls update expires_at \
  --collection-group=rate_limits \
  --project=myon-53d85
```

3. Backfill `expires_at` on existing documents (batch script)

#### Files to Modify

| File | Change |
|------|--------|
| `firebase_functions/functions/training/set-facts-generator.js` | Add `expires_at` field (2 years from `workout_date`) |
| `firebase_functions/functions/strengthos/stream-agent-normalized.js` | Add `expires_at` to workspace_entries writes (30 days) |
| `firebase_functions/functions/active_workout/log-set.js` | Add `expires_at` to idempotency docs (7 days) |
| `scripts/backfill_ttl.js` | **NEW** — backfill `expires_at` on existing documents |

---

### 3.5 v1 to v2 Function Migration

**Priority**: P2 — v1 = 1 request per instance; v2 with concurrency = 80 requests per instance
**Severity**: MEDIUM
**Effort**: Medium (per-function, low risk)

#### Problem

~80 functions still use v1 (`functions.https.onRequest`), which spawns a new instance for every concurrent request. v2 with `concurrency: 80` handles 80 concurrent requests per instance.

#### Fix

Migrate high-traffic v1 functions to v2 format. Priority order:

1. `getUser` / `updateUser` — high frequency user profile ops
2. `getUserTemplates` / `getTemplate` / `createTemplate` — template CRUD
3. `getUserRoutines` / `getRoutine` / `createRoutine` — routine CRUD
4. `getExercises` / `searchExercises` — catalog reads
5. All remaining v1 functions

Migration pattern:
```javascript
// BEFORE (v1):
exports.getUser = functions.https.onRequest((req, res) => withApiKey(getUser)(req, res));

// AFTER (v2):
const { onRequest } = require('firebase-functions/v2/https');
exports.getUser = onRequest(
  { memory: '256MiB', maxInstances: 200, concurrency: 80 },
  (req, res) => withApiKey(getUser)(req, res)
);
```

---

## Phase 4 — Optimization (Ongoing)

### 4.1 Expand Fast Lane Patterns

**Effort**: Low | **Impact**: ~10% reduction in LLM costs

Add more regex patterns to `adk_agent/canvas_orchestrator/app/shell/router.py` for common queries that don't need LLM reasoning:

| Pattern | Intent | Response | Saves |
|---------|--------|----------|-------|
| `^(help\|\\?)$` | HELP | Static help text | $0.15/req |
| `^status$` | STATUS | Cached routine/workout info | $0.15/req |
| `^(summary\|recap)$` | SUMMARY | Cached workout summary | $0.15/req |

**File**: `adk_agent/canvas_orchestrator/app/shell/router.py:~58-79`

### 4.2 Planning Context Caching

**Effort**: Medium | **Impact**: 5–8 Firestore reads → 1 read per agent interaction

Cache planning context in Firestore under `users/{uid}/agent_cache/planning_context` with 5-minute TTL. Invalidate on routine/template mutations.

**Files**: `firebase_functions/functions/agents/get-planning-context.js`

### 4.3 Batch Analytics Writes

**Effort**: Medium | **Impact**: 18+ individual writes → 1 batched write on workout completion

Collect all muscle/exercise series writes into a single `db.batch()` call instead of individual writes. Part of the #3.1 worker implementation.

**File**: The new `firebase_functions/functions/workers/analytics-processor.js`

### 4.4 Training Analyst Horizontal Scaling

**Effort**: Low | **Impact**: Prevents job queue backlog at scale

Configure Cloud Run Job for `adk_agent/training_analyst/` with:
- `maxInstances: 20`
- Job prioritization (post-workout = P1, weekly = P2, daily = P3)
- Rate limiting (max 1 analysis per user per hour)

**File**: `adk_agent/training_analyst/` deployment configuration

### 4.5 iOS SSE Connection Reuse

**Effort**: Medium | **Impact**: Saves 200–500ms TCP+TLS handshake on mobile

Reuse `URLSession` across queries in the same conversation. Currently each `streamQuery` call creates a new connection.

**File**: `Povver/Povver/Services/DirectStreamingService.swift:~112-268`

---

## Appendix A — Current Bottleneck Map

```
USER ACTION                    BOTTLENECK                           FIX ITEM
───────────────────────────────────────────────────────────────────────────────
App Launch                     Sequential prefetch waterfall         #2.1
                               No caching on exercise catalog        #2.2
                               Full workout history load              #2.3

Open Agent Chat                SSE proxy capped at 20 instances      #1.1
                               GCP token not cached (exchange)        #1.3
                               Premium check not cached               #1.2

Send Agent Message             Planning context: 4 sequential reads  #1.4
                               Rate limiter per-instance only         #3.2

During Workout (log set)       [OK — local-first, optimistic UI]     —

Complete Workout                Trigger fan-out: 35-45 writes         #3.1
                               Premium check (uncached) in trigger    #1.2

Browse Library                 Exercise catalog: 500+ reads           #2.2
Browse History                 Full collection scan                   #2.3

Background (cold start)        106 functions loaded per instance      #3.3
Background (data growth)       Unbounded set_facts, workouts          #3.4
```

---

## Appendix B — Cost Projections

### Current (estimated at 100k DAU)

| Component | Monthly Cost | Notes |
|-----------|-------------|-------|
| Firestore Reads | ~$90k | 500+ reads/session × 100k users |
| Firestore Writes | ~$25k | Trigger fan-out dominates |
| LLM Tokens (Gemini Flash) | ~$630k | 200k requests/day × $0.15 avg |
| Firebase Functions | ~$20k | Instance hours |
| **Total** | **~$765k/mo** | |

### After All Optimizations (estimated)

| Component | Monthly Cost | Savings |
|-----------|-------------|---------|
| Firestore Reads | ~$18k | -80% (caching) |
| Firestore Writes | ~$5k | -80% (async analytics) |
| LLM Tokens | ~$540k | -15% (expanded Fast Lane) |
| Firebase Functions | ~$12k | -40% (v2 migration, fewer instances) |
| **Total** | **~$575k/mo** | **-$190k/mo (25%)** |

---

## Appendix C — File Reference Index

### Firebase Functions (Backend)

| File | Relevance | Fix Items |
|------|-----------|-----------|
| `firebase_functions/functions/index.js` | Function exports, v2 configs | #1.1, #3.3, #3.5 |
| `firebase_functions/functions/strengthos/stream-agent-normalized.js` | SSE proxy, premium gate, rate limit | #1.1, #1.2, #3.2 |
| `firebase_functions/functions/agents/get-planning-context.js` | Sequential reads | #1.4, #4.2 |
| `firebase_functions/functions/auth/exchange-token.js` | Token caching gap | #1.3 |
| `firebase_functions/functions/utils/subscription-gate.js` | Premium check, no cache | #1.2 |
| `firebase_functions/functions/utils/rate-limiter.js` | Per-instance rate limiter | #3.2 |
| `firebase_functions/functions/triggers/weekly-analytics.js` | Trigger fan-out (35-45 writes) | #3.1 |
| `firebase_functions/functions/training/set-facts-generator.js` | Set facts generation | #3.1, #3.4 |
| `firebase_functions/functions/active_workout/log-set.js` | Hot-path set logging | #3.4 (TTL) |
| `firebase_functions/functions/active_workout/complete-active-workout.js` | Completion flow | #3.1 |
| `firebase_functions/functions/user/get-user.js` | Reference cache implementation | #1.2 (pattern) |
| `firebase_functions/functions/subscriptions/app-store-webhook.js` | Subscription updates | #1.2 (invalidation) |
| `firebase_functions/functions/workouts/get-user-workouts.js` | Workout history query | #2.3 |
| `firebase_functions/functions/canvas/open-canvas.js` | Reference token cache | #1.3 (pattern) |

### iOS (Client)

| File | Relevance | Fix Items |
|------|-----------|-----------|
| `Povver/Povver/Views/RootView.swift` | App launch waterfall | #2.1 |
| `Povver/Povver/Views/MainTabsView.swift` | Redundant prefetch | #2.1 |
| `Povver/Povver/Views/Tabs/CoachTabView.swift` | Redundant pre-warm | #2.1 |
| `Povver/Povver/Views/Tabs/HistoryView.swift` | Client-side pagination | #2.3 |
| `Povver/Povver/Services/CacheManager.swift` | Unused cache infrastructure | #2.2 |
| `Povver/Povver/Services/DirectStreamingService.swift` | SSE client, connection reuse | #4.5 |
| `Povver/Povver/Services/SessionPreWarmer.swift` | Pre-warming logic | #2.1 |
| `Povver/Povver/Services/FocusModeWorkoutService.swift` | Prefetch orchestration | #2.1 |
| `Povver/Povver/Repositories/ExerciseRepository.swift` | No caching | #2.2 |
| `Povver/Povver/Repositories/TemplateRepository.swift` | No caching | #2.2 |
| `Povver/Povver/Repositories/RoutineRepository.swift` | No caching | #2.2 |
| `Povver/Povver/Repositories/WorkoutRepository.swift` | No pagination | #2.3 |
| `Povver/Povver/Repositories/RecommendationRepository.swift` | Listener leak | #1.5 |
| `Povver/Povver/ViewModels/RecommendationsViewModel.swift` | Missing cleanup | #1.5 |

### Agent System (Vertex AI)

| File | Relevance | Fix Items |
|------|-----------|-----------|
| `adk_agent/canvas_orchestrator/app/shell/router.py` | Fast Lane patterns | #4.1 |
| `adk_agent/canvas_orchestrator/app/shell/tools.py` | Tool definitions | #4.2 |
| `adk_agent/canvas_orchestrator/app/skills/coach_skills.py` | Planning context consumer | #1.4, #4.2 |
| `adk_agent/canvas_orchestrator/app/libs/tools_common/http.py` | HTTP connection pooling | (already good) |
| `adk_agent/canvas_orchestrator/app/libs/tools_canvas/client.py` | Firebase client | #1.4 |
| `adk_agent/training_analyst/workers/analyst_worker.py` | Background worker | #4.4 |

### Configuration & Infrastructure

| File | Relevance | Fix Items |
|------|-----------|-----------|
| `firebase.json` | Function deployment config | #3.3 |
| `firestore.rules` | Security rules | #3.2, #3.4 |
| `firestore.indexes.json` | Composite indexes | (verify) |

### Documentation (Update After Implementation)

| File | When to Update |
|------|----------------|
| `docs/SYSTEM_ARCHITECTURE.md` | After #3.1 (async analytics), #3.2 (rate limiting) |
| `docs/FIREBASE_FUNCTIONS_ARCHITECTURE.md` | After #3.1, #3.3, #3.5 |
| `docs/IOS_ARCHITECTURE.md` | After #2.1, #2.2, #2.3 |
| `docs/FIRESTORE_SCHEMA.md` | After #3.2 (rate_limits collection), #3.4 (TTL fields) |
| `docs/SECURITY.md` | After #3.2 (global rate limiting) |
