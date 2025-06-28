# Firebase Functions - Myon Fitness App

Clean, domain-organized Firebase Functions for AI agent integration.

## Structure

```
functions/
├── user/                 # User operations (2 functions)
│   ├── get-user.js      # Get user profile with fitness context
│   └── update-user.js   # Update user preferences/settings
├── workouts/            # Workout operations (2 functions - read only)
│   ├── get-user-workouts.js  # Get workout history with analytics
│   └── get-workout.js   # Get specific workout details
├── templates/           # Template operations (5 functions)
│   ├── get-user-templates.js  # Get all user templates
│   ├── get-template.js  # Get specific template
│   ├── create-template.js     # Create template
│   ├── update-template.js     # Update existing template
│   └── delete-template.js     # Delete template (cleans routines)
├── routines/            # Routine operations (7 functions)
│   ├── get-user-routines.js   # Get all user routines
│   ├── get-routine.js   # Get specific routine
│   ├── create-routine.js      # Create weekly/monthly routine
│   ├── update-routine.js      # Update existing routine
│   ├── delete-routine.js      # Delete routine (clears active)
│   ├── get-active-routine.js  # Get user's active routine
│   └── set-active-routine.js  # Set active routine
├── exercises/           # Exercise operations (3 functions)
│   ├── get-exercises.js # Get all exercises
│   ├── get-exercise.js  # Get specific exercise
│   └── search-exercises.js    # Search with filters
├── triggers/            # Firestore triggers (3 functions)
│   └── muscle-volume-calculations.js  # Auto-calculate analytics
├── auth/               # Authentication middleware
│   └── middleware.js   # Dual auth (Firebase + API Keys)
├── utils/              # Shared utilities
│   └── firestore-helper.js    # Database operations
├── health/             # Health check
│   └── health.js       # Simple health endpoint
└── index.js           # Function exports
```

## Implemented Functions (23 total)

### ✅ User Operations (2)
- `getUser` - Get user profile with fitness context
- `updateUser` - Update user preferences/goals

### ✅ Workout Operations (2 - Read Only)  
- `getUserWorkouts` - Get workout history with analytics
- `getWorkout` - Get specific workout with metrics

**Note**: Workout creation/update/delete are deliberately scoped out for AI agents (read-only access)

### ✅ Template Operations (5)
- `getUserTemplates` - Get all user templates
- `getTemplate` - Get specific template
- `createTemplate` - Create template
- `updateTemplate` - Update existing template
- `deleteTemplate` - Delete template with cleanup

### ✅ Routine Operations (7)
- `getUserRoutines` - Get all user routines
- `getRoutine` - Get specific routine
- `createRoutine` - Create weekly/monthly routine
- `updateRoutine` - Update existing routine
- `deleteRoutine` - Delete routine with cleanup
- `getActiveRoutine` - Get user's active routine
- `setActiveRoutine` - Set active routine

### ✅ Exercise Operations (3)
- `getExercises` - Get all exercises
- `getExercise` - Get specific exercise
- `searchExercises` - Search with filters

### ✅ Firestore Triggers (3)
- `onTemplateCreated` - Auto-calculate muscle volume analytics when AI creates templates
- `onTemplateUpdated` - Recalculate analytics when AI updates templates
- `onWorkoutCreated` - Calculate workout analytics when AI creates workouts

## Muscle Volume Calculations

The Firestore triggers automatically calculate muscle volume analytics when AI agents create or update templates/workouts. This mirrors the Swift app's `StimulusCalculator` and `ActiveWorkoutManager` logic:

- **Template Analytics**: Projected volume, sets, and reps per muscle/muscle group
- **Workout Analytics**: Actual volume, sets, and reps based on completed sets
- **Distribution Logic**: 
  - Muscle categories: Even distribution
  - Individual muscles: Uses contribution percentages from exercise data

The triggers only activate for documents created without existing analytics (i.e., by AI agents), preventing conflicts with the Swift app's calculations.

## Authentication

Dual authentication system:
- **Firebase Auth**: Bearer tokens for user apps
- **API Keys**: For AI agents (set in `VALID_API_KEYS` env var)

## Base URL
```
https://us-central1-myon-53d85.cloudfunctions.net/
```

## Deployment

```bash
firebase deploy --only functions
``` 