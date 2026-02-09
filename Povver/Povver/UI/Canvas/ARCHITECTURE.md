# Canvas UI — Module Architecture

The Canvas is the primary AI interaction surface. It displays agent-proposed cards organized in a grid layout, handles agent streaming visualization, and provides card-level actions (accept, reject, start workout, swap exercise).

## File Inventory

### Core Layout

| File | Purpose |
|------|---------|
| `Models.swift` | Canvas card models: `CanvasCardModel`, `CardType`, `CardLane`, `CardStatus`, `CanvasCardData` |
| `CanvasGridView.swift` | Masonry grid layout for cards |
| `CardContainer.swift` | Universal card wrapper with header, actions, and status badge |
| `CardHeader.swift` | Card title, subtitle, status indicator |
| `CardActionEnvironment.swift` | Environment object for propagating card action handlers |
| `UpNextRailView.swift` | Horizontal rail showing up-next card queue |
| `PinnedRailView.swift` | Pinned cards rail |
| `WorkoutRailView.swift` | Horizontal exercise rail for workout cards |
| `WorkspaceTimelineView.swift` | Timeline of workspace events |
| `ThinkingBubble.swift` | Agent thinking/tool execution visualization |

### Cards (`Cards/`)

| File | Card Type | Purpose |
|------|-----------|---------|
| `SessionPlanCard.swift` | `session_plan` | Workout plan with exercises and sets grid |
| `RoutineSummaryCard.swift` | `routine_summary` | Multi-day routine overview (anchor card) |
| `RoutineOverviewCard.swift` | `routine_overview` | Routine summary display |
| `VisualizationCard.swift` | `visualization` | Charts (line, bar, table) |
| `AnalysisSummaryCard.swift` | `analysis_summary` | Progress analysis results |
| `ClarifyQuestionsCard.swift` | `clarify_questions` | Agent clarification questions |
| `AgentStreamCard.swift` | `agent_stream` | Live streaming agent output |
| `AgentMessageCard.swift` | — | Agent message display |
| `ChatCard.swift` | `chat` | Chat message card |
| `SuggestionCard.swift` | `suggestion` | Quick action suggestions |
| `SmallContentCard.swift` | `text` | Simple text content |
| `ListCardWithExpandableOptions.swift` | `list_card` | Generic expandable list |
| `VisualCard.swift` | — | Visual content card |
| `ProposalGroupHeader.swift` | — | Accept-all / Reject-all group actions |
| `SetGridView.swift` | — | Exercise set editing grid (used within cards) |
| `ExerciseDetailSheet.swift` | — | Exercise detail modal |

### Shared Card Components (`Cards/Shared/`)

| File | Purpose |
|------|---------|
| `ExerciseRowView.swift` | Single exercise row in a workout card |
| `ExerciseSwapSheet.swift` | Exercise swap modal |
| `ExerciseActionsRow.swift` | Per-exercise action buttons |
| `IterationActionsRow.swift` | Iteration-level action buttons |

### Charts (`Charts/`)

| File | Purpose |
|------|---------|
| `LineChartView.swift` | Line chart for trends |
| `BarChartView.swift` | Bar chart for comparisons |
| `RankedTableView.swift` | Ranked data table |
| `VisualizationModels.swift` | Chart data models |

## Card Type → View Mapping

The `CardContainer` dispatches to the correct card view based on `CanvasCardModel.type`:

```
session_plan      → SessionPlanCard
routine_summary   → RoutineSummaryCard
routine_overview  → RoutineOverviewCard
visualization     → VisualizationCard
analysis_summary  → AnalysisSummaryCard
clarify_questions → ClarifyQuestionsCard
agent_stream      → AgentStreamCard
suggestion        → SuggestionCard
text              → SmallContentCard
list_card         → ListCardWithExpandableOptions
```

## Cross-References

- Card type schemas: `firebase_functions/functions/canvas/schemas/card_types/`
- Canvas ViewModel: `Povver/Povver/ViewModels/CanvasViewModel.swift`
- Canvas Screen: `Povver/Povver/Views/CanvasScreen.swift`
- Design tokens: `Povver/Povver/UI/DesignSystem/Tokens.swift`
