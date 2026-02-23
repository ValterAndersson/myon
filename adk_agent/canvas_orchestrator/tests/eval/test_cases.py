"""
Shell Agent Eval Test Cases — 108 cases across 9 categories.

Each case defines a user query and expected behavior for automated scoring.
Cases are designed to test generalizable agent behavior — none should be
added verbatim to agent instructions.

Categories:
- EASY (12): Single-tool, straightforward queries
- MODERATE (15): Date reasoning or multi-step tool selection
- COMPLEX (10): Multi-tool, ambiguity, or boundary cases
- EDGE (8): No data, adversarial, or boundary conditions
- ACTIVE_WORKOUT (25): 2-sentence constraint with workout brief (untested tools,
  natural language variations, mid-workout boundaries, weight advice)
- SCIENCE (10): Evidence-based reasoning
- PERIODIZATION (8): Programming structure
- ANALYSIS (10): Deep data interpretation
- ROUTINE_BUILDING (10): Workout/routine creation
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class TestCase:
    """Single eval test case."""
    id: str
    query: str
    category: str
    expected_tools: List[str]
    expected_behavior: str
    gold_standard: str
    workout_brief: Optional[str] = None
    tags: List[str] = field(default_factory=list)


# =============================================================================
# SAMPLE WORKOUT BRIEF (for ACTIVE_WORKOUT cases)
# =============================================================================

SAMPLE_WORKOUT_BRIEF = """[WORKOUT BRIEF]
Workout: Push Day | Started: 14:32 | Sets: 2/17

1. Bench Press (Barbell) [ex-bench-001] ← CURRENT
   ✓ Set 1: 100kg × 8 @ RIR 2
   ✓ Set 2: 100kg × 8 @ RIR 2
   → Set 3 [set-bench-003]: 100kg × 8 planned
   ○ Set 4 [set-bench-004]: 100kg × 8 planned
   History: 100×8, 100×8, 97.5×8 (last 3 sessions)

2. Incline Dumbbell Press (Dumbbell) [ex-incline-002]
   ○ Set 1 [set-inc-001]: 32kg × 10 planned
   ○ Set 2 [set-inc-002]: 32kg × 10 planned
   ○ Set 3 [set-inc-003]: 32kg × 10 planned
   History: 32×10, 30×10, 30×10

3. Cable Fly (Cable) [ex-fly-003]
   ○ Set 1 [set-fly-001]: 15kg × 12 planned
   ○ Set 2 [set-fly-002]: 15kg × 12 planned
   ○ Set 3 [set-fly-003]: 15kg × 12 planned
   History: 15×12, 15×11, 12.5×12

4. Lateral Raise (Dumbbell) [ex-lat-004]
   ○ Set 1 [set-lat-001]: 10kg × 15 planned
   ○ Set 2 [set-lat-002]: 10kg × 15 planned
   ○ Set 3 [set-lat-003]: 10kg × 15 planned
   History: 10×15, 10×14, 10×12

5. Overhead Tricep Extension (Cable) [ex-tri-005]
   ○ Set 1 [set-tri-001]: 20kg × 12 planned
   ○ Set 2 [set-tri-002]: 20kg × 12 planned
   History: 20×12, 20×11, 17.5×12

6. Face Pull (Cable) [ex-fp-006]
   ○ Set 1 [set-fp-001]: 12.5kg × 15 planned
   ○ Set 2 [set-fp-002]: 12.5kg × 15 planned
   History: 12.5×15, 12.5×14, 10×15
"""

# Late-stage workout brief: 14/18 sets done, on the last exercise before curls.
LATE_WORKOUT_BRIEF = """[WORKOUT BRIEF]
Workout: Pull Day | Started: 15:10 | Sets: 14/17

1. Barbell Row (Barbell) [ex-row-001]
   ✓ Set 1: 80kg × 8 @ RIR 2
   ✓ Set 2: 80kg × 8 @ RIR 1
   ✓ Set 3: 80kg × 7 @ RIR 1
   History: 80×8, 77.5×8, 77.5×8

2. Lat Pulldown (Cable) [ex-lat-002]
   ✓ Set 1: 65kg × 10 @ RIR 2
   ✓ Set 2: 65kg × 10 @ RIR 2
   ✓ Set 3: 65kg × 9 @ RIR 1
   History: 65×10, 62.5×10, 60×10

3. Seated Cable Row (Cable) [ex-scr-003]
   ✓ Set 1: 55kg × 12 @ RIR 2
   ✓ Set 2: 55kg × 11 @ RIR 1
   ✓ Set 3: 55kg × 11 @ RIR 1
   History: 55×12, 52.5×12, 52.5×11

4. Face Pull (Cable) [ex-fp-004]
   ✓ Set 1: 15kg × 15 @ RIR 2
   ✓ Set 2: 15kg × 14 @ RIR 1
   ✓ Set 3: 15kg × 13 @ RIR 1
   History: 15×15, 12.5×15, 12.5×14

5. Bicep Curl (Dumbbell) [ex-curl-005] ← CURRENT
   ✓ Set 1: 14kg × 10 @ RIR 2
   ✓ Set 2: 14kg × 10 @ RIR 1
   → Set 3 [set-curl-003]: 14kg × 10 planned
   History: 14×10, 12×12, 12×12

6. Hammer Curl (Dumbbell) [ex-ham-006]
   ○ Set 1 [set-ham-001]: 12kg × 12 planned
   ○ Set 2 [set-ham-002]: 12kg × 12 planned
   History: 12×12, 12×11, 10×12
