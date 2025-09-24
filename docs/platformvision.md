## MYON Platform Vision: Agent‑Driven Canvas

### Executive summary
MYON evolves from “logbook + chat” into an agent‑driven training canvas. The canvas is a live, ranked stream of cards where agents propose and the user confirms. A single backend reducer applies all state changes after schema, science, and safety validation. The iOS app consumes the canvas via real‑time subscriptions and performs only one type of mutating request: applyAction. Agent reasoning is strictly off the hot path (no LLM calls inside the reducer), guaranteeing deterministic outcomes, low latency, and full auditability.

### Product experience (user lens)
- The app opens with a prominent search bar and mic. The user describes intent (e.g., “analyze my squat progress over 6 months” or “let’s train upper body today”).
- The user transitions into a canvas: a grid‑like, ranked set of cards. Cards show proposals, execution targets, visualizations, tables, summaries, and prompts.
- For ad‑hoc analysis, conversational scaffolding cards appear and then “clear out” as the system posts final visualizations and insights.
- For active workouts, a persistent rail presents the current exercise, sets, and progress. Users can reorder, mark sets as failed, adjust load, add notes, and so on without losing context.
- After completing a workout, the canvas pivots to analysis: charts, comparisons over time, and targeted recommendations.
- Users can navigate to preset canvases such as Progress or Dashboard that are continuously updated by agents.

---

## Core concepts and glossary
- Canvas: A Firestore‑backed workspace per purpose (ad‑hoc analysis, active workout, progress, dashboard). Identified as `users/{uid}/canvases/{canvasId}`.
- Card: Typed, immutable content unit stored under a canvas. Cards can be proposed by agents or created/activated by user actions.
- Up‑Next: A prioritized queue referencing cards that should surface next in the UI.
- Action: The single way to mutate state (via applyAction). Encodes user intent (e.g., ACCEPT_PROPOSAL, LOG_SET, SWAP).
- Reducer: Pure business logic that transforms state in an atomic Firestore transaction. Enforces invariants, versioning, and emits audit events.
- Operators/Agents: Off‑path services that reason, compute, and call proposeCards to enqueue cards. They never mutate state directly.
- Validation gates: SchemaCheck (JSON schema), ScienceCheck (programming heuristics and bounds), SafetyCheck (contraindications, guardrails).
- Lanes: UI convention to separate persistent workout content from ephemeral analysis scaffolding (e.g., lanes: workout, analysis, system).

---

## End‑to‑end architecture

### High‑level dataflow
```
User (iOS)
  │
  │  applyAction {type, payload, idempotency_key}
  ▼
HTTPS Function: applyAction
  ├── SchemaCheck → ScienceCheck → SafetyCheck
  └── Firestore Transaction (Reducer):
        - optimistic concurrency on state.version
        - update state/cards/up_next atomically
        - append minimal event
  ▼
Firestore (users/{uid}/canvases/{canvasId}/...)
  ▲              ▲
  │              └─ iOS subscribes to state/cards/up_next and re-renders
  │
Operators/Agents (off-path)
  │  proposeCards {cards[]}
  ▼
HTTPS Function: proposeCards (service-only)
  - write proposed cards
  - update up_next priorities (no state change)
```

### Key properties
- Determinism: Reducer is pure; no LLM calls inside the transaction.
- Single writer: All state changes flow through applyAction → reducer.
- Auditability: Every commit appends an event capturing inputs and deltas.
- Performance: Target ≤ 250–400 ms P95 for action→UI round trip.

---

## Status audit and roadmap (Sep 2025)

### Current state (implemented)
- Backend
  - Single-writer reducer via `applyAction` with optimistic concurrency (`state.version`) and per-canvas idempotency.
  - Action handlers: `ADD_INSTRUCTION`, `ACCEPT_PROPOSAL`, `REJECT_PROPOSAL`, `ADD_NOTE` (UNDO-supported), `LOG_SET`, `SWAP`, `ADJUST_LOAD`, `REORDER_SETS`, `PAUSE`, `RESUME`, `COMPLETE`, `UNDO` (limited to accept/reject/note).
  - Analysis replacement by `refs.topic_key`; invariant: single active `set_target` per `(exercise_id, set_index)`.
  - `proposeCards` (service-only) with Ajv-validated typed content (session_plan, set_target, coach_proposal, visualization, agent_stream, clarify-questions, list, inline-info, proposal-group, routine-overview); supports shared fields `layout|actions|menuItems|meta` and `priority`.
  - Server-side defaults for shared fields in `proposeCards`: injects `layout|actions|menuItems|meta` when omitted; normalizes `meta.groupId`; clamps `priority`.
  - Action payload validators include `EDIT_SET` (schema present); reducer currently returns `UNIMPLEMENTED` for `EDIT_SET` (MVP stub).
  - Proposal expiry via HTTPS sweep and scheduled function; composite index for `cards(lane, refs.topic_key)` present.
- Up-Next ordering/index: collection group index exists on `up_next(priority DESC, inserted_at ASC)` to support deterministic ordering and trimming; reducer and proposer enforce cap N=20.
  - Firestore rules enforce single-writer: clients have read-only access under `users/{uid}/canvases/**`.
  - `bootstrapCanvas` endpoint creates or returns canvas by `(userId,purpose)` with initialized state.
  - `up_next` cap enforced (N=20) in `proposeCards` and reducer with priority-based trimming.
  - Firestore transaction constraint satisfied: post-transaction, best-effort `up_next` trimming (no reads-after-writes inside tx).
  - Group-level actions `ACCEPT_ALL`/`REJECT_ALL` using `meta.groupId`, emitting compact `group_action` events.
  - Events: `instruction_added {instruction_id, text}`; trailing `apply_action` includes `instruction_id`; `session_started` emitted when a `session_plan` is accepted.
  - `apply_action` includes a `correlation_id` of `${canvasId}:${version}` for UI telemetry.
  - Science/Safety: accepting a `session_plan` validates targets (reps 1–30, RIR 0–5).
- iOS
  - Canvas bootstraps via `bootstrapCanvas` in `CanvasViewModel.start(userId, purpose)`; subscribes live via `CanvasRepository` to `state/cards/up_next`; caches `state.version` for optimistic concurrency.
  - Central dispatcher: Accept/Reject/Accept all/Reject all invoke `applyAction` with `expected_version` and idempotency; single retry on `STALE_VERSION`; UNDO exposed via toast.
  - Visual system: hardened tokens (neutral scale, accent tiers), subtle elevation, hairline borders.
  - UI states: skeleton/empty/error patterns for charts and lists; baseline chart theme (neutral gridlines, min heights) for consistent visuals.
  - Up‑Next rail: ordered by `priority`, capped visually to top 20 with overflow badge; sticky rail with blur background; pinned rail present.
  - UX readiness: “Connecting to canvas…” overlay until first snapshot; inputs disabled with spinner overlay during `applyAction`; brief new‑card highlight on insert.
  - Networking: `ApiClient` passes Firebase ID token, uses exponential backoff, decodes normalized error envelopes to map backend errors to banners/toasts.
  - Telemetry: events listener logs reducer `correlation_id` for debugging.

### Gaps and risks
- Minimal operator not yet implemented: no Stage‑1 proposer reacting to `instruction_added` to emit initial `session_plan`/`set_target`.
- Emulator flakiness: local Functions/Firestore emulator health check is inconsistent; unit/contract tests pass. Maintain a lightweight staging smoke test.
- Typed content mapping in iOS (`CanvasMapper`) is tolerant but not exhaustive; continue expanding as backend schemas grow and schemas gain `$id`s.
- Internationalization/accessibility: add i18n hooks and strengthen accessibility labels across interactive chips and charts.
- Interaction polish: optimistic confirmation and haptic feedback on Accept/Reject (including group actions).
- Auth ops: ensure API key configuration (`VALID_API_KEYS`) and key rotation remain correct in non‑dev environments.

