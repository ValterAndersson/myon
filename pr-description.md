This update introduces a weekly analytics engine and dashboard integration.

**Backend**
- New `weekly-analytics.js` trigger aggregates workout metrics each time a workout is completed or deleted.
- Weekly stats are stored under `users/{userId}/analytics/weekly_stats/{weekId}`.
- `index.js` exports the new trigger functions.

**iOS App**
- Added `WeeklyStats` model plus `AnalyticsRepository` and `WeeklyStatsViewModel` for loading stats.
- Moved `StatRow` into `DashboardComponents.swift` and updated `HomeDashboardView` to display weekly totals.

**Documentation**
- `README.md` now lists the new trigger file and documents the weekly stats collection schema.

Run `make test` in `adk_agent/strengthos-v2` to execute unit and integration tests.
