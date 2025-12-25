from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from .action_schema import (
    Action,
    ActionPlan,
    EvidenceTag,
    Lane,
    Mode,
    OperationType,
    PlanSummary,
    Target,
    compute_idempotency_key,
    compute_plan_hash,
)
from .lint import lint_exercise

if TYPE_CHECKING:
    from .media_agent import MotionGifAgent


class ActionPlanner:
    def __init__(self, lane: Lane, media_agent: Optional["MotionGifAgent"] = None):
        self.lane = lane
        self.media_agent = media_agent

    def _build_upsert_action(self, target: Target, before: Dict[str, Any], patch: Dict[str, Any]) -> Action:
        after = {**before, **patch}
        plan_hash = compute_plan_hash({"before": before, "after": after})
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

    def _build_media_action(self, target: Target, before: Dict[str, Any], asset: Dict[str, Any]) -> Action:
        media = dict(before.get("media") or {})
        media["motion_gif"] = asset
        after = {**before, "media": media}
        plan_hash = compute_plan_hash({"before": before, "after": after, "asset": asset})
        action_dict = {
            "op_type": OperationType.attach_motion_gif,
            "risk_tier": 0,
            "field_path": "media.motion_gif",
            "before": before,
            "after": after,
            "evidence_tag": EvidenceTag.template,
            "confidence": 0.85,
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
        media_asset = None
        if self.media_agent:
            media_asset = self.media_agent.generate_motion_gif(exercise, lane=self.lane)
        if media_asset:
            actions.append(self._build_media_action(target, exercise, media_asset))
        if not actions:
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
