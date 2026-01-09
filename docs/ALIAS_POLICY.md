# Alias Policy for Catalog Admin v2

## Overview

This document defines how exercise aliases are handled when exercises are split by equipment (e.g., "Deadlift (Barbell)", "Deadlift (Dumbbell)").

## Policy Decision: Option 1 - Default to Most Common Equipment

When an ambiguous alias like "deadlift" is queried, it resolves to the **most common equipment variant**, typically Barbell for compound movements.

### Default Equipment Mapping

```python
DEFAULT_EQUIPMENT_FOR_ALIAS = {
    # Compound movements → Barbell
    "deadlift": "barbell",
    "squat": "barbell", 
    "bench-press": "barbell",
    "overhead-press": "barbell",
    "row": "barbell",
    
    # Isolation movements → varies
    "lateral-raise": "dumbbell",
    "curl": "dumbbell",
    "tricep-extension": "cable",
    "fly": "dumbbell",
}
```

### Resolution Behavior

1. **Exact match**: If alias matches `name_slug` exactly → return that exercise
2. **Family alias**: If alias matches `family_slug` → return default equipment variant
3. **No match**: Return null or suggest candidates

### Example

Query: `"deadlift"`
- Checks `exercise_aliases/deadlift` → maps to `deadlift-barbell`
- Returns: `Deadlift (Barbell)`

Query: `"deadlift-dumbbell"` 
- Exact match in aliases
- Returns: `Deadlift (Dumbbell)`

## Alias Collection Schema

```
exercise_aliases/{alias_slug}
├── alias_slug: string (doc ID)
├── exercise_id: string (Firestore doc ID of exercise)
├── family_slug: string (optional, for family-level aliases)
├── is_family_alias: boolean (if true, uses default equipment resolution)
├── created_at: timestamp
└── updated_at: timestamp
```

## Alias Invariants

1. **One-to-one mapping**: Each `alias_slug` points to exactly one `exercise_id` (or one `family_slug`)
2. **No orphans**: All `exercise_id` values must reference existing exercises
3. **No silent overwrites**: Updating an alias that points to a different exercise requires explicit intent
4. **Old slugs become aliases**: When renaming an exercise, the old `name_slug` becomes an alias

## Implementation Notes

- Validators check alias collisions before apply
- ALIAS_REPAIR job fixes orphaned aliases
- ALIAS_INVARIANT_SCAN detects violations
- UI/search layer should use alias resolver, not direct name matching

## Future Considerations

- **Option 2** (context-aware): Could use user history/preferences to disambiguate
- **Option 3** (multi-target): Could return candidate list for ambiguous aliases
- These require schema changes and are not implemented in v2

---

*Decision made: 2026-01-09*
*Implementation: app/family/taxonomy.py*
