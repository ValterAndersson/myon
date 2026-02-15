# Artifacts — Module Architecture

Handles artifact lifecycle actions: accept, dismiss, save_routine, start_workout, save_template, save_as_new.

## File Inventory

| File | Purpose |
|------|---------|
| `artifact-action.js` | Single endpoint for all artifact actions. Replaces the canvas `apply-action.js` reducer. |

## Artifact Action Endpoint

**Auth**: `requireFlexibleAuth` (Bearer lane for iOS, API key lane for agent)

**Input**: `{ userId, conversationId, artifactId, action, day? }`

**Actions**:

| Action | Artifact Types | Behavior |
|--------|---------------|----------|
| `accept` | Any | Sets status to `accepted` |
| `dismiss` | Any | Sets status to `dismissed` |
| `save_routine` | `routine_summary` | Creates templates for each workout day via `convertPlanToTemplate()`, creates/updates routine doc, sets as active routine |
| `start_workout` | `session_plan`, `routine_summary` | Returns plan blocks for iOS to call `startActiveWorkout`. For routines, uses `day` param to select workout. |
| `save_template` | `session_plan` | Creates/updates a single template via `convertPlanToTemplate()` |
| `save_as_new` | `session_plan`, `routine_summary` | Same as save_routine/save_template but always creates new (ignores source IDs) |

## Firestore Paths

- Artifact: `users/{userId}/conversations/{conversationId}/artifacts/{artifactId}`
- Templates: `users/{userId}/templates/{templateId}`
- Routines: `users/{userId}/routines/{routineId}`

## Cross-References

- Streaming: `strengthos/stream-agent-normalized.js` (creates artifacts from tool responses)
- Template conversion: `utils/plan-to-template-converter.js`
- iOS caller: `Povver/Povver/Services/AgentsApi.swift` → `artifactAction()`
