# Canvas Domain

Deterministic, reducer-driven interface for agent/user collaboration. The iOS app subscribes to `users/{uid}/canvases/{canvasId}/{state,cards,up_next}` and mutates via a single gateway: `applyAction`. Agents write proposals via `proposeCards`.

## Data model
- `users/{uid}/canvases/{canvasId}`
  - `state`: `{ phase: "planning|active|analysis", version, purpose?, lanes? }`
  - `cards/{cardId}`: `{ type, status, lane, content, refs, ttl?, by, created_at, updated_at }`
  - `up_next/{entryId}`: `{ card_id, priority, inserted_at }` (bounded, top 20)
  - `events/{eventId}`: `{ type: 'apply_action', payload: { action, card_id?, note_id? }, created_at }`
  - `idempotency/{key}`: `{ key, created_at }`

## File Inventory

| File | Endpoint(s) | Purpose |
|------|-------------|---------|
| `apply-action.js` | `applyAction` | Single writer for all canvas state mutations (transactions, version checks, idempotency) |
| `propose-cards.js` | `proposeCards` | Agent card proposal endpoint — writes proposed cards and adds to up_next queue |
| `propose-cards-core.js` | — (library) | Shared card writing logic used by `propose-cards.js` |
| `bootstrap-canvas.js` | `bootstrapCanvas` | Find-or-create canvas for a `(userId, purpose)` pair |
| `open-canvas.js` | `openCanvas`, `preWarmSession` | Combined bootstrap + session init in one call (optimized); pre-warm with min instances |
| `initialize-session.js` | `initializeSession` | Create/reuse Vertex AI session at user level |
| `emit-event.js` | `emitEvent` | Service-only endpoint to emit custom events to canvas event stream |
| `purge-canvas.js` | `purgeCanvas` | Delete all canvas data (cards, events, up_next) for testing/cleanup |
| `expire-proposals.js` | `expireProposals` | Sweep proposed cards by TTL |
| `expire-proposals-scheduled.js` | `expireProposalsScheduled` | Scheduled TTL sweep (every 15 minutes) |
| `reducer-utils.js` | — (library) | Shared reducer utilities for `apply-action.js` |
| `validators.js` | — (library) | Canvas-specific validation helpers |

## Endpoints

### applyAction (HTTPS)
- Auth: flexible (Bearer or API key); user must own canvas
- Request:
```json
{
  "canvasId": "c1",
  "expected_version": 3,
  "action": {
    "type": "ADD_INSTRUCTION|ACCEPT_PROPOSAL|REJECT_PROPOSAL|ADD_NOTE|LOG_SET|SWAP|ADJUST_LOAD|REORDER_SETS|PAUSE|RESUME|COMPLETE|UNDO",
    "card_id": "optional",
    "payload": {},
    "idempotency_key": "uuid"
  }
}
```
- Response:
```json
{ "success": true, "data": { "state": {"version": 4}, "changed_cards": [], "up_next_delta": [], "version": 4 } }
```
- Notes:
  - Optimistic concurrency on `state.version` (STALE_VERSION on mismatch)
  - Scoped idempotency: `users/{uid}/canvases/{canvasId}/idempotency/{key}`
  - In-transaction event append with minimal payload (enables UNDO). `apply_action` includes `changed_cards` and `correlation_id`.
  - Phase guards and simple science checks enforced
  - Auto-start: accepting a `session_plan` sets `state.phase` to `active` and emits `session_started`
  - Up-Next trimming is enforced best-effort after the transaction to satisfy Firestore txn constraints (no reads after writes inside txn).

Supported actions (Phase 1):
- `ADD_INSTRUCTION` → creates instruction card (analysis lane)
- `ACCEPT_PROPOSAL|REJECT_PROPOSAL` → updates card status; lane replacement by `refs.topic_key` for analysis; ensures single active `set_target`
- `ACCEPT_ALL|REJECT_ALL` → group-level actions targeting cards with `meta.groupId`
- `ADD_NOTE` → creates note card (workout lane); event includes `note_id` (UNDO support)
- `LOG_SET` → writes workout event via shared core; transitions `set_target→set_result`
- `SWAP` / `ADJUST_LOAD` / `REORDER_SETS` → workout events via shared cores
- `PAUSE` / `RESUME` / `COMPLETE` → phase transitions
- `UNDO` → limited to last `ACCEPT_PROPOSAL|REJECT_PROPOSAL|ADD_NOTE`

