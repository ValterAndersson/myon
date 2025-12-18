# Session Architecture & Performance Optimization

## Goals
1. **Blazing fast** - Minimize cold start, fast tool responses
2. **Persistent context** - Sessions build on previous conversations
3. **Let agent do its job** - Tools for data, not bloated state

## Core Principle: Agent Engine Best Practices

**Don't** bloat session state with data dumps (workouts, routines, etc.) because:
1. Agent relies on stale data instead of making tool calls
2. Increases prompt size / token usage
3. Agent Engine is designed for tool use, not context reading

**Do** focus on:
1. **Session persistence** - Reuse sessions to preserve conversation history
2. **Minimal state** - Just user ID, canvas ID, purpose
3. **Fast tools** - Cache data in Firebase, use proper indexes
4. **Smart prompts** - Reduce unnecessary clarifications

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        iOS App                                   │
├─────────────────────────────────────────────────────────────────┤
│  1. User opens Canvas → `initializeSession(canvasId)`           │
│  2. Get sessionId (reused if valid, or new)                     │
│  3. All messages use same sessionId                             │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│              Vertex AI Session (MINIMAL STATE)                   │
├─────────────────────────────────────────────────────────────────┤
│  {                                                              │
│    "user:id": "uid",                                            │
│    "canvas:id": "canvasId",                                     │
│    "canvas:purpose": "workout_planning"                         │
│  }                                                              │
│                                                                 │
│  + Conversation history (automatic via session)                 │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FAST TOOLS (Cached)                          │
├─────────────────────────────────────────────────────────────────┤
│  tool_get_user_profile → Firebase (cached in memory/Firestore) │
│  tool_get_recent_workouts → Pre-indexed, paginated             │
│  tool_search_exercises → Indexed by muscle group               │
│                                                                 │
│  ⚡ Target: <500ms per tool call                                │
└─────────────────────────────────────────────────────────────────┘
```

## Speed Optimization Strategy

### 1. Session Persistence (Biggest Win)
Reusing sessions means:
- **No cold start** - Vertex AI doesn't need to initialize new session
- **Conversation history preserved** - Agent remembers previous messages
- **Automatic context** - "User wanted leg workout" from 2 messages ago

```javascript
// Session reuse logic
const SESSION_TTL_MS = 30 * 60 * 1000; // 30 minutes

async function getOrCreateSession(userId, canvasId) {
  const canvasDoc = await db.collection('users').doc(userId)
    .collection('canvases').doc(canvasId).get();
  
  const { sessionId, lastActivity } = canvasDoc.data() || {};
  const age = Date.now() - (lastActivity?.toMillis() || 0);
  
  // Reuse if session is recent
  if (sessionId && age < SESSION_TTL_MS) {
    return { sessionId, isReused: true };
  }
  
  // Create new session with MINIMAL state
  const newSessionId = await createVertexSession({
    'user:id': userId,
    'canvas:id': canvasId
  });
  
  await canvasDoc.ref.set({
    sessionId: newSessionId,
    lastActivity: admin.firestore.FieldValue.serverTimestamp()
  }, { merge: true });
  
  return { sessionId: newSessionId, isReused: false };
}
```

### 2. Fast Tool Responses (Second Biggest Win)

Tools should be **<500ms**. Current bottleneck is Firebase queries.

**Solution: Firebase Function-Level Caching**

```javascript
// In-memory cache for hot data
const profileCache = new Map();
const PROFILE_TTL = 60 * 1000; // 1 minute

