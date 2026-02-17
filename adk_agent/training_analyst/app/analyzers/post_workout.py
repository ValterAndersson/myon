"""Post-workout analyzer - immediate feedback after workout completion.

Data budget: ~8KB to LLM
- Trimmed workout (~1.5KB): exercise names + set summaries
- 4 weeks of rollups (~2KB): weekly totals
- Exercise series (~4KB): weekly points for exercises in this workout

Model: gemini-2.5-pro (temperature=0.2)
Output: users/{uid}/analysis_insights/{autoId} (TTL 7 days)
"""

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.analyzers.base import BaseAnalyzer
from app.config import MODEL_PRO, TTL_INSIGHTS
from app.firestore_client import get_db


class PostWorkoutAnalyzer(BaseAnalyzer):
    """Analyzes completed workouts against recent aggregated trends."""

    def __init__(self):
        super().__init__(MODEL_PRO)

    def analyze(self, user_id: str, workout_id: str) -> Dict[str, Any]:
        """
        Analyze a completed workout.

        Args:
            user_id: User ID
            workout_id: Completed workout document ID

        Returns:
            Result dict with success status and insight_id
        """
        self.log_event("post_workout_started", user_id=user_id, workout_id=workout_id)

        db = get_db()

        # 1. Read workout (trimmed to ~1.5KB)
        workout = self._read_workout_trimmed(db, user_id, workout_id)
        if not workout:
            raise ValueError(f"Workout {workout_id} not found for user {user_id}")

        # 2. Read 4 weeks of analytics rollups (~2KB)
        rollups = self._read_rollups(db, user_id, weeks=4)

        # 3. Read exercise series for exercises in this workout (~4KB)
        exercise_ids = [
            ex["exercise_id"] for ex in workout.get("exercises", [])
            if ex.get("exercise_id")
        ]
        series = self._read_exercise_series(db, user_id, exercise_ids, weeks=4)

        # 4. Build LLM input (~8KB total)
        llm_input = json.dumps({
            "workout": workout,
            "recent_rollups": rollups,
            "exercise_series": series,
        }, indent=2, default=str)

        # 5. Call LLM
        result = self.call_llm(
            self._get_system_prompt(), llm_input,
            required_keys=["summary", "highlights", "flags", "recommendations"],
        )

        # 6. Write to analysis_insights
        insight_id = self._write_insight(db, user_id, workout_id, workout, result)

        self.log_event(
            "post_workout_completed",
            user_id=user_id,
            workout_id=workout_id,
            insight_id=insight_id,
        )

        return {"success": True, "insight_id": insight_id}

    def _read_workout_trimmed(
        self, db, user_id: str, workout_id: str
    ) -> Optional[Dict[str, Any]]:
        """Read workout and trim to exercise summaries only (~1.5KB).

        NEVER passes raw set data to LLM. Extracts only:
        - Exercise names, IDs, working set count
        - Top weight, rep range, avg RIR, volume, e1RM
        - Workout-level analytics summary (if present)
        """
        doc = (
            db.collection("users").document(user_id)
            .collection("workouts").document(workout_id).get()
        )
        if not doc.exists:
            return None

        data = doc.to_dict()
        started = data.get("started_at") or data.get("start_time")
        ended = data.get("ended_at") or data.get("end_time")

        # Calculate duration
        duration_minutes = data.get("duration_minutes")
        if not duration_minutes and started and ended:
            try:
                delta = ended - started
                duration_minutes = round(delta.total_seconds() / 60)
            except Exception:
                duration_minutes = None

        # Extract date string
        workout_date = None
        if ended:
            try:
                workout_date = ended.strftime("%Y-%m-%d") if hasattr(ended, "strftime") else str(ended)[:10]
            except Exception:
                pass

        trimmed = {
            "workout_date": workout_date,
            "duration_minutes": duration_minutes,
            "exercises": [],
        }

        for ex in data.get("exercises", []):
            sets = ex.get("sets", [])
            # Filter to working sets only (exclude warmups)
            working_sets = [s for s in sets if not s.get("is_warmup")]
            if not working_sets:
                working_sets = sets

            weights = [s.get("weight_kg", 0) for s in working_sets if s.get("weight_kg")]
            reps_list = [s.get("reps", 0) for s in working_sets if s.get("reps")]
            rirs = [s.get("rir") for s in working_sets if s.get("rir") is not None]

            volume = sum(
                (s.get("weight_kg", 0) or 0) * (s.get("reps", 0) or 0)
                for s in working_sets
            )

            # e1RM from best set (Epley, reps <= 12)
            e1rm = None
            for s in working_sets:
                r = s.get("reps", 0) or 0
                w = s.get("weight_kg", 0) or 0
                if 0 < r <= 12 and w > 0:
                    est = round(w * (1 + r / 30), 1)
                    if e1rm is None or est > e1rm:
                        e1rm = est

            # Rep range string
            rep_range = None
            if reps_list:
                mn, mx = min(reps_list), max(reps_list)
                rep_range = str(mn) if mn == mx else f"{mn}-{mx}"

            trimmed["exercises"].append({
                "name": ex.get("exercise_name") or ex.get("name"),
                "exercise_id": ex.get("exercise_id"),
                "working_sets": len(working_sets),
                "top_weight_kg": max(weights) if weights else None,
                "rep_range": rep_range,
                "avg_rir": round(sum(rirs) / len(rirs), 1) if rirs else None,
                "volume": round(volume),
                "e1rm": e1rm,
            })

        # Include workout-level analytics summary if present
        analytics = data.get("analytics")
        if analytics:
            trimmed["analytics_summary"] = {
                "total_sets": analytics.get("total_sets"),
                "total_volume": analytics.get("total_volume") or analytics.get("total_weight"),
                "muscle_groups_hit": list(
                    (analytics.get("muscle_groups") or {}).keys()
                )[:10],
            }

        return trimmed

    def _read_rollups(
        self, db, user_id: str, weeks: int
    ) -> List[Dict[str, Any]]:
        """Read weekly analytics rollups (~500B each).

        Reads from users/{uid}/analytics_rollups ordered by doc ID desc.
        """
        rollups = []
        ref = (
            db.collection("users").document(user_id)
            .collection("analytics_rollups")
        )

        # Rollup doc IDs are week-start dates (YYYY-MM-DD) or yyyy-ww
        # Rollup doc IDs are week-start dates — fetch recent and sort in Python
        # (avoids needing a composite index on __name__)
        docs = ref.order_by("updated_at", direction="DESCENDING").limit(weeks).stream()

        for doc in docs:
            data = doc.to_dict()
            rollups.append({
                "week_id": doc.id,
                "workouts": data.get("workouts", 0),
                "total_sets": data.get("total_sets", 0),
                "total_weight": data.get("total_weight", 0),
                "hard_sets_total": data.get("hard_sets_total", 0),
                "low_rir_sets_total": data.get("low_rir_sets_total", 0),
            })

        return rollups

    def _read_exercise_series(
        self, db, user_id: str, exercise_ids: List[str], weeks: int
    ) -> List[Dict[str, Any]]:
        """Read exercise series weekly points for specific exercises.

        Each series doc has a 'weeks' map: { "YYYY-MM-DD": { sets, volume, e1rm_max, ... } }
        We extract only the last N weeks of data.
        """
        series = []
        ref = (
            db.collection("users").document(user_id)
            .collection("series_exercises")
        )

        for ex_id in exercise_ids[:15]:  # Cap to avoid oversized reads
            doc = ref.document(ex_id).get()
            if not doc.exists:
                continue

            data = doc.to_dict()
            weeks_map = self.extract_weeks_map(data)

            # Sort week keys descending, take last N
            sorted_weeks = sorted(weeks_map.keys(), reverse=True)[:weeks]

            weekly_points = []
            for wk in sorted_weeks:
                raw = weeks_map[wk]
                weekly_points.append({
                    "week_start": wk,
                    "sets": raw.get("sets") or raw.get("set_count", 0),
                    "volume": raw.get("volume", 0),
                    "e1rm_max": raw.get("e1rm_max"),
                    "hard_sets": raw.get("hard_sets", 0),
                    "load_max": raw.get("load_max"),
                    "avg_rir": (
                        round(raw["rir_sum"] / raw["rir_count"], 1)
                        if raw.get("rir_count")
                        else None
                    ),
                })

            series.append({
                "exercise_id": ex_id,
                "exercise_name": data.get("exercise_name") or data.get("name"),
                "weeks": weekly_points,
            })

        return series

    def _write_insight(
        self, db, user_id: str, workout_id: str,
        workout: Dict[str, Any], result: Dict[str, Any]
    ) -> str:
        """Write insight to analysis_insights with plan-specified schema."""
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=TTL_INSIGHTS)

        doc_data = {
            "type": "post_workout",
            "created_at": now,
            "expires_at": expires_at,
            "workout_id": workout_id,
            "workout_date": workout.get("workout_date"),
            "summary": result.get("summary", ""),
            "highlights": result.get("highlights", []),
            "flags": result.get("flags", []),
            "recommendations": result.get("recommendations", []),
        }

        ref = (
            db.collection("users").document(user_id)
            .collection("analysis_insights")
        )
        _, doc_ref = ref.add(doc_data)

        return doc_ref.id

    def _get_system_prompt(self) -> str:
        return """You are a training analyst providing post-workout feedback.

Analyze the completed workout in context of recent weekly aggregated trends.
Compare this session's volume, intensity (RIR), and estimated 1RMs against
the 4-week baseline from rollups and exercise series.

CRITICAL RULES:
- ONLY reference exercises, numbers, and data that appear in the input. NEVER invent or assume data.
- If fewer than 3 weeks of rollup data exist, say "early days — not enough history for trend analysis" in the summary. Do not claim stalls or trends.
- If exercise_series is empty for an exercise, skip trend analysis for it.
- Every numeric claim (e1RM, volume, sets) MUST come from the provided data.

Return JSON matching this schema EXACTLY:
{
  "summary": "2-3 sentence overview of the session",
  "highlights": [
    {
      "type": "pr | volume_up | consistency | intensity",
      "message": "Human-readable highlight referencing specific numbers",
      "exercise_id": "exercise ID from workout.exercises (or omit if workout-level)",
      "data": {}
    }
  ],
  "flags": [
    {
      "type": "stall | volume_drop | overreach | fatigue | form_concern",
      "severity": "info | warning | action",
      "message": "Human-readable flag with specific evidence",
      "muscle_group": "optional muscle group",
      "exercise_id": "exercise ID from the input (or omit)",
      "data": {}
    }
  ],
  "recommendations": [
    {
      "type": "progression | deload | swap | volume_adjust",
      "target": "exercise name or muscle group name FROM THE INPUT",
      "action": "concise next-step suggestion with specific numbers",
      "reasoning": "1-2 sentences: what data you evaluated, why this recommendation follows",
      "signals": ["e1RM stable at 125kg for 3 weeks", "avg RIR 2.0 across sets"],
      "confidence": 0.0-1.0
    }
  ]
}

For each recommendation:
- "action" must include specific numbers (weights, reps, percentages) from the input
- "reasoning" explains the logic chain: which metrics you compared, what threshold was met, why this change
- "signals" lists the 2-4 key data points that support this recommendation, each as a short phrase with numbers

Detection rules:
- PR: this session's e1RM exceeds the highest e1rm_max in exercise_series
- volume_up: this session's total_sets or volume > avg of rollup weeks
- stall: e1rm_max flat (±2%) across 3+ weeks in exercise_series
- volume_drop: this week's total_sets < 70% of rollup average
- overreach: avg_rir < 1.0 across multiple exercises while volume is high

Output limits: 2-4 highlights, 0-3 flags, 1-3 recommendations"""
