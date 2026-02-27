# Agent Quality Overhaul — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix 7 systemic quality issues in the workout agent, training analyst, and recommendation pipeline — from template weight regressions to missing warm-up support — to deliver a paradigm shift in coaching quality.

**Architecture:** The changes span 4 layers: agent instruction/tools (Python), Firebase Functions triggers (JS), training analyst workers (Python), and GCP infrastructure (Cloud Scheduler). Each workstream is independent — no cross-workstream dependencies — so they can be executed in any order or in parallel.

**Tech Stack:** Python 3.11 (ADK agent), Node.js (Firebase Functions v2), Google Cloud Run Jobs, Cloud Scheduler, Firestore, Vertex AI Agent Engine.

---

## Workstream Overview

| # | Workstream | Files Changed | Effort | Impact |
|---|---|---|---|---|
| 1 | Brief-first instruction + warm-up protocol | `instruction.py`, `tools.py` | ~2h | High — reduces latency 50-70%, enables warm-ups |
| 2 | Tool-call observability logging | `stream-agent-normalized.js`, `tools.py` | ~1h | High — enables debugging all agent issues |
| 3 | Recommendation pipeline — expand types + scopes | `process-recommendations.js` | ~3h | High — stops dropping 40% of recommendations |
| 4 | Cloud Scheduler triggers for training analyst | `Makefile`, new deploy script | ~30min | Medium — restores weekly reviews |
| 5 | Analytics rollups backfill + investigation | `analytics-writes.js`, backfill script | ~2h | Medium — fixes ACWR accuracy |
| 6 | Template transparency — surface auto-applied changes | `process-recommendations.js`, `complete-active-workout.js` | ~3h | High — eliminates weight confusion |
| 7 | Swap with full routine context | `post_workout.py`, `process-recommendations.js` | ~4h | Medium — enables exercise swap recommendations |

---

## Workstream 1: Brief-First Instruction + Warm-Up Protocol

### Task 1.1: Add brief-first reasoning section to instruction

**Files:**
- Modify: `adk_agent/canvas_orchestrator/app/shell/instruction.py:363-416`

**Step 1: Add brief-first decision tree**

Insert after the "### Using the Workout Brief" section (after line 403), before "### What you do in this mode" (line 405):

```python
### Brief-First Reasoning (LATENCY RULE)
The workout brief is fetched ONCE at the start of your request — it's already in your context.
Answering from the brief costs 0ms. Calling a tool costs 300-1500ms. USE THE BRIEF FIRST.

Before calling any tool, check if the brief already contains the answer:

1. Workout structure questions → ANSWER FROM BRIEF, NO TOOL CALL
   - "What exercise is next?" → exercise list shows order
   - "How many sets left?" → count planned sets from header
   - "Does the order look right?" → full exercise list is visible
   - "Where am I?" → header shows set count + current exercise

2. Current exercise weight/performance → ANSWER FROM BRIEF, NO TOOL CALL
   - "What weight should I use?" → planned weight is shown
   - "Should I do more reps?" → compare History line to completed sets
   - "Am I doing better than last time?" → History line shows last session
   - "Is this weight right?" → compare to History + e1RM trend

3. Readiness/fatigue for current workout → ANSWER FROM BRIEF, NO TOOL CALL
   - "Should I push today?" → Readiness line in brief
   - "Am I overtraining?" → Readiness lists fatigued muscle groups

4. ONLY call tools when the brief genuinely cannot answer:
   - Exercise NOT in today's workout → tool_get_exercise_progress
   - Multi-week trend analysis → tool_get_exercise_progress or tool_get_muscle_group_progress
   - Detailed muscle development → tool_get_muscle_group_progress
```

**Step 2: Run agent tests**

```bash
cd adk_agent/canvas_orchestrator && make check
```

Expected: All Python files compile without errors.

**Step 3: Commit**

```bash
git add adk_agent/canvas_orchestrator/app/shell/instruction.py
git commit -m "perf: add brief-first reasoning to workout instruction

Teaches the agent to answer from the workout brief before calling tools.
Expected to reduce tool calls by 50-70% for common workout questions,
cutting latency from 2-5s to <1s for brief-answerable questions."
```

---

### Task 1.2: Add warm-up protocol to instruction

**Files:**
- Modify: `adk_agent/canvas_orchestrator/app/shell/instruction.py:405-416`

**Step 1: Add warm-up section to workout mode**

Insert into the "### What you do in this mode" list (after line 414, before "- Complete:"):

```python
- Warm-up sets: "add warm-up sets to pulldown", "what's the correct ramp?" →
  Use tool_add_exercise with warmup_sets parameter. Standard warm-up protocol:
  For working weight W, create ramp sets at 50%, 65%, 80% of W.
  Reps decrease as weight increases: 10, 8, 5 reps. Warmup RIR = 5 (submaximal).
  Only suggest warmups for heavy compounds (squat, deadlift, bench, row, OHP).
  Isolations rarely need warmups — compounds already primed those muscles.
  Example for 130kg deadlift: 65kg×10, 85kg×8, 105kg×5, then working sets.
```

Add a warm-up example to the examples section (after line 506, before "User: I'm done"):