### proposeCards (HTTPS)
- Auth: service-only (API key) with `X-User-Id`
- Request:
```json
{
  "canvasId": "c1",
  "cards": [
    { "type": "session_plan", "lane": "workout", "content": { "blocks": [] } },
    { "type": "set_target", "lane": "workout", "content": { "target": { "reps": 8, "rir": 1 } }, "refs": { "exercise_id": "e", "set_index": 0 } },
    { "type": "visualization", "lane": "analysis", "content": { "chart_type": "line", "spec_format": "vega_lite", "spec": {} } }
  ]
}
```
- Response: `{ success: true, data: { created_card_ids: ["..."] } }`
- Validation:
  - Typed content schemas enforced via Ajv (session_plan, coach_proposal, visualization)
  - Typed content schemas also supported: `set_target`, `agent_stream`, `clarify-questions`, `list`, `inline-info`, `proposal-group`, `routine-overview`.
  - Optional `priority` field accepted (clamped to [-1000,1000]).
  - Cards may include `layout`, `actions`, `menuItems`, and `meta` (e.g., `meta.groupId`).
  - Server defaults: when omitted, defaults are injected for `layout|actions|menuItems|meta`; `meta.groupId` is normalized (lowercase/slug-like). `refs` defaults to `{}`.

### bootstrapCanvas (HTTPS)
- Auth: flexible (Bearer or API key)
- Request:
```json
{ "userId": "uid", "purpose": "ad_hoc|workout|progress|dashboard" }
```
- Behavior: returns existing canvas id for `(userId,purpose)` or creates a new one with
  `state:{ phase:'planning', version:0, purpose, lanes:['workout','analysis','system'] }` and `meta:{ user_id }`.
- Response: `{ success: true, data: { canvasId } }`

### openCanvas (HTTPS)
- Auth: flexible (Bearer or API key)
- Request: `{ "userId": "uid", "purpose": "...", "canvasId"?: "..." }`
- Response: `{ success: true, data: { canvasId, sessionId, resumeState } }`
- Combines `bootstrapCanvas` + `initializeSession` in a single call. Preferred entry point.

### initializeSession (HTTPS)
- Auth: flexible (Bearer or API key)
- Request: `{ "userId": "uid", "canvasId": "c1" }`
- Response: `{ success: true, data: { sessionId, agent_id } }`
- Creates or reuses a Vertex AI session at user level (not canvas level)

### emitEvent (HTTPS)
- Auth: service-only (API key)
- Request: `{ "userId": "uid", "canvasId": "c1", "event": { "type": "...", ... } }`
- Response: `{ success: true, data: { event_id } }`

### purgeCanvas (HTTPS)
- Auth: flexible (Bearer or API key)
- Request: `{ "userId": "uid", "canvasId": "c1" }`
- Response: `{ success: true, data: { deleted_cards, deleted_events, deleted_up_next } }`
- Deletes all canvas data for testing/cleanup

### expireProposals (HTTPS) / expireProposalsScheduled (Scheduled)
- Sweeps proposed cards by TTL; removes matching `up_next` entries
- Accepts `{ userId, canvasId? }` (HTTPS) or scans collection group (scheduled)

## Schema references
- Action schema: `canvas/schemas/action.schema.json`
- Apply request: `canvas/schemas/apply_action_request.schema.json`
- Propose request: `canvas/schemas/propose_cards_request.schema.json`
- Card types: `canvas/schemas/card_types/*.json`

## Notes for iOS
- Subscribe to `state`, `cards`, `up_next`; send only `applyAction` with `expected_version` and `idempotency_key`
- Respect lanes: workout is persistent, analysis is ephemeral with replacement groups by `refs.topic_key`
 - Use `bootstrapCanvas` before first use to create/lookup a canvas for a given purpose.
 - `up_next` limited to top 20; provide `priority` when proposing.
  - `EDIT_SET` action is validated but currently returns `UNIMPLEMENTED` from the reducer (MVP stub).