### Prioritized next steps
- Critical
  - Stand up a minimal operator that reacts to `instruction_added` and proposes Stage‑1 cards (`session_plan` + first `set_target`) with grouping/priority; enrich in background.
  - Add action payload validators mirroring iOS sheets where applicable (e.g., `edit-set`).
- Important
  - Add a lightweight staging smoke test automation. (Initial emulator smoke present; extend to staging.)
  - Add reducer property tests for invariants (replacement policies, single active `set_target`, bounds).
  - Consider `uiDigest`/`uiSchema` (or a kit) for schema distribution and caching.
- Nice-to-haves
  - Optimistic UI + haptics on Accept/Reject and group actions; sticky Up‑Next rail; accessibility/i18n pass.
  - Enrich event payloads with compact commit summaries; optional in‑app telemetry overlay.
  - Visualization size policy enforcement with `dataset_ref` upload path.

## Agent system requirements and orchestration

### Functional requirements (and how we satisfy them)
- Receive a prompt (freeform or templated)
  - Source: `applyAction(ADD_INSTRUCTION, { text })` from iOS; optional templated intents from UI actions.
  - Handling: Agents subscribe to canvas `events` and react to `instruction_added` or read latest `instruction` cards in the analysis lane.
- Ask follow‑up questions if needed
  - Emit `clarify-questions` cards via `proposeCards` (lane: analysis, short TTL). Include `meta.groupId` for grouping and `refs.topic_key` for replacement. Answers from the user are routed back via `applyAction(ADD_INSTRUCTION)` or a typed action later.
- Break up the task to return fast
  - Use a pipeline: Stage 1 responds within ~800–1200 ms with minimal viable cards (e.g., `session_plan` skeleton + first `set_target`). Stage 2 enriches asynchronously (summaries, more targets, visuals) as separate proposals.
  - Avoid LLMs on path; any heavy compute runs off‑path with streaming `agentStream` cards when useful.
- Formulate a strategy for how many cards to show
  - Respect `up_next` cap (N≈20) and lane heuristics; keep Stage‑1 proposals minimal (≤3 cards), group related cards via `meta.groupId`, and set explicit priorities.
- Pick UI schema components for visualization
  - Use documented schemas: `session_plan` (workout lane), `set_target`, `summary`, `visualization` (vega‑lite), `inline-info` for explanations, and `proposal-group` for bundle headers. Ajv‑typed validation currently covers `session_plan`, `visualization`, `coach_proposal`; expand coverage next.
- Push content back to the user
  - Call `proposeCards({ canvasId, cards[] })` with typed payloads, TTLs, priorities, and grouping metadata. No state mutation outside the reducer.
- Evaluate user responses and adapt
  - Subscribe to `events` and `cards` to detect `ACCEPT_PROPOSAL|REJECT_PROPOSAL`; use `coach_proposal.reason_code` and inline feedback. On reject/unsafe, propose alternatives or ask clarifying questions; on accept, proceed to populate the rail or queue next targets.

### Reference architecture (MVP: “Generate a workout”)
- Orchestrator (stateless)
  - Watches canvas `events` for `instruction_added` with workout intent. Debounces per canvas and ensures idempotency.
- Card Pipeline Manager
  - Stage 1 (fast path): produces a minimal `session_plan` skeleton (blocks/exercises) and the first `set_target` (lane=workout), plus optional `summary` header (lane=analysis) grouped via `meta.groupId`.
  - Stage 2 (background): enriches with additional `set_target` items, `summary`, and `visualization` as separate proposals.
  - Sets `refs.topic_key` for analysis results to enable replacement on future accepts.
- Workout Proposer (domain logic)
  - Selects 3–6 exercises from catalog constraints (basic heuristics), generates targets with rep/RIR bounds (ScienceCheck‑compatible), and emits typed cards.
- Delivery
  - All outputs via `proposeCards` with Ajv‑compliant content; no writes to `state`/`up_next` outside reducer. Streaming steps can use `agentStream` when helpful.

### Latency strategy and SLAs
- Stage 1 budget: ≤ 800–1200 ms to first cards; prefer ≤ 400 ms function time where feasible.
- Stage 2 enrichments: opportunistic; must not block Stage 1. Keep payloads ≤ 32 KB inline; use `dataset_ref` for larger visuals.
- Reducer budgets unchanged: P50 ≤ 200 ms function time; P95 ≤ 400 ms end‑to‑end per action.

### Alignment check (are we on track?)
- Yes. The existing reducer, schemas, `proposeCards`, Firestore rules, and `bootstrapCanvas` support the MVP pipeline. To ship E2E fast we need a minimal operator that reacts to `instruction_added` and emits Stage‑1 cards; server‑side defaults and a staging smoke test will harden the slice.

---

## UI schema exposure and LLM consumption (fast path + rapid UI dev)

### Goals
- Minimize agent/LLM round‑trip time (no multi‑second schema pulls before proposing cards).
- Keep one canonical contract for cards and shared fields (`layout|actions|menuItems|meta|priority`).
- Allow rapid UI iteration without breaking agents; small, versioned, cacheable increments.
- Make iOS never upload component definitions to Firestore; only agents propose instances; reducer validates.

### Canonical source of truth
- Backend JSON Schemas under `firebase_functions/functions/canvas/schemas/card_types/*` are canonical for all card types.
- Shared fields contract is defined once (outside per‑type) and referenced by all types.
- Versioning:
  - Schema set semver: `schema_set_version` (e.g., `2.3.0`).
  - Per‑type major version: `$id` includes `@<major>` (e.g., `.../session_plan@1`).
  - Backwards policy: minor adds are additive; breaking changes require a new `@major` served in parallel during a deprecation window.

### Option A (recommended): Minimal HTTP digest + conditional type fetches
- `GET /uiDigest` → tiny payload (≪ 10 KB):
  - `{ schema_set_version, shared_fields_version, types: { [type]: { version, sha256 } } }`
  - Used to detect updates without pulling any schemas.
- `GET /uiSchema?type=<t>&version=<v>` → a single JSON Schema for `<t>@<v>`
  - Responds with `ETag: <sha256>` and `Cache-Control: public, max-age=86400`.
  - Agents/LLMs cache by `<type>@<version>` and use `If-None-Match` to avoid re‑downloads.
- Behavior:
  - Agents start with local cache; call `uiDigest` opportunistically (e.g., hourly/background) to learn about changes.
  - Only fetch schemas that are missing or have a new `sha256`.
- Benefits: O(1) small call on hot path; no full manifest transfers.

### Option B: Curated use‑case “kits” (ultra‑compact bundles)
- `GET /uiKit?purpose=workout_generation_v1` → returns just the 4–6 essential types for that flow
  - Example: `session_plan`, `set_target`, `summary`, `proposal-group`, `inline-info` + tiny examples + default priorities.
  - Versioned as `kit_version` separate from schema set.
- Agents pin a kit for prompts/tools and only refresh on `kit_version` change.
- Benefits: Zero per‑type branching in agent logic; smallest prompting surface.

### Option C: Prebuilt SDK packages (no network on hot path)
- Publish versioned packages generated from backend schemas:
  - Node package `@myon/ui-schemas` (precompiled Ajv validators + TS types + tiny examples).
  - Swift Package `MyonUISchemas` (generated Swift types + examples).
- Agents import these packages at build time and validate locally; call `uiDigest` only to detect updates and plan a background refresh/redeploy.
- Benefits: Lowest latency; best developer ergonomics; immutable builds.

### Option D: Static CDN with function proxy
- Publish schema and kit artifacts to GCS (`gs://myon-static/ui-schemas/<version>/...`) fronted by CDN.
- Functions serve as a proxy (same endpoints) with in‑memory caches and ETags for environments where direct CDN isn’t available.
- Benefits: Global low latency and resilient caching.

### Server‑side defaults and normalization (to reduce payloads)
- `proposeCards` accepts minimal payloads and fills defaults for shared fields:
  - If `layout|actions|menuItems|priority|meta` are omitted, server injects reasonable defaults.
  - Normalizes `meta.groupId` and records it so group actions work reliably.
- Outcome: Agents/LLMs emit fewer fields; UI iteration on defaults doesn’t require agent changes.

