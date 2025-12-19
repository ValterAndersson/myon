# Muscle Volume Calculation Service Plan

*Created: December 19, 2024*
*Status: Planned, not yet implemented*

## Overview

A service to calculate precise muscle volume distribution for workout plans, enabling:
- Per-workout muscle breakdown visualization
- Routine-level roll-up (weekly volume per muscle)
- Agent validation of workout balance

## Existing Code

The calculation logic already exists in `firebase_functions/functions/utils/analytics-calculator.js`:

- **`calculateTemplateAnalytics(template)`** - For planned workouts (uses projected weights)
- **`calculateWorkoutAnalytics(workout)`** - For completed workouts (uses actual weights)

### Key Data Structures

**Exercise Model:**
```javascript
exercise.muscles = {
  primary: ["quadriceps", "glutes"],           // Array of primary muscles
  secondary: ["hamstrings", "core"],           // Array of secondary muscles
  category: ["legs"],                          // Muscle groups
  contribution: {                              // Coefficient map (0-1, sums to 1)
    "quadriceps": 0.5,
    "glutes": 0.3,
    "hamstrings": 0.2
  }
}
```

**Calculation Output:**
```javascript
{
  sets_per_muscle: { "quadriceps": 9, "glutes": 6 },
  projected_volume_per_muscle: { "quadriceps": 5760, "glutes": 4320 },
  relative_stimulus_per_muscle: { "quadriceps": 100, "glutes": 75 },
  sets_per_muscle_group: { "legs": 12 },
  // ... same for muscle_groups
}
```

---

## Architecture Plan

### 1. Cloud Function: `calculatePlanVolume`

New endpoint that extracts the calculation logic for reuse.

```javascript
// POST /calculatePlanVolume
// Input
{
  exercises: [
    { exercise_id: "barbell-squat", sets: 3, reps: 8, weight_kg: 80 },
    { exercise_id: "romanian-deadlift", sets: 3, reps: 10, weight_kg: 60 }
  ]
}

// Output
{
  muscles: {
    "quadriceps": { sets: 3, volume: 5760, relative: 100 },
    "glutes": { sets: 6, volume: 4320, relative: 75 },
    "hamstrings": { sets: 3, volume: 1800, relative: 31 }
  },
  muscle_groups: {
    "legs": { sets: 6, volume: 7560, relative: 100 }
  }
}
```

**Fallback Logic:**
If an exercise lacks `muscles.contribution`, distribute evenly across `muscles.primary`.

---

### 2. Agent Tool: `tool_calculate_volume`

Conditional tool for the agent to verify workout balance.

```python
def tool_calculate_volume(
    *,
    exercises: List[Dict[str, Any]],  # [{exercise_id, sets, reps, weight_kg}]
) -> Dict[str, Any]:
    """
    Calculate precise muscle volume distribution for a workout plan.
    
    Use this when:
    - Building a routine and need to ensure balanced weekly volume
    - User explicitly asks about muscle focus or balance
    - Verifying that a workout targets the intended muscles
    
    Returns breakdown by muscle and muscle group (sets, volume, percentage).
    """
```

**Agent Instruction Addition:**
```
## VOLUME VERIFICATION (Optional)
When building routines or when volume balance matters:
- Call `tool_calculate_volume(exercises=[...])` to get precise numbers
- Check if the distribution matches the user's request
- If imbalanced, adjust before publishing

Use when:
- Creating multi-day routines
- User says "balanced", "equal", "hit all muscles"
- Verifying a specific muscle focus (e.g., "glute-focused leg day")
```

---

### 3. iOS UI: `MuscleBreakdownPanel`

**Location:** Info icon next to 3-dot menu on `SessionPlanCard`

**Design:**
```
┌─────────────────────────────────────┐
│ Muscle Groups          Sets  Volume │
│ ──────────────────────────────────  │
│ 🦵 Legs               ████████ 14   │
│    Quadriceps         ██████   10   │
│    Glutes             █████    8    │
│    Hamstrings         ████     6    │
│                                     │
│ 💪 Arms               ████     4    │
│    Triceps            ███      3    │
│    Biceps             ██       2    │
└─────────────────────────────────────┘
```

**Behavior:**
- Muscle groups collapsed by default, expandable to show individual muscles
- Sorted by total volume (sets × weight × reps × contribution)
- Visual bar indicator (relative to max)
- Shows both sets count and volume

---

### 4. Data Flow

**Single Workout:**
```
User → "Plan a leg day"
Agent → searches → creates plan → publishes
iOS → sees session_plan → calls calculatePlanVolume → caches in card state
User → taps info icon → sees MuscleBreakdownPanel
```

**Routine (multi-workout):**
```
User → "Create a 4-day upper/lower split"
Agent → creates Day 1 → calls tool_calculate_volume → validates
Agent → creates Day 2 → calls tool_calculate_volume → validates  
Agent → aggregates weekly totals → checks balance
Agent → publishes routine with embedded breakdown
```

---

### 5. Routine Roll-up Strategy

For routines (e.g., "5-day PPL split"):
```javascript
Routine {
  workouts: [
    { day: 1, type: "Push", muscles_summary: {...} },
    { day: 2, type: "Pull", muscles_summary: {...} },
    { day: 3, type: "Legs", muscles_summary: {...} }
  ],
  weekly_totals: {
    "chest": { sets: 16, volume: 28000 },
    "back": { sets: 18, volume: 32000 },
    // ...
  }
}
```

---

## Implementation Order

### Phase 1: Foundation
1. [ ] Create `calculatePlanVolume` Cloud Function (extract from existing calculator)
2. [ ] Add fallback logic for missing contribution data
3. [ ] Test endpoint

### Phase 2: Agent Integration  
4. [ ] Add `tool_calculate_volume` to unified_agent.py
5. [ ] Update agent instruction with conditional usage guidelines
6. [ ] Deploy agent

### Phase 3: iOS UI
7. [ ] Create `MuscleBreakdownPanel` SwiftUI component
8. [ ] Add info icon to SessionPlanCard title row
9. [ ] Wire up API call or local calculation

### Phase 4: Routine Support (Future)
10. [ ] Create routine card type
11. [ ] Add weekly roll-up aggregation
12. [ ] Agent routine planning flow

---

## Design Decisions

1. **iOS calls Cloud Function when user taps info icon** (vs. embedding in card)
   - Keeps agent flow fast
   - Data is always fresh
   - Can optimize later with caching or pre-computation

2. **Both muscle groups AND individual muscles calculated**
   - Groups for high-level view (legs, chest, back)
   - Individual muscles for advanced users (quadriceps, glutes)
   - UI: groups collapsed by default, expandable

3. **Agent uses tool conditionally**
   - Single workouts: agent doesn't call tool (keeps response fast)
   - Routines: agent calls tool to verify weekly balance
   - Balance requests: agent calls tool to verify distribution

---

## Related Files

- `firebase_functions/functions/utils/analytics-calculator.js` - Existing calculation logic
- `firebase_functions/functions/analytics/worker.js` - Analytics aggregation
- `MYON2/MYON2/UI/Canvas/Cards/SessionPlanCard.swift` - Card UI to extend
- `adk_agent/canvas_orchestrator/app/unified_agent.py` - Agent to add tool to
