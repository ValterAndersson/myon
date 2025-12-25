from __future__ import annotations

from typing import Any, Dict, List


class LintResult:
    def __init__(self, score: float, reasons: List[str]):
        self.score = score
        self.reasons = reasons

    def improvement(self, other: "LintResult") -> float:
        return self.score - other.score


BANNED_PHRASES = ["lorem ipsum", "placeholder", "todo"]
REQUIRED_FIELDS = ["name", "description"]


def _score_text(text: str) -> float:
    text = text.strip()
    if not text:
        return 0.0
    length = len(text)
    score = min(length / 400.0, 1.0)
    if any(bad in text.lower() for bad in BANNED_PHRASES):
        score *= 0.5
    return score


def lint_exercise(exercise: Dict[str, Any]) -> LintResult:
    reasons: List[str] = []
    score = 0.0
    for field in REQUIRED_FIELDS:
        val = exercise.get(field)
        if not val:
            reasons.append(f"missing:{field}")
            continue
        score += 0.25
    desc = str(exercise.get("description") or "")
    score += _score_text(desc) * 0.5
    coaching = str(exercise.get("coaching_cues") or "")
    if coaching:
        score += min(len(coaching) / 200.0, 0.2)
    if exercise.get("variant_key"):
        score += 0.05
    score = min(score, 1.0)
    return LintResult(score=score, reasons=reasons)
