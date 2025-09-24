## Firestore Data Model (Current State)

This document describes the current Firestore structure, collections, subcollections, document shapes, security posture, and indexes as implemented across the Firebase Functions and the iOS app. It reflects the live schema implied by code, not an idealized design. Field names and nesting match production usage observed in the repository.

### Conventions
- Timestamps: `created_at`, `updated_at` are generally set by backend using serverTimestamp().
- IDs: Many documents embed their document ID in-field as `id` after creation; some rely only on the Firestore document ID.
- User-scoped data lives under `users/{uid}/...`.
- Admin/service writes are performed via HTTPS Functions; direct client writes are limited per rules.

---

## Root Collections

### users/{uid}
Top-level user profile and owner of most subcollections.

- Example fields
  - `uid: string` (mirrors auth uid)
  - `email: string`
  - `name?: string`
  - `provider: string`
  - `created_at: Timestamp`
  - `week_starts_on_monday: boolean` (default true)
  - `timezone?: string`
  - `activeRoutineId?: string` (points to a routine doc under `users/{uid}/routines`)
  - (Historic mirrors) `weightFormat?`, `heightFormat?`, `locale?` (canonical values live in `user_attributes`)

Subcollections:
1) user_attributes/{uid}
   - Canonical store for user preferences and fitness profile.
   - Fields (observed):
     - `timezone?: string`
     - `weight_format?: 'kilograms' | 'pounds'`
     - `height_format?: 'centimeter' | 'feet'`
     - `week_starts_on_monday?: boolean`
     - `locale?: string`
     - `fitness_goal?: string`
     - `fitness_level?: string`
     - `equipment_preference?: string`
     - `height?: number`
     - `weight?: number`
     - `workouts_per_week_goal?: number`
     - `created_at?, updated_at?: Timestamp`

2) linked_devices/{deviceId}
   - Device linkage state.
   - Fields:
     - `device_type: string`
     - `device_name: string`
     - `last_sync: Timestamp`
     - `is_active: boolean`
     - `permissions: { [perm: string]: boolean }`
     - `created_at?, updated_at?: Timestamp`

3) workouts/{workoutId}
   - Archived/completed workouts. Used by analytics and weekly stats triggers.
   - Query patterns: order by `end_time`, filter by `end_time` range, collectionGroup from triggers.
   - Fields:
     - `user_id: string`
     - `source_template_id?: string`
     - `created_at: Timestamp`
     - `start_time: Timestamp`
     - `end_time: Timestamp` (presence indicates completion)
     - `notes?: string`
     - `exercises: Array<{
           exercise_id: string,
           name?: string,
           position?: number,
           sets: Array<{
             id?: string,
             reps: number,
             rir: number,
             type?: string,
             weight_kg: number,
             is_completed?: boolean
           }>,
           analytics?: ExerciseAnalytics
         }>`
     - `analytics?: WorkoutAnalytics` (computed by trigger if absent)

   - ExerciseAnalytics (per exercise):
     - `total_sets, total_reps, total_weight: number`
     - `weight_format: 'kg' | 'lbs'`
     - `avg_reps_per_set, avg_weight_per_set, avg_weight_per_rep: number`
     - `weight_per_muscle_group: { [group]: number }`
     - `weight_per_muscle: { [muscle]: number }`
     - `reps_per_muscle_group: { [group]: number }`
     - `reps_per_muscle: { [muscle]: number }`
     - `sets_per_muscle_group: { [group]: number }`
     - `sets_per_muscle: { [muscle]: number }`

   - WorkoutAnalytics (workout-level): same shape as ExerciseAnalytics aggregates.

4) weekly_stats/{weekId}
   - Aggregate stats keyed by the week start date (ISO date as string), start day depends on user preference.
   - Written by triggers on workout completion/deletion and periodic recalculation job.
   - Fields:
     - `workouts: number`
     - `total_sets, total_reps, total_weight: number`
     - `weight_per_muscle_group, weight_per_muscle: { [key]: number }`
     - `reps_per_muscle_group, reps_per_muscle: { [key]: number }`
     - `sets_per_muscle_group, sets_per_muscle: { [key]: number }`
     - `updated_at: Timestamp`
     - `recalculated_at?: Timestamp`

