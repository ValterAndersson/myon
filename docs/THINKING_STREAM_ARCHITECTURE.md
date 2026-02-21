# Thinking Stream Architecture

## Overview

This document describes the unified architecture for agent thinking streams - the user-facing messages that show what the agent is doing while processing a request.

## Design Principle: Single Source of Truth

**Tools emit their own display text.** There is no mapping layer. Each tool function includes `_display` metadata in its return value, which flows through the system unchanged.

## Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           AGENT (Python)                                     │
│  tool_search_exercises(muscle_group="chest")                                 │
│  └─ Returns: {                                                               │
│       "items": [...],                                                        │
│       "_display": {                                                          │
│         "running": "Searching chest exercises",                              │
│         "complete": "Found 12 exercises",                                    │
│         "phase": "searching"                                                 │
│       },                                                                     │
│       "_debug": { "args": {...}, "duration_ms": 340 }                        │
│     }                                                                        │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     Firebase (stream-agent-normalized.js)                    │
│  Extracts _display from function_response:                                   │
│  └─ Emits: {                                                                 │
│       "type": "toolComplete",                                                │
│       "content": {                                                           │
│         "tool": "tool_search_exercises",                                     │
│         "text": "Found 12 exercises",   // FROM _display.complete            │
│         "phase": "searching"             // FROM _display.phase              │
│       }                                                                      │
│     }                                                                        │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              iOS (Swift)                                     │
│  Renders event.content.text directly - NO REMAPPING                          │
│  Uses event.content.phase for AgentProgressState                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## _display Metadata Structure

Every tool return value should include a `_display` object:

```python
{
    "_display": {
        "running": str,    # Message shown while tool is executing
        "complete": str,   # Message shown when tool completes successfully
        "error": str,      # Message shown on error (optional, defaults to "Failed")
        "phase": str,      # Phase for AgentProgressState (understanding/searching/building/etc)
    }
}
```

## Phase Mapping

| Phase | Tools | UI Meaning |
|-------|-------|------------|
| `understanding` | `tool_get_user_profile`, `tool_get_planning_context` | Loading user context |
| `searching` | `tool_search_exercises`, `tool_get_recent_workouts` | Finding data |
| `building` | `tool_propose_workout`, `tool_propose_routine` | Creating artifacts |
| `finalizing` | `tool_save_workout_as_template`, `tool_create_routine` | Saving/publishing |
| `analyzing` | `tool_get_analytics_features` | Analyzing data |

## Safe Display Text Construction

**Rule: Only include details that are explicitly passed as parameters.**

```python
# ✅ SAFE - only uses args we have
def tool_search_exercises(muscle_group=None, ...):
    running = f"Searching {muscle_group} exercises" if muscle_group else "Searching exercises"
    
# ❌ RISKY - assumes context we don't have
running = "Searching chest exercises"  # What if user asked for legs?
```

## Tool Display Specifications

### Context Tools

| Tool | Running | Complete |
|------|---------|----------|
| `tool_get_user_profile` | "Reviewing profile" | "Profile loaded" |
| `tool_get_planning_context` | "Loading context" | "Context loaded" |
| `tool_get_recent_workouts` | "Checking workout history" | "Loaded {count} workouts" |

### Search Tools

| Tool | Running | Complete |
|------|---------|----------|
| `tool_search_exercises` | "Searching {muscle_group/movement_type} exercises" or "Searching exercises" | "Found {count} exercises" |

### Template/Routine Tools

| Tool | Running | Complete |
|------|---------|----------|
| `tool_get_template` | "Loading template" | "Template loaded" |
| `tool_get_next_workout` | "Finding next workout" | "Next: {template_name}" or "No active routine" |
| `tool_save_workout_as_template` | "Saving template" | "Template saved" |
| `tool_create_routine` | "Creating routine" | "Created {name}" |
| `tool_manage_routine` | "Updating routine" | "Routine updated" |

### Creation Tools

| Tool | Running | Complete |
|------|---------|----------|
| `tool_propose_workout` | "Building workout" | "Published {title}" |
| `tool_propose_routine` | "Building routine" | "Published {name}" |

### Communication Tools

| Tool | Running | Complete |
|------|---------|----------|
| `tool_ask_user` | "Asking question" | "Question sent" |
| `tool_send_message` | "Sending message" | "Message sent" |

## Debug Information

The `_debug` object provides detailed information for Xcode logging:

```python
{
    "_debug": {
        "args": {...},           # Tool arguments
        "http_status": 200,      # HTTP response code (if applicable)
        "duration_ms": 340,      # Execution time
        "item_count": 12,        # Result count (if applicable)
        "error_type": str,       # Error class name (if error)
        "error_message": str,    # Full error message (if error)
    }
}
```

## Implementation Status

### ✅ Completed - Backend

1. **Python (adk_agent/canvas_orchestrator/app/agents/planner_agent.py)**
   - `tool_get_user_profile` - returns `_display` with running/complete/phase
   - `tool_get_recent_workouts` - returns `_display` with dynamic count
   - `tool_get_planning_context` - returns `_display` with routine status
   - `tool_search_exercises` - returns `_display` with search context (muscle_group, etc.)
   - `tool_propose_workout` - returns `_display` with workout title
   - `tool_propose_routine` - returns `_display` with routine name

2. **Firebase (firebase_functions/functions/strengthos/stream-agent-normalized.js)**
   - Extracts `_display` from function_response results
   - Passes `displayText` and `phase` to `transformToIOSEvent`
   - Falls back to existing `TOOL_LABELS` for backwards compatibility
   - Adds `phase` to event content and metadata

### ✅ Completed - iOS (Single Source of Truth)

1. **`ThinkingProcessState.swift`** - Unified state for thinking UI
   - Groups tools into semantic phases (Planning → Gathering → Building → Finalizing)
   - Uses `event.content["text"]` from server for tool display names
   - Falls back to `humanReadableToolName()` only for legacy tools without `_display`
   - Tracks live elapsed time, step progress (from planner's `suggested_tools`), and active tool detail
   - Session-scoped `sessionId` for stable SwiftUI identity in timeline

2. **`ThinkingBubble.swift`** - Gemini-style collapsible UI
   - Collapsed header shows active tool label, step progress ("Step 2 of 5"), and elapsed time
   - Expanded view shows phase-level steps (3-4 rows) with checkmarks and durations
   - No per-tool breakdown — keeps the UI clean and scannable

3. **`CanvasViewModel.swift`** - Forwards all SSE events to ThinkingProcessState
   - Calls `thinkingState.complete()` on all stream cleanup paths (timeout, error, no-done-event)

### 🔲 Future Cleanup (After Deployment Verification)

Once the backend changes are deployed and verified working, these legacy mappings
can be fully removed (currently kept as fallbacks):

1. **`ThinkingProcessState.swift`** - `humanReadableToolName()` (~6 lines)
2. **`DirectStreamingService.swift`** - Legacy mappings (~130 lines)

### Backwards Compatibility

The Firebase layer checks for `_display` first, falls back to existing `TOOL_LABELS`:

```javascript
const resultText = adkEvent.displayText || describeToolResult(toolName, summary);
```

This allows gradual migration - tools can be updated one at a time.

## Testing Checklist

- [ ] Deploy updated planner_agent.py to Vertex AI
- [ ] Deploy updated stream-agent-normalized.js to Firebase Functions
- [ ] Test workout planning flow - verify display text flows through
- [ ] Test routine creation flow - verify display text flows through
- [ ] Verify Xcode console shows tool events with correct text
- [ ] Once verified, proceed with iOS cleanup
