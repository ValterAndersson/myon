# Firebase Functions - Povver

Agent-first backend for Povver. This README reflects the current code and endpoints (authoritative). Use this as the tool contract for agents and for manual cURL testing.

## Auth
- API key header for agents: `X-API-Key: <key>`
- Environment-driven keys: set `VALID_API_KEYS` (comma-separated). In emulator, a fallback dev key is allowed. The `withApiKey` and `requireFlexibleAuth` wrappers both use the same validator.
- Some endpoints accept optional `X-User-Id`, but most write endpoints now work with API key only (default `created_by: "service"`).

Base URL:
```
https://us-central1-myon-53d85.cloudfunctions.net/
```

Responses use a normalized shape via utils/response:
- Success: `{ success: true, data: {...}, meta? }`
- Error: `{ success: false, error: { code, message, details? } }`

---
## Endpoint Inventory (by domain)

### Health
- `health` – liveness probe

### User
- `getUser` – profile + normalized preferences context
- `updateUser` – update profile fields
- `getUserPreferences` / `updateUserPreferences` – single source of truth (`users/{uid}/user_attributes/{uid}` mirrored to `users/{uid}`)
  - Note: `updateUserPreferences` uses upsert for both the subdocument and the user mirror. If docs don't exist, they are created.

### Workouts
- `getUserWorkouts` – history + analytics summary
- `getWorkout` – single workout + metrics
- `upsertWorkout` – create or update workout with inline analytics and set_facts (import scripts)
- `deleteWorkout` – delete completed workout (v2, Bearer lane). `onWorkoutDeleted` trigger in `weekly-analytics.js` handles stats rollback

### Templates
- `getUserTemplates`, `getTemplate`, `createTemplate`, `updateTemplate`, `deleteTemplate`

### Routines
- `getUserRoutines`, `getRoutine`, `createRoutine`, `updateRoutine`, `deleteRoutine`, `getActiveRoutine`, `setActiveRoutine`

### Active Workout (agent tools)
- `proposeSession` – plan stub
- `startActiveWorkout`, `getActiveWorkout`
- `logSet` (v2, idempotent), `patchActiveWorkout` (v2), `autofillExercise` (v2)
- `addExercise` (v2, idempotent), `swapExercise` (v2, idempotent)
- `completeActiveWorkout` (v2), `cancelActiveWorkout` (v2)

See `active_workout/ARCHITECTURE.md` for detailed endpoints and shared cores (used by Canvas reducer).

### Exercises (catalog + curation)
- Read
  - `getExercises` – list, `getExercise` – by id/name/slug/alias
  - `searchExercises` – flexible filters, name prefix fallback
  - `listFamilies` – grouped view by `family_slug` with members (+ variants)
  - `searchAliases` – prefix search in `exercise_aliases`
- Write/curate
- `upsertExercise` – create/update; canonicalizes name/slug, sets family/variant, reserves aliases; idempotent-like by slug; uses upsert semantics (merge)
  - `refineExercise` – schema-lite metadata enrichment
  - `approveExercise` – mark approved
  - `ensureExerciseExists` – find-or-create by name
  - `resolveExercise` – choose best candidate given context
  - `mergeExercises` – safe merge (same family + variant); preserves history via `merged_into` redirect
  - `upsertAlias` / `deleteAlias` – manage alias slugs in `exercise_aliases`
  - `repointAlias` / `repointShorthandAliases` – maintenance: retarget aliases to canonical ids
  - `suggestFamilyVariant` – pure: infer `family_slug` + `variant_key`
  - `suggestAliases` – pure: generate alias candidates (verbose + shorthands)
- Maintenance / normalization
  - `normalizeCatalog` – sweep normalization (fields + alias registry); large calls may time out
  - `normalizeCatalogPage` – paginated normalization (preferred)
  - `backfillNormalizeFamily` – plan/apply merges for a single family; merges within `family_slug::variant_key` only
  - `listFamilies` – inspect remaining duplicates and variants

Catalog model:
- `exercises/{exerciseId}` (canonical docs)
- `exercise_aliases/{alias_slug}` → `{ exercise_id, family_slug }` (source of truth for name routing)
- Core fields: `name`, `name_slug`, `family_slug`, `variant_key`, `movement`, `equipment`, `metadata`, `merged_into?`, `merge_lineage?`, timestamps