5) templates/{templateId}
   - User-authored or AI-authored workout templates.
   - Fields:
     - `id: string` (backfilled after create)
     - `user_id: string`
     - `name: string`
     - `description?: string`
     - `exercises: Array<{
           id?: string, // per-template unique
           exercise_id: string, // reference to master `exercises/{id}`
           position: number,
           sets: Array<{ id?: string, reps: number, rir: number, type?: string, weight: number, duration?: number }>,
           rest_between_sets?: number
         }>`
     - `analytics?: TemplateAnalytics` (computed server-side for AI-created/updated templates)
     - `created_at, updated_at: Timestamp`

   - TemplateAnalytics:
     - `template_id: string`
     - `total_sets, total_reps, projected_volume: number`
     - `weight_format: 'kg' | 'lbs'`
     - `estimated_duration?: number`
     - `projected_volume_per_muscle_group, projected_volume_per_muscle: { [key]: number }`
     - `sets_per_muscle_group, sets_per_muscle: { [key]: number }`
     - `reps_per_muscle_group, reps_per_muscle: { [key]: number }`
     - `relative_stimulus_per_muscle_group, relative_stimulus_per_muscle: { [key]: number }`

6) routines/{routineId}
   - Weekly/monthly routine structure referencing templates.
   - Fields:
     - `id: string`
     - `user_id: string`
     - `name: string`
     - `description?: string`
     - `template_ids: string[]` (template IDs under this user)
     - `frequency: number` (workouts per week)
     - `created_at, updated_at: Timestamp`

7) progress_reports/{reportId}
   - StrengthOS progress reports written by service endpoints (API key auth).
   - Fields:
     - `period: { start: Timestamp, end: Timestamp }`
     - `metrics: { [key]: any }`
     - `proposals: { [key]: any }`
     - `created_at, updated_at: Timestamp`

8) active_workouts/{activeWorkoutId}
   - Current in-progress workout state. Ephemeral; upon completion, a record is archived under `workouts` and this is marked completed.
   - Fields:
     - `user_id: string`
     - `status: 'in_progress' | 'completed'`
     - `source_template_id?: string`
     - `plan?: any` (structured blocks used to initialize)
     - `current?: any`
     - `exercises: any[]` (app-managed during session)
     - `totals: { sets: number, reps: number, volume: number, stimulus_score: number }`
     - `start_time: Timestamp`
     - `end_time?: Timestamp`
     - `notes?: string`
     - `analytics?: WorkoutAnalytics`
     - `created_at, updated_at: Timestamp`

   - Subcollection: events/{eventId}
     - Logged events during an active workout.
     - Fields:
       - `type: string` (e.g., `set_performed`)
       - `payload: { exercise_id: string, set_index: number, actual: { reps: number, rir: number, weight?: number } }`
       - `created_at: Timestamp`

9) canvases/{canvasId}
   - Deterministic collaboration surface for planning/active/analysis phases.
   - Root document fields:
     - `state: { phase: 'planning' | 'active' | 'analysis', version: number, purpose: string, lanes: string[], created_at: Timestamp, updated_at: Timestamp }`
     - `meta: { user_id: string }`

   - Subcollections:
     - cards/{cardId}
       - Fields:
         - `type: string` (e.g., `session_plan`, `set_target`, `set_result`, `note`, `visualization`, `instruction`, `coach_proposal`, etc.)
         - `status: 'proposed' | 'active' | 'accepted' | 'rejected' | 'expired' | 'completed'`
         - `lane: 'workout' | 'analysis' | 'system'`
         - `content: { ... }` (type-specific payload)
         - `refs?: { exercise_id?: string, set_index?: number, topic_key?: string }`
         - `layout?: any`, `actions?: any[]`, `menuItems?: any[]`, `meta?: any`, `ttl?: number`
         - `by: 'user' | 'agent'`
         - `created_at, updated_at: Timestamp`

     - up_next/{entryId}
       - Queue of next actions/cards; trimmed to max 20.
       - Fields: `card_id: string`, `priority: number`, `inserted_at: Timestamp`

     - events/{eventId}
       - Reducer events for deterministic replay/undo.
       - Fields:
         - `type: 'apply_action' | 'instruction_added' | 'group_action' | 'session_started' | ...`
         - `payload: { action?: string, card_id?: string, changed_cards?: string[], note_id?: string }`
         - `correlation_id?: string`
         - `created_at: Timestamp`

    - idempotency/{key}
      - Scoped idempotency guard.
      - Fields: `key: string`, `created_at: Timestamp`