### Prompt and tool contract guidance for agents/LLMs
- Never fetch the full manifest. Preferred sequence:
  1) Use a pinned kit (Option B) or local SDK (Option C) for prompting/validation.
  2) Occasionally call `uiDigest` to detect updates; fetch only changed types.
  3) Omit optional fields; rely on server defaults.
- Keep examples tiny (≤ 1 KB) in manifests/kits; point to larger docs only for human reading.

### CI/CD and publishing pipeline
- On schema change in backend:
  - Validate all schemas; bump `schema_set_version` and affected per‑type `@major` if breaking.
  - Generate artifacts: `uiDigest`, per‑type schemas, kits, `ui-docs.md`.
  - Publish to GCS/CDN and warm caches; update SDK packages (Node/Swift) and tag releases.
  - Optionally auto‑update `firebase_functions/functions/canvas/README.md` with a generated “UI Schemas” section.
- Drift guards:
  - Verify iOS UI schemas (if any) reference the same `$id`s. Prefer removing iOS‑side schema copies and consuming generated Swift types to eliminate drift entirely.

### Rapid UI iteration options (conjectures)
- Backend‑first (strict canonical): UI changes land as backend schema PRs; codegen updates Swift types. Pros: single source; Cons: requires backend PRs for every UI tweak.
- Shared module (monorepo): A `schemas/` workspace owned by UI + backend with codegen into both projects. Pros: fast iteration; Cons: tooling overhead.
- Dev overlays: Support `GET /uiSchema?type=...&dev=true` to serve draft schemas for test canvases only; disallow in production. Pros: UI prototypes quickly; Cons: requires extra guardrails.

### Risks and mitigations
- Risk: Schema drift between iOS components and backend.
  - Mitigation: single canonical source + codegen + CI drift checks; prefer removing iOS schema copies.
- Risk: LLM latency from schema fetches.
  - Mitigation: Kits/SDKs + `uiDigest` only; ETag caching; CDN.
- Risk: Frequent breaking changes during rapid development.
  - Mitigation: per‑type `@major` co‑existence and short deprecation windows; server defaults for optional fields.

### Proposed initial rollout
- Server‑side: keep canonical JSON Schemas in Functions and validate via Ajv (already in place). Optional: add `uiDigest`/`uiSchema`/`uiKit` for distribution and caching when needed.
- Defaults: add server‑side defaults in `proposeCards` (persist shared fields; normalize `meta.groupId`).
- SDKs: optional future step to publish generated packages once schemas stabilize.

## Implementation status and references

Links (authoritative docs for implementers):
- Canvas: `firebase_functions/functions/canvas/README.md`
- Active Workout: `firebase_functions/functions/active_workout/README.md`
- Functions master: `firebase_functions/functions/README.md`

Implemented (Phase 1):
- Canvas endpoints: `applyAction` (single writer) and `proposeCards` (service-only) with Ajv validation; `expireProposals` (HTTPS) and a scheduled sweep.
- Reducer core: optimistic concurrency with `state.version`, per-canvas idempotency, atomic updates to `state/cards/up_next/events`.
- Actions: `ADD_INSTRUCTION`, `ACCEPT_PROPOSAL`, `REJECT_PROPOSAL`, `ADD_NOTE` (with deterministic UNDO), `LOG_SET`, `SWAP`, `ADJUST_LOAD`, `REORDER_SETS`, `PAUSE`, `RESUME`, `COMPLETE`, `UNDO` (limited to accept/reject/note).
- Invariants and policies: analysis-lane replace-on-accept via `refs.topic_key`; single active `set_target` per set; `up_next` cap enforced (N=20) in reducer and `proposeCards`.
- Typed card schemas enforced in `proposeCards` (Ajv 2020): `session_plan`, `coach_proposal`, `visualization`.
- Shared cores (reused from Active Workout): `log_set_core`, `swap_core`, `adjust_load_core`, `reorder_sets_core`.
- Security and infra: composite index for `cards(lane, refs.topic_key)` present; Firestore rules enforce single-writer for canvases (clients read-only under `users/{uid}/canvases/**`).

Notes:
- Emulator E2E pending (Java install required locally); unit/contract tests cover reducers, schemas, and golden flow at the contract level.
- Minimal progress reports endpoints exist for future use (`upsertProgressReport`, `getProgressReports`).
- `bootstrapCanvas` endpoint is implemented and exported; iOS calls it on start.

Next (targeted scope from this vision):
- Implement minimal operator to react to `instruction_added` and propose Stage‑1 cards; enrich asynchronously.
- Add server‑side defaults/normalization for shared fields in `proposeCards` and consider `uiDigest`/`uiSchema`/`uiKit` endpoints when distribution needs arise.
- Add payload validators that mirror iOS sheets where applicable (e.g., `edit-set`).
- Add more property tests for invariants across `SWAP`/`ADJUST_LOAD`/`REORDER_SETS` and replacement policies.

### Current iOS UI status (component-driven)

- Design tokens: centralized in `MYON2/UI/DesignSystem/Tokens.swift` with spacing, typography, colors, elevation, and layout (`canvasColumns=12`, `contentMaxWidth=860`).
- Grid: `CanvasGridView` uses a 12-track grid; cards span `.oneThird|.oneHalf|.full` via `.gridCellColumns`.
- Cards are schema-driven with a central action dispatcher (`cardActionHandler` in Environment):
  - AgentStreamCard (streaming steps)
  - ClarifyQuestionsCard (structured questions)
  - RoutineOverviewCard (summary: split/days/notes)
  - ListCardWithExpandableOptions (generic list; used for days/exercises)
  - ProposalGroupHeader (Accept all / Reject all)
  - SmallContentCard, SessionPlanCard, SuggestionCard, VisualCard, ChatCard (legacy-compatible)
- Sheets: RefineSheet, SwapSheet, EditSetSheet; Feedback: UndoToast, Banner, Toast; Rails: UpNext and Pinned.
- JSON Schemas under `MYON2/UI/Schemas/*` define all card types and actions (draft-07) with examples in `UI/Schemas/examples/*`.

Runtime behaviors and UX affordances
- Live bootstrap and subscriptions: `CanvasViewModel.start(userId, purpose)` calls `bootstrapCanvas` and attaches Firestore listeners for `state/cards/up_next`.
- Conflict handling: `applyAction` includes `expected_version` and idempotency; single retry on `STALE_VERSION`.
- Readiness and latency UX: a "Connecting to canvas…" overlay blocks input until the first snapshot arrives; interactions disable with a lightweight spinner during `applyAction`.
- Up‑Next rail: strictly ordered by backend `priority`, visually capped to 20 items with an overflow badge; pinned items have a dedicated rail.
- Group actions: ProposalGroupHeader dispatches `ACCEPT_ALL`/`REJECT_ALL` with `payload.group_id = meta.groupId`.
- Undo: toast affordance routes to `applyAction(UNDO)` when eligible.
 - New‑card insertion feedback: brief accent‑tint highlight when cards appear.
 - UI states and charts: skeleton/empty/error patterns; baseline chart theme with neutral gridlines, compact tooltips, and min chart heights.

Why this matters
- Agents can author UI by emitting JSON; the app renders deterministically and routes actions to reducers.
- The UI remains minimal and elegant, with consistent spacing/widths and a clear primary CTA per card or per proposal group.

### Backend implications and proposed evolutions

What stays the same:
- Single-writer reducer via `applyAction` with Schema/Science/Safety checks.
- Agents call `proposeCards` off-path; no LLMs inside the reducer.

What evolves to support UI contracts:
- Expand Ajv schemas to include `layout`, `actions`, `menuItems`, and `meta` (context/groupId/pinned) for new card types:
  - `agentStream`, `clarify-questions`, `routine-overview`, `list` (generic list), `inline-info`, `proposal-group`.
- Support `proposal groups` with consistent `groupId` and group-level actions (accept_all/reject_all) surfaced as events.
- Provide action payload validators for `swap-request` and `edit-set` to mirror iOS sheets (or model as typed `coach_proposal` variants).
- Emit `inline explanations` as `inline-info` cards instead of concatenated prose; TTL optional.

