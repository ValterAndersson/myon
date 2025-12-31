# Comprehensive Session Logging

This document describes the radically improved logging system for debugging agent interactions. The logs are designed to be the **single source of truth** for understanding what happened during a user session.

## Overview

The logging system captures:
- **Session context** (user ID, canvas ID, session ID, device info)
- **HTTP request/response** with full bodies, status codes, and timing
- **SSE stream events** with full payloads
- **Canvas state snapshots** showing all cards and their status
- **Agent routing decisions**
- **Tool calls** with arguments and results
- **Firestore snapshot updates**
- **Errors** with full context

## Quick Start

1. Run the app in Xcode (Debug mode)
2. Copy the console output after a session
3. Paste to an LLM with the question "What went wrong?"

The LLM will be able to understand:
- What the user asked
- Which agent was selected
- What tools were called and with what arguments
- What the responses were
- Where errors occurred
- The full state of the canvas at any point

## Log Output Example

```
╔══════════════════════════════════════════════════════════════════════════════════════════════════════════════════╗
║ 🚀 SESSION START                                                                                                  ║
╠══════════════════════════════════════════════════════════════════════════════════════════════════════════════════╣
║ User:    abc123xyz                                                                                                ║
║ Canvas:  general                                                                                                  ║
║ Session: pending                                                                                                  ║
║ Device:  iPhone / iOS 17.0                                                                                        ║
║ Time:    2024-12-30T22:31:45.123Z                                                                                 ║
╚══════════════════════════════════════════════════════════════════════════════════════════════════════════════════╝

[22:31:45.234] ℹ️ [Canvas] Canvas start BEGIN (new canvas)

[22:31:45.456] 📤 HTTP REQUEST
  POST openCanvas
  Body: {
    "purpose": "general",
    "userId": "abc123xyz"
  }

[22:31:46.789] 📥 HTTP RESPONSE (1333ms) ✅ 200
  POST openCanvas
  Body: {
    "canvasId": "general",
    "isNewSession": false,
    "sessionId": "session_12345",
    "success": true
  }

[22:31:46.800] ℹ️ [Canvas] openCanvas completed
  | {"canvas_id": "general", "duration_s": "1.33", "session_id": "session_12345"}

[22:31:46.850] 🔍 [Canvas] Listeners attached
  | {"elapsed_s": "0.62"}

[22:31:47.100] 🔥 FIRESTORE: canvases/general/cards (2 docs, source: server)

[22:31:47.105] 🔄 CANVAS SNAPSHOT (firestore_update)
  Phase: planning
  Version: 5
  Cards (2):
    [0] session_plan (proposal) id=card_abc123 - "Push Day"
    [1] routine_summary (final) id=card_def456 - "4-Week Strength"
  UpNext: [card_abc123]

[22:31:47.110] ℹ️ [Canvas] Canvas READY
  | {"elapsed_s": "0.88"}

[22:31:50.000] 📡 SSE STREAM START
  Endpoint: /streamAgentNormalized
  Correlation: corr_xyz789
  Session: session_12345
  Message: "Create a 3 day push pull legs routine"

[22:31:50.500] 🧠 SSE: THINKING (agent: orchestrator)
  Content: {
    "text": "Analyzing request..."
  }

[22:31:51.000] 🔀 AGENT ROUTING
  Agent: 📋 planner
  Intent: create_routine
  Confidence: 0.95
  Reason: User wants to create a new training routine

[22:31:51.200] ⚙️ SSE: TOOL_RUNNING (agent: planner)
  Content: {
    "phase": "researching",
    "text": "Fetching user preferences...",
    "tool": "get_user"
  }

[22:31:51.800] ✅ SSE: TOOL_COMPLETE (agent: planner)
  Content: {
    "text": "User profile loaded",
    "tool": "get_user"
  }

[22:31:52.000] ⚙️ TOOL CALL: search_exercises (phase: researching)
  Args: {
    "limit": 20,
    "muscle_groups": "chest,shoulders,triceps"
  }

[22:31:52.500] ✅ TOOL RESULT: search_exercises (500ms)
  Result: {
    "count": 15,
    "exercises": [...]
  }

[22:31:55.000] 💬 SSE: MESSAGE (agent: planner)
  Content: {
    "text": "I've created a Push Pull Legs routine for you..."
  }

[22:31:55.100] 🏁 SSE STREAM END
  Events: 12
  Duration: 5100ms

[22:31:55.200] 🔥 FIRESTORE: canvases/general/cards (3 docs, source: server)

[22:31:55.210] 🔄 CANVAS SNAPSHOT (firestore_update)
  Phase: planning
  Version: 6
  Cards (3):
    [0] session_plan (proposal) id=card_new123 - "Push Pull Legs"
    [1] session_plan (dismissed) id=card_abc123 - "Push Day"
    [2] routine_summary (final) id=card_def456 - "4-Week Strength"
  UpNext: [card_new123]
```

## Error Example