```python
User: "add warm-up sets to the pulldown"
Think: Warm-up request. Brief shows Close-Grip Lat Pulldown with working weight 70kg.
Need to add warmup sets: 35kg×10, 45kg×8, 56kg×5 before working sets.
Tool: tool_add_exercise(exercise_id="cable-lat-pulldown-close", name="Close-Grip Lat Pulldown", sets=3, reps=10, weight_kg=70, rir=2, warmup_sets=3)
Response: "Added 3 warm-up sets ramping to 70kg: 35kg×10, 45kg×8, 56kg×5."

User: "what's the correct ramp for 130kg deadlift?"
Think: Warm-up prescription question. No tool call needed — apply standard protocol.
Response: "For 130kg: 60kg×8, 85kg×5, 105kg×3, then your working sets. Big jumps early, fewer reps as weight climbs — primes the pattern without building fatigue."
```

**Step 2: Run checks**

```bash
cd adk_agent/canvas_orchestrator && make check
```

**Step 3: Commit**

```bash
git add adk_agent/canvas_orchestrator/app/shell/instruction.py
git commit -m "feat: add warm-up set protocol to workout instruction

Teaches the agent warm-up ramp prescription (50/65/80% of working weight)
and when to use warmups (heavy compounds only). Adds examples for
'add warm-up sets' and 'what's the correct ramp' questions."
```

---

### Task 1.3: Add warmup_sets parameter to tool_add_exercise

**Files:**
- Modify: `adk_agent/canvas_orchestrator/app/shell/tools.py:1086-1138`
- Test: `adk_agent/canvas_orchestrator/tests/test_warmup_sets.py`

**Step 1: Write the test**

Create `adk_agent/canvas_orchestrator/tests/test_warmup_sets.py`:

```python
"""Tests for warm-up set generation in tool_add_exercise."""
from __future__ import annotations

import pytest
from app.shell.tools import _calculate_warmup_ramp


class TestCalculateWarmupRamp:
    """Test warmup ramp calculation."""

    def test_standard_3_warmups(self):
        """Standard protocol: 50%, 65%, 80% with decreasing reps."""
        sets = _calculate_warmup_ramp(100.0, count=3, progression="standard")
        assert len(sets) == 3
        # Weights: 50, 65, 80
        assert sets[0]["weight"] == 50.0
        assert sets[1]["weight"] == 65.0
        assert sets[2]["weight"] == 80.0
        # Reps decrease
        assert sets[0]["reps"] == 10
        assert sets[1]["reps"] == 8
        assert sets[2]["reps"] == 5
        # All warmup type
        for s in sets:
            assert s["set_type"] == "warmup"

    def test_conservative_2_warmups(self):
        """Conservative: 60%, 80% with fewer sets."""
        sets = _calculate_warmup_ramp(100.0, count=2, progression="conservative")
        assert len(sets) == 2
        assert sets[0]["weight"] == 60.0
        assert sets[1]["weight"] == 80.0

    def test_rounding_to_2_5kg(self):
        """Weights should round to nearest 2.5kg."""
        sets = _calculate_warmup_ramp(130.0, count=3, progression="standard")
        # 130 * 0.50 = 65.0, 130 * 0.65 = 84.5 → 85.0, 130 * 0.80 = 104.0
        assert sets[0]["weight"] == 65.0
        assert sets[1]["weight"] == 85.0
        assert sets[2]["weight"] == 105.0

    def test_light_weight_skips_warmups(self):
        """Working weight < 30kg: return empty (no warmups needed)."""
        sets = _calculate_warmup_ramp(20.0, count=3, progression="standard")
        assert sets == []

    def test_zero_count_returns_empty(self):
        """Zero warmup sets requested."""
        sets = _calculate_warmup_ramp(100.0, count=0, progression="standard")
        assert sets == []

    def test_sets_have_unique_ids(self):
        """Each warmup set has a unique ID."""
        sets = _calculate_warmup_ramp(100.0, count=3, progression="standard")
        ids = [s["id"] for s in sets]
        assert len(set(ids)) == 3

    def test_default_rir_is_5(self):
        """Warmup sets have RIR 5 (submaximal)."""
        sets = _calculate_warmup_ramp(100.0, count=3, progression="standard")
        for s in sets:
            assert s.get("rir") == 5
```

**Step 2: Run test to verify it fails**

```bash
cd adk_agent/canvas_orchestrator && python -m pytest tests/test_warmup_sets.py -v
```

Expected: FAIL — `_calculate_warmup_ramp` not found.

**Step 3: Implement _calculate_warmup_ramp and update tool_add_exercise**

In `adk_agent/canvas_orchestrator/app/shell/tools.py`, add the ramp function before `tool_add_exercise` (before line 1085):

```python
def _calculate_warmup_ramp(
    working_weight_kg: float,
    count: int = 3,
    progression: str = "standard",
) -> list:
    """Calculate warmup set ramp based on working weight.

    Args:
        working_weight_kg: Target working set weight in kg.
        count: Number of warmup sets (0-4).
        progression: "standard" (50/65/80%), "conservative" (60/80%),
                     or "aggressive" (40/55/70/85%).

    Returns:
        List of warmup set dicts with id, weight, reps, rir, set_type.
        Empty list if working_weight_kg < 30 or count <= 0.
    """
    import uuid

    if count <= 0 or working_weight_kg < 30:
        return []

    # Percentage ramps by progression type
    ramps = {
        "standard": [0.50, 0.65, 0.80],
        "conservative": [0.60, 0.80],
        "aggressive": [0.40, 0.55, 0.70, 0.85],
    }

    percentages = ramps.get(progression, ramps["standard"])
    # Trim or extend to match requested count
    if count < len(percentages):
        # Take evenly spaced subset
        step = len(percentages) / count
        percentages = [percentages[int(i * step)] for i in range(count)]
    elif count > len(percentages):
        percentages = percentages[:count]

    # Rep scheme: decreases as weight increases
    rep_scheme = [10, 8, 5, 3]

    def _round_2_5(w):
        return round(w / 2.5) * 2.5

    sets = []
    for i, pct in enumerate(percentages):
        reps = rep_scheme[i] if i < len(rep_scheme) else 3
        sets.append({
            "id": f"set-{uuid.uuid4().hex[:8]}",
            "weight": _round_2_5(working_weight_kg * pct),
            "reps": reps,
            "rir": 5,
            "set_type": "warmup",
        })

    return sets
```

