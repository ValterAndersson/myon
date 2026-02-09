# Exercises — Module Architecture

Exercise catalog CRUD, search, and curation endpoints. Manages the global `exercises` collection and `exercise_aliases` registry.

## File Inventory

### Read Endpoints

| File | Endpoint | Purpose |
|------|----------|---------|
| `get-exercises.js` | `getExercises` | List exercises with optional filters |
| `get-exercise.js` | `getExercise` | Get by `id`, `name`, `slug`, or `alias_slug` (fallback chain: `name_slug` → `alias_slugs` → `exercise_aliases/{slug}`) |
| `search-exercises.js` | `searchExercises` | Flexible search with muscle group, movement type, equipment, category filters. v2 endpoint. |
| `search-aliases.js` | `searchAliases` | Prefix search in `exercise_aliases` collection |
| `list-families.js` | `listFamilies` | Grouped view by `family_slug` with members and variants |

### Write/Curate Endpoints

| File | Endpoint | Purpose |
|------|----------|---------|
| `upsert-exercise.js` | `upsertExercise` | Create/update exercise. Canonicalizes name/slug, sets family/variant, reserves aliases. Idempotent by slug. |
| `refine-exercise.js` | `refineExercise` | Schema-lite metadata enrichment (movement, muscles, notes) |
| `approve-exercise.js` | `approveExercise` | Mark exercise as approved |
| `ensure-exercise-exists.js` | `ensureExerciseExists` | Find-or-create by name (draft if new) |
| `resolve-exercise.js` | `resolveExercise` | Best-candidate ranking given context (equipment, user preferences) |
| `merge-exercises.js` | `mergeExercises` | Safe merge within same `family_slug::variant_key`. Sets `merged_into` redirect. |
| `suggest-family-variant.js` | `suggestFamilyVariant` | Pure inference of `family_slug` + `variant_key` from name and metadata |
| `suggest-aliases.js` | `suggestAliases` | Generate alias candidates (verbose + shorthands) |

### Maintenance

| File | Endpoint | Purpose |
|------|----------|---------|
| `normalize-catalog.js` | `normalizeCatalog` | Full sweep normalization (fields + alias registry). May time out on large catalogs. |
| `normalize-catalog-page.js` | `normalizeCatalogPage` | Paginated normalization (preferred over full sweep) |
| `backfill-normalize-family.js` | `backfillNormalizeFamily` | Plan/apply merges for a single family |

## Alias Resolution Flow

```
User query: "db bench"
    → getExercise(slug: "db-bench")
    → 1. Search exercises.name_slug == "db-bench"  → miss
    → 2. Search exercises where "db-bench" in alias_slugs  → miss
    → 3. Lookup exercise_aliases/db-bench  → { exercise_id: "xyz" }
    → 4. Return exercises/xyz
```

## Cross-References

- Alias utilities: `utils/aliases.js`, `utils/strings.js`
- Agent curation tools: `adk_agent/catalog_orchestrator/workers/`
- Catalog dashboard: `admin/catalog_dashboard/`
- Exercise model (iOS): `Povver/Povver/Models/Exercise.swift`