Nice-to-haves (not blockers):
- An evaluation signal for `pin|unpin|explain|refine` so agents can learn preferences without mutating core state.
- A small server-side templater that can coalesce multi-card proposals into a bundled response with an explicit `groupHeader` and ordered children.

Risk notes
- UI will expect reasonable defaults (`layout.width`, gentle text lengths). Agents must avoid overlong bodies in list rows.
- Replacement policies should continue to use `refs.topic_key` for analysis-lane content to avoid duplication.

Performance alignment
- The UI introduces no additional roundtrips; actions still go through `applyAction`. Streaming steps can be rendered via `agentStream` messages from operators writing to `proposeCards`.

---

## Analytics computation and LLM consumption (current)

### Deterministic analytics (off‑path, Phase 1)
- Triggers and jobs compute analytics and write to Firestore under `users/{uid}/analytics_*`:
  - `analytics_series_exercise/{exercise_id}`: daily per‑exercise points `{ e1rm, vol }`, compacted to `weeks_by_start` after 90 days
  - `analytics_series_muscle/{muscle}`: weekly `{ sets, volume }`
  - `analytics_rollups/{yyyy-ww|yyyy-mm}`: compact weekly/monthly totals
  - `analytics_state/current`: job watermarks and cursors
- Compaction merges older day‑level points into weekly buckets to keep storage sublinear.
- These analytics are the source of truth for charts, trends, and deltas and are updated idempotently from watermarks.

### LLM/agent read path (no auto‑publishing)
- Read‑only HTTPS endpoint for compact, typed features; LLMs or fast services consume this to decide if/what to propose:
  - `POST getAnalyticsFeatures` (API key or Bearer)
  - Request includes `mode: 'weekly' | 'week' | 'range' | 'daily'` plus filters (`muscles`, `exerciseIds`) and windows (`weeks`, `weekId`, `start/end`, or `days`).
  - Response includes week ids or daily windows, rollups, per‑muscle weekly series, and per‑exercise daily series with slopes.
- Policy: The platform does not auto‑publish analytics to canvases. LLMs fetch, reason, and then publish cards via `proposeCards` only when appropriate.
- iOS/fast models can read `analytics_*` directly for charts without creating cards.

### Near‑term gaps
- Minimal operator not yet using `getAnalyticsFeatures` to seed “stage‑1” proposals; wiring remains.
- Additional schemas for large visualization payloads (`dataset_ref`) will evolve with UI needs.

Unfinished/near-term front‑end items
- Optimistic UI and haptics: subtle confirmation feedback on Accept/Reject (including group actions).
- Internationalization and accessibility: i18n hooks; additional accessibility labels for chips and charts.
- Content mapping: continue expanding `CanvasMapper` alongside backend schema additions and align on `$id`s.
- Error surfacing: add inline field‑specific hints when action payload validators land (`swap-request`, `edit-set`).


---

## Firestore data model

### Layout
```
users/{uid}/canvases/{canvasId}
  state: {
    phase: "planning|active|analysis",
    purpose: "ad_hoc|workout|progress|dashboard",
    timebox_min?: number,
    current_exercise_id?: string,
    lanes?: ["workout","analysis","system"],
    version: number,
    updated_at, created_at
  }
  meta: {
    user_id: string,
    routine_id?: string,
    name?: string,
    ttl_min?: number,
    tags?: string[]
  }

  cards/{cardId}: {
    type: string,
    status: "proposed|active|accepted|rejected|expired|completed",
    lane?: "workout"|"analysis"|"system",
    content: object,
    refs?: object,
    by: "user"|"agent"|"system",
    ttl?: { minutes: number },
    created_at, updated_at
  }

  actions/{actionId}: {
    type: string,
    card_id?: string,
    payload?: object,
    by: "user"|"agent",
    idempotency_key: string,
    created_at
  }

  up_next/{entryId}: {
    card_id: string,
    priority: number,    // higher first
    inserted_at
  }

  events/{eventId}: {
    type: string,
    payload: object,     // compact commit summary
    created_at
  }

  idempotency/{key}: {
    key: string,
    created_at
  }

  progress_reports/{reportId}: {
    period: { start: timestamp, end: timestamp },
    metrics: object,
    proposals?: object,
    created_at, updated_at
  }
```

### Notes
- Canvases live under `users/{uid}` to simplify security rules and iOS subscriptions.
- `state.version` increments per reducer commit and is used for optimistic concurrency.
- `events` capture commit summaries. If detailed payloads are large, reference Cloud Storage or secondary docs.
- `up_next` should be bounded (e.g., top N) to avoid large reorder writes.

---

## API surface (HTTPS Functions)

### applyAction (single write gateway)
- Input
```json
{
  "canvasId": "string",
  "expected_version": 12,
  "action": {
    "type": "ADD_INSTRUCTION|ACCEPT_PROPOSAL|REJECT_PROPOSAL|ACCEPT_ALL|REJECT_ALL|ADD_NOTE|LOG_SET|EDIT_SET|SWAP|ADJUST_LOAD|REORDER_SETS|PAUSE|RESUME|COMPLETE|UNDO",
    "card_id": "optional",
    "payload": {},
    "by": "user|agent",
    "idempotency_key": "string"
  }
}
```
- Processing: SchemaCheck → ScienceCheck → SafetyCheck → Reducer (transaction with version check) → append event.
- Output
```json
{
  "success": true,
  "data": {
    "state": {"version": 13, "phase": "active", ...},
    "changed_cards": [{"card_id": "...", "status": "accepted"}],
    "up_next_delta": [{"op": "add|remove|reorder", "card_id": "..."}],
    "version": 13
  }
}
```
- Errors: `{ success:false, error:{ code, message, details[] } }` with codes such as `INVALID_ARGUMENT`, `STALE_VERSION`, `SCIENCE_VIOLATION`, `SAFETY_VIOLATION`.

### proposeCards (service‑only)
- Input
```json
{ "canvasId": "string", "cards": [ { "type": "...", "content": {"..."}, "lane": "analysis", "ttl": {"minutes": 10} } ] }
```
- Side‑effects: Writes proposed cards, updates `up_next`. No state mutation. Auth via API key only; require `X-User-Id`.

### bootstrapCanvas
- Purpose: Create or return a canvas id for a given user and purpose.
- Input
```json
{ "userId": "string", "purpose": "ad_hoc|workout|progress|dashboard" }
```
- Output
```json
{ "success": true, "data": { "canvasId": "string" } }
```
- Behavior
- If canvas exists for `(userId, purpose)`, return it; otherwise create with `{ state: { phase: "planning", version: 0, purpose, lanes:["workout","analysis","system"] }, meta: { user_id } }`.

### expireProposals (scheduled)
- Marks `coach_proposal`/ephemeral cards as `expired` and removes them from `up_next` based on TTL.

### UNDO (via applyAction)
- Reverses the most recent reversible action within policies (time window, scope). Submit `applyAction { action: { type: "UNDO", idempotency_key } }`. Uses the event log to derive a deterministic inverse.

### PAUSE / RESUME / COMPLETE (via applyAction)
- Phase transitions handled through `applyAction` with reducer guards: `PAUSE`, `RESUME`, `COMPLETE`.

### upsertProgressReport / getProgressReports
- Persist and fetch weekly/monthly summaries and proposals for strategist features.

### recalcWorkoutAnalytics(workoutId)
- Targeted recalculation for a single workout when data changes or backfills are needed.

---

## Reducer design

### Principles
- Pure business logic: all randomness and LLM calls are off‑path.
- Single responsibility: map an Action + current State → new State + deltas.
- Safety first: invariant checks are centralized and deterministic.
- Atomicity: state/cards/up_next/event update in one transaction.

### Invariants (examples)
- Only one active `set_target` per set.
- Workout rail content cannot be deleted by analysis flows.
- Phase guards: workout mutations allowed only in `phase === "active"`.
- Version must match `expected_version` or the commit aborts.

