from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional

from .action_schema import Action, ActionPlan, Lane, Mode, OperationType, Target, PlanSummary, EvidenceTag, compute_idempotency_key, compute_plan_hash
from .lint import lint_exercise


class ActionPlanner:
    def __init__(self, lane: Lane):
        self.lane = lane

    def _build_upsert_action(self, target: Target, before: Dict[str, Any], patch: Dict[str, Any]) -> Action:
        after = {**before, **patch}
        plan_hash = compute_plan_hash({"before": before})
        action_dict = {
            "op_type": OperationType.upsert_exercise,
            "risk_tier": 0,
            "field_path": list(patch.keys())[0] if patch else "description",
            "before": before,
            "after": after,
            "evidence_tag": EvidenceTag.lint,
            "confidence": 0.8,
            "plan_hash": plan_hash,
        }
        action_dict["idempotency_key"] = compute_idempotency_key(self.lane, target, action_dict)
        return Action(**action_dict)

    def build_plan_for_exercise(self, target: Target, exercise: Dict[str, Any], mode: Mode = Mode.dry_run) -> ActionPlan:
        lint_before = lint_exercise(exercise)
        actions: List[Action] = []
        patch: Dict[str, Any] = {}
        if not exercise.get("description"):
            patch["description"] = "Auto-filled description pending enrichment."
        if not exercise.get("variant_key") and exercise.get("equipment"):
            eq = exercise.get("equipment")
            if isinstance(eq, list) and eq:
                patch["variant_key"] = f"equipment:{str(eq[0]).lower()}"
        if patch:
            actions.append(self._build_upsert_action(target, exercise, patch))
        else:
            actions.append(
                Action(
                    op_type=OperationType.noop,
                    risk_tier=0,
                    field_path="noop",
                    before=exercise,
                    after=exercise,
                    evidence_tag=EvidenceTag.lint,
                    confidence=1.0,
                    idempotency_key=compute_idempotency_key(self.lane, target, {"op_type": OperationType.noop, "field_path": "noop"}),
                    plan_hash=compute_plan_hash({"before": exercise}),
                )
            )
        lint_after = lint_exercise(actions[-1].after if actions else exercise)
        summary = PlanSummary(
            lint_before=lint_before.score,
            lint_after=lint_after.score,
            improvement=lint_after.score - lint_before.score,
            cooldown_blocked=False,
            reasons=lint_before.reasons,
        )
        return ActionPlan(lane=self.lane, mode=mode, target=target, actions=actions, summary=summary)
