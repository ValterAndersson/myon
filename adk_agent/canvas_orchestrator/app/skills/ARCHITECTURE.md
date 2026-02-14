# Skills — Module Architecture

Pure logic modules shared across all Shell Agent lanes. Skills contain the "shared brain" — domain logic that is independent of routing or LLM interaction.

## File Inventory

| File | Lane Usage | Purpose |
|------|-----------|---------|
| `copilot_skills.py` | FAST | Pattern-matched responses: set logging ("8 @ 100"), navigation ("done", "next set"), workout control. No LLM needed. |
| `coach_skills.py` | SLOW (read tools) | Analytics and user data retrieval: `get_training_context`, `get_user_profile`, `search_exercises`, `get_exercise_details`, `get_muscle_group_progress`, `get_muscle_progress`, `get_exercise_progress`, `query_training_sets`, `get_training_analysis` |
| `planner_skills.py` | SLOW (write tools) | Canvas write operations: `propose_workout`, `propose_routine`, `propose_routine_update`, `propose_template_update`, `get_planning_context` |
| `gated_planner.py` | — (deprecated) | Previously wrapped planner skills with Safety Gate confirmation. Now bypassed — cards have accept/dismiss buttons. |
| `progression_skills.py` | WORKER | Post-workout progression analysis |
| `__init__.py` | — | Module exports |

## Lane → Skill Mapping

| Lane | Skills Used | Model |
|------|------------|-------|
| FAST | `copilot_skills` | None (pattern matching) |
| FUNCTIONAL | `copilot_skills` + domain handlers | Flash |
| SLOW | `coach_skills` (read) + `planner_skills` (write) | Flash |
| WORKER | `progression_skills` | Flash |

## Key Pattern: Skills vs Tools

Skills are plain Python functions. Tools (`shell/tools.py`) wrap skills with:
1. ADK `FunctionTool` compatibility
2. Context injection from `ContextVar` (user_id, canvas_id)
3. LLM-safe function signatures (no user_id parameter)

```
LLM calls tool_propose_workout(title, exercises, ...)
    → tools.py retrieves ctx.user_id from ContextVar
    → calls planner_skills.propose_workout(canvas_id, user_id, ...)
    → planner_skills calls Firebase Function /proposeCards
```

## Cross-References

- Tool wrappers: `app/shell/tools.py`
- Router: `app/shell/router.py` (lane selection)
- Firebase endpoints called: `proposeCards`, `bootstrapCanvas`, `getPlanningContext`, `searchExercises`, etc.