async function getCachedProfile(userId) {
  const cached = profileCache.get(userId);
  if (cached && Date.now() - cached.ts < PROFILE_TTL) {
    return cached.data; // ~0ms
  }
  
  const snap = await db.collection('users').doc(userId).get();
  const data = snap.data();
  profileCache.set(userId, { data, ts: Date.now() });
  return data; // ~100-200ms first time
}
```

**Solution: Proper Firestore Indexes**

```javascript
// Add composite indexes in firestore.indexes.json
{
  "indexes": [
    {
      "collectionGroup": "workouts",
      "queryScope": "COLLECTION",
      "fields": [
        { "fieldPath": "completedAt", "order": "DESCENDING" }
      ]
    }
  ]
}
```

### 3. Parallel Tool Execution

Agent Engine can call multiple tools simultaneously. Our agent should take advantage:

```python
# Agent instruction
"""
When you need both profile and recent workouts, call both tools 
in the SAME response. Don't wait for one to finish.

Example - do this:
  tool_get_user_profile()
  tool_get_recent_workouts(limit=5)

Not this:
  tool_get_user_profile()
  ... wait ...
  tool_get_recent_workouts()
"""
```

### 4. Smarter Agent Prompts

Reduce back-and-forth by being decisive:

```python
UNIFIED_INSTRUCTION = """
## Be Decisive

If the user says "plan a workout", make reasonable assumptions:
- Single session (not a multi-week program)
- Use their usual training style (from profile)
- Target 45-60 minutes

Only ask clarifying questions for AMBIGUOUS requests like:
- "Help me with my training" (what specifically?)
- "I want to get stronger" (what's the timeframe? priority?)

Do NOT ask clarifications for:
- "Plan a leg workout" → just plan it
- "Upper body push session" → you have enough info
- "Quick workout I can do at home" → plan it with bodyweight
"""
```

### 5. Exercise Catalog Pre-warming (Optional)

If agent frequently searches exercises, pre-load common ones:

```javascript
// On canvas initialize, cache common exercises
const COMMON_EXERCISES = [
  'barbell-back-squat', 'bench-press', 'deadlift',
  'lat-pulldown', 'dumbbell-curl', 'tricep-pushdown'
];

// Tool response includes these without DB query
```

## Performance Budget

| Component | Target | Current | Fix |
|-----------|--------|---------|-----|
| Session creation | <1s | ~3s | Reuse sessions |
| tool_get_user_profile | <500ms | ~2s | Caching |
| tool_get_recent_workouts | <500ms | ~2s | Indexes + cache |
| Agent thinking | ~5s | ~30s | Better prompts |
| **Total first response** | **<10s** | **~55s** | All above |

## Implementation Priority

### Phase 1: Session Persistence (Biggest impact)
1. Update `initializeSession` to reuse sessions
2. Update `streamAgentNormalized` to require sessionId
3. Update iOS to store/reuse sessionId

### Phase 2: Fast Tools
1. Add in-memory caching to tools
2. Ensure Firestore indexes exist
3. Add timing logs to identify slow queries

### Phase 3: Agent Optimization
1. Update prompt to be more decisive
2. Remove unnecessary clarification requests
3. Allow parallel tool calls

## Firebase Function: initializeSession (Revised)

```javascript
async function initializeSessionHandler(req, res) {
  const userId = req.user?.uid;
  const { canvasId, purpose = 'general' } = req.body;
  
  const canvasRef = db.collection('users').doc(userId)
    .collection('canvases').doc(canvasId);
  const canvasDoc = await canvasRef.get();
  const data = canvasDoc.data() || {};
  
  // Check for valid existing session
  const sessionAge = Date.now() - (data.lastActivity?.toMillis() || 0);
  if (data.sessionId && sessionAge < 30 * 60 * 1000) {
    await canvasRef.update({
      lastActivity: admin.firestore.FieldValue.serverTimestamp()
    });
    return res.json({
      sessionId: data.sessionId,
      isReused: true
    });
  }
  
  // Create new session with MINIMAL state
  const sessionId = await createVertexSession(userId, {
    'user:id': userId,
    'canvas:id': canvasId,
    'canvas:purpose': purpose
  });
  
  await canvasRef.set({
    sessionId,
    lastActivity: admin.firestore.FieldValue.serverTimestamp(),
    createdAt: admin.firestore.FieldValue.serverTimestamp(),
    purpose
  }, { merge: true });
  
  return res.json({
    sessionId,
    isReused: false
  });
}
```

## Key Insight

The speed comes from:
1. **Not creating sessions repeatedly** - conversation history is gold
2. **Fast tools** - agent waits for tools, so make them fast
3. **Smart prompts** - fewer back-and-forths
4. **Trust the agent** - let it call tools when needed, don't pre-load everything