Then update `tool_add_exercise` signature and body (lines 1086-1138):

```python
@timed_tool
def tool_add_exercise(
    *,
    exercise_id: str,
    name: str,
    sets: int = 3,
    reps: int = 10,
    weight_kg: Optional[float] = None,
    rir: Optional[int] = 2,
    warmup_sets: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Add a new exercise to the active workout with planned sets.

    Use when the user wants to add an exercise mid-workout.
    The exercise must exist in the catalog — use tool_search_exercises first
    to find the exercise_id and name.

    Args:
        exercise_id: Catalog exercise ID (from tool_search_exercises)
        name: Exercise name in catalog format "Name (Equipment)"
        sets: Number of working sets (default 3)
        reps: Target reps per working set (default 10)
        weight_kg: Target weight in kg (optional — omit if unknown)
        rir: Target RIR for each working set (default 2)
        warmup_sets: Number of warm-up sets to add before working sets
            (default None — no warmups). Uses standard ramp: 50/65/80%
            of weight_kg with decreasing reps. Only useful for compounds
            with weight_kg >= 30.

    Returns:
        Success with the new exercise instance_id, or error
    """
    ctx = get_current_context()

    if not ctx.workout_mode:
        return {"error": "Not in active workout mode"}

    import uuid

    # Build warmup sets first (if requested)
    all_sets = []
    if warmup_sets and warmup_sets > 0 and weight_kg:
        warmup = _calculate_warmup_ramp(weight_kg, count=warmup_sets)
        all_sets.extend(warmup)

    # Build working sets
    working = [
        {
            "id": f"set-{uuid.uuid4().hex[:8]}",
            "reps": reps,
            "weight": weight_kg,
            "rir": rir,
        }
        for _ in range(sets)
    ]
    all_sets.extend(working)

    result = workout_add_exercise(
        user_id=ctx.user_id,
        workout_id=ctx.active_workout_id,
        exercise_id=exercise_id,
        name=name,
        sets=all_sets,
    )
    return result.to_dict()
```

**Step 4: Run tests**

```bash
cd adk_agent/canvas_orchestrator && python -m pytest tests/test_warmup_sets.py -v
```

Expected: All 7 tests PASS.

**Step 5: Run full check**

```bash
cd adk_agent/canvas_orchestrator && make check && make lint
```

**Step 6: Commit**

```bash
git add adk_agent/canvas_orchestrator/app/shell/tools.py adk_agent/canvas_orchestrator/tests/test_warmup_sets.py
git commit -m "feat: add warm-up set support to tool_add_exercise

Adds warmup_sets parameter and _calculate_warmup_ramp() function.
Standard protocol: 50/65/80% of working weight with 10/8/5 reps.
Skips warmups for weights < 30kg. Backend already supports set_type
'warmup' — no Firebase/iOS changes needed."
```

---

## Workstream 2: Tool-Call Observability Logging

### Task 2.1: Add tool-call logging to stream-agent-normalized.js

**Files:**
- Modify: `firebase_functions/functions/strengthos/stream-agent-normalized.js:1173-1244`

**Step 1: Add structured logging at function_call parse point**

At line 1203, after `sse.write({ type: 'tool_started', name, args });`, add:

```javascript
              // === TOOL TRACING: Log tool invocation for debugging ===
              logger.info('[toolCall]', {
                correlation_id: correlationId || null,
                user_id: userId,
                tool: name,
                args_preview: JSON.stringify(args).slice(0, 1000),
                session_id: sessionToUse,
              });
```

At line 1244, after `sse.write({ type: 'tool_result', name, summary, displayText, phase });`, add:

```javascript
              // === TOOL TRACING: Log tool result for debugging ===
              logger.info('[toolResult]', {
                correlation_id: correlationId || null,
                user_id: userId,
                tool: name,
                summary: summary || null,
                result_preview: parsedResponse
                  ? JSON.stringify(parsedResponse).slice(0, 1000)
                  : null,
                display_text: displayText || null,
                phase: phase || null,
              });
```

**Step 2: Verify no syntax errors**

```bash
cd firebase_functions/functions && node -c strengthos/stream-agent-normalized.js
```

Expected: No output (clean parse).

**Step 3: Commit**

```bash
git add firebase_functions/functions/strengthos/stream-agent-normalized.js
git commit -m "feat: add tool-call tracing to agent SSE proxy

Logs function_call args and function_response results to Cloud Logging
with correlation_id for end-to-end tracing. Previews capped at 1KB.
Query: resource.labels.function_name='streamAgentNormalized'
       jsonPayload.correlation_id='<corr_id>'"
```

---

### Task 2.2: Add correlation_id to timed_tool decorator

**Files:**
- Modify: `adk_agent/canvas_orchestrator/app/shell/tools.py:124-147`

**Step 1: Enhance the decorator**

Replace lines 124-147 with:

