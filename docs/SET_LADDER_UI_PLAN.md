# Set Ladder UI Architecture Plan

*Created: December 19, 2024*
*Revised: December 19, 2024 — Spreadsheet Grid Direction*
*Status: Planned, ready for implementation*

---

## Design Principles (Non-negotiable)

| Principle | Rationale |
|-----------|-----------|
| **Density + Scanability** | Lifters want the familiarity and information density of a spreadsheet |
| **Bulk Edits Default** | Working sets are usually identical—editing one should update all by default |
| **Large Tap Targets** | Mobile gym reality punishes small targets and repeated modal edits |
| **No Modal Loops** | "Open, edit, save, close" loops waste taps; use inline selection + dock |

---

## 1. Grid Layout Specification

### Table Structure

Sets render as a **true data grid** with aligned columns:

```
┌──────────┬────────┬──────┬─────┬──────┐
│ Type/Set │ Weight │ Reps │ RIR │ Done │
├──────────┼────────┼──────┼─────┼──────┤
│ WU       │ 30kg   │  10  │  —  │  ○   │
│ WU       │ 45kg   │   6  │  —  │  ○   │
├──────────┼────────┼──────┼─────┼──────┤
│ 1        │ 60kg   │   8  │  3  │  ○   │
│ 2        │ 60kg   │   8  │  2  │  ○   │
│ 3        │ 60kg   │   8  │  2  │  ○   │
│ 4        │ 60kg   │   8  │  1  │  ○   │
└──────────┴────────┴──────┴─────┴──────┘
```

### Visual Rules

- **Plain table text** — no pills, no chips, no badges
- **Tabular digits** (`.monospacedDigit()`) for aligned numbers
- **Consistent column widths** — avoid jitter on value changes
- **Clear grid lines** — subtle separators (light gray or divider color)
- **Warm-up rows visually subdued** — lighter text weight or secondary color

### Sizing Requirements (Explicit)

| Element | Minimum | Preferred |
|---------|---------|-----------|
| Tap target | 44×44pt | 48–56pt |
| Row height | 60pt | 60–72pt |
| Cell padding | 8pt | 12pt horizontal |

---

## 2. Selection + Dock Editing Model

### Selection Flow

1. **Tap a cell** → cell becomes selected
   - Visual: highlight background + cursor/outline
   - Only ONE cell selected at a time (single selection mode)
   
2. **Editing dock appears** inline:
   - Position: above keyboard when keyboard visible, otherwise at bottom
   - Contains: value control (stepper or picker) + scope toggle + confirm
   
3. **Edit completes** when:
   - User taps outside the cell
   - User taps another cell (auto-applies + moves selection)
   - User dismisses keyboard

### Dock Content by Field

| Field | Dock Control |
|-------|--------------|
| **Weight** | `−2.5` `[value]` `+2.5` + direct input |
| **Reps** | `−1` `[value]` `+1` + direct input |
| **RIR** | Segmented picker `0 1 2 3 4 5` |
| **Done** | Checkmark tap (no dock needed) |

### No Modal Loop

❌ **Old pattern:** Tap → Sheet opens → Edit → Save → Sheet closes  
✅ **New pattern:** Tap → Selection + dock → Edit in place → Tap elsewhere to confirm

---

## 3. Bulk Scope System (First-Class)

### Scope Options

Every edit to **Weight / Reps / RIR** applies with a scope:

| Scope | Description | When to Use |
|-------|-------------|-------------|
| **All working sets** | Updates every working set row | Default for most edits |
| **Remaining working sets** | Updates current + all following | Mid-workout adjustments |
| **Selected sets only** | Updates only explicitly selected rows | Per-set overrides |

### Scope Selector

- Small segmented control in the editing dock
- Default: "All working"
- Persists within editing session (resets when exercise collapses)

### Visual Feedback

When "All working" is active and user edits Weight:
- All working set rows flash/highlight briefly to confirm bulk update
- Changed values animate to new value

---

## 4. Base Prescription + Override Model

### Linked by Default

Working sets **start linked** to a base prescription:

```swift
struct BasePrescription {
    var weight: Double
    var reps: Int
    var rir: Int  // Target RIR for final working set
}
```

When base values change → all **linked** working rows update automatically.

### Breaking the Link (Override)

To change ONE set differently:

1. Select the cell
2. Tap "Override this set" in dock (or long-press cell)
3. Cell gets subtle "override" indicator (small dot or different border)
4. That row is now independent of base prescription

### Override Visual

- Overridden rows: small indicator dot in margin
- Tooltip on dot: "This set has custom values"
- Menu option: "Reset to base prescription"

---

## 5. Warm-up Ramp Handling

### Generation

- **One-tap action:** "Generate warm-up ramp" near exercise header
- Agent or algorithm determines ramp based on:
  - Working weight
  - Exercise type (compound vs isolation)
  - User preference (2 vs 3 warm-up sets)

### Display Options

| State | Display |
|-------|---------|
| **Collapsed** | `Warm-up ramp: 2 sets` (one line, tappable to expand) |
| **Expanded** | Individual WU rows in grid, visually subdued |

### Editing Warm-ups

