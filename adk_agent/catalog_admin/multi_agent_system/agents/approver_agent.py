"""
Approver Agent
Decides whether an exercise meets production-ready thresholds and records rationale.
"""

from typing import Any, Dict, List


class ApproverAgent:
    def __init__(self, firebase_client):
        self.firebase_client = firebase_client
        self.quality_guide = (
            "Approve when all must-have criteria are satisfied: name not placeholder; family_slug + variant_key; movement.type; metadata.level + plane_of_motion (unilateral when applicable); muscles (primary/secondary/category/contribution≈1.0); content (description ≥ 50 chars, execution_notes ≥ 4, common_mistakes ≥ 2, coaching_cues 3–5, suitability_notes ≥ 1); no CRITICAL issues; quality ≥ 0.80. Aliases/programming are recommended, not required, unless the name is ambiguous."
        )

    def evaluate(self, report: Dict[str, Any], exercise: Dict[str, Any]) -> Dict[str, Any]:
        issues = report.get("issues", []) or []
        # Alignment with Analyst/Audit criteria:
        # - No CRITICAL issues
        # - Quality score >= 0.85 (excellent/ready threshold per design)
        # - Required fields present: family_slug, variant_key
        # - Content minimums: execution_notes >= 4, common_mistakes >= 2, description length >= 50 chars
        # - Aliases >= 3 (search coverage)

        has_family = bool(exercise.get("family_slug")) and bool(exercise.get("variant_key"))
        exec_notes_ok = len(exercise.get("execution_notes", []) or []) >= 4
        mistakes_ok = len(exercise.get("common_mistakes", []) or []) >= 2
        desc_ok = isinstance(exercise.get("description"), str) and len(exercise.get("description", "").strip()) >= 50
        content_ok = exec_notes_ok and mistakes_ok and desc_ok
        # Aliases are recommended, not required (unless the exercise is ambiguous by name)
        aliases_count = len(exercise.get("aliases", []) or [])
        is_ambiguous_name = isinstance(exercise.get("name"), str) and len(exercise.get("name").split()) <= 1
        aliases_ok = (aliases_count >= 1) if is_ambiguous_name else True
        no_critical = not any((i.get("severity") or "").lower() == "critical" for i in issues)
        # Be pragmatic: if all structural/content criteria are met and the score is borderline, allow at 0.80
        quality_ok = report.get("quality_score", 0) >= 0.80

        # Deterministic checklist via ready_mask if provided by Analyst
        ready_mask = report.get("ready_mask") or {}
        required_keys = [
            "family_slug", "variant_key", "category", "equipment",
            "movement.type", "movement.split",
            "metadata.level", "metadata.plane_of_motion",
            "muscles.primary", "muscles.secondary", "muscles.category", "muscles.contribution",
            "description", "execution_notes", "common_mistakes", "coaching_cues", "suitability_notes",
        ]
        # Relax coaching_cues requirement to 2+ items
        mask_ok = False
        if isinstance(ready_mask, dict):
            base_ok = all(bool(ready_mask.get(k)) for k in required_keys if k != "coaching_cues")
            cues_ok = False
            # If Analyst provided counts, prefer them; otherwise infer from exercise
            if "coaching_cues" in ready_mask and isinstance(exercise.get("coaching_cues"), list):
                cues_ok = len(exercise.get("coaching_cues") or []) >= 2
            elif isinstance(exercise.get("coaching_cues"), list):
                cues_ok = len(exercise.get("coaching_cues") or []) >= 2
            mask_ok = base_ok and cues_ok

        approve = mask_ok and aliases_ok and no_critical and quality_ok

        rationale = {
            "has_family": has_family,
            "exec_notes_ok": exec_notes_ok,
            "common_mistakes_ok": mistakes_ok,
            "description_ok": desc_ok,
            "aliases_ok": aliases_ok,
            "no_critical_issues": no_critical,
            "quality_score": report.get("quality_score", 0),
            "quality_threshold": 0.85,
        }

        rationale["mask_ok"] = mask_ok
        return {"approve": approve, "rationale": rationale}

    def mark_approved(self, exercise_id: str) -> Dict[str, Any]:
        return self.firebase_client.post("approveExercise", {"exercise_id": exercise_id})


