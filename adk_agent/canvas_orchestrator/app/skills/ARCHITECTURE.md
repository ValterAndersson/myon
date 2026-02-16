# Skills — Module Architecture

Pure logic modules shared across all Shell Agent lanes. Skills contain the "shared brain" — domain logic that is independent of routing or LLM interaction.

## File Inventory

| File | Lane Usage | Purpose |
|------|-----------|---------|
| `copilot_skills.py` | FAST | Pattern-matched responses: set completion ("done" → `completeCurrentSet`), shorthand logging ("8 @ 100"), navigation ("next set"), workout control. No LLM needed. |
| `coach_skills.py` | SLOW (read tools) | Analytics and user data retrieval: `get_training_context`, `get_user_profile`, `search_exercises`, `get_exercise_details`, `get_muscle_group_progress`, `get_muscle_progress`, `get_exercise_progress`, `query_training_sets`, `get_training_analysis` |
| `planner_skills.py` | SLOW (write tools) | Canvas write operations: `propose_workout`, `propose_routine`, `propose_routine_update`, `propose_template_update`, `get_planning_context` |
| `workout_skills.py` | SLOW (workout tools) | Active workout operations: `get_workout_state_formatted` (Workout Brief builder), `log_set`, `add_exercise`, `prescribe_set`, `swap_exercise`, `complete_workout`. Called by workout tool wrappers in `shell/tools.py`. |
| `gated_planner.py` | — (deprecated) | Previously wrapped planner skills with Safety Gate confirmation. Now bypassed — cards have accept/dismiss buttons. |
| `progression_skills.py` | WORKER | Post-workout progression analysis |
| `__init__.py` | — | Module exports |

## Lane → Skill Mapping

| Lane | Skills Used | Model |
|------|------------|-------|
| FAST | `copilot_skills` | None (pattern matching) |
| FUNCTIONAL | `copilot_skills` + domain handlers | Flash |
| SLOW | `coach_skills` (read) + `planner_skills` (write) + `workout_skills` (workout mode) | Flash |
| WORKER | `progression_skills` | Flash |

## Key Pattern: Skills vs Tools

Skills are plain Python functions. Tools (`shell/tools.py`) wrap skills with:
1. ADK `FunctionTool` compatibility
2. Context injection from `ContextVar` (user_id, canvas_id, workout_mode)
3. LLM-safe function signatures (no user_id parameter)

```
LLM calls tool_propose_workout(title, exercises, ...)
    → tools.py retrieves ctx.user_id from ContextVar
    → calls planner_skills.propose_workout(canvas_id, user_id, ...)
    → planner_skills calls Firebase Function /proposeCards

LLM calls tool_log_set(exercise_instance_id, set_id, reps, weight_kg)
    → tools.py checks ctx.workout_mode (returns error if false)
    → tools.py retrieves ctx.user_id, ctx.active_workout_id
    → calls workout_skills.log_set(user_id, workout_id, ...)
    → workout_skills calls Firebase Function /logSet via client.log_set()
```

## workout_skills.py — Design Notes

### Workout Brief (`get_workout_state_formatted`)

Called by `agent_engine_app.py` once per Slow Lane request (not per LLM turn). Builds a compact text representation of the active workout state:

- Parallel fetch with `ThreadPoolExecutor(max_workers=3)`: `getActiveWorkout` + `getAnalysisSummary(daily_brief)` + `getExerciseSummary` (after workout response resolves to identify current exercise)
- Formats as `[WORKOUT BRIEF]` text (~1350 tokens)

### Firebase endpoint mapping

| Skill Function | Client Method | Firebase Endpoint | Auth Pattern |
|----------------|---------------|-------------------|--------------|
| `log_set()` | `client.log_set()` | `logSet` | `requireFlexibleAuth` — X-User-Id header |
| `add_exercise()` | `client.add_exercise()` | `addExercise` | `requireFlexibleAuth` — X-User-Id header |
| `prescribe_set()` | `client.patch_active_workout()` | `patchActiveWorkout` | `requireFlexibleAuth` — X-User-Id header |
| `swap_exercise()` | `client.swap_exercise()` | `swapExercise` | `requireFlexibleAuth` — X-User-Id header |
| `complete_workout()` | `client.complete_active_workout()` | `completeActiveWorkout` | `requireFlexibleAuth` — X-User-Id header |
| brief: workout | `client.get_active_workout()` | `getActiveWorkout` | `requireFlexibleAuth` — X-User-Id header |
| brief: history | `client.get_exercise_summary()` | `getExerciseSummary` | `withApiKey` — userId in body |
| brief: readiness | `client.get_analysis_summary()` | `getAnalysisSummary` | `requireFlexibleAuth` — userId in body |

### copilot_skills.py — Fast Lane endpoints

| Skill Function | Firebase Endpoint | Notes |
|----------------|-------------------|-------|
| `log_set()` | `completeCurrentSet` | Accepts only `workout_id`, discovers target set server-side |
| `get_next_set()` | `getActiveWorkout` | Parses workout exercises array to find first planned set |
| `log_set_shorthand()` | `logSet` | Sends explicit reps/weight via `action: log_explicit` |

### Field naming

Active workout endpoints use **snake_case** in request bodies (`workout_id`, `exercise_instance_id`, `set_id`). The `logSet` endpoint requires a nested `values: {weight, reps, rir}` object per `LogSetSchemaV2` in `validators.js`.

## Cross-References

- Tool wrappers: `app/shell/tools.py`
- Router: `app/shell/router.py` (lane selection)
- Firebase client: `app/libs/tools_canvas/client.py`
- Firebase endpoints called: `proposeCards`, `bootstrapCanvas`, `getPlanningContext`, `searchExercises`, `logSet`, `completeCurrentSet`, `swapExercise`, `completeActiveWorkout`, `getActiveWorkout`, etc.
