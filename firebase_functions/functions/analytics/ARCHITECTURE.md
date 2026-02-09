# Analytics — Module Architecture

Analytics pipeline for computing, storing, and serving training analytics. Handles per-exercise and per-muscle progression tracking, weekly rollups, and compaction.

## File Inventory

| File | Purpose |
|------|---------|
| `controller.js` | `runAnalyticsForUser` — Orchestrates full analytics rebuild for a user (backfill entry point) |
| `worker.js` | Analytics computation worker: processes workouts and builds series data |
| `get-features.js` | `getAnalyticsFeatures` — Compact analytics features for agent consumption (modes: weekly, week, range, daily) |
| `compaction.js` | `analyticsCompactionScheduled`, `compactAnalyticsForUser` — Compacts `points_by_day` older than 90 days into `weeks_by_start` to keep storage sublinear |
| `publish-weekly-job.js` | `publishWeeklyJob` — Proposes weekly summary cards to the canvas |
| `recalculate-weekly-for-user.js` | `recalculateWeeklyForUser` — Recalculates `weekly_stats` for a user from workout history |

## Pipeline Flow

```
Workout completed
    → Trigger: onWorkoutCompleted (triggers/weekly-analytics.js)
    → Writes to: analytics_series_exercise/{id}, analytics_series_muscle/{id}
    → Writes to: analytics_rollups/{week}, weekly_stats/{week}

Scheduled compaction (daily)
    → analyticsCompactionScheduled
    → Compacts points_by_day → weeks_by_start for data > 90 days old

Agent queries
    → getAnalyticsFeatures (modes: weekly, week, range, daily)
    → Reads: analytics_series_*, analytics_rollups, weekly_stats
```

## Data Collections

| Collection | Purpose |
|------------|---------|
| `users/{uid}/analytics_series_exercise/{id}` | Per-exercise weekly progression (e1RM, volume) |
| `users/{uid}/analytics_series_muscle/{id}` | Per-muscle weekly volume and hard sets |
| `users/{uid}/analytics_rollups/{week}` | Weekly totals across all muscles |
| `users/{uid}/weekly_stats/{week}` | Legacy weekly aggregates (still updated) |
| `users/{uid}/analytics_state/current` | Watermarks for incremental processing |

## Cross-References

- Triggers: `triggers/weekly-analytics.js` (data population)
- Utils: `utils/analytics-writes.js`, `utils/analytics-calculator.js`
- Training v2 (newer): `training/` directory provides token-safe alternatives
- Agent tools: `adk_agent/canvas_orchestrator/app/shell/tools.py`