10) analytics_series_exercise/{exercise_id}
   - Per-exercise time series of daily points and compacted weekly aggregates (sublinear growth).
   - Fields:
     - `points_by_day: { [YYYY-MM-DD]: { e1rm?: number, vol?: number } }`
     - `weeks_by_start?: { [YYYY-MM-DD]: { e1rm_max: number, vol_sum: number } }`
     - `schema_version: number`
     - `updated_at: Timestamp`, `compacted_at?: Timestamp`

11) analytics_series_muscle/{muscle}
   - Per-muscle weekly aggregates.
   - Fields:
     - `weeks: { [YYYY-MM-DD]: { sets: number, volume: number } }`
     - `updated_at: Timestamp`

12) analytics_rollups/{periodId}
   - Weekly/monthly compact rollups keyed by `yyyy-ww` or `yyyy-mm`.
   - Fields:
     - `total_sets, total_reps, total_weight: number`
     - `weight_per_muscle_group: { [group]: number }`
     - `updated_at: Timestamp`

13) analytics_state/current
   - Watermarks and cursors for idempotent incremental processing.
   - Fields:
     - `last_processed_workout_at?: string (ISO)`
     - `last_compaction_at?: string (ISO)`
     - `job_cursors?: { [key]: any }`
     - `updated_at: Timestamp`

---

## Global Collections

### exercises/{exerciseId}
Master exercise catalog (shared across all users).

- Fields:
  - `id?: string` (sometimes mirrored)
  - `name: string`
  - `name_slug: string`
  - `aliases?: string[]`
  - `alias_slugs?: string[]`
  - `family_slug: string` (e.g., `deadlift`, `squat`, ...)
  - `variant_key: string` (e.g., `variant:romanian`)
  - `category: string`
  - `description?: string`
  - `metadata: { level: string, plane_of_motion?: string, unilateral?: boolean }`
  - `movement: { type: string, split?: string }`
  - `equipment: string[]`
  - `muscles: { primary: string[], secondary: string[], category?: string[], contribution?: { [muscle]: number } }`
  - `execution_notes?: string[]`
  - `common_mistakes?: string[]`
  - `programming_use_cases?: string[]`
  - `stimulus_tags?: string[]`
  - `suitability_notes?: string[]`
  - `coaching_cues?: string[]`
  - `status?: 'draft' | 'approved' | ...`
  - `version?: number`
  - `_debug_project_id?: string`
  - `created_by: string`
  - `created_at, updated_at: Timestamp`

Indexes and lookups:
- Find by `name_slug` or by `alias_slugs` (array-contains/array-contains-any).
- Alias registry fallback maps slugs to `exercise_id`.

### exercise_aliases/{alias_slug}
Registry mapping name/alias slugs to canonical `exercises/{exerciseId}`.

- Fields:
  - `alias_slug: string` (document ID)
  - `exercise_id: string`
  - `family_slug?: string`
  - `created_at, updated_at: Timestamp`

### idempotency/{userId:tool:key}
Global idempotency keys for non-canvas operations.

- Fields: `user_id: string`, `tool: string`, `key: string`, `created_at: Timestamp`

### exercises_backup/{exerciseId}
Point-in-time snapshots of `exercises` created by maintenance tooling.

- Fields: All fields from the source exercise plus
  - `_backup_meta: { source: 'exercises', backed_up_at: Timestamp, tag: string }`

---

## Canvas Indexes

firestore.indexes.json contains a collection group index for `cards`:
- Fields: `lane` ASC, `refs.topic_key` ASC
- Scope: `COLLECTION_GROUP` on `cards` (under all canvases)

This supports queries that group or replace analysis-lane proposals by topic key.

Additionally, a collection group index exists for `up_next` to support deterministic ordering and trimming:
- Fields: `priority` DESC, `inserted_at` ASC
- Scope: `COLLECTION_GROUP` on `up_next`

Notes:
- Reducer and proposer code may order by `priority` only in some paths; the two-field index is present for stable ordering where both are used (see `apply-action.js`, `propose-cards-core.js`).

---

## Analytics Indexes

- `workouts` collection group: index on `end_time` (ascending) for time-range queries and active user discovery.
- `analytics_rollups` collection group: index on `updated_at` (descending) for recent rollups.
- Series collections are typically point-lookups by document id; no composite indexes required initially.

---

## Security Rules (firestore.rules)