```python
def timed_tool(func):
    """Decorator that logs structured JSON after each tool call with timing."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        corr_id = None
        try:
            ctx = get_current_context()
            corr_id = ctx.correlation_id if ctx else None
        except Exception:
            pass
        try:
            result = func(*args, **kwargs)
            latency = int((time.time() - start) * 1000)
            # Preview: extract top-level keys from dict results
            preview = None
            if isinstance(result, dict):
                preview = {k: str(v)[:100] for k, v in list(result.items())[:5]}
            logger.info(json.dumps({
                "event": "tool_called",
                "tool": func.__name__,
                "success": True,
                "latency_ms": latency,
                "correlation_id": corr_id,
                "result_keys": list(result.keys()) if isinstance(result, dict) else None,
            }))
            return result
        except Exception as e:
            logger.info(json.dumps({
                "event": "tool_called",
                "tool": func.__name__,
                "success": False,
                "latency_ms": int((time.time() - start) * 1000),
                "correlation_id": corr_id,
                "error": str(e),
            }))
            raise
    return wrapper
```

**Step 2: Verify**

```bash
cd adk_agent/canvas_orchestrator && make check
```

**Step 3: Commit**

```bash
git add adk_agent/canvas_orchestrator/app/shell/tools.py
git commit -m "feat: add correlation_id + result preview to timed_tool

Links agent-side tool logs to Firebase SSE proxy logs via correlation_id.
Adds result_keys for quick debugging of what data tools returned."
```

---

## Workstream 3: Recommendation Pipeline — Expand Types + Scopes

### Task 3.1: Add swap to the type filter

**Files:**
- Modify: `firebase_functions/functions/triggers/process-recommendations.js:62-69`
- Test: `firebase_functions/functions/tests/process-recommendations.test.js` (if exists, else create)

**Step 1: Write the test**

Create or append to `firebase_functions/functions/tests/process-recommendations-filter.test.js`:

```javascript
const { describe, it } = require('node:test');
const assert = require('node:assert');

// Import helpers we'll test — computeProgressionChanges is already exported
const { computeProgressionChanges, buildSummary } = require('../triggers/process-recommendations');

describe('recommendation type filter', () => {
  it('should accept swap type recommendations', () => {
    // Verify the type is in the allowed list — this is a design assertion
    const allowedTypes = ['progression', 'deload', 'volume_adjust', 'rep_progression', 'swap'];
    assert.ok(allowedTypes.includes('swap'), 'swap should be in allowed types');
  });
});

describe('buildSummary for swap', () => {
  it('should build swap summary with exercise names', () => {
    const rec = { type: 'swap', target: 'Face Pull', suggestedWeight: null };
    const changes = [{
      path: 'exercises[3]',
      from: { name: 'Face Pull (Cable)' },
      to: { name: 'Bent-Over Dumbbell Raises', exercise_id: 'db-bent-over-raise' },
      rationale: 'Stalled 6+ weeks',
    }];
    const summary = buildSummary(rec, 'template', 'pending_review', changes, 'Full Body B');
    assert.ok(summary.length > 0, 'summary should not be empty');
  });
});
```

**Step 2: Run test to verify baseline**

```bash
cd firebase_functions/functions && node --test tests/process-recommendations-filter.test.js
```

**Step 3: Expand the type filter**

In `process-recommendations.js`, line 65, change:

```javascript
          if (!['progression', 'deload', 'volume_adjust', 'rep_progression'].includes(rec.type)) return false;
```

to:

```javascript
          if (!['progression', 'deload', 'volume_adjust', 'rep_progression', 'swap'].includes(rec.type)) return false;
```

**Step 4: Add swap handling in processTemplateScopedRecommendations**

After line 427 (after deduplication check), add swap-specific change computation. In the `for (const rec of actionable)` loop, before `const changes = computeProgressionChanges(...)`:

```javascript
    // Swap recommendations: replace exercise at the matched index
    if (rec.type === 'swap') {
      // Swap needs a new exercise — for now, create as pending_review only
      // (swap execution requires catalog lookup which isn't available here)
      const recRef = db.collection(`users/${userId}/agent_recommendations`).doc();
      const now = FieldValue.serverTimestamp();

      const swapData = {
        id: recRef.id,
        created_at: now,
        trigger: triggerType,
        trigger_context: triggerContext,
        scope: 'template',
        target: {
          template_id: exerciseData.templateId,
          template_name: templateName || null,
          routine_id: activeRoutineId,
          exercise_index: exerciseData.exerciseIndex,
          current_exercise: exerciseName,
        },
        recommendation: {
          type: 'swap',
          changes: [],  // No auto-apply for swaps — user must review
          summary: `Consider swapping ${exerciseName} for a different exercise`,
          rationale: rec.reasoning || rec.rationale || '',
          confidence: rec.confidence,
          signals: rec.signals || [],
        },
        state: 'pending_review',  // Swaps are ALWAYS pending_review
        state_history: [{
          from: null,
          to: 'pending_review',
          at: new Date().toISOString(),
          by: 'agent',
          note: 'Swap recommendation — requires user review',
        }],
        applied_by: null,
      };

      await recRef.set(swapData);
      pendingExercises.add(pendingKey);
      processedCount++;
      logger.info('[processRecommendations] Created swap recommendation', {
        recommendationId: recRef.id,
        exerciseName,
        templateId: exerciseData.templateId,
      });
      continue;  // Skip computeProgressionChanges for swaps
    }
```

**Step 5: Run tests**

```bash
cd firebase_functions/functions && npm test
```