### Action handlers (non‑exhaustive)
- ACCEPT_PROPOSAL / REJECT_PROPOSAL: transition card status; update up_next; possible state transition hooks.
- ADD_INSTRUCTION: create an instruction card and event; does not change state.
- LOG_SET: persist result, transition `set_target → set_result`, update current set/exercise pointers.
- SWAP / REORDER_SETS / ADJUST_LOAD / MARK_SET_FAILED: mutate the workout rail safely with bounds checks.
- PAUSE / RESUME / COMPLETE: explicit phase transitions with safety rules.
- UNDO: limited, controlled rollbacks using last commit summary.

### Transaction boundary
- Read current state and select related docs (cards, up_next entries) needed for the action.
- Verify version; on mismatch return `STALE_VERSION`.
- Apply deltas; write updates; append minimal event.

---

## Validation gates

### SchemaCheck (Ajv)
- Card schema (typed `content` by `type`) and Action schema compiled on cold start and cached.
- Fail fast with `INVALID_ARGUMENT` and field‑level details.

### ScienceCheck (examples)
- Rep ranges 6–20 for hypertrophy targets; RIR 0–2 default; weekly set bounds per muscle group.
- Load delta guardrails vs last successful set.

### SafetyCheck (examples)
- Contraindications based on user flags; ROM/tempo sanity; equipment availability.

---

## Auth model & security
- `applyAction`: flexible auth (Bearer Firebase ID token preferred; API key allowed for operators). Writes to canvases must occur only via Cloud Functions (single writer).
- `proposeCards`: service‑only via `X-API-Key`; keys configured via environment only. Require `X-User-Id` to resolve the target user.
- Firestore rules: clients may read their own canvases; direct client writes to `users/{uid}/canvases/**` must be denied. Current rules are more permissive—tighten to enforce single-writer.

---

## Integrating existing endpoints (compatibility)
- Keep all current endpoints intact for backward compatibility.
- Extract core logic from `firebase_functions/functions/active_workout/*` into shared modules (`functions/shared/active_workout/…`).
- Both legacy endpoints and the reducer call these shared modules—no HTTP calls from the reducer.

- Phase 1 scope (current): shared cores are extracted and used for `LOG_SET`, `SWAP`, `ADJUST_LOAD`, and `REORDER_SETS`.

---

## iOS app consumption

### Access pattern
- Single mutating call: `applyAction` with `expected_version` and `idempotency_key`.
- Real‑time read: subscribe to `users/{uid}/canvases/{canvasId}/{state,cards,up_next}`.

### UI structure with lanes
- Workout lane: persistent rail (session_plan, current_exercise, set_target/result, notes).
- Analysis lane: ephemeral scaffolding (instruction, analysis_task, visualization, table, summary, followup_prompt) with TTL.
- System lane: low‑level events/prompts not typically shown by default.

### Lane semantics (policy)
- Replacement vs. persistence
  - Analysis lane: replace‑on‑accept. Cards sharing a `topic_key` (in `refs.topic_key`) form a replacement group. When a new result for the same topic is accepted, prior group members are marked `completed|expired` and the latest becomes primary. Short default TTL (e.g., 10 minutes) for scaffolding (`instruction`, `analysis_task`, `followup_prompt`).
  - Workout lane: append‑only/persistent. Cards represent the workout rail and are never wiped by analysis flows. Mutations occur via versioned replacements (e.g., `set_target → set_result`) through the reducer, not UI clearing. Deletions only via explicit reducer transitions (e.g., `COMPLETE`).
  - System lane: append‑only, hidden by default, lowest priority.

- Prioritization
  - `up_next` is global but respects lane heuristics: pinned workout rail items remain at the top; fresh analysis results bubble; system items are deprioritized.
  - Cap `up_next` to N=20 entries; reorders are incremental (avoid wholesale rewrites).

- Replacement groups
  - Cards include `refs.topic_key` to declare a logical group (e.g., `progress:squat:6m`). Accepting a new result in the analysis lane updates status of older group members and replaces them in `up_next` rather than adding unbounded duplicates.

### Example sequences

1) Ad‑hoc analysis (search/mic)
```
iOS → applyAction { type: "ADD_INSTRUCTION", payload:{ text:"analyze squats last 6 months" } }
Reducer → create instruction card; event("instruction_added")
Agent (off-path) sees event → compute datasets/charts → proposeCards([
  {type:"analysis_task", ...}, {type:"visualization", ...}, {type:"summary", ...}, {type:"followup_prompt", ...}
])
iOS subscription updates → show results; TTL removes scaffolding cards later
```

2) Active workout
```
iOS → applyAction { type:"ACCEPT_PROPOSAL", card_id: session_plan }
Reducer → state.phase="active"; populate workout rail
iOS → applyAction { type:"LOG_SET", payload:{ exercise_id, set_index, actual } }
Reducer → set_target→set_result; update pointers; event("set_logged")
iOS → applyAction { type:"COMPLETE" }
Reducer → state.phase="analysis"; event("workout_completed")
Agent → proposeCards([ charts, tables, session_summary ]) for post‑workout analysis
```

### Offline and conflict handling
- Use `expected_version` and idempotency keys. On `STALE_VERSION`, refetch state and retry.
- UI should cache the last version and only enable inputs when subscription confirms readiness.

### iOS MVP implementation plan (front‑end next steps)
- Repository and bootstrap
  - Implement `CanvasRepository.start(userId, purpose)` that:
    - Calls `bootstrapCanvas` to get or create `{ canvasId }` for the `purpose`.
    - Subscribes to `users/{uid}/canvases/{canvasId}/{state,cards,up_next}` and exposes typed publishers/observables to the ViewModel.
    - Persists `canvasId` for the session and caches the latest `state.version`.
- CanvasScreen wiring
  - Replace demo seeding with live repository data.
  - Bind `CanvasScreen` to repository streams and render cards by `type` using existing components (AgentStreamCard, ClarifyQuestionsCard, RoutineOverviewCard, ListCardWithExpandableOptions, ProposalGroupHeader, SessionPlanCard, VisualCard, etc.).
  - Implement Up‑Next rail ordering by `priority`; respect cap visually (top 20) and keep pinned items at the top.
- Action dispatcher
  - Provide a centralized `cardActionHandler` that maps UI interactions to `applyAction` payloads (ACCEPT_PROPOSAL, REJECT_PROPOSAL, ACCEPT_ALL, REJECT_ALL, LOG_SET, SWAP, ADJUST_LOAD, REORDER_SETS, ADD_NOTE, ADD_INSTRUCTION).
  - Always include `expected_version` from the last observed state and a fresh `idempotency_key` (UUID) per user interaction.
  - On `STALE_VERSION`, fetch the latest version from the repository and retry once; disable the CTA while retrying.
- Auth and networking
  - Ensure Firebase Auth is initialized and pass Bearer ID token for `applyAction` and `bootstrapCanvas` (no API key on device).
  - Centralize HTTP client with exponential backoff and structured error decoding.
- Version and idempotency handling
  - Cache and surface `state.version` in the ViewModel; gate CTAs until subscriptions are active.
  - Generate idempotency UUIDs per interaction; deduplicate repeated taps by disabling until response.
- Group actions
  - Wire ProposalGroupHeader “Accept all / Reject all” to `ACCEPT_ALL` / `REJECT_ALL` using `payload.group_id = card.meta.groupId`.
- Error and undo UX
  - Map backend errors to UX: `INVALID_ARGUMENT` → inline validation; `STALE_VERSION` → silent retry then banner; `SCIENCE_VIOLATION` → inline hints; `PHASE_GUARD` → disabled CTAs.
  - Show Undo toast for supported actions (accept/reject/note) and route to `applyAction(UNDO, idempotency_key)`.
- Telemetry and logs
  - Subscribe to `events` for debugging and include the reducer’s `correlation_id` in debug logs; optionally surface in a developer overlay.
- QA checklist (staging smoke test)
  - Start (bootstrap) → Propose (agent) → Accept (auto start) → Log set → Complete; verify Up‑Next order, group actions, and version retry path.
