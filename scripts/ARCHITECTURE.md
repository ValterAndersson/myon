# Scripts — Module Architecture

Standalone Node.js utility scripts for data management. Run manually via `node scripts/<name>.js`.

## File Inventory

| File | Purpose | Usage |
|------|---------|-------|
| `import_strong_csv.js` | Import workout history from Strong app CSV exports. Parses CSV, maps exercises to catalog, creates workout documents in `users/{uid}/workouts/`. | `node scripts/import_strong_csv.js` |
| `seed_simple.js` | Seed Firestore with minimal test data (user, templates, exercises). | `node scripts/seed_simple.js` |
| `seed_full_user.js` | Seed a full user profile with workout history, templates, routines, and analytics data. | `node scripts/seed_full_user.js` |
| `purge_user_data.js` | Delete all data for a user (workouts, templates, routines, analytics, canvases). Recursive subcollection deletion. | `node scripts/purge_user_data.js` |
| `backfill_set_facts.js` | Backfill `set_facts` collection from existing workout history. Used when deploying Training Analytics v2. | `node scripts/backfill_set_facts.js` |

## Prerequisites

- Firebase Admin SDK configured (typically via `GOOGLE_APPLICATION_CREDENTIALS` or emulator)
- For `import_strong_csv.js`: Strong app CSV export file

## Cross-References

- Workout schema: `docs/FIRESTORE_SCHEMA.md`
- Set facts generator: `firebase_functions/functions/training/set-facts-generator.js`
- Exercise catalog: `firebase_functions/functions/exercises/`