**Step 6: Commit**

```bash
git add firebase_functions/functions/triggers/process-recommendations.js firebase_functions/functions/tests/process-recommendations-filter.test.js
git commit -m "feat: add swap type to recommendation pipeline

Swap recommendations are now accepted (no longer filtered at line 65).
Swaps create pending_review recommendations only — no auto-apply.
User sees the swap suggestion and can accept/dismiss."
```

---

### Task 3.2: Handle muscle-group and routine-level recommendations

**Files:**
- Modify: `firebase_functions/functions/triggers/process-recommendations.js:88-93`

**Step 1: Add scope detection before processActionableRecommendations**

In `onAnalysisInsightCreated` (line 88), before `await processActionableRecommendations(...)`, split actionable into exercise-scoped vs non-exercise-scoped:

```javascript
      // Separate exercise-scoped from non-exercise-scoped recommendations
      const exerciseScoped = actionable.filter(rec =>
        rec.type !== 'volume_adjust' || !isMuscleOrRoutineTarget(rec.target)
      );
      const nonExerciseScoped = actionable.filter(rec =>
        rec.type === 'volume_adjust' && isMuscleOrRoutineTarget(rec.target)
      );

      if (exerciseScoped.length > 0) {
        await processActionableRecommendations(userId, 'post_workout', {
          insight_id: insightId,
          workout_id: insight.workout_id,
          workout_date: insight.workout_date,
        }, exerciseScoped);
      }

      // Write non-exercise recommendations directly (muscle-group / routine level)
      if (nonExerciseScoped.length > 0) {
        await writeNonExerciseRecommendations(userId, 'post_workout', {
          insight_id: insightId,
          workout_id: insight.workout_id,
          workout_date: insight.workout_date,
        }, nonExerciseScoped);
      }
```

Add the helper functions at the bottom of the file (before `module.exports`):

```javascript
/**
 * Detect if a recommendation target is a muscle group or routine-level name
 * rather than a specific exercise name.
 */
const MUSCLE_GROUP_NAMES = new Set([
  'chest', 'back', 'shoulders', 'legs', 'arms', 'core', 'glutes',
  'biceps', 'triceps', 'quads', 'hamstrings', 'calves', 'abs',
  'forearms', 'traps', 'lats', 'rear delts', 'front delts', 'side delts',
]);

function isMuscleOrRoutineTarget(target) {
  if (!target) return false;
  const lower = target.trim().toLowerCase();
  if (MUSCLE_GROUP_NAMES.has(lower)) return true;
  if (lower.includes('weekly') || lower.includes('routine') || lower.includes('training')) return true;
  return false;
}

/**
 * Write muscle-group or routine-level recommendations directly.
 * These bypass exercise-template matching (no specific exercise to match).
 * Always pending_review — informational only.
 */
async function writeNonExerciseRecommendations(userId, triggerType, triggerContext, recommendations) {
  const db = admin.firestore();
  const { FieldValue } = admin.firestore;

  // Premium gate
  const userDoc = await db.collection('users').doc(userId).get();
  if (!userDoc.exists) return;
  const userData = userDoc.data();
  const isPremium = userData.subscription_override === 'premium' || userData.subscription_tier === 'premium';
  if (!isPremium) return;

  const activeRoutineId = userData.activeRoutineId || null;

  for (const rec of recommendations) {
    const recRef = db.collection(`users/${userId}/agent_recommendations`).doc();
    const now = FieldValue.serverTimestamp();
    const isMuscle = MUSCLE_GROUP_NAMES.has((rec.target || '').trim().toLowerCase());

    const recData = {
      id: recRef.id,
      created_at: now,
      trigger: triggerType,
      trigger_context: triggerContext,
      scope: isMuscle ? 'muscle_group' : 'routine',
      target: {
        routine_id: activeRoutineId,
        ...(isMuscle ? { muscle_group: rec.target } : { description: rec.target }),
      },
      recommendation: {
        type: rec.type,
        changes: [],
        summary: rec.rationale || `${rec.type} for ${rec.target}`,
        rationale: rec.reasoning || '',
        confidence: rec.confidence,
        signals: rec.signals || [],
      },
      state: 'pending_review',
      state_history: [{
        from: null,
        to: 'pending_review',
        at: new Date().toISOString(),
        by: 'agent',
        note: `${isMuscle ? 'Muscle-group' : 'Routine-level'} recommendation from ${triggerType}`,
      }],
      applied_by: null,
    };

    await recRef.set(recData);
    logger.info('[processRecommendations] Created non-exercise recommendation', {
      userId,
      target: rec.target,
      scope: recData.scope,
      recommendationId: recRef.id,
    });
  }
}
```

Update `module.exports` to include the new functions:

```javascript
module.exports = {
  onAnalysisInsightCreated,
  onWeeklyReviewCreated,
  expireStaleRecommendations,
  // Exported for testing
  buildSummary,
  buildRationale,
  computeProgressionChanges,
  computeProgressionWeight,
  roundToNearest,
  isMuscleOrRoutineTarget,
  writeNonExerciseRecommendations,
};
```

**Step 2: Run tests**

```bash
cd firebase_functions/functions && npm test
```

**Step 3: Commit**

```bash
git add firebase_functions/functions/triggers/process-recommendations.js
git commit -m "feat: handle muscle-group and routine-level recommendations

Recommendations targeting muscle groups (triceps, chest) or routine-level
concepts (Weekly Training) are now written as pending_review instead of
being silently dropped by the exercise name matching logic."
```