- Definition of done
  - Canvas opens on live data without demo seeding; CTAs operate via `applyAction` with version/idempotency; error/undo UX present; staging smoke test passes.

---

## Card and Action schemas (LLM‑friendly)

### Card (generic)
```json
{
  "type": "instruction|analysis_task|visualization|table|summary|followup_prompt|session_plan|current_exercise|set_target|set_result|note|coach_proposal",
  "status": "proposed|active|accepted|rejected|expired|completed",
  "lane": "workout|analysis|system",
  "content": {},
  "refs": {},
  "by": "user|agent|system",
  "ttl": {"minutes": 10}
}
```

### Action
```json
{
  "type": "ADD_INSTRUCTION|ACCEPT_PROPOSAL|REJECT_PROPOSAL|ACCEPT_ALL|REJECT_ALL|ADD_NOTE|LOG_SET|EDIT_SET|SWAP|ADJUST_LOAD|REORDER_SETS|PAUSE|RESUME|COMPLETE|UNDO",
  "card_id": "optional",
  "payload": {},
  "by": "user|agent",
  "idempotency_key": "string"
}
```

#### LLM quick‑reference (validated server‑side via Ajv)
- applyAction request schema: `firebase_functions/functions/canvas/schemas/apply_action_request.schema.json`
- proposeCards request schema: `firebase_functions/functions/canvas/schemas/propose_cards_request.schema.json`
- Available card types now: `session_plan`, `set_target`, `coach_proposal`, `visualization`, `agent_stream`, `clarify-questions`, `list`, `inline-info`, `proposal-group`, `routine-overview`
- Shared fields on all cards: `layout`, `actions`, `menuItems`, `meta`, `refs`, `priority`, `ttl`
  - Server fills defaults for omitted shared fields; `meta.groupId` is normalized (lowercase slug)
- Replacement policy: set `refs.topic_key` on analysis cards to enable replace‑on‑accept


### CoachDecision (for coach_proposal.content)
```json
{
  "action": "LOG_SET|ADJUST_LOAD|SWAP|...",
  "delta": {},
  "reason_code": "enum",
  "rationale_ui": "string"
}
```

### SessionPlan (content)
- Reuse existing plan structure from active workout endpoints (typed JSON only, no prose).

### Visualization card payload (decision)
- Decision: cards carry a visualization spec plus a dataset reference when large; small datasets may be inlined.
```json
{
  "chart_type": "line|bar|table|heatmap|sparkline",
  "spec_format": "vega_lite",
  "spec": { },
  "dataset_inline": { },
  "dataset_ref": {
    "uri": "gs://myon-data/...",
    "format": "parquet|json|csv",
    "bytes": 12345,
    "sha256": "..."
  },
  "params": { }
}
```
- Size policy:
  - Inline if payload ≤ 32 KB; otherwise upload dataset to GCS and set `dataset_ref`.
  - Event payloads remain compact; large derivations live in referenced blobs or secondary docs.

---

## Performance and scaling
- Target ≤ 250–400 ms P95 action→UI.
- Keep transaction scope minimal: state + small set of docs. Cap `up_next` list.
- Precompile JSON Schemas (Ajv) at cold start and reuse.
- Prefer references to blobs/specs for large charts/tables over inlining large datasets.

- Guardrails:
  - Reducer transaction touches ≤ 10 documents and ≤ 2 index updates.
  - `up_next` size ≤ 20; per‑commit reorder ops ≤ 10.
  - Event payload ≤ 2 KB; store verbose details out‑of‑band.
  - Reads: ≤ 2 targeted queries per action; no collection scans; avoid cross‑canvas joins.
  - Latency budgets: P50 ≤ 200 ms function time; P95 ≤ 400 ms end‑to‑end including Firestore commit.

---

## Learning and self‑improvement
- Log rejected `coach_proposal` cards and their `reason_code` for offline evaluation.
- Persist lightweight feedback docs (or encode in `events`) for nightly analysis:
```json
{
  "type": "coach_feedback",
  "proposal_card_id": "...",
  "decision": "rejected|accepted",
  "reason_code": "enum",
  "context": { "lane": "analysis|workout", "topic_key": "..." },
  "created_at": "timestamp"
}
```
- Use aggregate feedback to adjust operator prompts/strategies (off‑path), not reducer logic.

---

## Observability and audit
- Events include action inputs, affected doc ids, state version before/after.
- Centralized logging with correlation id `{canvasId}:{version}`.
- Metrics: transaction latency, contention rate, P95 end‑to‑end, duplicate idempotency hits, Science/Safety rejection counts.

---

## Failure modes and rollback
- `STALE_VERSION`: instruct client to refetch and retry.
- Science/Safety violation: show structured error with fix hints; do not write.
- Undo (V1): only ACCEPT/REJECT_PROPOSAL and ADD_NOTE are undoable; sets/logs are not undoable until lineage is robust.

---

## Backwards compatibility
- Existing functions remain; the reducer calls shared helpers extracted from them.
- iOS migrates screen‑by‑screen: new canvases first, then legacy paths can be retired gradually.

---

## Initial implementation plan (phased)
1) Data model + rules
   - Add `users/{uid}/canvases/*` with subcollections; write base rules.
2) Gateways
   - `applyAction` (ADD_INSTRUCTION, ACCEPT/REJECT_PROPOSAL, ADD_NOTE) + Ajv + scoped idempotency + events.
   - `proposeCards` (service‑only) + `expireProposals`.
3) Workout rail basics
   - Extract minimal shared logic for `LOG_SET` only in Phase 1; support `SWAP` and `ADJUST_LOAD` next.
4) iOS wiring
   - Hook search/mic → `ADD_INSTRUCTION`; subscribe to lanes; render visualization/table cards.
5) Tests & perf
   - Contract tests, reducer property tests, golden E2E replay, load test.

---

## Open questions
- Topic grouping: best practices for generating `refs.topic_key` (intent hash vs semantic label) and TTL for groups.
- Undo window: precise constraints (e.g., last 1 commit within 10 minutes) and UX for surfacing undo affordances.
- Dataset retention: GCS lifecycle/TTL for large visualization datasets; storage cost thresholds.
- Progress and dashboard canvases: cadence of updates and ownership (agent schedules vs on‑demand).

---

## Backend analytics pipeline (phased) — trigger evolution and end‑state

### Why now
- We already compute several analytics via Functions and triggers (workout/template analytics, weekly stats). The canvas vision benefits most when analytics and insights are precomputed and written back for fast, deterministic UI and operator consumption.
- This section details how to evolve existing triggers and calculations into a scalable, extendable, performant pipeline with two phases: deterministic analytics (no LLMs) and reasoning‑assisted insights (LLMs off‑path). It also specifies storage, TTL/retention, orchestration, and the end‑state contract with the canvas.

### Inventory (current, from code and schema)
- Triggers and jobs
  - `triggers/weekly-analytics.js`: updates `users/{uid}/weekly_stats/{weekId}` on workout completion/deletion; scheduled daily recalculation and manual callable.
  - `triggers/muscle-volume-calculations.js`: computes `template.analytics` and `workout.analytics` when missing/updated.
  - Active workout HTTPS tools (`active_workout/*`) with shared cores for `log_set`, `adjust_load`, `reorder_sets`.
  - Canvas reducer (`canvas/apply-action.js`): single‑writer transactional updates with events, `up_next` management, TTL sweeps for proposals.
- Data products
  - Archived `workouts` with optional embedded `analytics`; `weekly_stats` aggregates; template analytics.
  - Canvas artifacts (cards/up_next/events) produced by reducer and off‑path operators via `proposeCards`.
- Gaps
  - No canonical per‑exercise/muscle time series for long‑horizon trends (e1RM, volume, PR events).
  - No compact "insights" store with TTL and replacement semantics.
  - Analytics recomputation is partially spread across triggers; lacks watermarks/idempotent controllers for backfills and incremental updates.

