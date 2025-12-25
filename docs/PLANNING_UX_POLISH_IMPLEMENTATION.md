# Planning Mode UX Polish - Implementation Tracker

*Created: December 22, 2024*
*Status: In Progress*

---

## Implementation Phases

### Phase 2: Set Grid Correctness (BLOCKER) ✅ COMPLETE
- [x] Remove pendingValue caching - use table as single source of truth
- [x] Add haptic feedback on selection and value changes
- [x] Ensure zero desyncs between grid and editor
- [x] Add duplicate set swipe action

### Phase 0: Token Architecture ✅ COMPLETE
- [x] Add Surface.focusedRow with light/dark values
- [x] Add Surface.editingRow with light/dark values
- [x] Add Separator.hairline token
- [x] Add Color extension for light/dark init

### Phase 1: Progress State Architecture ✅ COMPLETE
- [x] Create AgentProgressState.swift
- [x] Integrate in CanvasViewModel (progressState property + advance/complete calls)
- [x] Hook up tool events to advance progress monotonically

### Phase 3: Editing Attached to Grid ✅ COMPLETE (via Phase 2)
- [x] Editor appears as inline row directly under selected set
- [x] Shows scope with affected count ("Applying to: 4 sets")

### Phase 4: Bulk Edit Guardrails ✅ PARTIAL
- [x] Show "Applying to: X sets" in editor
- [ ] Undo toast for every bulk mutation (requires further work)
- [x] Scope selector inside editor row

### Phase 5: Skeleton Loading ✅ PARTIAL
- [x] Create PlanCardSkeleton with pulsing (not shimmer)
- [ ] Integrate in timeline/canvas screen (requires CanvasScreen changes)
- [ ] Remove full-screen overlay during agent work

### Phase 6: Hit Areas + Haptics
- [ ] Increase cell hit areas to 48pt minimum
- [ ] Add haptic feedback throughout
- [ ] Remove micro targets

### Phase 7: Coach Narrative ✅ COMPLETE
- [x] Add coach caption to plan card header
- [x] No italics, plain secondary text
- [x] One line max

### Phase 8: Restrained Quick Prompts ✅ COMPLETE
- [x] Max 2-3 text buttons (Shorter, Harder visible)
- [x] Coach menu for less common actions (Swap Focus, Regenerate, Balance Volume, Equipment Limits)
- [x] Clean hierarchy with Spacer() to left-align actions

---

## Files Modified

| File | Phase | Status |
|------|-------|--------|
| `SetGridView.swift` | 2, 3, 4, 6 | 🔄 |
| `Tokens.swift` | 0 | ⏳ |
| `AgentProgressState.swift` | 1 | ⏳ |
| `SessionPlanCard.swift` | 7 | ⏳ |
| `CanvasViewModel.swift` | 1 | ⏳ |
| `CanvasScreen.swift` | 5, 8 | ⏳ |
| `PlanCardSkeleton.swift` | 5 | ⏳ |

---

## Acceptance Criteria Checklist

### Grid Correctness
- [ ] Table value and editor value ALWAYS identical
- [ ] Bulk change NEVER modifies warmups unless explicit
- [ ] Duplicate set available via swipe leading

### Visual Language
- [ ] Focused row unmissable in light AND dark mode
- [ ] Selection styling independent of brand color

### Progress
- [ ] Progress never regresses
- [ ] Unknown tools fall back gracefully

### Editing UX
- [ ] Editor is part of the grid (inline row)
- [ ] User knows target, field, scope before tapping

### Bulk Edits
- [ ] Always reversible via undo
- [ ] Scope visible at moment of change

### Loading
- [ ] Skeleton appears immediately
- [ ] No full-screen overlay during work
- [ ] Subtle pulse, not shimmer

### Usability
- [ ] Operable with sweaty fingers
- [ ] No micro targets
- [ ] Haptic feedback on interactions

---

*End of document*