- `users/{uid}/canvases/**`: read allowed to the authenticated owner; writes are disallowed directly (single-writer via Functions only). All canvas mutations flow through HTTPS endpoints (e.g., `applyAction`, `proposeCards`, `bootstrapCanvas`).
- Other user subcollections under `users/{uid}`: read/write allowed to the authenticated owner (excluding `canvases`). This includes `workouts`, `weekly_stats`, `templates`, `routines`, `user_attributes`, `linked_devices`, `progress_reports`, `active_workouts`, and analytics collections under `analytics_*` prefixes.
- Admin/agents: Function-layer auth (API keys, service accounts) mediates privileged writes.
- Analytics: lives under `users/{uid}/analytics_*` and inherits owner read/write. Backend Functions (triggers/HTTPS) write these docs on behalf of the user.

Implications:
- Client apps should not attempt to write to `users/{uid}/canvases/**` directly.
- Direct client reads of canvases are supported (for UI live updates), but writes must go through Functions.

---

## Query Patterns (Representative)

- Workouts (per user): `users/{uid}/workouts` ordered by `end_time` desc, with optional date range filters.
- Weekly stats: direct doc get/set `users/{uid}/weekly_stats/{weekId}`.
- Template and Routine CRUD: subcollection reads/writes under the user, with analytics calculations performed by triggers or function logic.
- Active workout session: `users/{uid}/active_workouts` latest by `updated_at`; log set events via `active_workouts/{id}/events`.
- Canvas:
  - Reducer transaction updates `users/{uid}/canvases/{canvasId}` and subcollections (`cards`, `up_next`, `events`, `idempotency`).
  - Agents propose cards in batch and manage `up_next`, enforcing max 20 entries.
 - Analytics:
   - Series (exercise): read `users/{uid}/analytics_series_exercise/{exercise_id}`; use `points_by_day[YYYY-MM-DD]` for recent, or `weeks_by_start` for older windows.
   - Series (muscle): read `users/{uid}/analytics_series_muscle/{muscle}` and pull `weeks[yyyy-ww]`.
   - Rollups: read `users/{uid}/analytics_rollups/{yyyy-ww}` (and `yyyy-mm` when present) ordered by `updated_at` when listing.

---

## Field Naming Notes and Migrations

- The system is converging on snake_case field names in Firestore (`start_time`, `end_time`, `weight_kg`, etc.).
- Some iOS models include camelCase but map via `CodingKeys` to snake_case. When adding fields, prefer snake_case in Firestore.
- Preferences canonical store is `users/{uid}/user_attributes/{uid}`; minimal mirrors on `users/{uid}` may exist for legacy compatibility.

---

## Gaps and TODOs (Observed)

- Active workout analytics and totals may be partial until archived; triggers compute workout analytics post-write if missing.
- Canvas card `content` is type-specific; JSON Schemas live under `firebase_functions/functions/canvas/schemas`. Clients should validate against these when relevant.
- Exercise alias resolution uses both `alias_slugs` on exercises and `exercise_aliases` registry; conflicts are handled with best-effort reservation and may log conflicts.

---

## Summary Diagram (Textual)

```
users/{uid}
  ├─ user_attributes/{uid}
  ├─ linked_devices/{deviceId}
  ├─ workouts/{workoutId}
  ├─ weekly_stats/{weekId}
  ├─ templates/{templateId}
  ├─ routines/{routineId}
  ├─ progress_reports/{reportId}
  ├─ active_workouts/{activeWorkoutId}
  │    └─ events/{eventId}
  └─ canvases/{canvasId}
       ├─ cards/{cardId}
       ├─ up_next/{entryId}
       ├─ events/{eventId}
       └─ idempotency/{key}

exercises/{exerciseId}
exercise_aliases/{alias_slug}
idempotency/{userId:tool:key}
```

---

## Appendix: Types (Condensed)

- WorkoutAnalytics/ExerciseAnalytics keys: `total_sets, total_reps, total_weight, weight_format, avg_reps_per_set, avg_weight_per_set, avg_weight_per_rep, weight_per_muscle_group, weight_per_muscle, reps_per_muscle_group, reps_per_muscle, sets_per_muscle_group, sets_per_muscle`.
- TemplateAnalytics adds `projected_volume`, `estimated_duration`, and relative stimulus maps.
- Canvas state: `{ phase, version, purpose, lanes }`; Cards: `{ type, status, lane, content, refs, by, created_at, updated_at }`.

---

## Automatic Data Mutations and Background Processes

This section focuses on what data gets added or mutated automatically over time by Cloud Functions (triggers, scheduled jobs, HTTPS reducers) and by the production Catalog Admin agent pipeline.