- Per-row editable (fine—only 2-3 rows)
- No bulk scope for warm-ups (they're supposed to be different)
- "Regenerate ramp" action resets to algorithm defaults

---

## 6. Row Operations

### Delete Row

| Method | Behavior |
|--------|----------|
| **Swipe left** | Row deletes with undo toast (5s window) |
| **Row menu** | Fallback for non-swipe users: tap `⋯` → Delete |

### Reorder Rows

**Dedicated mode only** (not inline drag):

1. Long-press any row → enters reorder mode
2. All rows show drag handles on left
3. Row spacing increases slightly for easier targets
4. Drag to reorder
5. Tap "Done" button to exit reorder mode

### Add Set

**Single control** at bottom of set grid:

```
[ + Add Set ]
```

Tap → action sheet:
- Add warm-up set
- Add working set
- Add backoff set (future)

**No scattered icons under each row.**

---

## 7. Agent Controls Placement

### Design Rule

> Complex coach actions stay **near the exercise header**, not inside the grid.

### Entry Point

Single "Coach / Adjust" button beside exercise name:

```
┌─────────────────────────────────────────────┐
│ 🏋️ Incline Barbell Press       [Coach ▾]   │
└─────────────────────────────────────────────┘
```

### Actions Available

Tap "Coach" → dropdown or sheet with:

- **Swap movement** — find alternative exercise
- **Make shorter** — reduce sets
- **Make harder** — increase intensity/volume
- **Change scheme** — different rep/set structure
- **Regenerate warm-ups** — recalculate ramp
- **Adjust remaining sets** — bulk modify based on fatigue

### Why Not Inline

- Inline action buttons compete with grid tap targets
- Multiple buttons per exercise = visual clutter
- Coach actions are less frequent than data edits

---

## 8. Planning vs Active Mode

### Planning Mode

| Aspect | Behavior |
|--------|----------|
| **Default view** | Compact summary per exercise |
| **Expand** | One exercise at a time expands to full grid |
| **Purpose** | Review/edit plan before starting |

Summary format:
```
Incline Barbell Press
WU: 2 set ramp · Work: 4 × 8 @ RIR 2 · 60kg target
```

### Active Workout Mode

| Aspect | Behavior |
|--------|----------|
| **Default view** | Grid always visible for current exercise |
| **Current set** | Highlighted row (bold/accent border) |
| **Completion** | Tap "Done" column → logs actual values |
| **Editing** | Same selection + dock model as planning |

### Continuity

The **same grid component** and **same editing model** work in both modes:
- Planning: edit targets before workout
- Active: edit actuals during workout (with target reference)

---

## 9. Data Model

### PlanSet (aligned with Firestore)

```swift
struct PlanSet: Identifiable, Equatable, Codable {
    let id: String
    var type: SetType          // .warmup, .working
    var reps: Int
    var weight: Double?        // kg
    var rir: Int?              // nil for warm-ups
    var isLinkedToBase: Bool   // true = uses base prescription
    
    // Active workout fields
    var isCompleted: Bool?
    var actualReps: Int?
    var actualWeight: Double?
    var actualRir: Int?
}

enum SetType: String, Codable {
    case warmup = "warmup"
    case working = "working"
    case backoff = "backoff"
}
```

### PlanExercise

```swift
struct PlanExercise: Identifiable, Equatable, Codable {
    let id: String
    let exerciseId: String?
    let name: String
    var sets: [PlanSet]
    var basePrescription: BasePrescription?  // For linked working sets
    let primaryMuscles: [String]?
    let equipment: String?
    var coachNote: String?
    var warmupCollapsed: Bool               // UI state
    
    // Computed
    var warmupSets: [PlanSet] { sets.filter { $0.type == .warmup } }
    var workingSets: [PlanSet] { sets.filter { $0.type == .working } }
}

struct BasePrescription: Equatable, Codable {
    var weight: Double
    var reps: Int
    var targetRir: Int  // RIR for final working set
}
```

---

## 10. Implementation Phases

### Phase 1: Grid + Selection Model

- [ ] Create `SetGridView` component with table layout
- [ ] Implement cell selection state and highlight
- [ ] Create `EditingDock` component (bottom bar)
- [ ] Wire up Weight/Reps/RIR editing via dock
- [ ] Implement tap-outside-to-confirm behavior

### Phase 2: Bulk Scope + Base Prescription

- [ ] Add scope selector to EditingDock
- [ ] Implement "All working sets" bulk update
- [ ] Add `BasePrescription` to data model
- [ ] Implement linked/override state per set
- [ ] Add override indicator UI

### Phase 3: Row Operations

- [ ] Swipe-to-delete with undo toast
- [ ] Long-press → reorder mode
- [ ] "Add Set" action sheet
- [ ] Warm-up collapse/expand

### Phase 4: Active Workout Integration

- [ ] Current set highlighting
- [ ] Completion tap in Done column
- [ ] Actual vs target display
- [ ] Timer integration

---

## 11. Related Files

- `MYON2/MYON2/UI/Canvas/Cards/SessionPlanCard.swift` — Card container
- `MYON2/MYON2/UI/Canvas/SetGridView.swift` — Grid component (to create)
- `MYON2/MYON2/UI/Canvas/EditingDock.swift` — Bottom editor (to create)
- `MYON2/MYON2/UI/Canvas/Models.swift` — PlanExercise, PlanSet models
- `MYON2/MYON2/Services/CanvasDTOs.swift` — JSON parsing

---

## Appendix: Tap Target Checklist

Before shipping any set-related UI:

- [ ] Every interactive cell ≥ 44×44pt
- [ ] Numeric cells prefer 48–56pt width
- [ ] Row height ≥ 60pt
- [ ] Action labels not truncated
- [ ] Stepper buttons ≥ 44×44pt
- [ ] Works comfortably one-handed

---

*End of document*
