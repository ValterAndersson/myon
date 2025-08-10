# Strong Workout Import Script

Import a Strong-formatted text export into Firestore as a workout adhering to the iOS app schema.

Requirements:
- Node.js 18+
- `GOOGLE_APPLICATION_CREDENTIALS` set to a service account JSON with Firestore access
- `npm install`

Usage:

```bash
node scripts/import_strong_workout.js --file /abs/path/to/workout.txt --user USER_ID [--yes] [--default-warmup-rir 3] [--tz Europe/Oslo] [--analytics cloud|local|none]
```

Notes:
- The script fetches `/exercises` and proposes mappings by fuzzy match. You can search or accept suggestions.
- RPE in the text is mapped to RIR: 10→0, 9→1, 8→2, 7→3, 6→4. Missing values will be prompted; warm-ups can use `--default-warmup-rir`.
- Writes to `users/{userId}/workouts` with fields `start_time`, `end_time`, `exercises[*].{exercise_id,name,position,sets[*].{id,reps,rir,type,weight_kg,is_completed}}`, and `notes`.
- Analytics: by default, the script includes zeroed analytics fields to satisfy the app schema and your triggers will overwrite/update them. You can control behavior with `--analytics`:
  - `cloud` (recommended): omit analytics and let triggers compute.
  - `local`: include zeroed analytics placeholders immediately.
  - `none`: omit analytics entirely.