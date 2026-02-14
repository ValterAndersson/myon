# Scripts — Module Architecture

Standalone utility scripts for data management and catalog normalization.

## Node.js Scripts

Run via `node scripts/<name>.js`. Require Firebase Admin SDK (ADC or emulator).

| File | Purpose | Usage |
|------|---------|-------|
| `import_strong_csv.js` | Import workout history from Strong app CSV exports. Parses CSV, maps exercises to catalog, creates workout documents in `users/{uid}/workouts/`. | `node scripts/import_strong_csv.js` |
| `seed_simple.js` | Seed Firestore with minimal test data (user, templates, exercises). | `node scripts/seed_simple.js` |
| `seed_full_user.js` | Seed a full user profile with workout history, templates, routines, and analytics data. | `node scripts/seed_full_user.js` |
| `purge_user_data.js` | Delete all data for a user (workouts, templates, routines, analytics, canvases). Recursive subcollection deletion. | `node scripts/purge_user_data.js` |
| `backfill_set_facts.js` | Backfill `set_facts` collection from existing workout history. Used when deploying Training Analytics v2. | `node scripts/backfill_set_facts.js` |
| `backfill_analysis_jobs.js` | Enqueue POST_WORKOUT, WEEKLY_REVIEW, and DAILY_BRIEF analysis jobs for historical data. Idempotent (deterministic job IDs). Run after `backfill_set_facts.js`. | `node scripts/backfill_analysis_jobs.js --user <userId> --months 3` |
| `find_analysis_users.js` | Find users with existing analysis data (analysis_insights, daily_briefs, weekly_reviews). | `node scripts/find_analysis_users.js` |
| `dump_analysis_data.js` | Dump latest analysis insights/briefs/reviews for a user. | `node scripts/dump_analysis_data.js` |

## Python Scripts — Catalog Normalization

Run via `python3 scripts/<name>.py`. Require `google-cloud-firestore` and ADC. All support `--apply` dry-run safety (default: dry-run, prints what would change).

| File | Purpose | Usage |
|------|---------|-------|
| `normalize_muscle_names.py` | Normalize muscle names in the `exercises` collection. Maps aliases to canonical names (e.g. "delts" → "deltoid"), fixes underscores/casing. | `python3 scripts/normalize_muscle_names.py [--apply]` |
| `normalize_equipment.py` | Normalize equipment values. Maps plurals, underscores, abbreviations to canonical values (e.g. "dumbbells" → "dumbbell"). | `python3 scripts/normalize_equipment.py [--apply]` |
| `normalize_movement_types.py` | Normalize `movement.type` and `movement.split` fields. Maps invalid values to canonical (e.g. "press" → "push", "full body" → "full_body"). | `python3 scripts/normalize_movement_types.py [--apply]` |
| `fix_contribution_sums.py` | Re-normalize `muscles.contribution` maps where values don't sum to ~1.0. | `python3 scripts/fix_contribution_sums.py [--apply]` |
| `identify_duplicates.py` | Report potential duplicate exercises by name similarity and family_slug clustering. Read-only by default. | `python3 scripts/identify_duplicates.py [--output report.json] [--archive-test --apply]` |
| `requeue_failed_import_jobs.py` | Re-queue failed import enrichment jobs with corrected payload structure. | `python3 scripts/requeue_failed_import_jobs.py [--apply]` |

### Recommended Run Order

Muscle names should be normalized before contribution sums (avoids duplicate keys):

1. `normalize_muscle_names.py`
2. `normalize_equipment.py`
3. `normalize_movement_types.py`
4. `fix_contribution_sums.py`
5. `identify_duplicates.py`
6. `requeue_failed_import_jobs.py`

## Prerequisites

- **Node.js scripts**: Firebase Admin SDK credentials:
  ```bash
  export GOOGLE_APPLICATION_CREDENTIALS=$FIREBASE_SA_KEY
  ```
- **Python scripts**: `google-cloud-firestore` package with GCP credentials:
  ```bash
  export GOOGLE_APPLICATION_CREDENTIALS=$GCP_SA_KEY
  ```
- See [CLAUDE.md — Service Account Keys](../CLAUDE.md#service-account-keys) for key file setup.
- For `import_strong_csv.js`: Strong app CSV export file

## Cross-References

- Canonical values (source of truth): `adk_agent/catalog_orchestrator/app/enrichment/exercise_field_guide.py`
- Workout schema: `docs/FIRESTORE_SCHEMA.md`
- Set facts generator: `firebase_functions/functions/training/set-facts-generator.js`
- Exercise catalog: `firebase_functions/functions/exercises/`