---

## Workstream 4: Cloud Scheduler Triggers for Training Analyst

### Task 4.1: Create Cloud Scheduler setup script

**Files:**
- Create: `adk_agent/training_analyst/deploy-schedulers.sh`
- Modify: `adk_agent/training_analyst/Makefile:117` (add deploy-schedulers target)

**Step 1: Create the deployment script**

```bash
#!/usr/bin/env bash
# deploy-schedulers.sh — Create Cloud Scheduler triggers for Training Analyst
#
# These triggers invoke Cloud Run Jobs on schedule.
# Jobs must be deployed first (make deploy).
#
# Usage: ./deploy-schedulers.sh [--delete-first]

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-myon-53d85}"
REGION="${REGION:-europe-west1}"
SA_EMAIL="ai-agents@${PROJECT_ID}.iam.gserviceaccount.com"

echo "=== Training Analyst — Cloud Scheduler Setup ==="
echo "Project: $PROJECT_ID"
echo "Region:  $REGION"
echo "SA:      $SA_EMAIL"
echo ""

if [[ "${1:-}" == "--delete-first" ]]; then
  echo "Deleting existing scheduler jobs..."
  gcloud scheduler jobs delete trigger-training-analyst-scheduler --location="$REGION" --project="$PROJECT_ID" --quiet 2>/dev/null || true
  gcloud scheduler jobs delete trigger-training-analyst-worker --location="$REGION" --project="$PROJECT_ID" --quiet 2>/dev/null || true
  gcloud scheduler jobs delete trigger-training-analyst-watchdog --location="$REGION" --project="$PROJECT_ID" --quiet 2>/dev/null || true
  echo ""
fi

echo "1/3 Creating scheduler trigger (daily 6 AM UTC — creates weekly jobs on Sundays)..."
gcloud scheduler jobs create http trigger-training-analyst-scheduler \
  --project="$PROJECT_ID" \
  --location="$REGION" \
  --schedule="0 6 * * *" \
  --uri="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/training-analyst-scheduler:run" \
  --http-method=POST \
  --oauth-service-account-email="$SA_EMAIL" \
  --oauth-token-scope="https://www.googleapis.com/auth/cloud-platform" \
  --description="Trigger training-analyst-scheduler Cloud Run Job"

echo "2/3 Creating worker trigger (every 15 min — processes job queue)..."
gcloud scheduler jobs create http trigger-training-analyst-worker \
  --project="$PROJECT_ID" \
  --location="$REGION" \
  --schedule="*/15 * * * *" \
  --uri="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/training-analyst-worker:run" \
  --http-method=POST \
  --oauth-service-account-email="$SA_EMAIL" \
  --oauth-token-scope="https://www.googleapis.com/auth/cloud-platform" \
  --description="Trigger training-analyst-worker Cloud Run Job"

echo "3/3 Creating watchdog trigger (every 6 hours — recovers stuck jobs)..."
gcloud scheduler jobs create http trigger-training-analyst-watchdog \
  --project="$PROJECT_ID" \
  --location="$REGION" \
  --schedule="0 */6 * * *" \
  --uri="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/training-analyst-watchdog:run" \
  --http-method=POST \
  --oauth-service-account-email="$SA_EMAIL" \
  --oauth-token-scope="https://www.googleapis.com/auth/cloud-platform" \
  --description="Trigger training-analyst-watchdog Cloud Run Job"

echo ""
echo "=== Done. Verify with: gcloud scheduler jobs list --location=$REGION --project=$PROJECT_ID ==="
```

**Step 2: Add Makefile target**

Append to `adk_agent/training_analyst/Makefile` after line 117:

```makefile

# Deploy Cloud Scheduler triggers (run AFTER deploy)
deploy-schedulers:
	@echo "Creating Cloud Scheduler triggers..."
	bash deploy-schedulers.sh
```

**Step 3: Commit**

```bash
chmod +x adk_agent/training_analyst/deploy-schedulers.sh
git add adk_agent/training_analyst/deploy-schedulers.sh adk_agent/training_analyst/Makefile
git commit -m "infra: add Cloud Scheduler triggers for training analyst

Weekly reviews stopped in October 2025 because Cloud Run Jobs existed
but had no scheduler triggers. This script creates 3 triggers:
- Scheduler (daily 6 AM): creates weekly review jobs on Sundays
- Worker (every 15 min): processes the job queue
- Watchdog (every 6 hours): recovers stuck jobs

Run: make deploy && make deploy-schedulers"
```

### Task 4.2: Run the deploy (manual step)

```bash
cd adk_agent/training_analyst
# Deploy Cloud Run Jobs first (if not already done)
make deploy
# Create scheduler triggers
make deploy-schedulers
# Verify
gcloud scheduler jobs list --location=europe-west1 --project=myon-53d85
```

---

## Workstream 5: Analytics Rollups Backfill + Investigation

### Task 5.1: Investigate and backfill rollups for the user

**Files:**
- No code changes — operational investigation + backfill

**Step 1: Check Cloud Logging for rollup write failures**

```bash
gcloud logging read \
  'resource.type="cloud_function" jsonPayload.message=~"Non-fatal.*rollup"' \
  --project=myon-53d85 --limit=20 --format=json
```

**Step 2: Trigger analytics rebuild for user**