"""

# =============================================================================
# EASY (12): Single-tool, straightforward
# =============================================================================

EASY_CASES = [
    TestCase(
        id="easy_001",
        query="How did my last workout go?",
        category="easy",
        expected_tools=["tool_get_training_analysis"],
        expected_behavior="Uses pre-computed insights to summarize last workout performance",
        gold_standard="Summarizes workout with key metrics (sets, volume, highlights). "
                       "Mentions any PRs or flags. Gives one actionable next step.",
        tags=["insights", "summary"],
    ),
    TestCase(
        id="easy_002",
        query="Is my bench press progressing?",
        category="easy",
        expected_tools=["tool_get_exercise_progress"],
        expected_behavior="Fetches bench press progress via exercise_name fuzzy search",
        gold_standard="States e1RM trend direction and magnitude. Cites last session numbers. "
                       "Gives one concrete recommendation (weight/rep change).",
        tags=["exercise_progress", "bench"],
    ),
    TestCase(
        id="easy_003",
        query="Am I ready to train today?",
        category="easy",
        expected_tools=["tool_get_training_analysis"],
        expected_behavior="Fetches weekly_review section for readiness/fatigue assessment",
        gold_standard="States readiness level based on fatigue_status and ACWR. "
                       "Relays any adjustments. Gives clear train/skip recommendation.",
        tags=["readiness", "weekly_review"],
    ),
    TestCase(
        id="easy_004",
        query="How many sets per week do I need for chest growth?",
        category="easy",
        expected_tools=[],
        expected_behavior="Answers from general knowledge — no tool call needed",
        gold_standard="Cites evidence-based range (10-20 sets/week for most). "
                       "Qualifies with experience level. No hallucinated personal data.",
        tags=["knowledge", "no_tools"],
    ),
    TestCase(
        id="easy_005",
        query="What exercises hit rear delts?",
        category="easy",
        expected_tools=["tool_search_exercises"],
        expected_behavior="Searches exercises by muscle group or answers from knowledge",
        gold_standard="Lists 3-5 rear delt exercises. May mention face pulls, reverse flyes, "
                       "band pull-aparts. Keeps it concise.",
        tags=["exercise_search", "knowledge"],
    ),
    TestCase(
        id="easy_006",
        query="What's my training frequency?",
        category="easy",
        expected_tools=["tool_get_planning_context"],
        expected_behavior="Gets planning context to check routine frequency",
        gold_standard="Reports frequency from active routine or recent workout pattern. "
                       "Does not invent numbers.",
        tags=["routine", "frequency"],
    ),
    TestCase(
        id="easy_007",
        query="How much did I bench last session?",
        category="easy",
        expected_tools=["tool_get_exercise_progress"],
        expected_behavior="Fetches exercise progress with last_session data",
        gold_standard="Reports exact weight and reps from last bench session. "
                       "Cites actual numbers from data, not estimates.",
        tags=["exercise_progress", "last_session"],
    ),
    TestCase(
        id="easy_008",
        query="What's good form for Romanian deadlifts?",
        category="easy",
        expected_tools=[],
        expected_behavior="Answers from knowledge — technique question, no data needed",
        gold_standard="Covers 2-3 key form cues (hip hinge, soft knees, bar path). "
                       "Concise, actionable. No personal data claims.",
        tags=["knowledge", "form", "no_tools"],
    ),
    TestCase(
        id="easy_009",
        query="How is my back developing?",
        category="easy",
        expected_tools=["tool_get_muscle_group_progress"],
        expected_behavior="Uses muscle group progress for 'back' overview",
        gold_standard="Reports volume trend, top exercises, and any flags. "
                       "Mentions specific weeks of data.",
        tags=["muscle_group", "back"],
    ),
    TestCase(
        id="easy_010",
        query="Show me my recent workouts",
        category="easy",
        expected_tools=["tool_get_planning_context"],
        expected_behavior="Gets planning context which includes recentWorkoutsSummary",
        gold_standard="Lists last 3-5 workouts with dates and exercise names. "
                       "Does not fabricate workout details.",
        tags=["recent_workouts", "planning_context"],
    ),
    TestCase(
        id="easy_011",
        query="What's the difference between RIR and RPE?",
        category="easy",
        expected_tools=[],
        expected_behavior="Answers from knowledge — definitional question",
        gold_standard="Explains both concepts clearly. Notes they're inversely related "
                       "(RPE 10 = RIR 0). Concise.",
        tags=["knowledge", "no_tools"],
    ),
    TestCase(
        id="easy_012",
        query="Do I have an active routine?",
        category="easy",
        expected_tools=["tool_get_planning_context"],
        expected_behavior="Checks planning context for active routine",
        gold_standard="States whether routine exists. If yes, names it and mentions frequency. "
                       "If no, suggests creating one.",
        tags=["routine", "planning_context"],
    ),
]

# =============================================================================
# MODERATE (15): Date reasoning or multi-step tool selection
# =============================================================================

MODERATE_CASES = [
    TestCase(
        id="mod_001",
        query="What did I do yesterday?",
        category="moderate",
        expected_tools=["tool_get_planning_context"],
        expected_behavior="Must compute yesterday's date from today in context prefix. "
                          "Uses planning context (recent workouts) or query_training_sets with date filter.",
        gold_standard="Reports exercises and sets from yesterday's workout. "
                       "If no workout yesterday, says so plainly.",
        tags=["date_reasoning", "yesterday"],
    ),
    TestCase(
        id="mod_002",
        query="I feel tired, should I still train?",
        category="moderate",
        expected_tools=["tool_get_training_analysis"],
        expected_behavior="Checks readiness data before validating emotional state. "
                          "Does not default to skipping based on feeling alone.",
        gold_standard="Checks weekly_review fatigue_status for objective readiness. Gives data-backed "
                       "recommendation. Acknowledges feeling but doesn't over-empathize.",
        tags=["readiness", "emotional", "weekly_review"],
    ),
    TestCase(
        id="mod_003",
        query="Volume this week vs last?",
        category="moderate",
        expected_tools=["tool_get_planning_context"],
        expected_behavior="Current week data requires live data source. Uses "
                          "tool_get_planning_context (recentWorkoutsSummary) or "
                          "tool_query_training_sets for current week, and may use "
                          "tool_get_training_analysis for last week comparison.",
        gold_standard="Reports set/volume delta between weeks with actual numbers. "
                       "Notes if current week is incomplete. Uses live data for current week.",
        tags=["volume", "comparison", "current_week"],
    ),
    TestCase(
        id="mod_004",
        query="Which exercises are stalling?",
        category="moderate",
        expected_tools=["tool_get_training_analysis"],
        expected_behavior="Uses weekly_review stalled_exercises list",
        gold_standard="Lists stalled exercises with weeks stalled. Suggests specific actions "
                       "(deload, swap, rep range change). Cites data.",
        tags=["stalls", "weekly_review"],
    ),
    TestCase(
        id="mod_005",
        query="How many bench sets this week?",
        category="moderate",
        expected_tools=["tool_query_training_sets"],
        expected_behavior="Computes current week date range from today. Uses query_training_sets "
                          "with exercise_name='bench press' and start/end dates.",
        gold_standard="Reports exact number of bench sets this week with dates. "
                       "Does not use stale pre-computed data for current week.",
        tags=["date_reasoning", "current_week", "sets"],
    ),
    TestCase(
        id="mod_006",
        query="What should my next workout look like?",
        category="moderate",
        expected_tools=["tool_get_planning_context"],
        expected_behavior="Gets planning context to find nextWorkout in routine. If no routine, "
                          "may propose a workout based on recent history (artifact response). "
                          "NOTE: If agent proposes a workout, the card has details — text is minimal.",
        gold_standard="If routine exists: describes the next workout. If no routine: either "
                       "suggests creating one or proposes a workout. If proposing, text "
                       "confirmation is sufficient (card has details).",
        tags=["next_workout", "planning"],
    ),
    TestCase(
        id="mod_007",
        query="Am I training enough back?",
        category="moderate",
        expected_tools=["tool_get_muscle_group_progress"],
        expected_behavior="Fetches back muscle group progress to assess volume adequacy",
        gold_standard="Reports weekly back sets and compares to evidence-based targets. "
                       "Notes trend direction. Recommends adjustment if needed.",
        tags=["volume_adequacy", "muscle_group"],
    ),
    TestCase(
        id="mod_008",
        query="Compare my bench to my squat progress",
        category="moderate",
        expected_tools=["tool_get_exercise_progress"],
        expected_behavior="Calls exercise progress for both bench and squat. May need two calls.",
        gold_standard="Compares e1RM trends for both lifts. Notes which is progressing faster. "
                       "Cites actual numbers from each.",
        tags=["comparison", "multi_exercise"],
    ),
    TestCase(
        id="mod_009",
        query="My shoulders feel beat up after pressing. What should I change?",
        category="moderate",
        expected_tools=["tool_get_training_analysis", "tool_get_muscle_group_progress"],
        expected_behavior="Checks training data for shoulder volume and pressing frequency. "
                          "Gives evidence-based recovery suggestions.",
        gold_standard="Reviews pressing volume and shoulder stress. Suggests concrete changes "
                       "(reduce volume, swap exercises, add rear delt work). Does not diagnose injury.",
        tags=["discomfort", "programming"],
    ),
    TestCase(
        id="mod_010",
        query="How are my legs developing over time?",
        category="moderate",
        expected_tools=["tool_get_muscle_group_progress"],
        expected_behavior="Uses muscle group progress for legs with longer window",
        gold_standard="Reports multi-week leg development trend. Mentions volume, top exercises, "
                       "and any flags (plateau, imbalance).",
        tags=["muscle_group", "trend", "legs"],
    ),
    TestCase(
        id="mod_011",
        query="What should I focus on improving?",
        category="moderate",
        expected_tools=["tool_get_training_analysis"],
        expected_behavior="Uses broad analysis to identify weak points",
        gold_standard="Identifies 2-3 areas for improvement based on data (stalls, volume gaps, "
                       "muscle imbalances). Gives priority order and concrete first step.",
        tags=["broad_advice", "weak_points"],
    ),
    TestCase(
        id="mod_012",
        query="Rate my training consistency",
        category="moderate",
        expected_tools=["tool_get_training_analysis"],
        expected_behavior="Uses weekly_review for session count trends",
        gold_standard="Reports session frequency over recent weeks. Notes consistency trend. "
                       "Gives constructive feedback.",
        tags=["consistency", "weekly_review"],
    ),
    TestCase(
        id="mod_013",
        query="How much volume am I doing for chest vs back?",
        category="moderate",
        expected_tools=["tool_get_muscle_group_progress"],
        expected_behavior="Fetches muscle group progress for both chest and back. Two calls.",
        gold_standard="Compares weekly sets/volume for chest vs back. Flags imbalance if present. "
                       "Recommends adjustment based on ratio.",
        tags=["comparison", "volume", "balance"],
    ),
    TestCase(
        id="mod_014",
        query="How are my rhomboids doing?",
        category="moderate",
        expected_tools=["tool_get_muscle_progress"],
        expected_behavior="Uses specific muscle progress (not muscle group) for rhomboids",
        gold_standard="Reports rhomboid-specific volume and trend. Lists exercises contributing. "
                       "Uses tool_get_muscle_progress, not tool_get_muscle_group_progress.",
        tags=["specific_muscle", "muscle_progress"],
    ),
    TestCase(
        id="mod_015",
        query="Did I hit any PRs this week?",
        category="moderate",
        expected_tools=["tool_get_training_analysis"],
        expected_behavior="Uses insights for PR highlights",
        gold_standard="Lists PRs from this week if any. If none, says so plainly. "
                       "Reports actual numbers (exercise, weight, e1RM).",
        tags=["prs", "insights"],
    ),
]

# =============================================================================
# COMPLEX (10): Multi-tool, ambiguity, or boundary cases
# =============================================================================

COMPLEX_CASES = [
    TestCase(
        id="complex_001",
        query="Create me a push pull legs routine",
        category="complex",
        expected_tools=["tool_get_planning_context", "tool_search_exercises",
                        "tool_propose_routine"],
        expected_behavior="Gets planning context first, searches exercises for each day, "
                          "then proposes a full routine via tool_propose_routine. "
                          "NOTE: The artifact card (with full routine details) is delivered "
                          "as a separate UI element — the text response is intentionally "
                          "minimal (1 confirmation sentence).",
        gold_standard="Calls propose_routine with correct structure. Text response is a "
                       "short confirmation like 'Your Push Pull Legs routine is ready.' "
                       "This is correct — the card has the details and accept/dismiss buttons.",
        tags=["artifact", "routine", "multi_tool"],
    ),
    TestCase(
        id="complex_002",
        query="Improve my current routine",
        category="complex",
        expected_tools=["tool_get_planning_context", "tool_get_training_analysis",
                        "tool_search_exercises"],
        expected_behavior="Gets current routine, analyzes weaknesses from training data, "
                          "then proposes updates via tool_update_routine.",
        gold_standard="Identifies specific issues in current routine based on data. "
                       "Proposes targeted changes. Uses tool_update_routine, not propose_routine.",
        tags=["artifact", "update", "multi_tool"],
    ),
    TestCase(
        id="complex_003",
        query="How many sets did I do this week?",
        category="complex",
        expected_tools=["tool_get_planning_context"],
        expected_behavior="Staleness trap: pre-computed weekly_review may not cover current week. "
                          "Should use tool_get_planning_context (has live recentWorkoutsSummary) "
                          "or tool_query_training_sets with current week dates. Must NOT use "
                          "pre-computed weekly_review which shows last week's data.",
        gold_standard="Reports total sets for the current week using live data from "
                       "planning_context or query_training_sets. Does not use stale "
                       "pre-computed weekly_review.",
        tags=["staleness", "current_week", "date_reasoning"],
    ),
    TestCase(
        id="complex_004",
        query="My shoulder hurts during overhead press. What should I do?",
        category="complex",
        expected_tools=["tool_search_exercises"],
        expected_behavior="Pain trigger: should suggest joint-friendly alternatives, "
                          "NOT diagnose or recommend pushing through. May search for alternatives.",
        gold_standard="Suggests stopping the painful exercise. Recommends 2-3 alternatives "
                       "(e.g., landmine press, neutral grip). Does NOT diagnose the injury.",
        tags=["pain", "safety", "exercise_swap"],
    ),
    TestCase(
        id="complex_005",
        query="I want to do a body recomp. Design my training.",
        category="complex",
        expected_tools=["tool_get_planning_context", "tool_search_exercises",
                        "tool_propose_routine"],
        expected_behavior="Broad request — should clarify or make reasonable assumptions. "
                          "Gets context, then builds a routine appropriate for recomp goals. "
                          "NOTE: Artifact card has full routine details — text response "
                          "is intentionally minimal. Exercise search calls should be ≤6.",
        gold_standard="Calls propose_routine with appropriate structure. Text response is "
                       "a short confirmation. May note that recomp also requires nutrition "
                       "management. Does not over-promise results.",
        tags=["artifact", "broad_request", "recomp"],
    ),
    TestCase(
        id="complex_006",
        query="Build me a workout for today based on what I haven't trained recently",
        category="complex",
        expected_tools=["tool_get_planning_context", "tool_search_exercises",
                        "tool_propose_workout"],
        expected_behavior="Must cross-reference recent workout history with muscle coverage "
                          "to find gaps, then build a workout targeting those gaps. "
                          "NOTE: Artifact card has full workout details — text response "
                          "is intentionally minimal.",
        gold_standard="Calls propose_workout with exercises targeting under-trained muscles. "
                       "Text response is a short confirmation. This is correct — the card "
                       "has the full workout and accept/dismiss buttons.",
        tags=["artifact", "gap_analysis", "multi_tool"],
    ),
    TestCase(
        id="complex_007",
        query="What's my weakest body part and how do I fix it?",
        category="complex",
        expected_tools=["tool_get_training_analysis"],
        expected_behavior="Uses muscle_balance from weekly_review to identify weakest area. "
                          "May drill down with muscle_group_progress for confirmation.",
        gold_standard="Identifies weakest muscle group with data (lowest volume, worst trend). "
                       "Gives 2-3 concrete fixes (add exercises, increase frequency, swap movements).",
        tags=["weak_point", "analysis", "actionable"],
    ),
    TestCase(
        id="complex_008",
        query="I just did 5x5 at 140kg on squat, was that good?",
        category="complex",
        expected_tools=["tool_get_exercise_progress"],
        expected_behavior="User provides performance data — agent needs history for context. "
                          "Fetches squat progress to compare against trend.",
        gold_standard="Compares reported performance against historical trend. If data exists, "
                       "gives contextual verdict. If no history, acknowledges the raw numbers "
                       "and suggests logging it.",
        tags=["user_data", "evaluation", "squat"],
    ),
    TestCase(
        id="complex_009",
        query="Show me everything about my chest training",
        category="complex",
        expected_tools=["tool_get_muscle_group_progress", "tool_query_training_sets"],
        expected_behavior="Broad request — should provide comprehensive chest overview. "
                          "May use multiple tools for different angles.",
        gold_standard="Reports chest volume trend, top exercises, recent sets, and any flags. "
                       "Organized clearly. Does not dump raw data.",
        tags=["comprehensive", "chest", "multi_tool"],
    ),
    TestCase(
        id="complex_010",
        query="Analyze my last 4 weeks of training and tell me what to change",
        category="complex",
        expected_tools=["tool_get_training_analysis"],
        expected_behavior="Uses weekly_review and insights for comprehensive 4-week analysis. "
                          "Synthesizes across multiple dimensions.",
        gold_standard="Covers volume trends, exercise progression, stalls, and muscle balance. "
                       "Prioritizes 2-3 changes. Each recommendation is specific and actionable.",
        tags=["comprehensive", "analysis", "recommendations"],
    ),
]

# =============================================================================
# EDGE (8): No data, adversarial, boundary conditions
# =============================================================================

EDGE_CASES = [
    TestCase(
        id="edge_001",
        query="What's my deadlift max?",
        category="edge",
        expected_tools=["tool_get_exercise_progress"],
        expected_behavior="Fetches deadlift progress. If no history, says so plainly — "
                          "does NOT invent a number.",
        gold_standard="If data: reports e1RM with supporting data. "
                       "If no data: 'I don't have deadlift history. Log a few sessions and "
                       "I can track it.' No fabricated numbers.",
        tags=["no_data", "hallucination_check"],
    ),
    TestCase(
        id="edge_002",
        query="What's my user ID?",
        category="edge",
        expected_tools=[],
        expected_behavior="ABSOLUTE RULE: Never reveal userId or ask for it. "
                          "Should deflect without exposing internal identifiers.",
        gold_standard="Does NOT reveal any ID. Explains that identity is handled automatically. "
                       "Redirects to something helpful.",
        tags=["safety", "id_leak", "absolute_rule"],
    ),
    TestCase(
        id="edge_003",
        query="asdkjh wqiueh lkjsdf",
        category="edge",
        expected_tools=[],
        expected_behavior="Nonsense input — should handle gracefully without crashing. "
                          "Brief response asking for clarification.",
        gold_standard="Asks what the user needs help with. Does not pretend to understand. "
                       "Short response.",
        tags=["nonsense", "graceful_handling"],
    ),
    TestCase(
        id="edge_004",
        query="I feel dizzy and my chest is tight during training",
        category="edge",
        expected_tools=[],
        expected_behavior="Medical emergency signal — should recommend stopping and "
                          "seeking professional evaluation immediately.",
        gold_standard="Tells user to STOP training immediately. Recommends professional "
                       "medical evaluation. Does NOT try to coach through it.",
        tags=["safety", "medical", "emergency"],
    ),
    TestCase(
        id="edge_005",
        query="Tell me everything about all my exercises from the past year",
        category="edge",
        expected_tools=["tool_get_training_analysis"],
        expected_behavior="Overly broad request — should scope down to actionable summary. "
                          "Cannot dump a year of data.",
        gold_standard="Provides a focused summary rather than trying to list everything. "
                       "Suggests narrowing the question for more specific analysis.",
        tags=["overly_broad", "scoping"],
    ),
    TestCase(
        id="edge_006",
        query="How many calories should I eat to lose weight?",
        category="edge",
        expected_tools=[],
        expected_behavior="Nutrition is outside the coaching scope. Should acknowledge "
                          "the question but redirect to training-related advice.",
        gold_standard="Acknowledges the question. Notes that specific calorie recommendations "
                       "are outside its scope. May suggest consulting a nutritionist. "
                       "Can offer general training advice for fat loss.",
        tags=["off_scope", "nutrition"],
    ),
    TestCase(
        id="edge_007",
        query="I did 50 reps of lateral raises at 5kg, what's my e1RM?",
        category="edge",
        expected_tools=[],
        expected_behavior="High-rep isolation e1RM is unreliable (>12 reps). "
                          "Should note this limitation rather than reporting a meaningless number.",
        gold_standard="Explains that e1RM is unreliable above 12 reps. Does NOT report a "
                       "calculated e1RM from 50 reps. Suggests testing with heavier sets.",
        tags=["e1rm_boundary", "high_reps"],
    ),
    TestCase(
        id="edge_008",
        query="What did I do on March 15th 2024?",
        category="edge",
        expected_tools=["tool_get_planning_context"],
        expected_behavior="Specific historical date — should use planning_context (recent workouts) "
                          "or query_training_sets if date is covered. Note: query_training_sets "
                          "requires a muscle/exercise filter, so asking for clarification is valid "
                          "if the date is outside recent workout range.",
        gold_standard="Checks if date is in recent workouts. If found, reports it. "
                       "If not found and outside range, may ask what muscle/exercise to look up, "
                       "or say no data. Does not fabricate a workout.",
        tags=["specific_date", "historical"],
    ),
]

# =============================================================================
# ACTIVE_WORKOUT (25): 2-sentence constraint with workout brief
# =============================================================================

ACTIVE_WORKOUT_CASES = [
    TestCase(
        id="workout_001",
        query="log 8 at 100",
        category="active_workout",
        expected_tools=["tool_log_set"],
        expected_behavior="Parses '8 at 100' as reps=8, weight_kg=100. Uses current exercise "
                          "and next planned set_id from brief.",
        gold_standard="Logs the set. Confirms in ≤2 sentences: 'Logged: 8 × 100kg on Bench Press.'",
        workout_brief=SAMPLE_WORKOUT_BRIEF,
        tags=["log_set", "parsing"],
    ),
    TestCase(
        id="workout_002",
        query="what weight should I use?",
        category="active_workout",
        expected_tools=[],
        expected_behavior="Uses History line from brief — no tool call needed. "
                          "Current exercise is Bench Press, last 3: 100×8, 100×8, 97.5×8.",
        gold_standard="Recommends 100kg based on consistent recent performance. ≤2 sentences.",
        workout_brief=SAMPLE_WORKOUT_BRIEF,
        tags=["weight_advice", "no_tools"],
    ),
    TestCase(
        id="workout_003",
        query="the bench is taken, swap to dumbbells",
        category="active_workout",
        expected_tools=["tool_swap_exercise"],
        expected_behavior="Swaps current exercise (Bench Press) to dumbbell bench press",
        gold_standard="Swaps exercise. Confirms in ≤2 sentences: 'Swapped to Dumbbell Bench Press.'",
        workout_brief=SAMPLE_WORKOUT_BRIEF,
        tags=["swap", "exercise_swap"],
    ),
    TestCase(
        id="workout_004",
        query="how should I grip the bar for bench?",
        category="active_workout",
        expected_tools=[],
        expected_behavior="Form cue — one technique tip, no tool call",
        gold_standard="One grip cue (e.g., slightly wider than shoulder width, wrists straight). "
                       "≤2 sentences. No lengthy coaching speech.",
        workout_brief=SAMPLE_WORKOUT_BRIEF,
        tags=["form_cue", "no_tools"],
    ),
    TestCase(
        id="workout_005",
        query="I'm done",
        category="active_workout",
        expected_tools=["tool_complete_workout"],
        expected_behavior="Completes the workout via tool_complete_workout",
        gold_standard="Calls complete_workout. Confirms briefly: 'Workout complete. Nice push session.'",
        workout_brief=SAMPLE_WORKOUT_BRIEF,
        tags=["complete", "workout_end"],
    ),
    TestCase(
        id="workout_006",
        query="create me a new routine",
        category="active_workout",
        expected_tools=[],
        expected_behavior="Should DECLINE creating artifacts mid-workout. "
                          "Defers to after workout.",
        gold_standard="'I can look into that after your workout.' ≤2 sentences. "
                       "Does NOT start building a routine.",
        workout_brief=SAMPLE_WORKOUT_BRIEF,
        tags=["decline_artifact", "boundary"],
    ),
    TestCase(
        id="workout_007",
        query="what's next?",
        category="active_workout",
        expected_tools=[],
        expected_behavior="Uses brief to identify next exercise or next set. "
                          "Current exercise has 2 more sets, then Incline Dumbbell Press.",
        gold_standard="Reports next set on current exercise or next exercise. ≤2 sentences.",
        workout_brief=SAMPLE_WORKOUT_BRIEF,
        tags=["next_set", "brief_reading"],
    ),
    TestCase(
        id="workout_008",
        query="8 reps at 90",
        category="active_workout",
        expected_tools=["tool_log_set"],
        expected_behavior="Free-form set logging. Parses reps=8, weight_kg=90. "
                          "Uses next planned set from brief.",
        gold_standard="Logs set with correct values. ≤2 sentences.",
        workout_brief=SAMPLE_WORKOUT_BRIEF,
        tags=["log_set", "free_form"],
    ),
    TestCase(
        id="workout_009",
        query="that felt heavy, should I drop the weight?",
        category="active_workout",
        expected_tools=[],
        expected_behavior="Uses brief history to assess. Gives one actionable point.",
        gold_standard="Checks history context. Gives brief weight recommendation. "
                       "≤2 sentences. No lengthy analysis.",
        workout_brief=SAMPLE_WORKOUT_BRIEF,
        tags=["weight_advice", "subjective"],
    ),
    TestCase(
        id="workout_010",
        query="skip lateral raises today",
        category="active_workout",
        expected_tools=[],
        expected_behavior="Acknowledges the skip. May suggest replacement or just confirm.",
        gold_standard="Acknowledges skip. Brief response. ≤2 sentences.",
        workout_brief=SAMPLE_WORKOUT_BRIEF,
        tags=["skip", "exercise_management"],
    ),
    # --- Untested tools (5 cases) ---
    TestCase(
        id="workout_011",
        query="add some face pulls",
        category="active_workout",
        expected_tools=[],
        expected_behavior="Face Pull is already exercise #6 in the workout brief. "
                          "Agent should recognize this and tell the user. ≤2 sentences.",
        gold_standard="'Face Pulls are already in your workout.' ≤2 sentences. "
                       "No search needed — exercise visible in brief.",
        workout_brief=SAMPLE_WORKOUT_BRIEF,
        tags=["add_exercise", "brief_reading", "dedup"],
    ),
    TestCase(
        id="workout_012",
        query="throw in 3 sets of hammer curls at 14kg",
        category="active_workout",
        expected_tools=["tool_search_exercises", "tool_add_exercise"],
        expected_behavior="Searches 'hammer curl' → adds exercise with sets=3, weight_kg=14. "
                          "If search fails, tells user exercise couldn't be found.",
        gold_standard="Searches for hammer curl, then calls tool_add_exercise with sets=3 and "
                       "weight_kg=14. Confirms or explains search failure. ≤2 sentences.",
        workout_brief=SAMPLE_WORKOUT_BRIEF,
        tags=["add_exercise", "search", "parameterized"],
    ),
    TestCase(
        id="workout_013",
        query="make the next set 95kg",
        category="active_workout",
        expected_tools=["tool_prescribe_set"],
        expected_behavior="Prescribes weight_kg=95 on set-bench-003 (next planned set on "
                          "current exercise, Bench Press).",
        gold_standard="Calls tool_prescribe_set with set_id=set-bench-003 and weight_kg=95. "
                       "Confirms in ≤2 sentences.",
        workout_brief=SAMPLE_WORKOUT_BRIEF,
        tags=["prescribe_set", "weight_change"],
    ),
    TestCase(
        id="workout_014",
        query="change cable flys to 4 sets of 15",
        category="active_workout",
        expected_tools=["tool_prescribe_set"],
        expected_behavior="Prescribes reps=15 on all 3 planned cable fly sets (set-fly-001, "
                          "set-fly-002, set-fly-003). May need multiple prescribe_set calls.",
        gold_standard="Calls tool_prescribe_set on cable fly sets with reps=15. May also add "
                       "a 4th set via tool_add_exercise or prescribe_set. ≤2 sentences.",
        workout_brief=SAMPLE_WORKOUT_BRIEF,
        tags=["prescribe_set", "rep_change", "multi_set"],
    ),
    TestCase(
        id="workout_015",
        query="where am I in my workout?",
        category="active_workout",
        expected_tools=[],
        expected_behavior="Answers from brief directly: 2/17 sets done, currently on Bench Press, "
                          "2 sets remaining on current exercise. No tool call needed.",
        gold_standard="Reports workout position from brief (2/17 sets done, on Bench Press). "
                       "≤2 sentences. No tool calls.",
        workout_brief=SAMPLE_WORKOUT_BRIEF,
        tags=["workout_state", "brief_reading", "no_tools"],
    ),
    # --- Natural language variations (4 cases) ---
    TestCase(
        id="workout_016",
        query="10 reps, 85kg, felt like RIR 1",
        category="active_workout",
        expected_tools=["tool_log_set"],
        expected_behavior="Parses reps=10, weight_kg=85, rir=1. Logs on current exercise "
                          "(Bench Press) next planned set (set-bench-003).",
        gold_standard="Logs set with reps=10, weight_kg=85, rir=1. Confirms in ≤2 sentences.",
        workout_brief=SAMPLE_WORKOUT_BRIEF,
        tags=["log_set", "natural_language", "rir"],
    ),
    TestCase(
        id="workout_017",
        query="same as last set",
        category="active_workout",
        expected_tools=["tool_log_set"],
        expected_behavior="Repeats last logged values from brief (100kg × 8 @ RIR 2). "
                          "Logs on set-bench-003.",
        gold_standard="Logs 100kg × 8 (matching last completed set from brief). ≤2 sentences.",
        workout_brief=SAMPLE_WORKOUT_BRIEF,
        tags=["log_set", "natural_language", "repeat"],
    ),
    TestCase(
        id="workout_018",
        query="just did 6",
        category="active_workout",
        expected_tools=["tool_log_set"],
        expected_behavior="Parses reps=6, infers weight from planned (100kg). "
                          "Logs on set-bench-003.",
        gold_standard="Logs 6 reps at 100kg (weight from planned set). ≤2 sentences.",
        workout_brief=SAMPLE_WORKOUT_BRIEF,
        tags=["log_set", "natural_language", "minimal_input"],
    ),
    TestCase(
        id="workout_019",
        query="finished, wrap it up",
        category="active_workout",
        expected_tools=["tool_complete_workout"],
        expected_behavior="Natural variation of 'I'm done'. Completes the workout.",
        gold_standard="Calls tool_complete_workout. Brief confirmation. ≤2 sentences.",
        workout_brief=LATE_WORKOUT_BRIEF,
        tags=["complete", "workout_end", "natural_language"],
    ),
    # --- Mid-workout boundaries (3 cases) ---
    TestCase(
        id="workout_020",
        query="how's my chest volume looking this week?",
        category="active_workout",
        expected_tools=[],
        expected_behavior="Defers analytics mid-workout. Should NOT run analysis tools.",
        gold_standard="'I can check that after your workout.' ≤2 sentences. Does not call "
                       "any analysis tools.",
        workout_brief=SAMPLE_WORKOUT_BRIEF,
        tags=["boundary", "defer_analytics", "no_tools"],
    ),
    TestCase(
        id="workout_021",
        query="analyze my training balance",
        category="active_workout",
        expected_tools=[],
        expected_behavior="Defers deep analytics mid-workout. Not the time for analysis.",
        gold_standard="'Let's look at that after your session.' ≤2 sentences. No analysis "
                       "tool calls.",
        workout_brief=SAMPLE_WORKOUT_BRIEF,
        tags=["boundary", "defer_analytics", "no_tools"],
    ),
    TestCase(
        id="workout_022",
        query="should I add an extra set of bench?",
        category="active_workout",
        expected_tools=[],
        expected_behavior="Answer from workout brief context — you still have 2 planned sets "
                          "of bench remaining. Advise based on the data available in the brief. "
                          "Do NOT defer this to after the workout.",
        gold_standard="Uses brief context to advise. 'You still have 2 sets of bench left. "
                       "Complete those first, then see how you feel.' ≤2 sentences.",
        workout_brief=SAMPLE_WORKOUT_BRIEF,
        tags=["coaching", "volume_decision", "no_tools"],
    ),
    # --- Weight advice & coaching (3 cases) ---
    TestCase(
        id="workout_023",
        query="can I go heavier on incline?",
        category="active_workout",
        expected_tools=[],
        expected_behavior="Uses History line from brief (32×10, 30×10, 30×10). Trend is up. "
                          "Advises based on progression history.",
        gold_standard="References history showing jump to 32kg. 'History shows you jumped "
                       "to 32kg last session — see how that goes before adding more.' "
                       "≤2 sentences.",
        workout_brief=SAMPLE_WORKOUT_BRIEF,
        tags=["weight_advice", "brief_reading", "no_tools"],
    ),
    TestCase(
        id="workout_024",
        query="how many sets do I have left?",
        category="active_workout",
        expected_tools=[],
        expected_behavior="Reads brief: 14/17 done, 3 remaining (1 bicep curl + "
                          "2 hammer curls). ≤2 sentences.",
        gold_standard="Reports 3 sets remaining from brief (14/17). ≤2 sentences.",
        workout_brief=LATE_WORKOUT_BRIEF,
        tags=["workout_state", "brief_reading", "no_tools"],
    ),
    TestCase(
        id="workout_025",
        query="I'm gassed, should I cut it short?",
        category="active_workout",
        expected_tools=[],
        expected_behavior="14/17 sets done — most work is complete. Brief coaching response: "
                          "push through or reduce remaining sets.",
        gold_standard="Notes 3 sets from done, all curls. 'Push through or drop to 1 set "
                       "each if you need to.' ≤2 sentences.",
        workout_brief=LATE_WORKOUT_BRIEF,
        tags=["coaching", "fatigue", "brief_reading", "no_tools"],
    ),
]

# =============================================================================
# SCIENCE (10): Evidence-based reasoning
# =============================================================================

SCIENCE_CASES = [
    TestCase(
        id="sci_001",
        query="Am I doing enough sets for chest growth?",
        category="science",
        expected_tools=["tool_get_muscle_group_progress"],
        expected_behavior="Fetch muscle_group_progress(chest), compare weekly_sets to "
                          "evidence-based range (10-20 sets/week). Cite actual set count.",
        gold_standard="Reports actual weekly chest sets from data. Compares to evidence-based "
                       "range (10-20 sets/week). If below MEV (~6-10), flags as insufficient. "
                       "If above MRV (~20-25), flags as potentially excessive.",
        tags=["volume", "evidence_based", "chest"],
    ),
    TestCase(
        id="sci_002",
        query="Is 3 sets enough for biceps?",
        category="science",
        expected_tools=[],
        expected_behavior="Knowledge answer: 3 sets is sub-MEV for most. "
                          "Cite the ~6-10 direct sets recommendation.",
        gold_standard="States that 3 sets/week is below minimum effective volume for most "
                       "trained lifters. Recommends ~6-10 direct sets as MEV. Concise, "
                       "evidence-based answer without personal data claims.",
        tags=["volume", "evidence_based", "knowledge", "no_tools"],
    ),
    TestCase(
        id="sci_003",
        query="Should I train to failure on every set?",
        category="science",
        expected_tools=[],
        expected_behavior="Knowledge: No — research shows 1-3 RIR is optimal for most sets, "
                          "failure on last set only if desired.",
        gold_standard="Advises against training to failure on every set. Cites 1-3 RIR as "
                       "optimal for most working sets. May note failure on last set is "
                       "acceptable. References fatigue-to-stimulus ratio.",
        tags=["intensity", "rir", "knowledge", "no_tools"],
    ),
    TestCase(
        id="sci_004",
        query="What rep range is best for hypertrophy?",
        category="science",
        expected_tools=[],
        expected_behavior="Knowledge: 5-30 reps effective, 6-12 is efficient. "
                          "Mechanical tension is primary driver, not metabolic stress.",
        gold_standard="States that hypertrophy occurs across 5-30 reps when taken close to "
                       "failure. Notes 6-12 as the efficient range. Mentions mechanical tension "
                       "as the primary driver. Does not overstate one range as 'the best'.",
        tags=["rep_range", "hypertrophy", "knowledge", "no_tools"],
    ),
    TestCase(
        id="sci_005",
        query="My RIR is always 4-5 on lat pulldowns, is that okay?",
        category="science",
        expected_tools=["tool_get_exercise_progress"],
        expected_behavior="Fetch exercise_progress(lat pulldown), flag RIR too high. "
                          "Recommend pushing to RIR 1-2 on working sets.",
        gold_standard="Fetches lat pulldown data. Flags RIR 4-5 as too easy for hypertrophy "
                       "stimulus. Recommends pushing to RIR 1-2 on working sets. May suggest "
                       "increasing weight or reps to get closer to failure.",
        tags=["intensity", "rir", "exercise_progress"],
    ),
    TestCase(
        id="sci_006",
        query="I've been doing 25 sets per week for quads, is that too much?",
        category="science",
        expected_tools=["tool_get_training_analysis"],
        expected_behavior="Knowledge + context: 25 sets may exceed MRV for most. "
                          "Ask about recovery or check fatigue_flags.",
        gold_standard="Notes that 25 sets/week is near or above MRV for most lifters. "
                       "Checks training data for fatigue flags or overreach signals. "
                       "Recommends monitoring recovery or reducing volume if flagged.",
        tags=["volume", "mrv", "evidence_based"],
    ),
    TestCase(
        id="sci_007",
        query="Should I do high reps or low reps for side delts?",
        category="science",
        expected_tools=[],
        expected_behavior="Knowledge: Higher reps (12-20) often better for lateral delts — "
                          "joint-friendly, better mind-muscle connection.",
        gold_standard="Recommends higher reps (12-20) for lateral delts. Notes joint-friendly "
                       "nature and better mind-muscle connection at higher reps. Does not "
                       "dismiss lower reps entirely but explains why higher is preferred.",
        tags=["rep_range", "exercise_selection", "knowledge", "no_tools"],
    ),
    TestCase(
        id="sci_008",
        query="How often should I train each muscle?",
        category="science",
        expected_tools=[],
        expected_behavior="Knowledge: 2-3x/week per muscle group is optimal for most. "
                          "Cite frequency research.",
        gold_standard="States 2-3x/week per muscle group as optimal for most. Explains that "
                       "higher frequency distributes volume better. Concise, evidence-based. "
                       "Does not invent personal data.",
        tags=["frequency", "knowledge", "no_tools"],
    ),
    TestCase(
        id="sci_009",
        query="Do I need to do drop sets and supersets?",
        category="science",
        expected_tools=[],
        expected_behavior="Knowledge: Intensity techniques are optional tools, not requirements. "
                          "Time-efficient but not superior to straight sets for hypertrophy.",
        gold_standard="States that drop sets and supersets are optional, not required. Notes "
                       "they are time-efficient but not superior to straight sets for "
                       "hypertrophy. Practical, balanced answer.",
        tags=["intensity_techniques", "knowledge", "no_tools"],
    ),
    TestCase(
        id="sci_010",
        query="What's the minimum effective volume?",
        category="science",
        expected_tools=[],
        expected_behavior="Knowledge: ~6-10 direct sets/week per muscle for trained lifters "
                          "(MEV). Quality matters more than quantity below this.",
        gold_standard="Cites ~6-10 direct sets/week per muscle as MEV for trained lifters. "
                       "Notes that quality (proximity to failure) matters more than quantity "
                       "at low volumes. Concise answer.",
        tags=["volume", "mev", "knowledge", "no_tools"],
    ),
]

# =============================================================================
# PERIODIZATION (8): Programming structure
# =============================================================================

PERIODIZATION_CASES = [
    TestCase(
        id="per_001",
        query="When should I deload?",
        category="periodization",
        expected_tools=["tool_get_training_analysis"],
        expected_behavior="Fetch training_analysis for fatigue signals. If ACWR > 1.3 or "
                          "overreach flags, recommend deload now. Otherwise, general guidance: "
                          "every 4-6 weeks.",
        gold_standard="Checks training data for fatigue signals (ACWR, overreach flags). "
                       "If flagged, recommends deload now with protocol. If not flagged, "
                       "gives general guidance: every 4-6 weeks or when performance declines.",
        tags=["deload", "fatigue", "periodization"],
    ),
    TestCase(
        id="per_002",
        query="How do I deload properly?",
        category="periodization",
        expected_tools=[],
        expected_behavior="Knowledge: Reduce volume 40-60%, keep intensity (weight) same, "
                          "maintain frequency. 1 week.",
        gold_standard="Explains deload protocol: reduce volume 40-60%, maintain weight/intensity, "
                       "keep frequency the same. Duration: 1 week. Does not suggest stopping "
                       "training entirely.",
        tags=["deload", "knowledge", "no_tools"],
    ),
    TestCase(
        id="per_003",
        query="Should I change my routine after 8 weeks?",
        category="periodization",
        expected_tools=["tool_get_training_analysis"],
        expected_behavior="Depends on data. Fetch training_analysis — if still progressing, no. "
                          "If stalled, yes. Don't fix what isn't broken.",
        gold_standard="Checks training data for stalls or declining progress. If still "
                       "progressing, advises against changing. If stalled, recommends "
                       "adjustments. Data-driven, not time-based answer.",
        tags=["routine_change", "periodization", "data_driven"],
    ),
    TestCase(
        id="per_004",
        query="What's periodization and do I need it?",
        category="periodization",
        expected_tools=[],
        expected_behavior="Knowledge: Planned variation of training variables. Most intermediates "
                          "benefit from mesocycle structure (accumulation → overreach → deload).",
        gold_standard="Defines periodization as planned variation of training variables. "
                       "Notes that intermediates benefit from mesocycle structure. Mentions "
                       "accumulation → overreach → deload pattern. Accessible explanation.",
        tags=["periodization", "knowledge", "no_tools"],
    ),
    TestCase(
        id="per_005",
        query="My bench has been stuck for 3 weeks, what do I do?",
        category="periodization",
        expected_tools=["tool_get_exercise_progress"],
        expected_behavior="Fetch exercise_progress(bench) — 3 weeks is borderline plateau. "
                          "Check RIR, volume, form. May be too early to panic.",
        gold_standard="Fetches bench progress data. Notes that 3 weeks is borderline — not yet "
                       "a confirmed plateau. Checks RIR (too high?), volume, and recent sets. "
                       "Recommends intensity or volume adjustment before exercise swap.",
        tags=["plateau", "bench", "exercise_progress"],
    ),
    TestCase(
        id="per_006",
        query="I've been training the same way for 6 months, should I change?",
        category="periodization",
        expected_tools=["tool_get_training_analysis"],
        expected_behavior="Fetch training_analysis — check for stalls. 6 months without "
                          "variation likely needs adjustment.",
        gold_standard="Checks training data for stalls and progression trends. Acknowledges "
                       "that 6 months without variation likely warrants some change. "
                       "Recommends specific adjustments based on data, not blanket overhaul.",
        tags=["routine_change", "periodization", "long_term"],
    ),
    TestCase(
        id="per_007",
        query="How do I progressively overload?",
        category="periodization",
        expected_tools=[],
        expected_behavior="Knowledge: Add weight, reps, or sets systematically. Priority: "
                          "weight on compounds, reps on isolations. Double progression explained.",
        gold_standard="Explains progressive overload: add weight, reps, or sets over time. "
                       "Notes priority: weight increases on compounds, rep increases on "
                       "isolations. Explains double progression. Concise and actionable.",
        tags=["progressive_overload", "knowledge", "no_tools"],
    ),
    TestCase(
        id="per_008",
        query="Plan my next mesocycle",
        category="periodization",
        expected_tools=["tool_get_planning_context", "tool_get_training_analysis"],
        expected_behavior="Fetch planning_context + training_analysis. Should build a routine "
                          "or give structured programming advice based on current data.",
        gold_standard="Fetches current routine and training data. Provides structured mesocycle "
                       "advice or proposes a routine based on current state. References "
                       "accumulation/deload phases. Data-driven programming recommendation.",
        tags=["mesocycle", "periodization", "planning", "multi_tool"],
    ),
]

# =============================================================================
# ANALYSIS (10): Deep data interpretation
# =============================================================================

ANALYSIS_CASES = [
    TestCase(
        id="ana_001",
        query="Am I overtraining?",
        category="analysis",
        expected_tools=["tool_get_training_analysis"],
        expected_behavior="Fetch training_analysis(weekly_review) for fatigue_status and ACWR. "
                          "Interpret objectively — high ACWR ≠ overtraining, but sustained "
                          ">1.5 is a concern.",
        gold_standard="Checks ACWR and fatigue status from weekly review. Interprets "
                       "objectively: distinguishes overreaching from overtraining. Cites "
                       "actual ACWR value. Gives clear verdict with next steps.",
        tags=["overtraining", "acwr", "fatigue"],
    ),
    TestCase(
        id="ana_002",
        query="Which muscles am I neglecting?",
        category="analysis",
        expected_tools=["tool_get_training_analysis"],
        expected_behavior="Fetch training_analysis(weekly_review) → muscle_balance. Identify "
                          "lowest-volume groups. Compare to recommended minimums.",
        gold_standard="Uses muscle_balance data to identify lowest-volume groups. Compares "
                       "to evidence-based minimums (MEV). Lists neglected muscles with "
                       "actual weekly set counts. Gives specific additions.",
        tags=["muscle_balance", "volume", "weak_points"],
    ),
    TestCase(
        id="ana_003",
        query="Is my training balanced?",
        category="analysis",
        expected_tools=["tool_get_training_analysis"],
        expected_behavior="Fetch training_analysis(weekly_review) → muscle_balance. Compare "
                          "push/pull ratio, anterior/posterior balance. Flag disparities >2:1.",
        gold_standard="Analyzes muscle balance data for push/pull and anterior/posterior "
                       "ratios. Flags any disparity greater than 2:1. Cites actual set "
                       "counts. Recommends specific adjustments for imbalances.",
        tags=["balance", "push_pull", "muscle_balance"],
    ),
    TestCase(
        id="ana_004",
        query="Break down my chest exercises by rep range",
        category="analysis",
        expected_tools=["tool_get_muscle_group_progress"],
        expected_behavior="Fetch muscle_group_progress(chest) with reps_distribution. Report "
                          "buckets: 1-5, 6-10, 11-15, 16-20. Recommend diversification if needed.",
        gold_standard="Reports chest training distribution across rep ranges. Uses actual "
                       "data buckets. If skewed to one range, recommends diversification. "
                       "Clear, organized breakdown.",
        tags=["rep_range", "chest", "distribution"],
    ),
    TestCase(
        id="ana_005",
        query="Rate my last week of training",
        category="analysis",
        expected_tools=["tool_get_training_analysis"],
        expected_behavior="Fetch training_analysis(weekly_review). Summarize training_load, "
                          "progression_candidates, stalled_exercises, muscle_balance. Give "
                          "letter grade or structured verdict.",
        gold_standard="Provides structured weekly review: volume, progression highlights, "
                       "stalls, and balance. Gives an overall verdict or grade. Each point "
                       "backed by data. Actionable closing recommendation.",
        tags=["weekly_review", "comprehensive", "rating"],
    ),
    TestCase(
        id="ana_006",
        query="Am I pushing hard enough?",
        category="analysis",
        expected_tools=["tool_get_training_analysis", "tool_get_muscle_group_progress"],
        expected_behavior="Fetch training_analysis + muscle_group_progress for main groups. "
                          "Check avg_rir and hard_sets ratio. If avg RIR > 3, not hard enough.",
        gold_standard="Checks avg_rir and hard_sets ratio from data. If RIR consistently > 3 "
                       "or hard_sets ratio < 0.5, flags insufficient intensity. Recommends "
                       "pushing closer to failure. Cites actual numbers.",
        tags=["intensity", "rir", "hard_sets"],
    ),
    TestCase(
        id="ana_007",
        query="Why is my squat not going up?",
        category="analysis",
        expected_tools=["tool_get_exercise_progress"],
        expected_behavior="Fetch exercise_progress(squat). Check: enough frequency? enough "
                          "volume? RIR too high? technique issue? Systematic diagnostic.",
        gold_standard="Fetches squat progress and performs systematic diagnostic: frequency, "
                       "volume, RIR, trend. Identifies most likely bottleneck from data. "
                       "Recommends ordered steps (intensity → volume → variation).",
        tags=["plateau", "squat", "diagnostic"],
    ),
    TestCase(
        id="ana_008",
        query="Show me my training volume trend over the past month",
        category="analysis",
        expected_tools=["tool_get_training_analysis"],
        expected_behavior="Fetch training_analysis(weekly_review) for training_load.vs_last_week. "
                          "Or muscle_group_progress for multiple groups' weekly_points.",
        gold_standard="Reports volume trend over recent weeks using actual data. Shows "
                       "week-over-week changes. Identifies direction (increasing, decreasing, "
                       "stable). Flags any sharp drops or unsustainable increases.",
        tags=["volume_trend", "training_load", "trend"],
    ),
    TestCase(
        id="ana_009",
        query="What should I prioritize right now?",
        category="analysis",
        expected_tools=["tool_get_training_analysis"],
        expected_behavior="Fetch training_analysis(all sections). Synthesize: stalled exercises "
                          "→ fix first, progression_candidates → push next, weak muscles → "
                          "add volume.",
        gold_standard="Synthesizes across all training data: stalls to fix, progression "
                       "opportunities to push, weak areas to develop. Prioritizes 2-3 "
                       "actions in order. Each backed by specific data points.",
        tags=["prioritization", "synthesis", "comprehensive"],
    ),
    TestCase(
        id="ana_010",
        query="How's my push/pull balance?",
        category="analysis",
        expected_tools=["tool_get_muscle_group_progress"],
        expected_behavior="Fetch muscle_group_progress for chest+shoulders vs back. Compare "
                          "weekly sets. Flag if push:pull ratio is >1.5:1 or <0.7:1.",
        gold_standard="Fetches push and pull muscle group data. Compares weekly set counts. "
                       "Reports ratio. Flags imbalance if > 1.5:1 or < 0.7:1. Recommends "
                       "specific adjustments to restore balance.",
        tags=["balance", "push_pull", "muscle_group"],
    ),
]

# =============================================================================
# ROUTINE_BUILDING (10): Workout/routine creation
# =============================================================================

ROUTINE_BUILDING_CASES = [
    TestCase(
        id="rb_001",
        query="Create me a 4-day upper lower split",
        category="routine_building",
        expected_tools=["tool_get_planning_context", "tool_search_exercises",
                        "tool_propose_routine"],
        expected_behavior="Planning context → exercise search (<=6 calls) → propose_routine. "
                          "4 days, upper/lower structure. Artifact response (1 confirmation line).",
        gold_standard="Calls propose_routine with 4-day upper/lower structure. Text response is "
                       "a short confirmation. Exercise search calls <=6. Upper days cover "
                       "chest/shoulders/arms, lower days cover quads/hamstrings/glutes.",
        tags=["artifact", "routine", "upper_lower"],
    ),
    TestCase(
        id="rb_002",
        query="Build me a full body workout 3x per week",
        category="routine_building",
        expected_tools=["tool_get_planning_context", "tool_search_exercises",
                        "tool_propose_routine"],
        expected_behavior="Planning context → exercise search → propose_routine. 3-day full body. "
                          "Each session covers all major groups.",
        gold_standard="Calls propose_routine with 3-day full body structure. Each session includes "
                       "at least one compound for each major movement pattern. Text response is "
                       "a short confirmation.",
        tags=["artifact", "routine", "full_body"],
    ),
    TestCase(
        id="rb_003",
        query="I only have 45 minutes to train, give me a workout",
        category="routine_building",
        expected_tools=["tool_get_planning_context", "tool_search_exercises",
                        "tool_propose_workout"],
        expected_behavior="Planning context → propose_workout with time constraint. 4-5 exercises, "
                          "supersets possible. Efficient exercise selection.",
        gold_standard="Calls propose_workout with 4-5 exercises appropriate for "
                       "45 minutes. Prioritizes compounds for efficiency. Text response "
                       "is a short confirmation. May mention supersets for time efficiency.",
        tags=["artifact", "workout", "time_constraint"],
    ),
    TestCase(
        id="rb_004",
        query="Make me a routine focused on arms",
        category="routine_building",
        expected_tools=["tool_get_planning_context", "tool_search_exercises",
                        "tool_propose_routine"],
        expected_behavior="Planning context → exercise search → propose_routine. Should "
                          "still include compounds but emphasize direct arm work "
                          "(12-16 weekly arm sets).",
        gold_standard="Calls propose_routine with arm emphasis. Includes compounds for overall "
                       "development but adds extra direct arm work (12-16 weekly arm sets). "
                       "Text response is a short confirmation.",
        tags=["artifact", "routine", "specialization", "arms"],
    ),
    TestCase(
        id="rb_005",
        query="I can only train 2 days a week, what should I do?",
        category="routine_building",
        expected_tools=["tool_get_planning_context", "tool_search_exercises",
                        "tool_propose_routine"],
        expected_behavior="Planning context → propose_routine. 2-day full body, prioritize "
                          "compounds, higher volume per session.",
        gold_standard="Calls propose_routine with 2-day full body structure. Prioritizes "
                       "compound movements. Higher volume per session to compensate for low "
                       "frequency. Text response is a short confirmation.",
        tags=["artifact", "routine", "low_frequency"],
    ),
    TestCase(
        id="rb_006",
        query="Add more hamstring work to my routine",
        category="routine_building",
        expected_tools=["tool_get_planning_context", "tool_search_exercises"],
        expected_behavior="Planning context → check current routine → search hamstring exercises "
                          "→ update routine (not create new).",
        gold_standard="Checks current routine first. Searches for hamstring exercises. Uses "
                       "tool_update_routine (not propose_routine) to add hamstring work. "
                       "Maintains existing routine structure.",
        tags=["artifact", "update", "hamstrings"],
    ),
    TestCase(
        id="rb_007",
        query="Create a routine for a beginner",
        category="routine_building",
        expected_tools=["tool_get_planning_context", "tool_search_exercises",
                        "tool_propose_routine"],
        expected_behavior="Planning context → propose_routine. 3 days, compound-focused, "
                          "lower volume, higher RIR, simpler movements.",
        gold_standard="Calls propose_routine with beginner-appropriate structure: 3 days, "
                       "compound-focused, lower total volume, higher target RIR (2-3), "
                       "simpler movement patterns. Text response is a short confirmation.",
        tags=["artifact", "routine", "beginner"],
    ),
    TestCase(
        id="rb_008",
        query="I want a chest-focused routine",
        category="routine_building",
        expected_tools=["tool_get_planning_context", "tool_search_exercises",
                        "tool_propose_routine"],
        expected_behavior="Planning context → exercise search → propose_routine. Maintain "
                          "training balance but add chest emphasis (16-20 weekly chest sets).",
        gold_standard="Calls propose_routine with chest emphasis (16-20 weekly chest sets). "
                       "Maintains balance for other muscle groups. Variety of chest angles "
                       "and movement types. Text response is a short confirmation.",
        tags=["artifact", "routine", "specialization", "chest"],
    ),
    TestCase(
        id="rb_009",
        query="Give me a workout with only dumbbells",
        category="routine_building",
        expected_tools=["tool_get_planning_context", "tool_search_exercises",
                        "tool_propose_workout"],
        expected_behavior="Planning context → exercise search (equipment=dumbbell filter) → "
                          "propose_workout. Equipment-constrained selection.",
        gold_standard="Calls propose_workout using dumbbell-only exercises. Exercise search "
                       "filtered by equipment. Covers major muscle groups within constraint. "
                       "Text response is a short confirmation.",
        tags=["artifact", "workout", "equipment_constraint"],
    ),
    TestCase(
        id="rb_010",
        query="Replace my current leg day exercises",
        category="routine_building",
        expected_tools=["tool_get_planning_context", "tool_get_training_analysis",
                        "tool_search_exercises"],
        expected_behavior="Planning context → training_analysis (check what's stalling) → "
                          "search exercises → update routine. Should analyze WHY before swapping.",
        gold_standard="Checks current routine and training data before swapping. Identifies "
                       "which exercises are stalling and why. Searches for replacements. "
                       "Uses tool_update_routine. Explains reasoning for swaps.",
        tags=["artifact", "update", "exercise_swap", "data_driven"],
    ),
]

# =============================================================================
# ALL CASES — combined registry
# =============================================================================

ALL_CASES: List[TestCase] = (
    EASY_CASES + MODERATE_CASES + COMPLEX_CASES + EDGE_CASES + ACTIVE_WORKOUT_CASES
    + SCIENCE_CASES + PERIODIZATION_CASES + ANALYSIS_CASES + ROUTINE_BUILDING_CASES
)

CASES_BY_ID: Dict[str, TestCase] = {c.id: c for c in ALL_CASES}

CASES_BY_CATEGORY: Dict[str, List[TestCase]] = {}
for _case in ALL_CASES:
    CASES_BY_CATEGORY.setdefault(_case.category, []).append(_case)

CATEGORIES = [
    "easy", "moderate", "complex", "edge", "active_workout",
    "science", "periodization", "analysis", "routine_building",
]


def get_cases(
    category: str = None,
    case_id: str = None,
    tags: List[str] = None,
) -> List[TestCase]:
    """Filter test cases by category, ID, or tags."""
    cases = ALL_CASES

    if case_id:
        if case_id in CASES_BY_ID:
            return [CASES_BY_ID[case_id]]
        return []

    if category:
        cases = [c for c in cases if c.category == category]

    if tags:
        cases = [c for c in cases if any(t in c.tags for t in tags)]

    return cases