### End‑state overview (what “done” looks like)
```
Cloud Scheduler ──▶ Cloud Run Controller ──▶ Cloud Tasks (per‑user, concurrency=1)
      │                         │
      │                         ├─▶ Deterministic Worker (Node) ──▶ Firestore (users/{uid}/analytics/*)
      │                         │                                      ├─ series_exercise/{exercise_id}
      │                         │                                      ├─ series_muscle/{muscle}
      │                         │                                      ├─ rollups/{yyyy‑ww|yyyy‑mm}
      │                         │                                      └─ insights/{insightId}
      │                         └─▶ Reasoning Worker (LLM) ─────────▶ proposeCards (service‑only)
      │                                                                   (+ optional insights docs)
      └─▶ Existing Triggers keep running (workout analytics, weekly_stats), now writing into shared modules/series

Canvas: iOS subscribes to state/cards/up_next; operators publish `visualization|summary|coach_proposal|inline-info|proposal-group` via `proposeCards`. Reducer remains pure, single writer.
```

Key properties
- Deterministic core first; LLMs only consume compact features, never mutate state directly; all outputs are typed cards or small insight docs.
- Incremental, idempotent, per‑user scheduling with watermarks; backfills safe and bounded.
- Storage separates compact Firestore facts (series/rollups/insights) from large chart data in GCS (`dataset_ref`).
- TTLs and downsampling maintain performance and cost; canvas proposals use replace‑on‑accept with `refs.topic_key` and group TTLs.

---

### Phase 1 — Deterministic analytics (no LLMs)

Scope
- Compute and store core metrics using traditional code and existing triggers, evolved into shared modules and a nightly controller.

Calculations
- Set/e1RM features
  - e1RM per set using method tag (`epley|brzycki`) with inputs `{weight_kg, reps}`; record method and parameters for audit.
  - Per‑exercise and per‑workout aggregates: total sets, reps, volume (Σ weight×reps), average RIR if available.
- Progression deltas and PRs
  - Deltas vs last same‑exercise session: load at matched reps, reps at fixed load, total volume, and density (volume/min if duration exists).
  - PR markers: rep PRs and e1RM PRs (per rep range bands) and volume PRs; store as sparse events in series.
- Weekly/monthly rollups
  - Per muscle: weekly set counts and volume; per exercise: weekly volume and top e1RM.
  - Adherence: planned vs completed sessions; consistency streaks (requires optional routine/plan metadata when present).
- Coverage and balance heuristics (deterministic signals only)
  - Rep range coverage (1–5, 6–12, 13–20), push/pull, quad/ham, horizontal/vertical press exposure counts.

Trigger evolution (how we extend what exists)
- `workout.analytics` computation
  - Move e1RM and aggregation logic into `functions/utils/analytics-calculator.js` as the single source (already referenced by triggers). Ensure both template/workout analytics reuse it.
  - When `workout.analytics` is produced by triggers or by the archival path in `active_workout/complete-active-workout.js`, also emit updates to series via a shared writer:
    - `analytics_writes.appendExerciseSeries(uid, exerciseId, point)`
    - `analytics_writes.appendMuscleSeries(uid, muscleKey, weekId, delta)`
- `weekly-analytics.js`
  - Keep writing `users/{uid}/weekly_stats/{weekId}` for backward compatibility.
  - Additionally update `analytics/rollups/{yyyy‑ww}` with a compact, denormalized document used by downstream features and LLMs.
  - On deletion paths, subtract via the same shared writer to maintain idempotence.
- Scheduled recomputation
  - Replace ad‑hoc scans with Cloud Scheduler → Cloud Run controller that enqueues per‑user tasks (Cloud Tasks) using watermarks:
    - `analytics_state.current`: `{ last_processed_workout_at, last_rollup_at, series_versions, job_cursors }` under `users/{uid}`.
    - Workers query only `workouts` with `updated_at > watermark` and commit new points/rollups.

Storage model (new/extended)
- `users/{uid}/analytics/series_exercise/{exercise_id}`
  - Fields: `{ points: [{ t, e1rm?, vol?, rep_pr?, rep_pr_meta?, density? }], schema_version, updated_at }`.
  - Compaction: keep high‑res points ≤ 90 days; beyond that, store weekly medians/maxima; preserve sparse PR events.
- `users/{uid}/analytics/series_muscle/{muscle}`
  - Weekly docs keyed by `yyyy‑ww`: `{ sets, volume, exposure, updated_at }`.
- `users/{uid}/analytics/rollups/{periodId}`
  - `periodId` is `yyyy‑ww` or `yyyy‑mm`; maps for per‑exercise and per‑muscle aggregates; very compact.
- `users/{uid}/analytics_state/current`
  - Watermarks and cursors for idempotent incremental processing.
- Visualization datasets
  - For larger charts, write compact datasets to GCS (`gs://myon-data/analytics/<uid>/<artifact>.parquet`) and reference via `dataset_ref` in `visualization` cards.

Publishing to the canvas (deterministic)
- Off‑path operator posts minimal cards via `proposeCards` using Ajv‑typed content:
  - `visualization` with `spec_format=vega_lite` and `dataset_ref` when needed.
  - `summary` and `inline-info` for compact callouts (PRs, adherence streaks).
  - `proposal-group` to bundle 2–4 related items with `meta.groupId` like `weekly_progress_<yyyy‑ww>`.
- Use `refs.topic_key` for analysis replacement (e.g., `progress:squat:6m`). Set TTL on ephemeral analysis cards (e.g., 14 days).

Retention and TTL policy (Phase 1)
- Workouts: keep indefinitely (source of truth).
- Series: high‑res for 90 days → compact weekly for older; keep PR events.
- Rollups: keep (very compact). `weekly_stats` remains for BC.
- Visualization datasets (GCS): lifecycle 180–365 days; can be regenerated.

Definition of done (Phase 1)
- Deterministic worker computes series/rollups idempotently using watermarks; triggers feed the same writers.
- At least two weekly proposal groups published (`Summary + Visualization + 1 coach‑agnostic callout`).
- Storage, compaction, and indices in place; costs and latencies within budgets.

---

### Phase 2 — Reasoning‑assisted insights (LLMs off‑path, aligned with LLM guidance)

Alignment principles (from our LLM guidance)
- No LLM calls inside the reducer; reasoning is strictly off‑path.
- Agents/LLMs output only Ajv‑typed cards and/or compact insight docs; server fills defaults for shared fields.
- Prefer Option B/C from UI schema exposure: use a curated kit (`uiKit`) or a prebuilt SDK for schemas/validators to avoid hot‑path manifest fetches; optionally call `uiDigest` out of band.

Inputs (bounded, precomputed)
- Deterministic features only: last 4–6 weeks rollups, e1RM slopes per key lifts, exposure counts, volume vs target ranges per muscle, adherence, PR events, balance metrics. Strict size cap.

Insight classes (science‑informed)
- Volume target adherence (Schoenfeld): recommend +/− sets to bring weekly volume per muscle into a target band (e.g., 10–20 sets/week).
- Progression heuristics (Israetel): if e1RM plateau with adequate volume/exposure, suggest a small load increase, rep progression, or a deload week.
- Balance and coverage (Nippard): push/pull; quad/ham; horizontal/vertical press; rep range diversity; suggest accessory swaps or redistribution.
- Fatigue signals: concurrent volume high and e1RM slope negative over ≥2–3 weeks → propose set reduction next week for affected muscle group.

Contracts and guardrails
- Emit `coach_proposal` with `{ action, delta, reason_code, rationale_ui }` where `reason_code ∈ { low_volume, high_volume, plateau_detected, steady_progress, imbalance_detected, fatigue_signals }`.
- Group proposals with `proposal-group` headers; add `summary` and `visualization` when helpful.
- All proposals must satisfy Science/Safety bounds enforced on accept by the reducer.
- Use `refs.topic_key` for replacement and `ttl` (30–60 days) on insight cards; write a matching compact doc under `analytics/insights/{id}` with `ttl_min` to enable sweeps.

