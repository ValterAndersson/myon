from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ValidationError, validator


class Lane(str, Enum):
    realtime = "realtime"
    batch = "batch"


class Mode(str, Enum):
    dry_run = "dry_run"
    apply = "apply"


class TargetType(str, Enum):
    exercise = "exercise"
    family = "family"
    alias = "alias"
    shard = "shard"


class OperationType(str, Enum):
    upsert_exercise = "upsert_exercise"
    upsert_alias = "upsert_alias"
    delete_alias = "delete_alias"
    normalize_page = "normalize_page"
    attach_motion_gif = "attach_motion_gif"
    noop = "noop"


class EvidenceTag(str, Enum):
    lint = "lint"
    missing_required = "missing_required"
    cooldown = "cooldown"
    human_report = "human_report"
    specialist = "specialist"
    analyst = "analyst"
    template = "template"
    policy = "policy"


ALLOWED_FIELD_PATHS = {
    "name",
    "description",
    "execution_notes",
    "coaching_cues",
    "common_mistakes",
    "equipment",
    "movement",
    "variant_key",
    "family_slug",
    "aliases",
    "programming_use_cases",
    "suitability_notes",
    "stimulus_tags",
    "media.motion_gif",
}


OPERATION_RISK_TIERS = {
    OperationType.noop: 0,
    OperationType.normalize_page: 0,
    OperationType.upsert_exercise: 0,
    OperationType.attach_motion_gif: 0,
    OperationType.upsert_alias: 1,
    OperationType.delete_alias: 2,
}


class Action(BaseModel):
    op_type: OperationType
    risk_tier: int = Field(ge=0, le=3)
    field_path: str
    before: Any = None
    after: Any = None
    evidence_tag: EvidenceTag
    confidence: float = Field(ge=0.0, le=1.0)
    idempotency_key: str
    plan_hash: str

    @validator("field_path")
    def field_path_whitelist(cls, v: str) -> str:
        if v not in ALLOWED_FIELD_PATHS and not v.startswith("alias:"):
            raise ValueError(f"field_path {v} not allowed")
        return v

    @validator("risk_tier")
    def tier_matches_op(cls, v: int, values: Dict[str, Any]) -> int:
        op = values.get("op_type")
        expected = OPERATION_RISK_TIERS.get(op)
        if expected is not None and v < expected:
            raise ValueError(f"risk tier {v} too low for {op}")
        return v


class Target(BaseModel):
    type: TargetType
    id: str
    shard_index: Optional[int] = None
    shard_total: Optional[int] = None


class PlanSummary(BaseModel):
    lint_before: float = 0.0
    lint_after: float = 0.0
    improvement: float = 0.0
    cooldown_blocked: bool = False
    reasons: List[str] = Field(default_factory=list)


class ActionPlan(BaseModel):
    lane: Lane
    mode: Mode
    target: Target
    actions: List[Action]
    summary: PlanSummary

    @validator("actions")
    def enforce_no_empty_actions(cls, v: List[Action]) -> List[Action]:
        if v is None:
            return []
        return v


# --- Helpers ---

def compute_plan_hash(payload: Dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_idempotency_key(lane: Lane, target: Target, action: Dict[str, Any]) -> str:
    material = {
        "lane": lane.value,
        "target": target.model_dump(mode="json"),
        "op_type": action.get("op_type"),
        "field_path": action.get("field_path"),
        "after": action.get("after"),
    }
    return compute_plan_hash(material)[:32]


def validate_action_plan_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a raw action plan payload and return machine-actionable feedback.

    The payload is not mutated. On success, the parsed plan object is returned for
    downstream execution. On failure, callers receive:
      - the attempted payload (for debugging/telemetry)
      - the ActionPlan JSON schema (so an LLM can regenerate in the correct format)
      - structured error entries containing path, message, type, and offending input
    """

    try:
        plan = ActionPlan.model_validate(payload)
        return {"ok": True, "plan": plan}
    except ValidationError as err:
        errors = []
        for e in err.errors():
            errors.append(
                {
                    "loc": ".".join(str(part) for part in e.get("loc", [])),
                    "message": e.get("msg"),
                    "error_type": e.get("type"),
                    "input": e.get("input"),
                }
            )
        return {
            "ok": False,
            "expected_schema": ActionPlan.model_json_schema(),
            "received": payload,
            "errors": errors,
        }