```
╔══════════════════════════════════════════════════════════════════════════════════════════════════════════════════╗
║ ❌ ERROR                                                                                                          ║
╠══════════════════════════════════════════════════════════════════════════════════════════════════════════════════╣
║ Time:     22:32:45.789                                                                                            ║
║ Category: HTTP                                                                                                    ║
║ Message:  HTTP request failed after 3 attempts                                                                    ║
║ Error:    The request timed out.                                                                                  ║
╠══════════════════════════════════════════════════════════════════════════════════════════════════════════════════╣
║ Session Context:                                                                                                  ║
║   User:        abc123xyz                                                                                          ║
║   Canvas:      general                                                                                            ║
║   Session:     session_12345                                                                                      ║
║   Correlation: corr_xyz789                                                                                        ║
╚══════════════════════════════════════════════════════════════════════════════════════════════════════════════════╝
  Error Context: {
    "attempts": 3,
    "path": "applyAction",
    "total_duration_ms": 45000
  }
```

## Key Components

### SessionLogger (DebugLogger.swift)

The central logging singleton that tracks session context:

```swift
// Start session tracking
SessionLogger.shared.startSession(userId: userId, canvasId: canvasId)

// Update context as IDs become available
SessionLogger.shared.updateContext(sessionId: sessionId, correlationId: correlationId)

// Log HTTP with full bodies
SessionLogger.shared.logHTTPRequest(method: "POST", endpoint: path, body: bodyDict)
SessionLogger.shared.logHTTPResponse(method: "POST", endpoint: path, statusCode: 200, durationMs: 150, body: responseBody)

// Log SSE events
SessionLogger.shared.logSSEStreamStart(endpoint: "/streamAgentNormalized", correlationId: correlationId, message: userMessage)
SessionLogger.shared.logSSEEvent(type: "tool_running", content: contentDict, agent: "planner")
SessionLogger.shared.logSSEStreamEnd(eventCount: 12, durationMs: 5100)

// Log canvas state snapshots
SessionLogger.shared.logCanvasSnapshot(phase: "planning", version: 6, cards: cardTuples, upNext: upNextIds)

// Log errors with full context
SessionLogger.shared.logError(category: .http, message: "Request failed", error: error, context: ["path": path])
```

### Verbose Mode

By default, verbose mode is enabled in DEBUG builds. This shows:
- Full HTTP request/response bodies
- Full SSE event payloads
- Tool call arguments and results

Toggle verbose mode:
```swift
DebugLogger.setVerbose(false)  // Compact mode - key info only
DebugLogger.setVerbose(true)   // Full payloads
```

### Event Types

| Emoji | Type | Description |
|-------|------|-------------|
| 🚀 | SESSION START | New debugging session |
| 🏁 | SESSION END | Session completed |
| 📤 | HTTP REQUEST | Outgoing HTTP request |
| 📥 | HTTP RESPONSE | HTTP response received |
| 📡 | SSE STREAM START | SSE connection opened |
| 🧠 | THINKING | Agent is thinking |
| 💭 | THOUGHT | Thought duration |
| ⚙️ | TOOL_RUNNING | Tool execution started |
| ✅ | TOOL_COMPLETE | Tool execution completed |
| 💬 | MESSAGE | Text from agent |
| 🔀 | AGENT ROUTING | Agent selection |
| 🔄 | CANVAS SNAPSHOT | Canvas state update |
| ⚡ | CANVAS ACTION | User action applied |
| 🔥 | FIRESTORE | Firestore snapshot |
| ❌ | ERROR | Error occurred |
| ❓ | CLARIFICATION | Agent asking question |
| 💓 | HEARTBEAT | Keep-alive ping |

## Files Modified

| File | Changes |
|------|---------|
| `DebugLogger.swift` | Complete rewrite with SessionLogger singleton, emoji-coded events, ASCII box errors |
| `ApiClient.swift` | Full HTTP request/response logging with JSON bodies, status codes, timing |
| `DirectStreamingService.swift` | SSE stream start/end, every event with full payload, agent routing |
| `CanvasViewModel.swift` | Session start logging, canvas state snapshots with all cards |
| `CanvasRepository.swift` | Firestore snapshot logging (cards, state, up_next) with source (cache/server) |
| `CloudFunctionService.swift` | Firebase callable function logging (request/response/timing) |
| `CanvasService.swift` | Canvas action logging (applyAction with type, cardId, payload, version) |

## Usage for Debugging

1. **Reproduce the issue** in the iOS simulator or device
2. **Copy the Xcode console output** (⌘+A, ⌘+C in the console)
3. **Paste to Claude/GPT** with the question:
   - "What went wrong in this session?"
   - "Why didn't the agent create the workout?"
   - "What was the HTTP response from applyAction?"
   - "What cards were on the canvas when the error occurred?"

The LLM will have complete context to diagnose the issue.

## Best Practices

1. **Always include the SESSION START banner** - it contains user/canvas/device info
2. **Include the full SSE stream** for agent issues - shows thinking + tool calls
3. **Include CANVAS SNAPSHOT** before and after actions - shows state changes
4. **Look for ERROR blocks** - they contain session context and error details
5. **Check HTTP timing** - slow responses indicate backend issues