### Workouts → Weekly Analytics (triggers and jobs)
- On workout completion
  - Trigger: `triggers/weekly-analytics.js:onWorkoutCompleted` on `users/{userId}/workouts/{workoutId}` when `end_time` is added.
  - Reads `workout.analytics` and updates `users/{uid}/weekly_stats/{weekId}` for the week starting on the user’s preference.
  - Week start preference is read from `users/{uid}.week_starts_on_monday` (defaults to Monday when missing).
- On workout deletion
  - Trigger: `onWorkoutDeleted` subtracts the workout’s analytics from the corresponding `weekly_stats/{weekId}`.
- Scheduled backfill/recalculation
  - Job: `weeklyStatsRecalculation` runs daily (2 AM UTC).
  - Discovers active users via `collectionGroup('workouts')` where `end_time` is within last 14 days, then recalculates aggregates for the user’s current and previous week.
  - Writes `updated_at` and `recalculated_at` on `weekly_stats/{weekId}`.
- Manual recalculation
  - Callable: `manualWeeklyStatsRecalculation` recalculates stats for current and previous week for the authenticated user.

Data impacted over time
- `users/{uid}/weekly_stats/{weekId}` continually accrues or decrements `workouts`, set/rep/weight totals, and per-muscle/per-group maps in response to workout lifecycle.

Sources
- `firebase_functions/functions/triggers/weekly-analytics.js` (onWorkoutCompleted, onWorkoutDeleted, weeklyStatsRecalculation, manualWeeklyStatsRecalculation)
- `firebase_functions/functions/index.js` (exports and scheduler wiring)

### Template and Workout Analytics (triggers)
- Template analytics
  - Trigger: `triggers/muscle-volume-calculations.js:onTemplateCreated` computes and writes `template.analytics` when a template under `users/{uid}/templates/{templateId}` is created without analytics and contains exercises.
  - Trigger: `onTemplateUpdated` recomputes `analytics` when exercises change and analytics are absent.
  - Fetches referenced `exercises/{exerciseId}` to drive computations.
- Workout analytics
  - Trigger: `onWorkoutCreated` computes `workout.analytics` and also writes per-exercise `exercises[].analytics` when a workout is created without analytics but contains exercises.
- Working set semantics
  - Only “working” set types are included in volume/rep/set computations (e.g., working set, drop set, failure set, etc.).

### Analytics series and rollups (triggers + controller + compaction + publisher)
- On workout completion (and on eligible creation)
  - Triggers: `triggers/weekly-analytics.js:onWorkoutCompleted` and `onWorkoutCreatedWithEnd` update:
    - `users/{uid}/weekly_stats/{weekId}` (backwards compatibility)
    - `users/{uid}/analytics_rollups/{weekId}` (compact rollup)
    - `users/{uid}/analytics_series_muscle/{muscle}.weeks[weekId]` per affected groups
    - `users/{uid}/analytics_series_exercise/{exercise_id}.points_by_day[YYYY-MM-DD]` with `{ e1rm, vol }` estimated using Epley
- Controller/Worker (HTTPS)
  - `analytics/controller.js:runAnalyticsForUser` processes workouts since watermark (or last 90 days) to backfill series/rollups and updates `analytics_state/current`.
- Compaction (scheduled + HTTPS)
  - `analytics/compaction.js:analyticsCompactionScheduled` compacts `points_by_day` older than 90 days into `weeks_by_start` and deletes old day keys.
  - `analytics/compaction.js:compactAnalyticsForUser` allows on-demand compaction per user.
- Weekly publisher (HTTPS)
  - `analytics/publish-weekly-job.js:publishWeeklyJob` proposes a weekly `proposal-group` (summary + visualization) to the user’s canvas via `proposeCards`.

Response contracts (for LLMs/agents):
- `analytics/get-features.js` responds with `{ userId, mode, period_weeks?, weekIds?, range?, daily_window_days?, rollups, series_muscle, series_exercise, schema_version }`.