Orchestration
- Scheduler → Cloud Run Reasoning Worker:
  - Per‑user task reads compact features from `analytics/rollups` and `series_*`, never raw workouts.
  - Generates ≤ 3 proposals per week; defers to deterministic Phase‑1 cards when insights are weak/ambiguous.
  - Optionally emits `clarify-questions` when data is insufficient (short TTL, grouped).
- Caching and schemas
  - Reasoning worker pins a `uiKit` or SDK version, validates outputs via precompiled Ajv; uses `uiDigest` periodically to detect schema changes.

Storage and TTL (Phase 2)
- `users/{uid}/analytics/insights/{id}`: `{ type, period, signal, recommendation, reason_code, ttl_min, created_at, updated_at }`.
- Canvas cards: grouped per week with `meta.groupId`; TTL 2–4 weeks; replace on accept per topic.

Definition of done (Phase 2)
- Weekly reasoning job emits typed proposals with enumerated reason codes and passes Ajv validation; reducer Science/Safety guards accept them deterministically.
- iOS shows proposal groups with clear next actions; undo and error UX aligned with existing policies.

---

### Data model, TTL, and indexes (additions)
- Collections
  - `users/{uid}/analytics_state/current` (watermarks/idempotency)
  - `users/{uid}/analytics/series_exercise/{exercise_id}` and `series_muscle/{muscle}`
  - `users/{uid}/analytics/rollups/{yyyy‑ww|yyyy‑mm}`
  - `users/{uid}/analytics/insights/{id}` with `ttl_min`
- TTL and sweeping
  - Extend existing `expire-proposals` sweeps with an `expire-insights` job that removes/archives insight docs past TTL and unlinks from `up_next`.
- Indexes
  - Ensure `workouts` indexed by `end_time` and `updated_at`.
  - Add composite where needed for `analytics/rollups` period range queries and `series_*` lookups by key.

### Orchestration, performance, and security
- Orchestration
  - Cloud Scheduler → Cloud Run Controller → Cloud Tasks (per‑user concurrency=1). Jobs are idempotent via `analytics_state` watermarks and per‑task idempotency keys.
  - Firestore triggers continue to run on workout/template changes, but delegate writes through shared analytics writers to keep a single data path.
- Performance
  - Incremental reads only (watermark > `updated_at`); batch writes; compaction to weekly points for old data; large datasets in GCS with `dataset_ref`.
  - Adhere to Firestore budgets (≤ 10 docs/2 index updates per transaction; avoid transactions for pure writes where safe).
- Security
  - `proposeCards`: API‑key only with `X-User-Id`; `applyAction`: Firebase ID token.
  - Firestore rules remain single‑writer for canvases; analytics collections are user‑scoped with standard owner read/write.

### Migration and compatibility plan
- Week 0–1
  - Introduce `analytics_state.current` and shared analytics writers; keep current triggers intact.
  - Start writing series/rollups alongside existing `weekly_stats` on new workouts only.
- Week 2–3
  - Backfill last 90 days per user via the controller using watermarks; compact older data on the fly.
  - Publish first weekly proposal group (deterministic visuals + summary) to the canvas for a small cohort.
- Week 4+
  - Enable reasoning worker on top of compact features; add enumerated reason codes; expand coverage gradually.
  - Optionally reduce duplicate fields in legacy `weekly_stats` once the canvas/UI consume rollups.

### User‑first outputs (prioritized content)
- Adherence and consistency: clear weekly summary and streaks.
- Simple, actionable progression: next‑week micro‑adjustments (add 1 rep, +1.25 kg, shift 1–2 sets).
- Volume vs target ranges per muscle: under/over by set counts.
- PR callouts: rep PRs and e1RM milestones with context.
- Balance checks: push/pull and quad/ham; rep‑range coverage.

---

### Summary (analytics pipeline)
- Phase 1 delivers deterministic series/rollups with compact storage, TTL, and weekly canvas cards; triggers evolve to shared writers and idempotent controllers.
- Phase 2 adds LLM‑assisted, science‑aligned proposals using only precomputed features, emitting typed cards under strict validation and guardrails.
- The reducer remains pure; the canvas stays fast and deterministic, with reasoning entirely off‑path and insights expiring gracefully.

### Phase 1 — next steps (actionable)
- Implement shared analytics writers
  - Create `functions/utils/analytics-writes.js` with `appendExerciseSeries`, `appendMuscleSeries`, `upsertRollup`, `updateWatermark`.
  - Refactor `triggers/muscle-volume-calculations.js` and `active_workout/complete-active-workout.js` to call these writers after computing `workout.analytics`.
- Add analytics state and collections
  - Write `users/{uid}/analytics_state/current` watermarks.
  - Create `users/{uid}/analytics/series_exercise/*`, `series_muscle/*`, and `rollups/*`; add minimal indexes.
- Orchestrate incremental jobs
  - Deploy Cloud Scheduler → Cloud Run controller → Cloud Tasks (per‑user concurrency=1) to process workouts with `updated_at > watermark`.
  - Backfill last 90 days using the controller; compact older points to weekly medians.
- Publish weekly canvas cards
  - Operator posts a `proposal-group` per week with `summary` + `visualization` (use `dataset_ref` for large data) and `refs.topic_key`.
  - Set TTL (e.g., 14 days) for ephemeral analysis cards; verify `up_next` cap and priorities.
- Tests, perf, and rules
  - Contract tests for series/rollups writers; property tests for compaction.
  - Ensure Firestore rules allow user‑scoped analytics writes by backend; keep canvases single‑writer.
  - Add lifecycle to GCS analytics artifacts (180–365 days).

### Phase 1 — guardrails, scaling, and edge cases
- Keep it simple
  - Only 3 primitives in Phase 1 storage: `series_exercise`, `series_muscle`, `rollups`, plus `analytics_state` watermarks. Everything else derives from these.
  - One controller, one per‑user worker; shared analytics writers used by both triggers and workers.
- Scaling assumptions (thousands of users)
  - Per‑user concurrency=1 prevents contention; work is O(Δworkouts) via watermarks.
  - Writes per workout bounded: ≤ 1 series_exercise append per exercised lift and ≤ 1 series_muscle update per muscle/week; batch where possible.
  - Compaction keeps series size sublinear over time (weekly beyond 90 days).
- Edge cases
  - New user (no data): controller writes empty rollup with zeros and sets watermark; publisher skips canvas visuals until ≥1 workout.
  - Churned user: no new `updated_at` > watermark; job becomes a no‑op; weekly publisher may emit adherence summary (“no sessions this week”) with low priority.
  - Active heavy user: batch points per workout; use GCS datasets for large visuals; enforce `up_next` cap.
  - Deleted/edited workouts: triggers call shared writers with negative deltas/overwrites keyed by workout id where needed; recomputation jobs reconcile via `updated_at`.
  - Timezone changes: rollups use user’s current timezone from `user_attributes` when computing week ids; on change, recompute last 2 weeks in next run.
  - Method changes (e1RM formula): bump `schema_version`; recompute affected points lazily on next compaction pass.
  - Partial data (missing RIR/duration): compute what’s available; omit density/avg RIR safely.
  - Data spikes (import/backfill): controller chunks processing windows (e.g., 100 workouts per task) to avoid timeouts.
  - Quotas/errors: retry with exponential backoff; store last error in `analytics_state` for observability; skip user after N failures and alert.



### Appendix: ASCII sequence diagrams

Ad‑hoc instruction to insights
```
User(iOS) → applyAction(ADD_INSTRUCTION) → Validator+Reducer → Event(instruction_added)
Agent(worker) ← subscribes/reads event → compute → proposeCards(analysis_task, visualizations, summary)
iOS ← Firestore subscriptions update → render cards in priority order
expireProposals(schedule) → marks scaffolding expired → UI hides them
```

Active workout logging
```
iOS → applyAction(ACCEPT_PROPOSAL: session_plan)
Reducer → state.phase=active; populate workout rail; event(session_started)
iOS → applyAction(LOG_SET: actual)
Reducer → update set_result; pointers; event(set_logged)
iOS → applyAction(COMPLETE)
Reducer → state.phase=analysis; event(workout_completed)
Agent → proposeCards(charts, tables, session_summary)
```


