# Routine-Based Continuous Planning

Implementation complete on branch `feature/routine-continuous-planning`.

## Overview

This project enables routine-based continuous planning where:
- Users can create and manage routines that reference templates
- The planner agent can generate plans from existing templates
- Plans can be saved as new templates or used to update existing ones
- Templates can be fully edited and persisted over time

## Architecture

### Deterministic Next Workout Selection

The system uses a cursor-based approach for O(1) next workout selection:

1. **Cursor Fields** (in `routines/{routineId}`):
   - `last_completed_template_id`: ID of the most recently completed template
   - `last_completed_at`: Timestamp of completion

2. **Selection Algorithm**:
   - If cursor exists: Find index of last completed template, return next in list (wrapping)
   - If no cursor: Scan last 30 days of workouts, find last matching template
   - If no history: Return first template in list

3. **Cursor Updates**:
   - Firestore trigger `onWorkoutCreatedUpdateRoutineCursor` automatically updates cursor
   - Only updates if workout has `source_routine_id` matching active routine

## Backend Endpoints

| Endpoint | Purpose |
|----------|---------|
| `getNextWorkout` | Get next template from active routine |
| `getPlanningContext` | Composite read: user, routine, templates, next workout |
| `createTemplateFromPlan` | Convert session_plan card to template |
| `patchTemplate` | Update template (name, description, exercises) |
| `patchRoutine` | Update routine (name, description, frequency, template_ids) |
| `onWorkoutCreatedUpdateRoutineCursor` | Trigger: Update routine cursor on workout completion |

## Agent Tools

| Tool | Purpose |
|------|---------|
| `tool_get_planning_context` | Full planning context in one call |
| `tool_get_next_workout` | Get next workout from routine |
| `tool_get_template` | Get specific template details |
| `tool_save_workout_as_template` | Save plan as new or update existing template |

### Agent Behavior

**Routine-Driven Planning (Primary)**:
```
User: "next workout" or "today's workout"
1. Agent calls tool_get_next_workout
2. If hasActiveRoutine=true, uses returned template
3. Converts template to tool_propose_workout format
4. Publishes plan
```

**Create From Scratch (Fallback)**:
```
User has no routine OR requests something new
1. Agent searches exercises
2. Builds plan from scratch
3. Publishes plan
```

## iOS UI Components

### Canvas Cards
- `RoutineSummaryCard`: Multi-day routine draft anchor card
  - Displays routine name, frequency, description
  - Lists all workout days with duration/exercise count
  - Actions: Save Routine, Dismiss, Regenerate

### Routines Tab
- `RoutinesListView`: List with active routine highlight
- `RoutineDetailView`: Shows workouts in order, "NEXT" indicator
- `RoutineEditView`: Create/edit name, description, frequency
- `TemplatePickerView`: Select and reorder templates

### Templates Tab
- `TemplatesListView`: Template library with analytics
- `TemplateDetailView`: Full editor with expandable exercises
- Inline set editing (weight, reps, RIR)

## Data Flow

```
User creates routine → Selects templates → Sets active
                                              ↓
User requests "next workout" → Agent calls getNextWorkout
                                              ↓
                              Template returned → Plan proposed
                                              ↓
User accepts plan → startActiveWorkout (with source_routine_id)
                                              ↓
User completes workout → completeActiveWorkout
                                              ↓
Trigger fires → Updates routine cursor → Next workout advances
```

## Validation

Canvas constraints enforced:
- Reps: 1-30
- RIR: 0-5
- Weight: nullable (for bodyweight exercises)

## Files Changed

### Backend (Firebase Functions)
- `routines/get-next-workout.js` - New
- `templates/create-template-from-plan.js` - New
- `templates/patch-template.js` - New
- `routines/patch-routine.js` - New
- `agents/get-planning-context.js` - New
- `triggers/workout-routine-cursor.js` - New
- `active_workout/start-active-workout.js` - Modified
- `active_workout/complete-active-workout.js` - Modified
- `templates/delete-template.js` - Fixed

### Agent (Python ADK)
- `app/libs/tools_canvas/client.py` - 10 new methods
- `app/unified_agent.py` - 4 new tools, updated prompt

### iOS (Swift)
- `UI/Routines/RoutinesListView.swift` - New
- `UI/Routines/RoutineDetailView.swift` - New
- `UI/Routines/RoutineEditView.swift` - New
- `UI/Templates/TemplatesListView.swift` - New
- `UI/Templates/TemplateDetailView.swift` - New
- `UI/Canvas/Cards/RoutineSummaryCard.swift` - New
- `UI/Canvas/Models.swift` - Added routine_summary types
- `UI/Canvas/CanvasGridView.swift` - Added routing for RoutineSummaryCard
- `ViewModels/RoutinesViewModel.swift` - New
- `Views/MainTabsView.swift` - Modified
- `Views/CanvasScreen.swift` - Added routine action handlers
- `Models/Routine.swift` - Modified (cursor fields)

## Testing Checklist

- [ ] Create routine with 2+ templates
- [ ] Set routine as active
- [ ] Request "next workout" from agent
- [ ] Verify correct template is used
- [ ] Accept plan and start workout
- [ ] Complete workout
- [ ] Request "next workout" again
- [ ] Verify rotation advanced
- [ ] Edit template (change sets/reps)
- [ ] Verify edits persist
- [ ] Delete template from routine
- [ ] Verify routine cleanup works
