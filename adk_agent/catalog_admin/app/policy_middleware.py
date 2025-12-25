from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from .action_schema import (
    ALLOWED_FIELD_PATHS,
    Action,
    ActionPlan,
    EvidenceTag,
    Lane,
    Mode,
    OPERATION_RISK_TIERS,
    OperationType,
)
from .cooldown import CooldownTracker
from .lint import lint_exercise


@dataclass
class PolicyConfig:
    enable_batch_apply: bool = False
    enable_tier2: bool = False
    enable_tier3: bool = False
    cooldown_days: int = 7
    lint_threshold: float = 0.05
    lane_allowlist: Dict[Lane, Tuple[int, ...]] = field(
        default_factory=lambda: {Lane.realtime: (0, 1), Lane.batch: (0, 1)}
    )


@dataclass
class PolicyResult:
    approved_actions: List[Action]
    rejected: List[Dict[str, str]]
    plan: ActionPlan


class PolicyMiddleware:
    def __init__(self, config: PolicyConfig):
        self.config = config

    def _check_tiers(self, plan: ActionPlan, action: Action) -> Tuple[bool, str]:
        allowed = self.config.lane_allowlist.get(plan.lane, tuple())
        if action.risk_tier not in allowed:
            return False, f"risk_tier_disallowed:{action.risk_tier}"
        if action.risk_tier >= 2 and not self.config.enable_tier2 and plan.lane == Lane.batch:
            return False, "tier2_disabled"
        if action.risk_tier >= 3 and not self.config.enable_tier3:
            return False, "tier3_disabled"
        return True, ""

    def _check_cooldown(self, tracker: CooldownTracker, action: Action) -> bool:
        if action.op_type in {OperationType.noop, OperationType.normalize_page}:
            return False
        return tracker.is_blocked(action.field_path)

    def evaluate(self, plan: ActionPlan, tracker: CooldownTracker) -> PolicyResult:
        approved: List[Action] = []
        rejected: List[Dict[str, str]] = []
        for action in plan.actions:
            ok_tier, reason = self._check_tiers(plan, action)
            if not ok_tier:
                rejected.append({"action": action.op_type.value, "reason": reason})
                continue
            if action.field_path not in ALLOWED_FIELD_PATHS and not action.field_path.startswith("alias:"):
                rejected.append({"action": action.op_type.value, "reason": "field_path_not_allowed"})
                continue
            if self._check_cooldown(tracker, action):
                rejected.append({"action": action.op_type.value, "reason": "cooldown"})
                continue
            approved.append(action)
        return PolicyResult(approved_actions=approved, rejected=rejected, plan=plan)

    def improvement_gate(self, before_obj, after_obj) -> float:  # type: ignore[no-untyped-def]
        before = lint_exercise(before_obj or {})
        after = lint_exercise(after_obj or before_obj or {})
        return after.improvement(before)

    def enforce_batch_dampening(self, plan: ActionPlan, tracker: CooldownTracker) -> PolicyResult:
        result = self.evaluate(plan, tracker)
        if plan.lane != Lane.batch:
            return result
        gated: List[Action] = []
        for action in result.approved_actions:
            if action.op_type == OperationType.upsert_exercise and plan.summary.improvement < self.config.lint_threshold:
                result.rejected.append({"action": action.op_type.value, "reason": "lint_not_improved"})
                continue
            gated.append(action)
        result.approved_actions = gated
        return result