### Training Analysis (pre-computed insights)
- `getAnalysisSummary` – retrieve pre-computed training analysis (insights, daily brief, weekly review). Supports `sections`, `date`, `limit` params. Called by Shell Agent's `tool_get_training_analysis`
- `getMuscleGroupSummary` / `getMuscleSummary` / `getExerciseSummary` – live drilldown summaries. `getExerciseSummary` accepts `exercise_name` for fuzzy name→ID resolution via the user's training history
- `querySets` / `aggregateSets` – raw set-level data queries with filtering (v2 onRequest + requireFlexibleAuth). Sorts by `workout_date` when date range filters are present to satisfy Firestore compound query constraints
- `getActiveSnapshotLite` – lightweight active workout state snapshot
- `getActiveEvents` – paginated workout event stream

See `training/ARCHITECTURE.md` for implementation details.

### Canvas (agent-driven UI surface)
- `applyAction` – single write gateway (phase guards, versioning, idempotency, events)
- `proposeCards` – service-only; writes proposed cards (typed schemas validated via Ajv)
- `expireProposals` – TTL cleanup; scheduled sweep also available

See `canvas/ARCHITECTURE.md` for data model, schemas, and examples.

### Canvas – Current capability (MVP)
- Single-writer via `applyAction` transaction; optimistic concurrency on `state.version`; per-canvas idempotency.
- Security rules: clients have read-only access under `users/{uid}/canvases/**`; all writes go through Functions.
- `bootstrapCanvas` (flex auth): find-or-create `(userId,purpose)` with initialized `state/meta`.
- Events: `apply_action` (now includes `changed_cards` and `correlation_id`), `instruction_added`, `session_started`.
- Actions: `ADD_INSTRUCTION`, `ACCEPT_PROPOSAL|REJECT_PROPOSAL`, `ACCEPT_ALL|REJECT_ALL`, `ADD_NOTE`, `LOG_SET`, `SWAP`, `ADJUST_LOAD`, `REORDER_SETS`, `PAUSE|RESUME|COMPLETE`, `UNDO` (scoped).
- Replacement policies: analysis lane via `refs.topic_key`; single active `set_target` per `(exercise_id,set_index)`.
- Ajv validation: `session_plan`, `set_target`, `coach_proposal`, `visualization`, `agent_stream`, `clarify-questions`, `list`, `inline-info`, `proposal-group`, `routine-overview`.
- Card shared fields: `layout`, `actions`, `menuItems`, `meta`; optional `priority` (clamped) supported; `up_next` capped at N=20 with priority-based trimming.
- Server defaults/normalization (new): `proposeCards` injects defaults for `layout|actions|menuItems|meta` and normalizes `meta.groupId`. `priority` is clamped. `up_next` trimming happens after writes.
- EDIT_SET (new): schema-level validator present; reducer returns `UNIMPLEMENTED` for now (stub for MVP).

### Canvas – Gaps & risks (to monitor)
- Schema parity: iOS UI JSON schemas (draft-07) vs backend Ajv (2020) may diverge; keep contract tests aligned and add samples as new card variants are introduced.
- Emulator E2E: HTTP flow in emulator is flaky to start locally; unit/contract tests pass. Recommend a staging smoke test (bootstrap → propose → accept → complete) before release.
- Auth hardening: API key path defaults to `myon-agent-key-2024` in dev; production must use env `VALID_API_KEYS` and rotate regularly.
- Operational caps: `up_next` cap and trimming are enforced; revisit limits under higher load and add metrics/alerts if contention grows.
- Observability: correlation ids are emitted on `apply_action`; extend to other writes as needed for traceability.

### StrengthOS (Vertex AI Agent Engine glue)
- `createStrengthOSSession`, `listStrengthOSSessions`, `deleteStrengthOSSession`
- `queryStrengthOS`, `queryStrengthOSv2`
- `streamAgentNormalized` – SSE stream proxy

### Maintenance
- `backupExercises` – snapshot `exercises` → `exercises_backup`

---
## Agent Curation Protocol (suggested)

1) Resolve intent
   - Call `resolveExercise(q)`; if not found, `ensureExerciseExists({ name })`
2) Classify
   - `suggestFamilyVariant(name, metadata?)` → then `refineExercise(exercise_id, { family_slug, variant_key })`
3) Aliases
   - `suggestAliases({...})` → upsert with `upsertAlias`, remove bad with `deleteAlias`
4) Enrichment
   - `refineExercise` for movement, equipment, muscles, notes; finally `approveExercise`
5) De-dup
   - If duplicates in same variant: `mergeExercises(source_id, target_id)`
6) Audit (batch)
   - `normalizeCatalogPage` and `listFamilies` regularly to keep catalog tidy

---
## Auth Notes
- Most write endpoints accept API key only and will set `created_by: "service"` when no user is present.
- Read endpoints work with API key only.

