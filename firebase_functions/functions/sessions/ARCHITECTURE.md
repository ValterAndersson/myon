# Sessions — Module Architecture

Manages Vertex AI agent session lifecycle: creation, reuse, pre-warming, and cleanup.

## File Inventory

| File | Purpose |
|------|---------|
| `cleanup-sessions.js` | Scheduled function (every 6 hours) that purges stale `agent_sessions` from Firestore. Uses collectionGroup query with 2-hour cutoff. |

Session creation and pre-warming are handled inline by `stream-agent-normalized.js` (creates sessions on demand) and the iOS `SessionPreWarmer` (pre-warms via `preWarmSession` endpoint).

## Session Lifecycle

1. **Pre-warm** (optional): iOS calls `preWarmSession` on app launch / tab appear. Creates a Vertex AI session and stores reference in `users/{uid}/agent_sessions/{purpose}`.
2. **Consume**: When user sends a message, `stream-agent-normalized.js` checks for an existing session in Firestore. If found and not stale, reuses it. Otherwise creates a new one.
3. **Update**: Each use updates `lastUsedAt` timestamp.
4. **Cleanup**: Scheduled function deletes sessions where `lastUsedAt` < 2 hours ago. Vertex AI sessions auto-expire at ~60min, so 2-hour cutoff is conservative.

## Firestore Path

`users/{uid}/agent_sessions/{purpose}` — purpose is typically `"ad_hoc"` or `"general"`.

Fields: `sessionId`, `purpose`, `createdAt`, `lastUsedAt`.

## Cross-References

- iOS pre-warmer: `Povver/Povver/Services/SessionPreWarmer.swift`
- Streaming consumer: `strengthos/stream-agent-normalized.js` (session reuse logic)
- Index.js export: `cleanupStaleSessions` (scheduled via Cloud Scheduler)