### Analytics features (LLM/agent read path)
- Read-only endpoint for compact, typed features that LLMs or fast services can consume to decide what to publish:
  - HTTPS: `analytics/get-features.js:getAnalyticsFeatures`
  - Auth: API key or Bearer token
  - Request:
    - `userId: string`
    - `mode: 'weekly' | 'week' | 'range' | 'daily'` (default `'weekly'`)
    - Weekly: `weeks?: number (1–52)`
    - Week: `weekId?: 'yyyy-mm-dd'` (user-aligned week start)
    - Range: `start?: 'yyyy-mm-dd'`, `end?: 'yyyy-mm-dd'` (week-aligned, inclusive)
    - Daily: `days?: number (1–120)` window for per-exercise daily points
    - Filters: `muscles?: string[] (≤50)`, `exerciseIds?: string[] (≤50)`
  - Response (schema_version=2):
    - `mode, period_weeks?, weekIds?, range?, daily_window_days?`
    - `rollups: [{ id: weekId, total_sets, total_reps, total_weight, weight_per_muscle_group, updated_at }]`
    - `series_muscle: { [muscle]: [{ week, sets, volume }] }`
    - `series_exercise: { [exerciseId]: { days: string[], e1rm: number[], vol: number[], e1rm_slope: number, vol_slope: number } }`

Data impacted over time
- New analytics subcollections under `users/{uid}` accumulate series points, weekly muscle aggregates, and compact rollups; day-level points older than 90 days are merged into weekly aggregates.
- `analytics_state/current` watermarks advance with processing and compaction operations.

Sources
- `firebase_functions/functions/triggers/weekly-analytics.js` (enhanced triggers, e1RM estimate)
- `firebase_functions/functions/active_workout/complete-active-workout.js` (ensures analytics on archive)
- `firebase_functions/functions/utils/analytics-writes.js` (shared writers)
- `firebase_functions/functions/analytics/worker.js`, `.../controller.js` (per-user processing)
- `firebase_functions/functions/analytics/compaction.js` (scheduled/HTTPS compaction)
- `firebase_functions/functions/analytics/publish-weekly-job.js` (weekly canvas group proposer)
- `firebase_functions/functions/analytics/get-features.js` (LLM-facing features API)

Data impacted over time
- `users/{uid}/templates/{templateId}.analytics` is populated/updated server-side as content changes.
- `users/{uid}/workouts/{workoutId}.analytics` and `exercises[].analytics` are filled on first creation if missing.

Sources
- `firebase_functions/functions/triggers/muscle-volume-calculations.js` (onTemplateCreated, onTemplateUpdated, onWorkoutCreated)
- `firebase_functions/functions/utils/analytics-calculator.js` (shared analytics calculator)
- `firebase_functions/functions/templates/create-template.js` and `firebase_functions/functions/templates/update-template.js` (agent-origin analytics path)

### Canvas (transactional reducer + TTL sweeps)
- Deterministic reducer
  - HTTPS: `canvas/apply-action.js` is the sole write gateway for `users/{uid}/canvases/{canvasId}` and subcollections.
  - Transactionally mutates:
    - `state.version` (optimistic concurrency) and `state.phase` transitions.
    - `cards/{cardId}.status` (e.g., proposed → accepted/rejected/expired/completed).
    - Ensures single active `set_target` per `(refs.exercise_id, refs.set_index)` and converts accepted targets into `set_result` on `LOG_SET`.
    - Appends reducer `events/{eventId}` (e.g., `apply_action`, `instruction_added`, `session_started`).
    - Maintains `up_next` priority queue; trims to max 20 entries after each reducer run.
  - Events:
    - `apply_action` payload includes `{ action, card_id?, changed_cards?[] }` and a `correlation_id` of the form `${canvasId}:${version}` for client telemetry.
    - Group actions append `group_action` events with `{ action: 'ACCEPT_ALL|REJECT_ALL', group_id }`.
  - Science/Safety checks enforced when accepting plans or logging sets:
    - `session_plan` targets must satisfy `reps ∈ [1,30]` and `rir ∈ [0,5]`.
    - `LOG_SET.actual` must satisfy `reps ≥ 0` and `rir ∈ [0,5]`.
  - Idempotency:
    - Per-canvas keys under `users/{uid}/canvases/{canvasId}/idempotency/{key}` prevent duplicate actions within a transaction.
- TTL expiration of proposed cards
  - Scheduled: `canvas/expire-proposals-scheduled.js` runs every 15 minutes. It performs a `collectionGroup('cards')` sweep for `status='proposed'` whose `created_at + ttl.minutes` has elapsed, updates those cards to `status='expired'`, and deletes corresponding `up_next` entries.
  - HTTPS: `canvas/expire-proposals.js` can sweep one or all canvases for a user on-demand.
- Bootstrap
  - HTTPS: `canvas/bootstrap-canvas.js` find-or-creates a canvas for `(userId, purpose)` and initializes `state` and `meta`.