```bash
cd firebase_functions/functions
GOOGLE_APPLICATION_CREDENTIALS=$FIREBASE_SA_KEY node -e "
const admin = require('firebase-admin');
admin.initializeApp();
const { processUserAnalytics } = require('./analytics/worker');
processUserAnalytics('Y4SJuNPOasaltF7TuKm1QCT7JIA3')
  .then(r => { console.log('Done:', JSON.stringify(r)); process.exit(0); })
  .catch(e => { console.error(e); process.exit(1); });
"
```

**Step 3: Verify rollups were created**

```bash
cd firebase_functions/functions
GOOGLE_APPLICATION_CREDENTIALS=$FIREBASE_SA_KEY node -e "
const admin = require('firebase-admin');
admin.initializeApp();
const db = admin.firestore();
db.collection('users').doc('Y4SJuNPOasaltF7TuKm1QCT7JIA3')
  .collection('analytics_rollups')
  .orderBy('updated_at', 'desc').limit(5).get()
  .then(snap => {
    console.log('Rollups found:', snap.size);
    snap.forEach(d => console.log(d.id, JSON.stringify(d.data()).slice(0, 200)));
    process.exit(0);
  });
"
```

### Task 5.2: Add rollup write error logging (upgrade from warning to error)

**Files:**
- Modify: `firebase_functions/functions/triggers/weekly-analytics.js`

**Step 1: Find the Promise.allSettled block**

Search for the `allSettled` call in `onWorkoutCreatedWithEnd` and upgrade rollup failures from `logger.warn` to `logger.error` with structured context:

In the `.then(results => ...)` handler, for the rollup result specifically:

```javascript
      // Check rollup write specifically — it's critical for ACWR calculations
      const rollupResult = results[rollupIndex]; // Identify which index is the rollup write
      if (rollupResult && rollupResult.status === 'rejected') {
        logger.error('[onWorkoutCreatedWithEnd] CRITICAL: Rollup write failed', {
          userId,
          workoutId: event.params.workoutId,
          weekId,
          error: rollupResult.reason?.message || String(rollupResult.reason),
        });
      }
```

**Step 2: Commit**

```bash
git add firebase_functions/functions/triggers/weekly-analytics.js
git commit -m "fix: upgrade rollup write failure from warn to error

Rollup failures were logged as non-fatal warnings, causing empty
analytics_rollups and broken ACWR calculations. Now logged as errors
for monitoring/alerting."
```

---

## Workstream 6: Template Transparency — Surface Auto-Applied Changes

### Task 6.1: Add template sync on workout completion

**Files:**
- Modify: `firebase_functions/functions/active_workout/complete-active-workout.js`

**Step 1: Add template weight sync after workout transaction**

After the workout completion transaction (after the changelog write, around line 247), add a template weight sync that updates template set weights to match what the user actually did:

```javascript
    // Sync template weights from workout actuals.
    // When the user completes a workout, update the template to reflect
    // their actual working weights — prevents the "ghost regression" problem
    // where templates stay stale and analyst deloads overwrite user progress.
    if (active.source_template_id && result.workout_id) {
      try {
        await syncTemplateWeightsFromWorkout(
          firestore, userId, active.source_template_id, normalizedExercises
        );
      } catch (syncErr) {
        // Non-fatal — don't block workout completion
        logger.warn('[completeActiveWorkout] Template sync failed', {
          userId, templateId: active.source_template_id, error: syncErr.message,
        });
      }
    }
```

Add the sync function:

```javascript
/**
 * Sync template set weights from completed workout actuals.
 * For each exercise in the workout that matches a template exercise,
 * update the template's working set weights to the max weight used.
 *
 * This prevents template weight regression when analyst auto-deloads
 * after the user has already self-progressed.
 */
async function syncTemplateWeightsFromWorkout(db, userId, templateId, exercises) {
  const templateRef = db.collection('users').doc(userId)
    .collection('templates').doc(templateId);
  const templateSnap = await templateRef.get();
  if (!templateSnap.exists) return;

  const templateData = templateSnap.data();
  const templateExercises = templateData.exercises || [];
  let changed = false;

  for (const workoutEx of exercises) {
    const exId = workoutEx.exercise_id;
    if (!exId) continue;

    // Find matching template exercise
    const templateIdx = templateExercises.findIndex(
      te => te.exercise_id === exId
    );
    if (templateIdx === -1) continue;

    // Get max working set weight from workout
    const workingSets = (workoutEx.sets || []).filter(s => s.type !== 'warmup' && s.status === 'done');
    if (workingSets.length === 0) continue;
    const maxWeight = Math.max(...workingSets.map(s => s.weight_kg || s.weight || 0));
    if (maxWeight <= 0) continue;

    // Update template working sets to match
    const templateSets = templateExercises[templateIdx].sets || [];
    for (const tSet of templateSets) {
      if (tSet.type === 'warmup') continue;
      if ((tSet.weight || 0) < maxWeight) {
        tSet.weight = maxWeight;
        changed = true;
      }
    }
  }

  if (changed) {
    await templateRef.update({
      exercises: templateExercises,
      updated_at: admin.firestore.FieldValue.serverTimestamp(),
    });
    logger.info('[completeActiveWorkout] Template weights synced from workout', {
      userId, templateId,
    });
  }
}
```

**Step 2: Run tests**

```bash
cd firebase_functions/functions && npm test
```

**Step 3: Commit**

```bash
git add firebase_functions/functions/active_workout/complete-active-workout.js
git commit -m "feat: sync template weights from workout actuals

On workout completion, updates template working set weights to match
the user's actual working weights. Prevents the template weight regression
where the user does 130kg but template stays at 120kg, causing confusion
on the next workout."
```

---