---
## Firestore Write Conventions (critical)

- Upsert everywhere creation-on-missing is acceptable.
  - Use `set(..., { merge: true })` via helpers to avoid update-on-missing errors.
  - Helpers:
    - `upsertDocument(collection, id, data)`
    - `upsertDocumentInSubcollection(parent, parentId, sub, id, data)`
  - Timestamps: helpers set `updated_at` always; set `created_at` only when creating (never write `undefined`).

- Update only where document existence is guaranteed.
  - Functions that first read or create the doc (e.g., workout lifecycle) may use `updateDocument`.

- Alias registry (`exercise_aliases/{alias_slug}`):
  - Reservation uses transaction or merge set to prevent conflicts and never writes `undefined`.
  - Conflict error format: `ALIAS_CONFLICT:<slug>:<owner_id>` → returns HTTP 409.

- Idempotency (active workout tools):
  - Write tools accept optional `idempotency_key` and record `users:{uid}/idempotency` entries to prevent duplicates in a short window.

- Error model:
  - Success: `{ success: true, data: {...} }`
  - Error: `{ success: false, error: { code, message, details? } }`

References: Firestore upsert behavior is achieved with `set(..., { merge: true })`. See Firestore docs: https://firebase.google.com/docs/firestore/manage-data/add-data

---
## Examples (cURL)

Upsert exercise:
```
curl -sS -H "X-API-Key: <KEY>" -H "Content-Type: application/json" \
  -X POST "<BASE>/upsertExercise" \
  -d '{
    "exercise": {
      "name": "Dumbbell Bench Press",
      "equipment": ["dumbbell","bench"],
      "movement": {"type": "push", "split": "upper"}
    }
  }'
```

Upsert by id (update existing):
```
curl -sS -H "X-API-Key: <KEY>" -H "Content-Type: application/json" \
  -X POST "<BASE>/upsertExercise" \
  -d '{
    "exercise": {
      "id": "<EXISTING_ID>",
      "name": "Dumbbell Bench Press",
      "description": "Updated description"
    }
  }'
```

Link alias and resolve:
```
curl -sS -H "X-API-Key: <KEY>" -H "Content-Type: application/json" \
  -X POST "<BASE>/upsertAlias" -d '{"alias_slug":"db-bench","exercise_id":"<ID>"}'
curl -sS -H "X-API-Key: <KEY>" "<BASE>/getExercise?slug=db-bench"
```

Normalize a page:
```
curl -sS -H "X-API-Key: <KEY>" -H "Content-Type: application/json" \
  -X POST "<BASE>/normalizeCatalogPage" -d '{"pageSize":50}'
```

---
## Testing & Deployment

### Prerequisites

