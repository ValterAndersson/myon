"""Daily brief analyzer - morning readiness assessment.

Data budget: ~4KB to LLM
- Next template summary (~1KB): name, exercise names, focus muscles
- 4 weeks of rollups with per-muscle hard sets (~2KB): proper ACWR calculation
- Latest analysis_insights if <48h old (~1KB): highlights/flags from last session

Model: gemini-2.5-flash (temperature=0.3)
Output: users/{uid}/daily_briefs/{YYYY-MM-DD} (TTL 7 days)
"""

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.analyzers.base import BaseAnalyzer
from app.config import MODEL_FLASH, TTL_BRIEFS
from app.firestore_client import get_db


class DailyBriefAnalyzer(BaseAnalyzer):
    """Generates daily readiness briefs based on aggregated data."""

    def __init__(self):
        super().__init__(MODEL_FLASH)

    def analyze(self, user_id: str) -> Dict[str, Any]:
        """
        Generate daily brief for user.

        Args:
            user_id: User ID

        Returns:
            Result dict with success status and brief date
        """
        self.log_event("daily_brief_started", user_id=user_id)

        db = get_db()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # 1. Read next template from active routine (~1KB)
        planned_workout = self._read_next_template(db, user_id)

        # 2. Read 4 weeks of rollups for proper ACWR (acute:chronic ratio) (~2KB)
        rollups = self._read_recent_rollups(db, user_id, weeks=4)

        # 3. Read latest analysis_insights if <48h old (~1KB)
        recent_insight = self._read_recent_insight(db, user_id)

        # 4. Build LLM input (~3KB total)
        llm_input = json.dumps({
            "date": today,
            "planned_workout": planned_workout,
            "recent_rollups": rollups,
            "last_workout_insight": recent_insight,
        }, indent=2, default=str)

        # 5. Call LLM (Flash for simpler analysis)
        result = self.call_llm(
            self._get_system_prompt(), llm_input, temperature=0.3,
            required_keys=["readiness", "readiness_summary"],
        )

        # 6. Write to daily_briefs/{YYYY-MM-DD}
        self._write_brief(db, user_id, today, planned_workout, result)

        self.log_event("daily_brief_completed", user_id=user_id, date=today)

        return {"success": True, "brief_id": today}

    def _read_next_template(
        self, db, user_id: str
    ) -> Optional[Dict[str, Any]]:
        """Read the next scheduled template (name + exercise names only)."""
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
        cursor = routine.get("cursor", 0)

        if not template_ids:
            return None

        next_template_id = template_ids[cursor % len(template_ids)]

        template_doc = (
            db.collection("users").document(user_id)
            .collection("templates").document(next_template_id).get()
        )
        if not template_doc.exists:
            return None

        template = template_doc.to_dict()
        exercises = template.get("exercises", [])

        # Extract focus muscles from exercises
        focus_muscles = set()
        for ex in exercises:
            for m in (ex.get("muscles", {}).get("primary", []) or []):
                focus_muscles.add(m)

        return {
            "template_id": next_template_id,
            "template_name": template.get("name"),
            "exercise_count": len(exercises),
            "focus_muscles": list(focus_muscles)[:6],
        }

    def _read_recent_rollups(
        self, db, user_id: str, weeks: int
    ) -> List[Dict[str, Any]]:
        """Read recent rollups with per-muscle breakdowns for ACWR.

        4 weeks enables proper acute:chronic workload ratio:
        - Acute = most recent week
        - Chronic = average of all 4 weeks
        - ACWR = acute / chronic
        """
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
                "total_weight": data.get("total_weight", 0),
                "hard_sets_total": data.get("hard_sets_total", 0),
                # Per-muscle breakdowns for fatigue_flags accuracy
                "hard_sets_per_muscle_group": data.get("hard_sets_per_muscle_group", {}),
            })

        return rollups

    def _read_recent_insight(
        self, db, user_id: str
    ) -> Optional[Dict[str, Any]]:
        """Read latest analysis_insights if <48h old."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=48)

        ref = (
            db.collection("users").document(user_id)
            .collection("analysis_insights")
        )

        docs = (
            ref.where("created_at", ">=", cutoff)
            .order_by("created_at", direction="DESCENDING")
            .limit(1)
            .stream()
        )

        for doc in docs:
            data = doc.to_dict()
            return {
                "summary": data.get("summary"),
                "highlights": data.get("highlights", [])[:3],
                "flags": data.get("flags", [])[:3],
            }

        return None

    def _write_brief(
        self, db, user_id: str, date: str,
        planned_workout: Optional[Dict[str, Any]], result: Dict[str, Any]
    ) -> None:
        """Write brief to daily_briefs/{YYYY-MM-DD} with plan-specified schema."""
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=TTL_BRIEFS)

        doc_data = {
            "created_at": now,
            "expires_at": expires_at,
            "has_planned_workout": planned_workout is not None,
            "planned_workout": planned_workout,
            "readiness": result.get("readiness", "moderate"),
            "readiness_summary": result.get("readiness_summary", ""),
            "fatigue_flags": result.get("fatigue_flags", []),
            "adjustments": result.get("adjustments", []),
        }

        ref = (
            db.collection("users").document(user_id)
            .collection("daily_briefs")
        )
        ref.document(date).set(doc_data)

    def _get_system_prompt(self) -> str:
        return """You are a training coach providing a daily readiness brief.

Based on:
- The user's next scheduled workout (if any)
- 4 weeks of rollups with per-muscle-group hard sets (for ACWR calculation)
- Recent workout insights (highlights and flags from last session)

CRITICAL RULES:
- ONLY reference muscle groups and exercises that appear in the input data. NEVER invent data.
- If fewer than 2 weeks of rollup data exist, set readiness to "moderate" and say "not enough history for reliable readiness assessment" in readiness_summary. Do NOT output fatigue_flags or adjustments.
- Compute ACWR per muscle group from hard_sets_per_muscle_group:
  - acute = most recent week's hard sets for that group
  - chronic = average of all available weeks' hard sets for that group
  - ACWR = acute / chronic (if chronic > 0)
- Adjustments MUST reference exercises from planned_workout.focus_muscles or last_workout_insight only.

Return JSON matching this schema EXACTLY:
{
  "readiness": "fresh | moderate | fatigued",
  "readiness_summary": "2-3 sentences explaining readiness assessment with specific data",
  "fatigue_flags": [
    {
      "muscle_group": "muscle group name from the input data",
      "signal": "fresh | building | fatigued | overreached",
      "acwr": 1.2
    }
  ],
  "adjustments": [
    {
      "exercise_name": "exercise from planned_workout that might need adjustment",
      "type": "reduce_weight | reduce_sets | skip | swap",
      "rationale": "why, referencing ACWR or flags"
    }
  ]
}

ACWR interpretation:
- fresh: ACWR < 0.8 or no recent sessions for that group
- building: ACWR 0.8-1.1 (normal training stress)
- fatigued: ACWR 1.1-1.5 (elevated load)
- overreached: ACWR > 1.5 (excessive acute spike)

Overall readiness:
- "fresh": No groups fatigued/overreached, total ACWR < 0.9
- "moderate": Some groups building, total ACWR 0.9-1.3
- "fatigued": Any group overreached, OR 2+ groups fatigued, OR total ACWR > 1.3, OR severity "action" flags from last workout

Output limits:
- fatigue_flags: Only groups with signal "building" or worse (omit "fresh" groups)
- adjustments: Only if readiness is "fatigued" or a specific group is "overreached". Max 3."""