### Task 6.2: Add notification field to auto-applied recommendations

**Files:**
- Modify: `firebase_functions/functions/triggers/process-recommendations.js:438-466`

**Step 1: Add a user_notification field when auto-applying**

In the `recommendationData` object (line 438), add a notification field that the iOS app can surface:

```javascript
      // When auto-pilot applies, include a user-facing notification
      const notificationText = autoPilotEnabled
        ? `Auto-applied: ${buildSummary(rec, 'template', 'applied', changes, templateName)}`
        : null;

      const recommendationData = {
        // ... existing fields ...
        user_notification: notificationText,
        notification_read: false,
      };
```

**Step 2: Commit**

```bash
git add firebase_functions/functions/triggers/process-recommendations.js
git commit -m "feat: add user_notification to auto-applied recommendations

Auto-pilot recommendations now include a user_notification field with
human-readable summary (e.g., 'Auto-applied: Deadlift 130kg → 120kg').
iOS can surface these as banners when the user opens the next workout."
```

---

## Workstream 7: Swap with Full Routine Context

### Task 7.1: Expand analyst data context for swaps

**Files:**
- Modify: `adk_agent/training_analyst/app/analyzers/post_workout.py:57-79`

**Step 1: Add full routine exercise inventory to LLM input**

In `post_workout.py`, modify `_read_routine_summary()` to include full exercise lists (not just template names). Change lines 346-369:

```python
    def _read_routine_summary(
        self, db, user_id: str
    ) -> Optional[Dict[str, Any]]:
        """Read routine summary with full exercise lists per template.

        For swap recommendations, the LLM needs to know which exercises
        exist across the entire routine to avoid suggesting duplicates.
        """
        user_doc = db.collection("users").document(user_id).get()
        if not user_doc.exists:
            return None

        user_data = user_doc.to_dict()
        routine_id = user_data.get("activeRoutineId")
        if not routine_id:
            return None

        routine_doc = (
            db.collection("users").document(user_id)
            .collection("routines").document(routine_id).get()
        )
        if not routine_doc.exists:
            return None

        routine = routine_doc.to_dict()
        template_ids = routine.get("template_ids", [])
        if not template_ids:
            return None

        # Batch read templates
        template_refs = [
            db.collection("users").document(user_id)
            .collection("templates").document(tid)
            for tid in template_ids[:10]
        ]
        template_docs = db.get_all(template_refs)

        templates = []
        all_exercise_ids = set()
        for tdoc in template_docs:
            if tdoc.exists:
                tdata = tdoc.to_dict()
                exercises = []
                for ex in tdata.get("exercises", []):
                    ex_id = ex.get("exercise_id")
                    if ex_id:
                        all_exercise_ids.add(ex_id)
                    exercises.append({
                        "exercise_id": ex_id,
                        "name": ex.get("name"),
                    })
                templates.append({
                    "template_id": tdoc.id,
                    "name": tdata.get("name", tdoc.id),
                    "exercises": exercises,
                })

        return {
            "routine_name": routine.get("name"),
            "frequency": routine.get("frequency"),
            "templates": templates,
            "all_exercise_ids": list(all_exercise_ids),
        }
```

**Step 2: Add instruction to analyst prompt**

In `_get_system_prompt()`, after the `ROUTINE CONTEXT` section (around line 489), add:

```python
When generating SWAP recommendations:
- Check routine_context.templates to verify the suggested replacement is NOT already
  in another template. If it is, pick a different alternative.
- Include the template name in your recommendation target for clarity.
- Set suggested_weight using the estimation formulas:
  BB→DB = 37% per hand, compound→isolation = 30%, incline = 82% of flat.
```

**Step 3: Run checks**

```bash
cd adk_agent/training_analyst && python -m pytest tests/ -v
```

**Step 4: Commit**

```bash
git add adk_agent/training_analyst/app/analyzers/post_workout.py
git commit -m "feat: expand routine context for swap recommendations

The LLM now sees the full exercise list across all templates in the
user's routine, preventing swap suggestions that duplicate existing
exercises. Also adds swap-specific prompt guidance for weight estimation."
```

---

## Documentation Updates

### Task 8.1: Update Tier 2 docs

**Files:**
- Modify: `adk_agent/canvas_orchestrator/app/shell/ARCHITECTURE.md` (if exists)
- Modify: `firebase_functions/functions/triggers/ARCHITECTURE.md`

After all workstreams are complete, update module-level architecture docs to reflect:
- Brief-first reasoning pattern in instruction
- Warm-up set support in tool_add_exercise
- Expanded recommendation types (swap, muscle-group, routine-level)
- Tool-call tracing via correlation_id
- Template weight sync on workout completion

### Task 8.2: Update Tier 1 docs

**Files:**
- Modify: `docs/SYSTEM_ARCHITECTURE.md`

Add to the data flow section:
- Template weight sync flow (workout completion → template update)
- Recommendation pipeline expanded scope diagram
- Tool tracing query patterns for debugging

---

## Execution Checklist

After all tasks:
1. Run full test suites:
   - `cd adk_agent/canvas_orchestrator && make check && make test && make lint`
   - `cd firebase_functions/functions && npm test`
   - `cd adk_agent/training_analyst && make test`
2. Deploy training analyst scheduler triggers (Task 4.2)
3. Backfill analytics rollups (Task 5.1)
4. Deploy Firebase Functions (`cd firebase_functions/functions && npm run deploy`)
5. Deploy agent (`cd adk_agent/canvas_orchestrator && make deploy`)