Authenticate with the Firebase Admin SDK service account before running emulators or tests locally:
```bash
export GOOGLE_APPLICATION_CREDENTIALS=$FIREBASE_SA_KEY
```
See [CLAUDE.md — Service Account Keys](../../CLAUDE.md#service-account-keys) for key file setup.

### Emulator
Run Functions + Firestore emulators and the test suite:
```
VALID_API_KEYS=myon-agent-key-2024 FIRESTORE_EMULATOR_HOST=127.0.0.1:8085 \
  firebase emulators:exec --project demo-myon --only functions,firestore \
  'npm --prefix functions test | cat'
```

### Deployment
```
firebase deploy --only functions
```

---
## Tool Contracts (AI-focused)

All tools return `{ success, data|error }`. Omitted fields are optional unless stated.

### getExercise
- Purpose: Resolve an exercise by `id`, `name`, `slug`, or any `alias_slug`.
- Request (any one of these):
```json
{ "exerciseId": "<id>" }
{ "slug": "barbell-back-squat" }
{ "name": "Barbell Back Squat" }
```
- Response (success):
```json
{
  "success": true,
  "data": {
    "id": "<id>",
    "name": "Barbell Back Squat",
    "name_slug": "barbell-back-squat",
    "family_slug": "squat",
    "variant_key": "variant:back",
    "movement": {"type": "squat", "split": "lower"},
    "equipment": ["barbell"],
    "merged_into": null
  }
}
```
- Notes: Fallback order: `exercises.name_slug` → `exercises.alias_slugs` → `exercise_aliases/{alias_slug}`.

### resolveExercise
- Purpose: Rank best exercise for a free-text query, considering context.
- Request:
```json
{ "q": "bench press", "context": { "available_equipment": ["dumbbell","bench"] } }
```
- Response:
```json
{ "success": true, "data": { "best": {"id": "<id>", "name": "Flat Dumbbell Press"}, "alternatives": [] } }
```

### ensureExerciseExists
- Purpose: Find or create a minimal draft if not found.
- Request:
```json
{ "name": "Romanian Deadlift" }
```
- Response: `{ success: true, data: { exercise_id, created?: true } }`

### upsertExercise
- Purpose: Create/update an exercise; sets `name_slug`, `family_slug`, `variant_key`, reserves aliases. Uses Firestore upsert semantics so it works whether the doc exists or not.
- Request (minimal):
```json
{
  "exercise": {
    "name": "Dumbbell Bench Press",
    "equipment": ["dumbbell","bench"],
    "movement": {"type": "push", "split": "upper"},
    "metadata": {"level": "intermediate"}
  }
}
```
- Request (update by id - preferred when available):
```json
{
  "exercise": {
    "id": "<existing_id>",
    "name": "Dumbbell Bench Press",
    "description": "Updated description",
    "execution_notes": ["Control tempo", "Pause at bottom"],
    "common_mistakes": ["Flaring elbows"],
    "programming_use_cases": ["Hypertrophy push day"],
    "suitability_notes": ["Intermediate lifters"],
    "stimulus_tags": ["hypertrophy"]
  }
}
```
- Response: `{ success: true, data: { exercise_id, status, name_slug, family_slug, variant_key } }`

Notes:
- If `exercise.id` is provided, the function performs a deterministic upsert on that document id.
- If `exercise.id` is omitted, the function tries to find an existing exercise by `name_slug` or alias; if found, merges into it; otherwise, creates a new doc.
- Upsert is implemented via Firestore `set(..., { merge: true })` to avoid update-on-missing errors. See Firestore docs: https://firebase.google.com/docs/firestore/manage-data/add-data

### refineExercise
- Purpose: Metadata enrichment (movement, equipment, muscles, notes).
- Request:
```json
{
  "exercise_id": "<id>",
  "updates": {
    "muscles": {"primary": ["pectoralis major"], "secondary": ["anterior deltoid", "triceps brachii"]},
    "execution_notes": ["Set bench to 30°", "Control tempo"]
  }
}
```

### approveExercise
- Purpose: Mark as approved. `{ exercise_id } → { status: "approved" }`.

### upsertAlias / deleteAlias
- Purpose: Manage `exercise_aliases/{alias_slug}`.
- Upsert:
```json
{ "alias_slug": "db-bench", "exercise_id": "<id>" }
```
- Delete:
```json
{ "alias_slug": "db-bench" }
```

### mergeExercises
- Purpose: Merge duplicates safely within same `family_slug::variant_key`.
- Request:
```json
{ "source_id": "<dup_id>", "target_id": "<canonical_id>" }
```
- Response: `{ merged: true }` and sets `source.status = "merged"`, `source.merged_into = target_id`.

### listFamilies
- Purpose: Inspect families and members with variants.
- Request: `?minSize=2&limit=50`
- Response: `{ families: [{ family, count, members: [...] }], totalFamilies }`

### normalizeCatalogPage (preferred)
- Purpose: Normalize a page of exercises: set slugs/family/variant, seed alias registry, canonicalize names.
- Request:
```json
{ "pageSize": 50, "startAfterName": "Optional Name" }
```
- Response: `{ processed, nextStartAfterName, conflicts: ["ALIAS_CONFLICT:..." ] }`

### searchAliases
- Purpose: Prefix search in alias registry.
- Request: `?q=<prefix>` → `{ items: [{ alias_slug, exercise_id }], count }`

---
## Naming & Slugging Rules (agent hints)
- Canonical names should be verbose (e.g., "Barbell Back Squat").
- `name_slug` is kebab-case of canonical name.
- Families are movement-based (e.g., `squat`, `deadlift`, `bench_press`, `overhead_press`, `barbell_row`, `seated_row`, `t_bar_row`, `lat_pulldown`, `pull_up`, `lunge_split_squat`).
- Variants are encoded in `variant_key` (e.g., `variant:back`, `variant:romanian`, `variant:sumo`).
- Shorthands (e.g., `db-bench`, `ohp`, `rdl`) are alias-slugs only; never primary names.
- Merges are allowed only when `family_slug` and `variant_key` match.

---
## Agent Playbooks (concise)
- Create-or-update flow: `resolveExercise` → `ensureExerciseExists` → `suggestFamilyVariant` → `refineExercise` → `suggestAliases` → `upsertAlias*` → `approveExercise`.
- De-dup flow: `listFamilies` → pick group → `mergeExercises` (within same family+variant).
- Cleanup flow: `normalizeCatalogPage` pages until `nextStartAfterName=null`.

