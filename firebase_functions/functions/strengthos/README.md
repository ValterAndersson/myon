# Stream Agent Normalized (SSE/NDJSON)

This module exposes an HTTP endpoint that proxies the Agent Engine `:streamQuery`, applies token-level normalization and emits canonical NDJSON lines over Server-Sent Events.

## Endpoint

- Name: `streamAgentNormalized`
- Type: HTTPS (SSE)
- Auth: Flexible (Bearer Firebase ID token or X-API-Key)

## Event Schema (per line JSON under `data:`)

- Common: `type`, `seq`, `ts`, `role`, `messageId`
- Text:
  - `text_delta`: `{ text }`
  - `text_commit`: `{ text }`
- Tools:
  - `tool_started`: `{ name, args, display }`
  - `tool_result`: `{ name, summary, counts }`
- Control:
  - `policy`: `{ markdown_policy }`
  - `heartbeat`, `error`, `done`

## Normalization

- Bullet normalization to `- `, drop markdown headings
- Sentence-aware commit windows, avoid open code-fence commits
- Rolling hash dedupe across the last window

## Timing

- Heartbeat every ~2.5s; graceful flush on end

## Architecture

```
Povver iOS App
    ↓ (Firebase Auth)
Firebase Functions (v2)
    ↓ (Google Cloud Auth)
Vertex AI Agent Engine
    ↓
Shell Agent (ADK)
```

## Other Functions

- `upsertProgressReport` — Write progress report (API key)
- `getProgressReports` — Read progress reports (flexible auth)

## Notes

- The legacy `createStrengthOSSession`, `queryStrengthOS`, `listStrengthOSSessions`, and `deleteStrengthOSSession` functions are no longer used. All agent communication flows through `streamAgentNormalized`.
