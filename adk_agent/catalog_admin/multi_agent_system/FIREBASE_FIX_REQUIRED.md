# Firebase Function Fix Required

## Issue
The `upsertExercise` Firebase function fails when updating existing exercises.

## Root Cause
The function uses `db.updateDocument()` which calls Firestore's `update()` method. According to [Firebase documentation](https://firebase.google.com/docs/firestore/manage-data/add-data), this fails if:
1. The document doesn't exist
2. Required fields are missing
3. The data structure doesn't match exactly

## Solution
Applied. `upsertExercise` now uses Firestore upsert semantics.

### Current Code (line 72-76):
```javascript
if ((mode === 'update' && id) || id) {
  await db.updateDocument('exercises', id, data);
} else {
  id = await db.addDocument('exercises', data);
}
```

### Fixed Code (effective)
`upsert-exercise.js` calls `FirestoreHelper.upsertDocument(collection, id, data)` which performs `set(..., { merge: true })` and manages timestamps. See file for details.

## Alternative Solutions

### Option 1: Update FirestoreHelper
Modify `firebase_functions/functions/utils/firestore-helper.js` to add a proper upsert method:

```javascript
async upsertDocument(collection, docId, data) {
  const docRef = this.db.collection(collection).doc(docId);
  await docRef.set(data, { merge: true });
  return docId;
}
```

### Option 2: Split into Separate Functions
Create two distinct endpoints:
- `createExercise` - Only creates new exercises
- `updateExercise` - Only updates existing exercises

## Impact
Currently affects:
- Content Specialist improvements
- Biomechanics Specialist improvements  
- Anatomy Specialist improvements
- Programming Specialist improvements

## Workaround Status
- ✅ Alias creation works (uses different endpoint)
- ✅ New exercise creation works
- ✅ Exercise updates now succeed (upsert)
- ✅ Pipeline saves improvements

## Testing
After fixing, test with:
```bash
curl -X POST https://us-central1-myon-53d85.cloudfunctions.net/upsertExercise \
  -H "X-API-Key: myon-agent-key-2024" \
  -H "Content-Type: application/json" \
  -d '{
    "exercise": {
      "id": "existing-exercise-id",
      "name": "Test Exercise",
      "description": "Updated description"
    }
  }'
```

## Priority
HIGH - This blocks all exercise improvements from specialist agents in the multi-agent pipeline.
