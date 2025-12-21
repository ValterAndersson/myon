# Canvas Architecture & Optimization Plan

> **Document Version:** 1.0  
> **Date:** December 21, 2024  
> **Status:** Active Development

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Vision](#vision)
3. [Current State Analysis](#current-state-analysis)
4. [Architecture Design](#architecture-design)
5. [Phase 1: Canvas Optimization](#phase-1-canvas-optimization)
6. [Phase 2: Active Workout Support](#phase-2-active-workout-support)
7. [Technical Specifications](#technical-specifications)
8. [Implementation Roadmap](#implementation-roadmap)

---

## Executive Summary

### The Problem

Canvas initialization and agent interaction currently takes **30-60+ seconds** from user query to first visible agent response. This latency is unacceptable for a modern, interactive experience and makes real-time workout coaching impossible.

### The Solution

A two-phase approach:
1. **Phase 1**: Optimize the current Canvas architecture for planning and insights (target: <10s first response)
2. **Phase 2**: Build event-driven active workout coaching with real-time agent awareness (target: <2s coaching feedback)

### Key Principles

- **Single Interface**: Canvas is the unified workspace for ALL user interactions
- **Agent Always Available**: The agent should be accessible at any point
- **Mode-Appropriate Speed**: Planning can take 5-15s; workout coaching must be <2s
- **Future-Ready**: Architecture supports voice input and sensor data integration

---

## Vision

### What Canvas Should Be

Canvas is the **single interface** where users interact with their AI strength coach. It handles:

```
┌────────────────────────────────────────────────────────────────────────────┐
│                           MYON CANVAS                                       │
│                                                                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐            │
│  │  PLANNING       │  │  ACTIVE WORKOUT │  │  INSIGHTS       │            │
│  │                 │  │                 │  │                 │            │
│  │  • Routines     │  │  • Live session │  │  • Analysis     │            │
│  │  • Programs     │  │  • Set coaching │  │  • Charts       │            │
│  │  • Single       │  │  • Voice input  │  │  • Trends       │            │
│  │    workouts     │  │  • Swaps/adjusts│  │  • Recs         │            │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘            │
│                                                                             │
│                    All powered by multi-agent orchestration                 │
│                                                                             │
└────────────────────────────────────────────────────────────────────────────┘
```

### User Journey Example

```
1. User: "Plan my leg day"
   → Agent thinks, searches exercises, proposes plan
   → Session plan card appears (5-10s) ✓

2. User: Accepts plan, taps "Start Workout"
   → Workout begins, agent enters observer mode
   → Agent sees full workout schema

3. User: Completes sets, logs RIR
   → Each event streams to agent
   → Agent stays silent for normal sets
   → Agent intervenes on failure (RIR=0): "Tough set! Consider dropping 5kg..."

4. User: "What should I do next?" (voice or text)
   → Agent responds with specific guidance (<2s)

5. User: Completes workout
   → "Analyze my session"
   → Charts and insights appear
```

### Why This Matters

- **Unified Experience**: No context switching between apps/modes
- **Contextual AI**: Agent always knows what's happening
- **Real-Time Coaching**: Like having a spotter who knows your history
- **Future-Ready**: Voice + sensors + real-time = next-gen training

---

## Current State Analysis

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            CURRENT FLOW                                      │
│                                                                              │
│  iOS App (CanvasScreen)                                                      │
│       │                                                                      │
│       ├──1. bootstrapCanvas() ────────────────> Firebase Function            │
│       │      [WAIT ~2-5s]                           │                        │
│       │                                             ▼                        │
│       │                                       Firestore query/create         │
│       │                                                                      │
│       ├──2. initializeSession() ──────────────> Firebase Function            │
│       │      [WAIT ~10-30s]                         │                        │
│       │                                             ▼                        │
│       │                                       Vertex AI create_session       │
│       │                                       (cold start penalty)           │
│       │                                                                      │
│       ├──3. purgeCanvas() ────────────────────> Firebase Function            │
│       │      [WAIT ~2-5s]                           │                        │
│       │                                             ▼                        │
│       │                                       Batch delete workspace_entries │
│       │                                                                      │
│       ├──4. Attach Firestore listeners (5+)                                  │
│       │      [WAIT for first snapshot]                                       │
│       │                                                                      │
│       ├──5. isReady = true                                                   │
│       │                                                                      │
│       └──6. startSSEStream() ─────────────────> Firebase Function            │
│              [START AGENT WORK]                     │                        │
│                                                     ▼                        │
│                                               streamAgentNormalized          │
│                                                     │                        │
│                                                     ▼                        │
│                                               Vertex AI streamQuery          │
│                                                     │                        │
│                                                     ▼                        │
│                                               Agent processes...             │
│                                               - tool_search_exercises        │
│                                               - tool_create_workout_plan     │
│                                               - tool_publish_workout_plan    │
│                                                                              │
│  TOTAL TIME: 30-60+ seconds                                                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Identified Bottlenecks

| Bottleneck | Impact | Root Cause |
|------------|--------|------------|
| **Sequential HTTP calls** | +10-20s | bootstrapCanvas → wait → initializeSession → wait → purgeCanvas |
| **forceNew: true** | +15-30s | Creates new Vertex AI session every time, bypassing 30-min reuse |
| **Vertex AI cold start** | +10-20s | Agent runtime initialization on new session |
| **Unnecessary purge** | +2-5s | purgeCanvas called even for fresh sessions |
| **Double session creation** | +5-10s | initializeSession creates one, streamAgentNormalized may create another |
| **Multiple Firestore listeners** | +2-3s | 5+ listeners attached sequentially |

### Code Evidence

**CanvasViewModel.swift** - The `forceNew: true` flag:
```swift
// PROBLEM: Forces new session every time, bypassing 30-minute reuse!
let sessionId = try await self.service.initializeSession(
    canvasId: cid, 
    purpose: purpose, 
    forceNew: true  // ← This is the killer
)
```

**Sequential Operations**:
```swift
// PROBLEM: All operations are sequential
let cid = try await self.service.bootstrapCanvas(for: userId, purpose: purpose)
// wait...
let sessionId = try await self.service.initializeSession(canvasId: cid, ...)
// wait...
try await self.service.purgeCanvas(userId: userId, canvasId: cid, ...)
// wait...
// THEN attach listeners
// THEN mark isReady = true
// THEN start SSE stream
```

---

## Architecture Design

### Two-System Problem

Currently, there are **two disconnected systems**:

1. **Canvas + Agent** (conversation-based, 30-60s latency)
2. **ActiveWorkoutManager + Firebase Functions** (local state, <100ms)

These systems don't communicate. Canvas doesn't know about active workouts, and active workouts don't have agent coaching.

### Unified Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        UNIFIED CANVAS ARCHITECTURE                           │
│                                                                              │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                           iOS CANVAS                                   │  │
│  │                                                                        │  │
│  │  Single UI that handles all modes:                                     │  │
│  │  - Planning conversations                                              │  │
│  │  - Active workout with set-by-set tracking                            │  │
│  │  - Post-workout analysis                                               │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                     │                                        │
│           ┌─────────────────────────┼─────────────────────────┐             │
│           │                         │                         │              │
│           ▼                         ▼                         ▼              │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐         │
│  │ CONVERSATIONAL  │    │   WORKOUT OPS   │    │  AGENT PUSH     │         │
│  │ (Slow Path)     │    │   (Fast Path)   │    │  (Background)   │         │
│  │                 │    │                 │    │                 │          │
│  │ • Planning      │    │ • Log set       │    │ • Proactive     │          │
│  │ • Analysis      │    │ • Swap exercise │    │   coaching      │          │
│  │ • Questions     │    │ • Adjust weight │    │ • Triggered     │          │
│  │                 │    │                 │    │   suggestions   │          │
│  │ Vertex AI       │    │ Firebase Fn     │    │ Firestore       │          │
│  │ (5-15s OK)      │    │ (<200ms)        │    │ triggers        │          │
│  └─────────────────┘    └─────────────────┘    └─────────────────┘         │
│           │                         │                         │              │
│           └─────────────────────────┼─────────────────────────┘             │
│                                     │                                        │
│                                     ▼                                        │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                           FIRESTORE                                    │  │
│  │                                                                        │  │
│  │  users/{uid}/canvases/{canvasId}/                                      │  │
│  │    ├── cards/              (agent publishes here)                      │  │
│  │    ├── workspace_entries/  (conversation log)                          │  │
│  │    ├── active_workout/     (NEW: workout state during session)         │  │
│  │    └── events/             (telemetry)                                 │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Event-Driven Agent Coaching (Phase 2)

For active workout mode, the agent operates in "Observer Mode":

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     ACTIVE WORKOUT - AGENT OBSERVER MODE                     │
│                                                                              │
│  Agent receives ALL events but only responds when:                           │
│  1. Critical trigger (failure, form breakdown, injury risk)                  │
│  2. User asks directly (text or voice)                                       │
│  3. Coaching opportunity (milestone, encouragement)                          │
│                                                                              │
│  Event Stream:                                                               │
│  ├── [00:00] workout_started                     → NO RESPONSE              │
│  ├── [02:15] set_complete: 80kg×8 RIR=2          → NO RESPONSE              │
│  ├── [05:30] set_complete: 85kg×7 RIR=1          → NO RESPONSE              │
│  ├── [08:45] set_complete: 85kg×5 RIR=0 ⚠️       → RESPOND!                 │
│  │           "That was a grinder! Consider 80kg for the next set."          │
│  ├── [12:00] user_message: "Should I push through?"  → RESPOND              │
│  │           "Given the RIR=0, I'd recommend..."                            │
│  └── [45:00] workout_complete                    → RESPOND (summary)        │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Event Schema with Response Hints

```javascript
// Every event includes hints for the agent
{
  type: "set_complete",
  timestamp: 1703185200,
  payload: {
    exercise_id: "barbell-back-squat",
    set_index: 2,
    actual: {
      reps: 5,
      weight: 85,
      rir: 0,
      form_score: null  // Future: from sensors
    },
    prescribed: {
      reps: 8,
      rir: 2
    }
  },
  // Response hints guide agent behavior
  hints: {
    deviation_type: "rep_failure",
    rir_deviation: -2,
    intensity_flag: "FAILURE",  // NO_CONCERN | CONCERN | FAILURE
    requires_intervention: true
  },
  context: {
    workout_progress: "3/12 sets",
    time_elapsed_min: 8,
    user_fatigue_estimate: "moderate"
  }
}
```

---

## Phase 1: Canvas Optimization

### Goals

- First agent response: **<10 seconds** (down from 30-60s)
- Subsequent responses: **<5 seconds**
- Session reuse rate: **>80%**

### Changes Required

#### 1.1 Remove `forceNew: true` (Immediate Impact)

**File**: `MYON2/MYON2/ViewModels/CanvasViewModel.swift`

```swift
// BEFORE
let sessionId = try await self.service.initializeSession(
    canvasId: cid, 
    purpose: purpose, 
    forceNew: true
)

// AFTER
let sessionId = try await self.service.initializeSession(
    canvasId: cid, 
    purpose: purpose, 
    forceNew: false  // Enable 30-minute session reuse
)
```

**Why**: This single change enables the 30-minute session reuse window. Reusing a warm session eliminates the 15-30s Vertex AI cold start.

#### 1.2 Parallelize Startup Operations

**File**: `MYON2/MYON2/ViewModels/CanvasViewModel.swift`

```swift
// BEFORE (Sequential - ~20s)
let cid = try await self.service.bootstrapCanvas(for: userId, purpose: purpose)
let sessionId = try await self.service.initializeSession(canvasId: cid, ...)
try await self.service.purgeCanvas(userId: userId, canvasId: cid, ...)

// AFTER (Parallel - ~8s)
// 1. Bootstrap canvas first (needed for canvas ID)
let cid = try await self.service.bootstrapCanvas(for: userId, purpose: purpose)

// 2. Run session init and UI setup in parallel
async let sessionTask = self.service.initializeSession(canvasId: cid, purpose: purpose, forceNew: false)

// 3. Attach listeners immediately (don't wait for session)
self.attachEventsListener(userId: userId, canvasId: cid)
self.attachWorkspaceEntriesListener(userId: userId, canvasId: cid)

// 4. Mark UI ready while session continues in background
self.isReady = true

// 5. Session resolves (user can already see Canvas)
self.currentSessionId = try? await sessionTask
```

**Why**: Users don't need the session to see the Canvas UI. Let them start typing while session initializes.

#### 1.3 Skip Unnecessary Purge

**File**: `MYON2/MYON2/ViewModels/CanvasViewModel.swift`

```swift
// BEFORE - Always purge
try await self.service.purgeCanvas(...)

// AFTER - Skip for fresh sessions
// Only purge if we're reusing an existing canvas with stale data
// For now, skip entirely - workspace_entries are session-scoped anyway
// do {
//     try await self.service.purgeCanvas(...)
// } catch {
//     DebugLogger.error(.canvas, "purgeCanvas failed: \(error.localizedDescription)")
// }
```

**Why**: The purge operation deletes workspace_entries on every Canvas open, which is unnecessary for fresh planning sessions and adds 2-5s latency.

#### 1.4 Optimistic UI Display

Show the Canvas immediately with a placeholder state:

```swift
// Set UI as ready immediately
self.isReady = true
self.cards = []  // Empty but visible

// Initialize in background
Task {
    // Bootstrap, session, listeners happen here
    // User can already see Canvas and start typing
}
```

**Why**: Perceived performance matters. Users can start composing their query while the backend initializes.

### Expected Results

| Metric | Before | After Phase 1 |
|--------|--------|---------------|
| Time to Canvas visible | 20-40s | <3s |
| Time to first agent response | 30-60s | 8-15s |
| Session reuse rate | 0% | >80% |
| Startup HTTP calls | 3 sequential | 1 + 1 parallel |

---

## Phase 2: Active Workout Support

> **Note**: Phase 2 will be implemented after Phase 1 is complete and stable.

### Goals

- Set logging: **<50ms** (fire-and-forget)
- Coaching feedback: **<2 seconds** when triggered
- Exercise swap: **5-10 seconds** (involves agent reasoning)
- Voice input: **Real-time transcription + agent response**

### Architecture Components

#### 2.1 WebSocket Connection for Real-Time Events

```
iOS App ←──── WebSocket ────→ Coaching Service (Cloud Run)
                                     │
                                     ▼
                              Event Processing
                                     │
                        ┌────────────┴────────────┐
                        │                         │
                        ▼                         ▼
                   Fast Path               Full Agent
                (Deterministic)           (LLM-powered)
                   <100ms                    1-3s
```

**Why WebSocket**: HTTP request-response adds latency and can't support proactive agent messages. WebSocket enables:
- Instant event streaming (iOS → Server)
- Proactive coaching (Server → iOS)
- Connection keep-alive (no cold starts)

#### 2.2 Workout State in Canvas

**New Collection**: `users/{uid}/canvases/{canvasId}/active_workout/current`

```javascript
{
  status: "active" | "completed" | "cancelled",
  plan: { /* original session_plan from card */ },
  current_exercise_index: 2,
  exercises: [
    {
      id: "ex_1",
      exercise_id: "barbell-back-squat",
      name: "Barbell Back Squat",
      prescribed_sets: [
        { reps: 8, rir: 2, weight: 80 },
        { reps: 8, rir: 2, weight: 85 },
        ...
      ],
      completed_sets: [
        { reps: 8, weight: 80, rir: 3, completed_at: timestamp },
        { reps: 7, weight: 85, rir: 1, completed_at: timestamp }
      ],
      status: "in_progress"
    }
  ],
  started_at: timestamp,
  last_event_at: timestamp
}
```

**Why**: Agent needs access to full workout state to provide contextual coaching.

#### 2.3 Response Filter (Determines When Agent Speaks)

```javascript
function evaluateCoaching(workout, event) {
  const { actual, prescribed } = event.payload;
  
  // Rule 1: Failure (RIR = 0)
  if (actual.rir === 0) {
    return {
      shouldRespond: true,
      type: "failure_coaching",
      message: "That was a tough set! Consider dropping weight..."
    };
  }
  
  // Rule 2: Too easy (RIR >= 4)
  if (actual.rir >= 4) {
    return {
      shouldRespond: true,
      type: "intensity_suggestion",
      message: "Looking strong! You could handle more weight."
    };
  }
  
  // Rule 3: Direct user question
  if (event.type === "user_message" || event.type === "voice_input") {
    return {
      shouldRespond: true,
      useLLM: true  // Complex questions need full agent
    };
  }
  
  // Default: Stay silent
  return { shouldRespond: false };
}
```

#### 2.4 Voice Integration

```
User speaks → iOS Speech-to-Text → Event (type: voice_input)
                                         │
                                         ▼
                                   Coaching Service
                                         │
                                         ▼
                                   Agent Response
                                         │
                                         ▼
                              iOS Text-to-Speech (optional)
```

#### 2.5 Future: Sensor Data Pipeline

```
Wearable Sensors → iOS App → Cloud Compute Service
                                    │
                                    ▼
                           Form Score, Fatigue Level,
                           Velocity Metrics, etc.
                                    │
                                    ▼
                           Injected into Event Stream
                                    │
                                    ▼
                           Agent sees processed metrics
```

---

## Technical Specifications

### Agent System Instructions for Active Workout

```python
ACTIVE_WORKOUT_INSTRUCTION = """
## ACTIVE WORKOUT OBSERVER MODE

You are monitoring a live workout session. You have access to the full workout state
including prescribed plan, completed sets, and real-time events.

### WHEN TO RESPOND

**STAY SILENT for:**
- Normal set completions (RIR 1-3, reps match prescription)
- Routine transitions between exercises
- Rest periods

**RESPOND for:**
- Failure (RIR = 0): Suggest weight reduction, extended rest
- Concern (RIR 1 + missed reps): Offer encouragement, form check
- Too easy (RIR >= 4): Suggest weight increase
- Direct questions: Always respond to user messages
- Milestones: Brief encouragement when exercise completed

### RESPONSE FORMAT

Always respond with this structure:
{
  "should_respond": true/false,
  "response_type": "coaching_card" | "inline_message" | "silent",
  "content": "Your coaching message (1-2 sentences max)",
  "suggested_action": {
    "type": "weight_change" | "rest_adjustment" | "exercise_swap" | null,
    "value": ...
  }
}

### COACHING VOICE

- Sound like a gym buddy, not a lecturer
- Be specific: "Drop to 80kg" not "Consider reducing weight"
- Keep it short - user is mid-workout
- Focus on actionable advice

### HYPERTROPHY PRINCIPLES

- RIR 2-3 is the sweet spot for hypertrophy
- RIR 0 occasionally is fine, but not every set
- Progressive overload: increase weight when RIR stays high
- Volume accumulation matters more than intensity
"""
```

### Performance Requirements

| Interaction | Target Latency | Implementation |
|-------------|----------------|----------------|
| Canvas initialization | <3s to visible | Optimistic UI |
| First agent response | <10s | Session reuse |
| Subsequent agent responses | <5s | Warm session |
| Set logging | <50ms | Fire-and-forget Firestore |
| Coaching feedback | <2s | Response filter + fast path |
| Exercise swap | 5-10s | Full agent reasoning |
| Voice input → response | <3s | Streaming transcription |

---

## Implementation Roadmap

### Phase 1: Canvas Optimization (Immediate)

**Week 1: Quick Wins** ✅ IMPLEMENTED (Dec 21, 2024)
- [x] Remove `forceNew: true` in CanvasViewModel
- [x] Parallelize startup operations
- [x] Skip unnecessary purgeCanvas
- [x] Add timing logs for measurement
- [x] New canvas per conversation (bootstrap-canvas.js)
- [x] User-level session reuse (initialize-session.js)
- [x] Test session reuse behavior

**Week 1.5: Agent Fixes & Self-Healing** ✅ IMPLEMENTED (Dec 21, 2024)
- [x] Fix agent context parsing (auto-parse canvas_id, user_id, correlation_id from message prefix)
- [x] Fix session_plan schema: sets require `target` wrapper object with `reps` and `rir`
- [x] Add self-healing validation responses to `proposeCards`:
  - Returns `attempted` (what agent sent)
  - Returns `expected_schema` (the actual JSON Schema)
  - Returns `errors` with paths and `hint` in plain English
  - Enables agents to self-correct when schema validation fails
- [x] Create shared utility: `firebase_functions/functions/utils/validation-response.js`
- [x] Document self-healing pattern in FIRESTORE_SCHEMA.md

**Current Performance**: End-to-end ~22 seconds (down from 30-60s)
**Target**: <10 seconds

**Week 2: Tool & Data Caching** ✅ ALREADY IMPLEMENTED (Discovered Dec 21, 2024)
All caching was already in place:
- [x] Exercise catalog caching (3-day Firestore TTL, 5-min memory TTL)
  - Location: `firebase_functions/functions/exercises/search-exercises.js`
  - Two-layer: memory → Firestore → fresh query
  - Cache key: MD5 hash of query params
  - Returns `source: 'memory' | 'firestore' | 'fresh'` in response
- [x] GCP auth token caching (55-min TTL, refreshes 5min before expiry)
  - Location: `firebase_functions/functions/strengthos/stream-agent-normalized.js`
  - Module-level singleton, persists across requests
- [x] User profile caching (24hr Firestore TTL, 5-min memory TTL)
  - Location: `firebase_functions/functions/user/get-user.js`
  - Two-layer: memory → Firestore → fresh query
  - Cache key: `profile_{userId}`
- [x] Cache invalidation hooks
  - Location: `firebase_functions/functions/user/update-user.js`
  - Calls `invalidateProfileCache(userId)` on user updates
  - Clears both memory and Firestore cache

**Week 3: Agent Refinement** ✅ IMPLEMENTED (Dec 21, 2024)
Complete rewrite of agent architecture from procedural to knowledge-based:

**Instruction Changes:**
- [x] Removed cookbook-style procedures ("Do step 1, then step 2")
- [x] Added domain knowledge layer (hypertrophy principles, programming logic)
- [x] Changed from lookup tables to reasoning principles
- [x] Added coaching persona (efficient, evidence-based, adaptive)
- [x] Anchored to hypertrophy research (explains when asked)

**Tool Changes:**
- [x] Reduced from 10 tools to 6 tools
- [x] Combined `tool_create_workout_plan` + `tool_publish_workout_plan` → `tool_propose_workout`
- [x] Removed unused tools: `tool_set_context`, `tool_record_user_info`, `tool_emit_status`
- [x] Kept: `tool_get_user_profile`, `tool_get_recent_workouts`, `tool_search_exercises`, `tool_propose_workout`, `tool_ask_user`, `tool_send_message`

**Expected Impact:**
- Fewer tool calls per request (1 workout tool instead of 2)
- More autonomous reasoning (less rigid procedures)
- Better adaptation to user context
- Evidence-based recommendations when asked

**Files Changed:**
- `adk_agent/canvas_orchestrator/app/unified_agent.py` - Agent v2.0
- `firebase_functions/functions/strengthos/stream-agent-normalized.js` - Tool labels

---

## Caching Strategy

### Overview

To reduce tool call latency, we implement multi-level caching with smart invalidation:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CACHING LAYERS                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  LAYER 1: In-Memory (Firebase Function instance)                     │    │
│  │  - GCP Auth Token (1hr TTL)                                          │    │
│  │  - Exercise Catalog chunks (until instance recycles)                 │    │
│  │  - User Profile (until instance recycles)                            │    │
│  │  ✅ Fastest: 0ms                                                      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                     │                                        │
│                                     ▼ miss                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  LAYER 2: Firestore Cache Collection                                 │    │
│  │  - `cache/exercises/{muscle_group}` (3-day TTL)                      │    │
│  │  - `cache/users/{uid}/profile` (24hr TTL)                            │    │
│  │  ✅ Fast: ~50-100ms                                                   │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                     │                                        │
│                                     ▼ miss                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  LAYER 3: Source Data                                                │    │
│  │  - exercises/{id} collection                                         │    │
│  │  - users/{uid} document                                              │    │
│  │  ⚠️ Slower: 100-500ms                                                 │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Cache Configurations

| Data Type | TTL | Invalidation Trigger | Notes |
|-----------|-----|---------------------|-------|
| **GCP Auth Token** | 1 hour | Auto (token expiry) | Never manually invalidated |
| **Exercise Catalog** | 3 days | Manual (admin trigger) | IDs/names rarely change |
| **User Profile** | 24 hours | On profile update | Equipment, goals, experience |
| **Recent Workouts** | 1 hour | On workout complete | Stale data less critical |

### Cache Invalidation Rules

#### Exercise Catalog
```javascript
// Invalidation: Only on admin catalog changes (rare)
// Trigger: Cloud Function on exercises collection write

exports.onExerciseWrite = onDocumentWritten("exercises/{exerciseId}", async (event) => {
  // Clear all cached exercise queries
  const cacheRef = db.collection('cache').doc('exercises');
  await cacheRef.delete();  // Or mark as stale
  console.log('Exercise cache invalidated due to catalog change');
});
```

#### User Profile
```javascript
// Invalidation: On user document update
// Trigger: Cloud Function on user write

exports.onUserWrite = onDocumentWritten("users/{userId}", async (event) => {
  const userId = event.params.userId;
  const cacheRef = db.collection('cache').doc(`users/${userId}/profile`);
  await cacheRef.delete();
  console.log(`User profile cache invalidated for ${userId}`);
});
```

#### Recent Workouts
```javascript
// Invalidation: On workout complete
// Trigger: Part of completeActiveWorkout function

async function completeActiveWorkout(userId, workoutId) {
  // ... complete workout logic ...
  
  // Invalidate workouts cache
  const cacheRef = db.collection('cache').doc(`users/${userId}/workouts`);
  await cacheRef.delete();
}
```

### Implementation: Cached Exercise Search

```javascript
// firebase_functions/functions/exercises/search-cached.js

const EXERCISE_CACHE_TTL_MS = 3 * 24 * 60 * 60 * 1000; // 3 days

// In-memory cache for hot path
const memoryCache = new Map();
const MEMORY_CACHE_TTL_MS = 5 * 60 * 1000; // 5 minutes

async function searchExercisesCached(query) {
  const cacheKey = `exercises:${JSON.stringify(query)}`;
  
  // Layer 1: Memory cache
  const memoryCached = memoryCache.get(cacheKey);
  if (memoryCached && Date.now() < memoryCached.expiresAt) {
    return { data: memoryCached.data, source: 'memory' };
  }
  
  // Layer 2: Firestore cache
  const firestoreCacheRef = db.collection('cache').doc(`exercises/${cacheKey.hashCode()}`);
  const firestoreCache = await firestoreCacheRef.get();
  
  if (firestoreCache.exists) {
    const cached = firestoreCache.data();
    const age = Date.now() - cached.cachedAt.toMillis();
    
    if (age < EXERCISE_CACHE_TTL_MS) {
      // Warm memory cache
      memoryCache.set(cacheKey, {
        data: cached.data,
        expiresAt: Date.now() + MEMORY_CACHE_TTL_MS
      });
      return { data: cached.data, source: 'firestore' };
    }
  }
  
  // Layer 3: Fresh query
  const results = await executeExerciseQuery(query);
  
  // Store in Firestore cache
  await firestoreCacheRef.set({
    query,
    data: results,
    cachedAt: admin.firestore.FieldValue.serverTimestamp()
  });
  
  // Store in memory cache
  memoryCache.set(cacheKey, {
    data: results,
    expiresAt: Date.now() + MEMORY_CACHE_TTL_MS
  });
  
  return { data: results, source: 'fresh' };
}
```

### Implementation: Cached User Profile

```javascript
// firebase_functions/functions/user/get-user-cached.js

const PROFILE_CACHE_TTL_MS = 24 * 60 * 60 * 1000; // 24 hours

// In-memory cache
const profileCache = new Map();

async function getUserProfileCached(userId) {
  // Layer 1: Memory cache
  const memoryCached = profileCache.get(userId);
  if (memoryCached && Date.now() < memoryCached.expiresAt) {
    return { data: memoryCached.data, source: 'memory' };
  }
  
  // Layer 2: Firestore cache
  const cacheRef = db.collection('cache').doc(`users/${userId}/profile`);
  const cacheDoc = await cacheRef.get();
  
  if (cacheDoc.exists) {
    const cached = cacheDoc.data();
    const age = Date.now() - cached.cachedAt.toMillis();
    
    if (age < PROFILE_CACHE_TTL_MS) {
      profileCache.set(userId, {
        data: cached.data,
        expiresAt: Date.now() + 5 * 60 * 1000 // 5 min memory TTL
      });
      return { data: cached.data, source: 'firestore' };
    }
  }
  
  // Layer 3: Fresh query
  const userDoc = await db.collection('users').doc(userId).get();
  const userData = userDoc.data();
  
  // Build profile for agent consumption
  const profile = {
    uid: userId,
    experience_level: userData?.attributes?.experience_level || 'intermediate',
    goals: userData?.attributes?.goals || [],
    available_equipment: userData?.attributes?.equipment || [],
    injuries: userData?.attributes?.injuries || [],
    preferred_workout_duration: userData?.attributes?.preferred_duration || 45,
  };
  
  // Store in cache
  await cacheRef.set({
    data: profile,
    cachedAt: admin.firestore.FieldValue.serverTimestamp()
  });
  
  profileCache.set(userId, {
    data: profile,
    expiresAt: Date.now() + 5 * 60 * 1000
  });
  
  return { data: profile, source: 'fresh' };
}
```

### Expected Performance Improvement

| Tool Call | Before (ms) | After (ms) | Improvement |
|-----------|-------------|------------|-------------|
| search_exercises (cold) | 300-500 | 300-500 | - |
| search_exercises (memory hit) | - | **0-5** | ~98% |
| search_exercises (firestore hit) | - | **50-100** | ~80% |
| get_user_profile (cold) | 200-400 | 200-400 | - |
| get_user_profile (cached) | - | **0-100** | ~75% |
| GCP auth token (cold) | 500-1000 | 500-1000 | - |
| GCP auth token (cached) | - | **0** | 100% |

**Total expected reduction for typical workout planning:**
- Best case (all cached): **5-15s** (down from 20-25s)
- Worst case (cold start): Same as before
- Typical case: **10-18s** (30-40% improvement)

### Phase 2: Active Workout Support (Future)

**Sprint 1: Foundation**
- [ ] Add `active_workout` collection to Canvas
- [ ] Bridge Canvas ↔ ActiveWorkoutManager
- [ ] Set up Firestore triggers for events
- [ ] Design `inline-coaching` card type

**Sprint 2: Coaching Logic**
- [ ] Implement response filter rules
- [ ] Build deterministic coaching paths
- [ ] Add fast LLM path for complex questions
- [ ] Test coaching triggers

**Sprint 3: Real-Time Connection**
- [ ] Implement WebSocket service (Cloud Run)
- [ ] iOS WebSocket client
- [ ] Event streaming and batching
- [ ] Connection resilience

**Sprint 4: Voice & Polish**
- [ ] Voice input integration
- [ ] Text-to-speech responses (optional)
- [ ] UI polish for coaching cards
- [ ] Performance optimization

**Future: Sensors**
- [ ] Sensor data pipeline architecture
- [ ] Cloud compute service for metrics
- [ ] Integration with event stream
- [ ] Agent access to sensor-derived data

---

## Success Metrics

### Phase 1

| Metric | Target | How to Measure |
|--------|--------|----------------|
| Time to Canvas visible | <3s | Performance logging |
| First agent response | <10s | SSE timing |
| Session reuse rate | >80% | Firestore logs |
| User complaints about speed | ↓50% | User feedback |

### Phase 2

| Metric | Target | How to Measure |
|--------|--------|----------------|
| Set logging latency | <50ms | Client-side timing |
| Coaching response time | <2s | End-to-end measurement |
| User engagement with coaching | >30% acceptance rate | Analytics |
| Workout completion rate | ↑10% | Before/after comparison |

---

## Appendix

### Files to Modify (Phase 1)

1. `MYON2/MYON2/ViewModels/CanvasViewModel.swift`
   - Remove `forceNew: true`
   - Parallelize startup
   - Skip purge

2. `firebase_functions/functions/canvas/initialize-session.js`
   - Add timing logs
   - Verify session reuse logic

3. `firebase_functions/functions/strengthos/stream-agent-normalized.js`
   - Add timing logs
   - Cache auth tokens

4. `adk_agent/canvas_orchestrator/app/unified_agent.py`
   - Refine system instructions
   - Add hypertrophy principles

### Related Documentation

- [CONTEXT_ARCHITECTURE.md](./CONTEXT_ARCHITECTURE.md) - Session management details
- [FIRESTORE_SCHEMA.md](./FIRESTORE_SCHEMA.md) - Data structure reference
- [platformvision.md](./platformvision.md) - Overall product vision
