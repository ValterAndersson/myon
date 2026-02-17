"""Weekly review analyzer - comprehensive training progression analysis.

Data budget: ~35KB to LLM
- 12 weeks of analytics_rollups (~6KB): per-week totals + per-muscle breakdowns
- Top 10 exercise series (~18KB): weekly e1rm_max, volume, sets per exercise
- 8 muscle group series (~10KB): weekly sets/volume/hard_sets per group
- Active routine template names (~1KB): structure context

Model: gemini-2.5-pro (temperature=0.2)
Output: users/{uid}/weekly_reviews/{YYYY-WNN} (TTL 30 days)
"""

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.analyzers.base import BaseAnalyzer
from app.config import MODEL_PRO, TTL_REVIEWS
from app.firestore_client import get_db


class WeeklyReviewAnalyzer(BaseAnalyzer):
    """Generates comprehensive weekly training reviews."""

    def __init__(self):
        super().__init__(MODEL_PRO)

    def analyze(
        self, user_id: str, window_weeks: int = 12, week_ending: str = None
    ) -> Dict[str, Any]:
        """
        Generate weekly review for user.

        Args:
            user_id: User ID
            window_weeks: Number of weeks to analyze (default 12)
            week_ending: Week ending date YYYY-MM-DD (default: current week)

        Returns:
            Result dict with success status and review_id
        """
        if not week_ending:
            today = datetime.now(timezone.utc)
            days_until_sunday = (6 - today.weekday()) % 7
            week_ending = (today + timedelta(days=days_until_sunday)).strftime("%Y-%m-%d")

        self.log_event(
            "weekly_review_started",
            user_id=user_id,
            week_ending=week_ending,
            window_weeks=window_weeks,
        )

        db = get_db()

        # 1. Read 12 weeks of rollups (~6KB)
        rollups = self._read_rollups(db, user_id, weeks=window_weeks)

        # 2. Read top 10 exercise series by volume (~18KB)
        exercise_series = self._read_top_exercise_series(
            db, user_id, rollups, limit=10, weeks=window_weeks
        )

        # 3. Read 8 muscle group series (~10KB)
        muscle_group_series = self._read_muscle_group_series(
            db, user_id, weeks=window_weeks
        )

        # 4. Read active routine template names (~1KB)
        routine_context = self._read_routine_context(db, user_id)

        # 5. Build LLM input (~35KB total)
        llm_input = json.dumps({
            "week_ending": week_ending,
            "window_weeks": window_weeks,
            "rollups": rollups,
            "exercise_series": exercise_series,
            "muscle_group_series": muscle_group_series,
            "routine_context": routine_context,
        }, indent=2, default=str)

        # 6. Call LLM (Pro for comprehensive analysis)
        result = self.call_llm(
            self._get_system_prompt(), llm_input,
            required_keys=["summary", "training_load", "muscle_balance",
                           "exercise_trends"],
        )

        # 7. Write to weekly_reviews/{YYYY-WNN}
        iso_week = self._date_to_iso_week(week_ending)
        self._write_review(db, user_id, iso_week, week_ending, result)

        self.log_event(
            "weekly_review_completed",
            user_id=user_id,
            iso_week=iso_week,
        )

        return {"success": True, "review_id": iso_week}

    def _read_rollups(
        self, db, user_id: str, weeks: int
    ) -> List[Dict[str, Any]]:
        """Read weekly analytics rollups with per-muscle breakdowns."""
        rollups = []
        ref = (
            db.collection("users").document(user_id)
            .collection("analytics_rollups")
        )

        docs = ref.order_by("updated_at", direction="DESCENDING").limit(weeks).stream()

        for doc in docs:
            data = doc.to_dict()
            rollups.append({
                "week_id": doc.id,
                "workouts": data.get("workouts", 0),
                "total_sets": data.get("total_sets", 0),
                "total_reps": data.get("total_reps", 0),
                "total_weight": data.get("total_weight", 0),
                "hard_sets_total": data.get("hard_sets_total", 0),
                "low_rir_sets_total": data.get("low_rir_sets_total", 0),
                # Per-muscle-group breakdowns for balance analysis
                "hard_sets_per_muscle_group": data.get("hard_sets_per_muscle_group", {}),
                "weight_per_muscle_group": data.get("weight_per_muscle_group", {}),
            })

        return rollups

    def _read_top_exercise_series(
        self, db, user_id: str, rollups: List[Dict[str, Any]],
        limit: int, weeks: int
    ) -> List[Dict[str, Any]]:
        """Read top N exercise series by total volume from rollups.

        Each series doc has a 'weeks' map with weekly aggregate points.
        """
        # We can't easily rank by volume from rollups (they don't have per-exercise breakdown)
        # Instead, read all series docs and rank by recent volume
        ref = (
            db.collection("users").document(user_id)
            .collection("series_exercises")
        )

        # Read up to 30 docs and rank by total volume in last N weeks
        all_docs = ref.limit(30).stream()

        candidates = []
        for doc in all_docs:
            data = doc.to_dict()
            weeks_map = self.extract_weeks_map(data)

            sorted_weeks = sorted(weeks_map.keys(), reverse=True)[:weeks]

            total_volume = sum(
                weeks_map[wk].get("volume", 0) for wk in sorted_weeks
            )

            weekly_points = []
            for wk in sorted_weeks:
                raw = weeks_map[wk]
                weekly_points.append({
                    "week_start": wk,
                    "sets": raw.get("sets") or raw.get("set_count", 0),
                    "volume": raw.get("volume", 0),
                    "effective_volume": raw.get("effective_volume", 0),
                    "e1rm_max": raw.get("e1rm_max"),
                    "hard_sets": raw.get("hard_sets", 0),
                    "load_max": raw.get("load_max"),
                    "avg_rir": (
                        round(raw["rir_sum"] / raw["rir_count"], 1)
                        if raw.get("rir_count")
                        else None
                    ),
                })

            candidates.append({
                "exercise_id": doc.id,
                "exercise_name": data.get("exercise_name") or data.get("name"),
                "total_volume": total_volume,
                "weeks": weekly_points,
            })

        # Sort by total volume and take top N
        candidates.sort(key=lambda x: x["total_volume"], reverse=True)
        top = candidates[:limit]

        # Remove the ranking field from output
        for c in top:
            del c["total_volume"]

        return top

    def _read_muscle_group_series(
        self, db, user_id: str, weeks: int
    ) -> List[Dict[str, Any]]:
        """Read muscle group series for balance analysis.

        Each doc has a 'weeks' map with weekly aggregate points.
        """
        series = []
        ref = (
            db.collection("users").document(user_id)
            .collection("series_muscle_groups")
        )

        # Read all muscle group docs (typically 8-12)
        all_docs = ref.stream()

        for doc in all_docs:
            data = doc.to_dict()
            weeks_map = self.extract_weeks_map(data)

            sorted_weeks = sorted(weeks_map.keys(), reverse=True)[:weeks]

            weekly_points = []
            for wk in sorted_weeks:
                raw = weeks_map[wk]
                weekly_points.append({
                    "week_start": wk,
                    "sets": raw.get("sets") or raw.get("set_count", 0),
                    "volume": raw.get("volume", 0),
                    "effective_volume": raw.get("effective_volume", 0),
                    "hard_sets": raw.get("hard_sets", 0),
                    "avg_rir": (
                        round(raw["rir_sum"] / raw["rir_count"], 1)
                        if raw.get("rir_count")
                        else None
                    ),
                })

            series.append({
                "muscle_group": doc.id,
                "weeks": weekly_points,
            })

        return series[:8]  # Cap at 8 muscle groups

    def _read_routine_context(
        self, db, user_id: str
    ) -> Optional[Dict[str, Any]]:
        """Read active routine template names for structure context."""
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

        # Read template names only
        template_names = []
        for tid in template_ids[:8]:
            tdoc = (
                db.collection("users").document(user_id)
                .collection("templates").document(tid).get()
            )
            if tdoc.exists:
                template_names.append(tdoc.to_dict().get("name", tid))

        return {
            "routine_name": routine.get("name"),
            "frequency": routine.get("frequency"),
            "template_names": template_names,
        }

    def _write_review(
        self, db, user_id: str, iso_week: str,
        week_ending: str, result: Dict[str, Any]
    ) -> None:
        """Write review to weekly_reviews/{YYYY-WNN} with plan-specified schema."""
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=TTL_REVIEWS)

        doc_data = {
            "created_at": now,
            "expires_at": expires_at,
            "week_ending": week_ending,
            "summary": result.get("summary", ""),
            "training_load": result.get("training_load", {}),
            "muscle_balance": result.get("muscle_balance", []),
            "exercise_trends": result.get("exercise_trends", []),
            "progression_candidates": result.get("progression_candidates", []),
            "stalled_exercises": result.get("stalled_exercises", []),
        }

        ref = (
            db.collection("users").document(user_id)
            .collection("weekly_reviews")
        )
        ref.document(iso_week).set(doc_data)

    def _date_to_iso_week(self, date_str: str) -> str:
        """Convert YYYY-MM-DD to YYYY-WNN."""
        date = datetime.strptime(date_str, "%Y-%m-%d")
        iso = date.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"

    def _get_system_prompt(self) -> str:
        return """You are a training analyst providing a comprehensive weekly progression review.

Analyze the training data across a 12-week window. You have:
- Weekly rollups with total sets, volume, intensity metrics, and per-muscle-group breakdowns
- Top 10 exercises with weekly e1RM, volume, and set progression
- Muscle group series with weekly volume and intensity
- Active routine context (name, frequency, template names)

CRITICAL RULES:
- ONLY reference exercise names, IDs, and muscle groups that appear in the input data. NEVER invent data.
- Every numeric claim (e1RM, volume, sets, slopes) MUST be computed from the provided data.
- If fewer than 4 weeks of rollup data exist, state "limited history" in summary and do NOT output progression_candidates or stalled_exercises (too little data for reliable trend detection).
- e1rm_slope: compute as (latest_e1rm - earliest_e1rm) / weeks_analyzed. Unit is kg/week.
- current_weight in progression_candidates = the load_max from the most recent week in that exercise's series.
- exercise_id and exercise_name in outputs MUST match values from the input exercise_series.

Return JSON matching this schema EXACTLY:
{
  "summary": "2-3 sentence paragraph summarizing the training week in context of the window",
  "training_load": {
    "sessions": 4,
    "total_sets": 80,
    "total_volume": 45000,
    "vs_last_week": { "sets_delta": 5, "volume_delta": 2000 }
  },
  "muscle_balance": [
    {
      "muscle_group": "chest",
      "weekly_sets": 16,
      "trend": "increasing | stable | decreasing",
      "status": "optimal | undertrained | overtrained"
    }
  ],
  "exercise_trends": [
    {
      "exercise_id": "from input",
      "exercise_name": "from input",
      "trend": "improving | plateaued | declining",
      "e1rm_slope": 0.5,
      "weeks_analyzed": 12,
      "note": "Brief observation citing specific numbers"
    }
  ],
  "progression_candidates": [
    {
      "exercise_id": "from input",
      "exercise_name": "from input",
      "current_weight": 100,
      "suggested_weight": 102.5,
      "rationale": "Evidence from the data",
      "reasoning": "why this candidate qualifies for progression",
      "signals": ["e1rm_slope: +0.8 kg/week over 6 weeks", "consistent RIR 1.5-2.0"],
      "confidence": 0.0-1.0
    }
  ],
  "stalled_exercises": [
    {
      "exercise_id": "from input",
      "exercise_name": "from input",
      "weeks_stalled": 5,
      "suggested_action": "deload | swap | vary_rep_range",
      "rationale": "Evidence from the data",
      "reasoning": "why this exercise is stalled and why this action is suggested",
      "signals": ["e1RM flat at 65kg for 5 weeks", "avg RIR 1.5 (not an effort issue)"]
    }
  ]
}

For progression_candidates and stalled_exercises:
- "reasoning" explains the logic chain: which metrics triggered this, why the suggestion follows
- "signals" lists 2-4 key data points supporting the assessment, each a short phrase with numbers

Detection rules:
- training_load: Compute from the most recent week's rollup. vs_last_week compares rollups[0] to rollups[1].
- muscle_balance: Assess each group from muscle_group_series — average weekly hard_sets over the window.
  - optimal: 10-20 hard sets/week, undertrained: <10, overtrained: >20
- exercise_trends: Classify based on e1RM trajectory across the exercise's weekly points.
  - improving: e1rm_slope > 0.5 kg/week (compounds) or > 0.25 kg/week (isolation)
  - plateaued: e1rm_slope within ±0.25 kg/week for 4+ data points
  - declining: e1rm_slope < -0.5 kg/week
- progression_candidates: ONLY exercises with improving trend AND confidence > 0.7 AND at least 4 weeks of data.
  - Suggest 2.5% increase for compounds (exercises with load_max > 40kg), 5% for isolation.
- stalled_exercises: ONLY exercises plateaued or declining for 4+ consecutive weeks with data.
  - deload: if volume is high but e1RM flat
  - swap: if stalled > 6 weeks
  - vary_rep_range: if stuck in same rep range every week"""