Constraints and caps:
- `up_next` is capped to 20 entries. Trimming is best-effort outside the Firestore transaction to avoid reads-after-writes inside the transaction boundary.

Data impacted over time
- `users/{uid}/canvases/{canvasId}` root `state` evolves; `cards`, `up_next`, and `events` change continuously via the reducer. TTL jobs convert stale proposals to `expired` and clean queues.

Sources
- `firebase_functions/functions/canvas/apply-action.js` (transactional reducer)
- `firebase_functions/functions/canvas/expire-proposals-scheduled.js` (scheduled TTL sweeper)
- `firebase_functions/functions/canvas/expire-proposals.js` (on-demand sweep)
- `firebase_functions/functions/canvas/bootstrap-canvas.js` (find-or-create)
- `firebase_functions/functions/canvas/validators.js` and `firebase_functions/functions/canvas/schemas/` (typed validation)

### Active Workout Lifecycle (HTTPS tools and shared cores)
- Start/cancel/complete
  - `startActiveWorkout` writes `users/{uid}/active_workouts/{id}` with `status='in_progress'`, `totals`, and timestamps.
  - `cancelActiveWorkout` updates the active doc to `status='cancelled'` and sets `end_time`.
  - `completeActiveWorkout` archives the in-progress doc to `users/{uid}/workouts` (mapping `weight → weight_kg` in sets, synthesizing analytics if missing), then marks the active doc `status='completed'` and sets `end_time`.
- Set prescription and logging
  - `prescribeSet`, `logSet`, `addExercise`, `swapExercise`, `reorderSets` append `events/{eventId}` under the active workout and update `updated_at`.
  - Idempotency keys recorded in global `idempotency/{userId:tool:key}` for duplicate suppression in non-canvas tools.
- Scoring
  - `scoreSet` exists for post-hoc scoring; it has no direct Firestore schema impact beyond normal event/log patterns.
- Latest active fetch
  - `getActiveWorkout` returns the most recent active workout (ordered by `updated_at`).

Data impacted over time
- `users/{uid}/active_workouts` grows and shrinks during sessions; `events` accumulate per active workout. Completed sessions are permanently archived to `users/{uid}/workouts`.

Sources
- `firebase_functions/functions/active_workout/start-active-workout.js`
- `firebase_functions/functions/active_workout/cancel-active-workout.js`
- `firebase_functions/functions/active_workout/complete-active-workout.js`
- `firebase_functions/functions/active_workout/get-active-workout.js`
- `firebase_functions/functions/active_workout/prescribe-set.js`
- `firebase_functions/functions/active_workout/log-set.js`
- `firebase_functions/functions/active_workout/add-exercise.js`
- `firebase_functions/functions/active_workout/swap-exercise.js`
- `firebase_functions/functions/shared/active_workout/log_set_core.js`
- `firebase_functions/functions/shared/active_workout/adjust_load_core.js`
- `firebase_functions/functions/shared/active_workout/reorder_sets_core.js`
- `firebase_functions/functions/utils/idempotency.js` (global keys for non-canvas tools)

### Exercise Catalog (service writes + maintenance + agent pipeline)
- Core writes (service HTTPS endpoints)
  - `upsertExercise` creates/merges canonical exercise docs; sets `name_slug`, infers `family_slug` and `variant_key` when needed; reserves alias slugs transactionally in `exercise_aliases/{alias_slug}`; sets `status`, `version`, `created_by`.
  - `ensureExerciseExists` finds-or-creates minimal drafts; seeds alias registry.
  - `refineExercise` merges structured fields; `approveExercise` sets `status='approved'`.
  - `mergeExercises` transfers alias slugs to the target, sets `source.merged_into`, and updates `target.merge_lineage` (union of previous + source id).
- Normalization and maintenance
  - `normalizeCatalog` / `normalizeCatalogPage` backfill `name_slug`, `family_slug`, `variant_key`, canonicalize names, and populate alias registry; optional merge planning can be applied.
  - `backfillNormalizeFamily` merges duplicates within a `family_slug::variant_key` bucket.
  - `repointAlias` / `repointShorthandAliases` retarget `exercise_aliases` entries to canonical exercises; shorthand expansions include `ohp`, `rdl`, `sldl`, `db-*`, `bb-*`, `tbar-*`.
  - `backupExercises` snapshots `exercises` into `exercises_backup` with `_backup_meta`.
