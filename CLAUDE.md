# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Sub-Agent Configuration

When spawning sub-agents via the Task tool, always pass `model: "sonnet"`. The default haiku model is not available in this environment.

## Agent Working Protocol

### Task Startup Sequence

Before writing any code, execute these steps in order:

1. **Read central docs.** Start with `docs/SYSTEM_ARCHITECTURE.md` (cross-layer data flows, schema contracts, auth patterns). Then read the module-specific doc for whichever layer you are working in:
   - iOS: `docs/IOS_ARCHITECTURE.md`
   - Firebase Functions: `docs/FIREBASE_FUNCTIONS_ARCHITECTURE.md`
   - Agent system: `docs/SHELL_AGENT_ARCHITECTURE.md`
   - Catalog orchestrator: `docs/CATALOG_ORCHESTRATOR_ARCHITECTURE.md`
2. **Read directory-level `ARCHITECTURE.md`** files in the directories you will modify.
3. **Read the source files** you intend to change. Understand adjacent files that call into or are called by them.
4. **Identify which layers are affected.** A change that touches data shape likely spans Firestore schema, Firebase Function, iOS model, and possibly agent tools. See [Cross-Stack Checklist](#cross-stack-checklist).
5. **Create a plan.** State what changes, where, and why. Explain any significant architectural decision. If there are multiple valid approaches, pick one and state why.
6. **Self-challenge before executing:**
   - Is every change necessary, or am I adding speculative scope?
   - Am I over-engineering? Would a simpler approach work?
   - Does this align with what was actually requested?
   - Am I making assumptions about unclear requirements? If yes — **ask the user** instead of guessing.

### Implementation Rules

- **Solve only what is requested.** No speculative features, no "while we're here" refactors, no unnecessary abstractions.
- **Justify added complexity.** If introducing a third-party library or a new pattern, explain why the native/existing approach is insufficient. The simplest native solution is the default.
- **Ask, don't guess.** If requirements are ambiguous, or if a design choice has user-visible tradeoffs, ask for clarification before implementing.
- **Bias toward one-shot implementations.** Prefer slightly more upfront planning and clarification over incremental trial-and-error. If a plan is uncertain, pause and ask rather than implement a partial solution.

### Code Style

- **Python** (agent system): PEP 8, line length 100. Enforced by `flake8` and `black`. Run `make lint` and `make format` in `adk_agent/catalog_orchestrator/`.
- **JavaScript** (Firebase Functions): Standard conventions. Use `const` by default, `require()` imports, `async/await` for all async operations. Response helpers: `ok(res, data)` / `fail(res, code, message, details, httpStatus)` from `utils/response.js`.
- **Swift** (iOS): Follow existing patterns. Models use `Codable` with `decodeIfPresent` + defaults for resilience. Use `@DocumentID` for Firestore doc IDs.
- **All languages**: Functions should be modular. Names should be descriptive. Patterns should be simple. Annotate complex or security-critical sections with structured comments explaining *what* and *why* (not change history).

### Documentation Updates (Three Tiers)

When modifying code, update **all affected tiers**. All documentation describes **how the system works now** — not a changelog. Exception: major architectural shifts should be noted briefly for strategic awareness.

**Tier 1 — Central (`docs/`): System architecture and data flow.**
Update when: a change affects cross-layer interaction, adds/removes an API endpoint, or alters a shared data shape (Firestore schema, SSE event format, auth pattern).

**Tier 2 — Directory (`ARCHITECTURE.md` in module directories): Module-level architecture.**
Update when: adding/removing files, changing internal responsibilities, or altering how components within the module interact. Each major directory should have an `ARCHITECTURE.md` that lets an agent understand the module without reading every file. Covers: file structure, entry points, internal patterns, how concepts work together. When creating a new module directory, always create a Tier 2 `ARCHITECTURE.md`. These docs cover only module-internal concerns — they are not copies of central docs. Exception: project-root directories that already have `README.md` (e.g., `firebase_functions/functions/README.md`) may keep that name.

**Tier 3 — File-level (inline annotations): Code-level context.**
Focus on:
- Complex logic that isn't self-evident from the code
- Security-critical sections (auth boundaries, userId derivation)
- Cross-file dependencies (e.g., `// Called by canvas/apply-action.js when action type is SAVE_ROUTINE`)
- Intentional constraints (e.g., `// ContextVar required — module globals leak across concurrent requests on Vertex AI`)

Do not annotate trivial code.

### Finishing a Task

End every task with a clean commit. The codebase must be in a stable, buildable state after your changes.

---

## Project Overview

Povver (formerly MYON) is an AI-powered fitness coaching platform. Three layers, Firestore as source of truth:

```
iOS App (SwiftUI) ──HTTP/SSE──> Firebase Functions (Node.js) ──HTTP──> Agent System (Python/Vertex AI)
       │                              │                                       │
       └──── Firestore Listeners ─────┴──────── Firestore Reads/Writes ──────┘
```

| Layer | Path | Runtime |
|-------|------|---------|
| iOS App | `Povver/Povver/` | SwiftUI, MVVM |
| Firebase Functions | `firebase_functions/functions/` | Node.js 22, us-central1 |
| Agent System | `adk_agent/catalog_orchestrator/` | Python, Vertex AI Agent Engine |
| Admin Dashboard | `admin/catalog_dashboard/` | Python/Flask |
| Utility Scripts | `scripts/` | Node.js |

---

## Service Account Keys

Keys live outside the repo at `~/.config/povver/`. Two named env vars point to each key file. Set `GOOGLE_APPLICATION_CREDENTIALS` to the correct one before running a command:

| Env Var | Key File | Use |
|---------|----------|-----|
| `FIREBASE_SA_KEY` | `~/.config/povver/myon-53d85-firebase-adminsdk-fbsvc-ca7beb1435.json` | Firebase Admin SDK — scripts, emulators, local functions |
| `GCP_SA_KEY` | `~/.config/povver/myon-53d85-80792c186dcb.json` | GCP service account — agent deploy, Cloud Run, Vertex AI |

**How to use:** Google SDKs read `GOOGLE_APPLICATION_CREDENTIALS`. Set it to the appropriate named var:

```bash
# Firebase / Firestore work (scripts, functions, emulators)
export GOOGLE_APPLICATION_CREDENTIALS=$FIREBASE_SA_KEY

# GCP work (agent deploy, Cloud Run, Vertex AI)
export GOOGLE_APPLICATION_CREDENTIALS=$GCP_SA_KEY
```

Add both named vars to your shell profile (`~/.zshrc`):
```bash
export FIREBASE_SA_KEY=~/.config/povver/myon-53d85-firebase-adminsdk-fbsvc-ca7beb1435.json
export GCP_SA_KEY=~/.config/povver/myon-53d85-80792c186dcb.json
```

**Never commit key files to the repo.** The `config/` directory is in `.gitignore` as a safeguard.

---

## Build & Development Commands

### iOS
```bash
xcodebuild -scheme Povver -destination 'platform=iOS Simulator,name=iPhone 16 Pro' build
```

### Firebase Functions
```bash
cd firebase_functions/functions
npm install                    # install dependencies
npm test                       # node --test ./tests/**/*.test.js
npm run serve                  # firebase emulators (functions:5001, firestore:8085, UI:4000)
npm run deploy                 # deploy to production
```

### Agent System (Canvas Orchestrator)

**Deploy to Vertex AI:** `make deploy` auto-resolves the GCP SA key in this order:
1. `$GOOGLE_APPLICATION_CREDENTIALS` (if set and file exists)
2. `$GCP_SA_KEY` (shell alias from `~/.zshrc`)
3. `~/.config/povver/myon-53d85-80792c186dcb.json` (hardcoded fallback)

The SA (`ai-agents@myon-53d85.iam.gserviceaccount.com`) must have `roles/aiplatform.user`.
Do NOT change ADC (`~/.config/gcloud/application_default_credentials.json`) — it's used for Claude billing.

```bash
cd adk_agent/canvas_orchestrator
make install       # pip install dependencies
make deploy        # deploy to Vertex AI Agent Engine (uses GCP SA key)
make dev           # local API server (adk api_server app)
make test          # pytest tests/ -v
make lint          # flake8 --max-line-length=100
make format        # black --line-length=100
make check         # compile-check all Python files
make chat          # interactive chat session
make deploy        # deploy to Vertex AI Agent Engine
```

### Training Analyst
```bash
cd adk_agent/training_analyst
make install       # pip install dependencies
make worker-local  # run analyst worker locally
make trigger-worker # trigger Cloud Run worker
```

### Utility Scripts
```bash
node scripts/import_strong_csv.js     # import Strong CSV workout data
node scripts/seed_simple.js           # seed Firestore test data
node scripts/purge_user_data.js       # purge user data
node scripts/backfill_set_facts.js    # backfill set_facts + series from workouts
node scripts/backfill_analysis_jobs.js # backfill training analysis (post-workout, weekly, daily)
```

---

## Architecture Reference

### iOS (Povver/Povver/)

MVVM: Views → ViewModels → Services/Repositories → Firebase SDK.

- **Entry**: `PovverApp.swift` → `RootView.swift` → `MainTabsView.swift` (tabs: Coach, Train, Routines, Templates)
- **Chat system**: Primary AI interaction surface. `CanvasViewModel` manages SSE streaming, artifact rendering, and conversation state. Artifacts (workout plans, routines, analysis) arrive via SSE events and render inline using card components (`SessionPlanCard`, `RoutineSummaryCard`, etc.).
- **Streaming**: `DirectStreamingService` opens SSE via `streamAgentNormalized` Firebase Function proxy to Vertex AI. Artifact events are emitted when agent tools return `artifact_type` data.
- **Models**: `Codable` structs with `decodeIfPresent` + sensible defaults. Use `@DocumentID` for Firestore doc IDs.
- **Design tokens**: `UI/DesignSystem/Tokens.swift` — spacing, radius, typography, colors.

### Firebase Functions (firebase_functions/functions/)

All functions exported from `index.js`. Two patterns for wrapping handlers:

**v1** (most endpoints): Wrapped in `index.js` with auth middleware:
```javascript
// Service lane — userId from req.body/query (trusted agent calls)
exports.getUser = functions.https.onRequest((req, res) => withApiKey(getUser)(req, res));
// Bearer lane — userId from req.auth.uid ONLY (iOS app calls)
exports.artifactAction = functions.https.onRequest((req, res) => requireFlexibleAuth(artifactAction)(req, res));
```

**v2** (newer endpoints): Self-contained with `onRequest` from `firebase-functions/v2/https`, auth middleware built-in. Exported directly: `exports.logSet = logSet;`

**When adding a new endpoint:**
1. Create handler file in the appropriate domain directory
2. Choose auth lane: `withApiKey` (service-only) or `requireFlexibleAuth` (iOS + service)
3. Use `ok(res, data)` / `fail(res, code, message, details, httpStatus)` from `utils/response.js`
4. Export in `index.js` with the correct middleware wrapper
5. For v2 functions, wrap internally and export directly

**Key patterns:**
- `stream-agent-normalized.js` handles SSE streaming, artifact detection, and message persistence to `conversations/{id}/messages` and `conversations/{id}/artifacts`
- `artifacts/artifact-action.js` handles artifact lifecycle (accept, dismiss, save_routine, start_workout)
- Auth security: Bearer-lane endpoints **never** trust client-provided userId — always derive from `req.auth.uid`

### Agent System — 4-Lane Shell Agent

The old multi-agent architecture (CoachAgent, PlannerAgent) is **deprecated** (`_archived/`). All code uses the Shell Agent.

| Lane | Trigger Pattern | Model | Latency | Handler |
|------|----------------|-------|---------|---------|
| FAST | `"done"`, `"8 @ 100"`, `"next set"` | None | <500ms | `copilot_skills.*` |
| FUNCTIONAL | `{"intent": "SWAP_EXERCISE", ...}` | Flash | <1s | `functional_handler.py` |
| SLOW | `"create a PPL routine"` | Pro | 2-5s | `shell/agent.py` |
| WORKER | PubSub `workout_completed` | Pro | async | `post_workout_analyst.py` |

- **Entry**: `app/agent_engine_app.py` → `app/shell/router.py` (lane selection) → lane handler
- **Skills** (`app/skills/`): Pure logic modules shared across all lanes. This is the "shared brain."
- **Context**: Thread-safe `ContextVar` per request — **required** because Vertex AI Agent Engine is concurrent serverless. Module-level globals would leak user data across requests.
- **Security**: `user_id` always from authenticated request context, never from LLM output.

### Catalog Orchestrator

Automated catalog curation via Cloud Run Jobs: quality audits, gap analysis, LLM enrichment, duplicate detection. Uses `gemini-2.5-flash` by default. Job queue in Firestore (`catalog_jobs` collection). See `adk_agent/catalog_orchestrator/Makefile` for all targets.

---

## Key Firestore Collections

| Collection | Purpose |
|------------|---------|
| `users/{uid}/conversations/{id}/messages` | Conversation history (user prompts, agent responses, artifact refs) |
| `users/{uid}/conversations/{id}/artifacts` | Proposed artifacts from agent (plans, routines, analysis) |
| `users/{uid}/agent_sessions/{purpose}` | Vertex AI session references for reuse |
| `users/{uid}/routines/{id}` | Ordered template sequences with cursor tracking |
| `users/{uid}/templates/{id}` | Reusable workout plans |
| `users/{uid}/active_workouts/{id}` | In-progress workouts |
| `users/{uid}/workouts/{id}` | Completed workout history |
| `exercises` | Global exercise catalog |
| `catalog_jobs` | Catalog orchestrator job queue |

Full schema with field-level detail: `docs/FIRESTORE_SCHEMA.md`

---

## Cross-Stack Checklist

When adding a new field or data shape, update across all affected layers:

1. **Firestore schema** → `docs/FIRESTORE_SCHEMA.md`
2. **Firebase Function write path** → e.g., `create-routine-from-draft.js`, `stream-agent-normalized.js`
3. **Firebase Function read path** → e.g., `get-routine.js`, `get-planning-context.js`
4. **iOS Model** → `Povver/Povver/Models/*.swift` (ensure `Codable` with `decodeIfPresent` + default)
5. **iOS UI** → relevant views
6. **Agent tools** → `app/skills/*.py` (if agent reads/writes the field)
7. **Documentation** → all three tiers as applicable

---

## Deprecated (Do Not Use)

| Deprecated | Replacement |
|------------|-------------|
| `adk_agent/canvas_orchestrator/_archived/` | Shell Agent (`app/shell/`) |
| `canvas/apply-action.js` and all `canvas/*.js` | Artifacts via `stream-agent-normalized.js` + `artifacts/artifact-action.js` |
| `CanvasRepository.swift` | Artifacts from SSE events in `CanvasViewModel` |
| `PendingAgentInvoke.swift` | Dead code — removed |
| `routines/create-routine.js` | `routines/create-routine-from-draft.js` |
| `routines/update-routine.js` | `routines/patch-routine.js` |
| `templates/update-template.js` | `templates/patch-template.js` |
| Field `templateIds` | `template_ids` |
| Field `weight` | `weight_kg` |
