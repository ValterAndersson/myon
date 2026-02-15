# Utils — Module Architecture

Shared helpers used across Firebase Function endpoints. These provide consistent patterns for responses, validation, Firestore operations, and domain logic.

## File Inventory

| File | Purpose |
|------|---------|
| `response.js` | Response helpers: `ok(res, data)` / `fail(res, code, message, details, httpStatus)`. All endpoints use these for consistent response shape. |
| `validators.js` | Ajv schema validation: loads and compiles JSON schemas, validates request/card payloads |
| `validation-response.js` | Validation error formatting for agent self-healing (includes attempted payload, errors, hints, expected schema) |
| `idempotency.js` | Idempotency key check and storage. Supports global, canvas-scoped, and workout-scoped (transactional) variants. |
| `active-workout-helpers.js` | Shared helpers for active workout mutations: `computeTotals`, `findExercise`, `findSet`, `findExerciseAndSet`. Used by all four hot-path endpoints. |
| `firestore-helper.js` | Firestore abstractions: `upsertDocument`, `upsertDocumentInSubcollection`, timestamp handling |
| `plan-to-template-converter.js` | Converts `session_plan` card content to a `WorkoutTemplate` document structure |
| `strings.js` | String utilities: slug generation, name normalization |
| `aliases.js` | Exercise alias management: slug lookup, alias reservation |
| `analytics-writes.js` | Analytics series write operations: batch updates to `analytics_series_exercise`, `analytics_series_muscle` |
| `analytics-calculator.js` | Analytics computation: e1RM, volume, set classification |
| `muscle-taxonomy.js` | Canonical muscle groups and muscles with stable IDs, catalog-to-canonical mapping |
| `workout-seed-mapper.js` | Maps seed data into workout document format |
| `caps.js` | Server-enforced caps for training analytics v2 (limits, max bytes, max weeks) |

## Key Exports

### `response.js`
```javascript
ok(res, data, meta?)    // → { success: true, data, meta? }
fail(res, code, msg, details?, httpStatus?)  // → { success: false, error: { code, message, details? } }
```

### `firestore-helper.js`
```javascript
upsertDocument(collection, id, data)  // set(..., { merge: true })
upsertDocumentInSubcollection(parent, parentId, sub, id, data)
```

### `validators.js`
```javascript
validateCardContent(type, content)  // Ajv validation against card_types/*.schema.json
```

## Cross-References

- Used by all endpoint handlers in `canvas/`, `active_workout/`, `routines/`, `templates/`, `exercises/`
- Schema files: `canvas/schemas/card_types/*.json`
- Muscle taxonomy used by: `training/set-facts-generator.js`, `analytics/`