- Production Agent Pipeline (Catalog Admin)
  - The orchestrator and agents under `adk_agent/catalog_admin/multi_agent_system` continuously call the HTTPS endpoints above:
    - Triage/Enrichment/Janitor/Specialists improve metadata, add aliases, approve, and merge duplicates.
    - Effects over time: more complete `exercises` documents; growing `exercise_aliases`; evolving `status` (`draft`→`approved` / `merged`), `merge_lineage`, and alias unions.

Data impacted over time
- Global `exercises` density/quality increases; alias registry grows; duplicates are merged; backups are periodically created; merges leave `merged_into` pointers for redirects.

Sources
- `firebase_functions/functions/exercises/upsert-exercise.js`
- `firebase_functions/functions/exercises/ensure-exercise-exists.js`
- `firebase_functions/functions/exercises/refine-exercise.js`
- `firebase_functions/functions/exercises/approve-exercise.js`
- `firebase_functions/functions/exercises/merge-exercises.js`
- `firebase_functions/functions/exercises/normalize-catalog.js`
- `firebase_functions/functions/exercises/normalize-catalog-page.js`
- `firebase_functions/functions/exercises/backfill-normalize-family.js`
- `firebase_functions/functions/exercises/list-families.js`
- `firebase_functions/functions/aliases/upsert-alias.js` and `firebase_functions/functions/aliases/delete-alias.js`
- `firebase_functions/functions/maintenance/repoint-alias.js`
- `firebase_functions/functions/maintenance/repoint-shorthand-aliases.js`
- `firebase_functions/functions/maintenance/backup-exercises.js`
- `firebase_functions/functions/exercises/search-exercises.js`
- `firebase_functions/functions/exercises/search-aliases.js`
- `firebase_functions/functions/exercises/resolve-exercise.js`
- Agent pipeline (production):
  - `adk_agent/catalog_admin/multi_agent_system/orchestrator/orchestrator.py` (batch orchestration)
  - `adk_agent/catalog_admin/app/orchestrator.py` (Agent Engine app integration)
  - `adk_agent/catalog_admin/app/libs/tools_firebase/client.py` (HTTP client to Firebase Functions)
  - `adk_agent/catalog_admin/multi_agent_system/agents/` (triage, enrichment, janitor, specialists)

### Templates and Routines (service writes + cleanup)
- Template lifecycle
  - `createTemplate` writes `users/{uid}/templates/{templateId}` and then backfills `id` field; when the caller is an agent (`auth.source='third_party_agent'`) and no `analytics` exist, analytics are computed and stored.
  - `updateTemplate` merges updates; when an agent updates exercises, analytics are recalculated.
  - `deleteTemplate` removes the template and attempts to remove `templateId` references from routines that track it (cleanup currently targets camelCase `templateIds` for backward compatibility, while the canonical routine field is `template_ids`).
- Routines
  - `createRoutine`/`updateRoutine`/`deleteRoutine` manage `users/{uid}/routines/{routineId}` with canonical `template_ids` and timestamps. `setActiveRoutine` writes `users/{uid}.activeRoutineId`.

Data impacted over time
- Template analytics become populated/recalculated; routines maintain references to templates and the user’s `activeRoutineId` may change.

Sources
- Templates: `firebase_functions/functions/templates/create-template.js`, `.../update-template.js`, `.../delete-template.js`, `.../get-template.js`, `.../get-user-templates.js`
- Routines: `firebase_functions/functions/routines/create-routine.js`, `.../update-routine.js`, `.../delete-routine.js`, `.../get-routine.js`, `.../get-user-routines.js`, `.../get-active-routine.js`, `.../set-active-routine.js`

### StrengthOS Progress Reports (service writes)
- `strengthos/progress-reports.js`
  - `upsertProgressReport` (API key only) upserts `users/{uid}/progress_reports/{reportId}` with `period.start/end`, `metrics`, and `proposals`.
  - `getProgressReports` lists the latest 20 reports ordered by `period.start`.

Sources
- `firebase_functions/functions/strengthos/progress-reports.js`

### Idempotency (duplicate suppression)
- Global: `idempotency/{userId:tool:key}` used by active workout tools (`log_set`, `add_exercise`, `swap_exercise`, `prescribe_set`).
- Canvas-scoped: `users/{uid}/canvases/{canvasId}/idempotency/{key}` inside reducer transactions.

Sources
- `firebase_functions/functions/utils/idempotency.js`
- `firebase_functions/functions/canvas/apply-action.js` (canvas-scoped usage)



