"""
Quality Scanner - Tier 1 of the multi-tier review pipeline.

This module provides cost-efficient quality scanning using:
1. Heuristic pre-filter (no LLM) - instantly scores obviously good exercises
2. Flash LLM scoring (gemini-2.5-flash) - quick quality assessment for the rest

Architecture:
- Phase 0: Heuristic check - skip LLM for exercises that pass all checks
- Phase 1: Flash scan - lightweight quality scoring, flags complex issues

Output per exercise:
- quality_score: 0-1 assessment
- issue_type: "none" | "missing_fields" | "naming" | "complex"
- needs_full_review: boolean (send to Pro review if true)

Cost: ~$0.05 per 1000 exercises (vs $5-10 with Pro for all)
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.enrichment.llm_client import get_llm_client, LLMClient

logger = logging.getLogger(__name__)

# Version for tracking which scanner version reviewed an exercise
SCANNER_VERSION = "1.0"

# Heuristic thresholds
HEURISTIC_PASS_SCORE = 0.85  # Score for exercises passing all heuristic checks
MIN_EXECUTION_NOTES = 2  # Minimum execution notes for heuristic pass
MIN_PRIMARY_MUSCLES = 1  # Minimum primary muscles for heuristic pass


# =============================================================================
# DATA MODELS
# =============================================================================

@dataclass
class QualityScanResult:
    """Result of quality scanning a single exercise."""
    exercise_id: str
    exercise_name: str
    quality_score: float
    issue_type: str  # "none", "missing_fields", "naming", "complex"
    needs_full_review: bool
    scan_method: str  # "heuristic" or "llm"
    details: Optional[str] = None


@dataclass
class QualityScanBatchResult:
    """Result of scanning a batch of exercises."""
    total_scanned: int = 0
    heuristic_passed: int = 0
    llm_scanned: int = 0
    needs_full_review: int = 0
    results: List[QualityScanResult] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_scanned": self.total_scanned,
            "heuristic_passed": self.heuristic_passed,
            "llm_scanned": self.llm_scanned,
            "needs_full_review": self.needs_full_review,
            "by_issue_type": self._count_by_issue_type(),
        }

    def _count_by_issue_type(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for r in self.results:
            counts[r.issue_type] = counts.get(r.issue_type, 0) + 1
        return counts


# =============================================================================
# HEURISTIC PRE-FILTER (Phase 0 - No LLM)
# =============================================================================

# Pattern for canonical naming: "Exercise Name (Equipment)"
CANONICAL_NAME_PATTERN = re.compile(r'^.+\s*\([^)]+\)$')

# Known equipment that should be in parentheses
EQUIPMENT_PREFIXES = [
    "barbell", "dumbbell", "cable", "machine", "kettlebell",
    "bodyweight", "band", "smith", "ez-bar", "trap bar",
]


def check_canonical_name(name: str) -> Tuple[bool, Optional[str]]:
    """
    Check if exercise name follows canonical format.

    Good: "Deadlift (Barbell)", "Lat Pulldown (Cable)"
    Bad: "Barbell Deadlift", "Conventional Deadlift"

    Returns:
        (is_valid, issue_description or None)
    """
    if not name:
        return False, "Empty name"

    # Check for canonical format: "Name (Equipment)"
    if CANONICAL_NAME_PATTERN.match(name):
        return True, None

    # Check for equipment prefix (wrong format)
    name_lower = name.lower()
    for eq in EQUIPMENT_PREFIXES:
        if name_lower.startswith(eq + " "):
            return False, f"Equipment '{eq}' should be in parentheses at end"

    # No parentheses but might be OK for bodyweight exercises
    if "bodyweight" in name_lower or name_lower in ["push-up", "pull-up", "plank", "crunch"]:
        return True, None

    # Missing equipment specification
    return False, "Missing equipment in parentheses"


def heuristic_score_exercise(exercise: Dict[str, Any]) -> Optional[QualityScanResult]:
    """
    Apply heuristic checks to instantly score obviously good exercises.

    Returns QualityScanResult if exercise passes all checks (skip LLM),
    or None if exercise needs LLM scanning.
    """
    exercise_id = exercise.get("id") or exercise.get("doc_id", "")
    name = exercise.get("name", "") or ""

    # Check 1: Canonical name format
    name_valid, name_issue = check_canonical_name(name)
    if not name_valid:
        return None  # Needs LLM for naming issues

    # Check 2: Has equipment (handle None explicitly)
    equipment = exercise.get("equipment") or []
    if not equipment:
        return None  # Needs LLM

    # Check 3: Has category
    category = exercise.get("category")
    if not category:
        return None  # Needs LLM

    # Check 4: Has primary muscles (check both schemas, handle None)
    muscles = exercise.get("muscles") or {}
    primary_muscles = (muscles.get("primary") or []) or (exercise.get("primary_muscles") or [])
    if len(primary_muscles) < MIN_PRIMARY_MUSCLES:
        return None  # Needs LLM

    # Check 5: Has execution notes (handle None explicitly)
    execution_notes = exercise.get("execution_notes") or []
    if len(execution_notes) < MIN_EXECUTION_NOTES:
        return None  # Needs LLM - missing content

    # Check 6: Category must be in canonical set
    from app.enrichment.exercise_field_guide import (
        CATEGORIES, MOVEMENT_TYPES, MOVEMENT_SPLITS,
    )
    if category not in CATEGORIES:
        return None  # Needs LLM — invalid category

    # Check 7: Movement type must be present and canonical
    movement = exercise.get("movement") or {}
    movement_type = movement.get("type")
    if not movement_type or movement_type not in MOVEMENT_TYPES:
        return None  # Needs LLM — missing or invalid movement type

    # Check 8: Movement split must be present and canonical
    movement_split = movement.get("split")
    if not movement_split or movement_split not in MOVEMENT_SPLITS:
        return None  # Needs LLM — missing or invalid movement split

    # Check 9: Description must be present and substantial
    description = exercise.get("description") or ""
    if len(description) < 50:
        return None  # Needs LLM — missing or too-short description

    # Check 10: Muscle names must be lowercase without underscores
    for m in primary_muscles:
        if isinstance(m, str) and ("_" in m or m != m.lower()):
            return None  # Needs LLM — non-normalized muscle names

    # All checks passed - this is a good exercise
    return QualityScanResult(
        exercise_id=exercise_id,
        exercise_name=name,
        quality_score=HEURISTIC_PASS_SCORE,
        issue_type="none",
        needs_full_review=False,
        scan_method="heuristic",
        details="Passed all heuristic checks",
    )


# =============================================================================
# FLASH LLM QUALITY SCAN (Phase 1)
# =============================================================================

QUALITY_SCAN_PROMPT = """You are a fitness catalog quality scanner. Score each exercise's quality and identify issues.

## Scoring Rubric (0-1)

**0.9-1.0**: Excellent - canonical name, complete data, ready for users
**0.8-0.89**: Good - minor gaps but usable
**0.6-0.79**: Needs work - missing important fields
**0.4-0.59**: Poor - significant issues
**0.0-0.39**: Bad - naming issues, duplicates, or unsalvageable

## Issue Types

- "none": No issues, good quality
- "missing_fields": Missing execution_notes, muscles, or other content (fixable with enrichment)
- "naming": Name doesn't follow "Exercise (Equipment)" format, or taxonomy violation
- "complex": Potential duplicate, merge candidate, or needs human review

## Examples

Exercise: {"name": "Bench Press (Barbell)", "equipment": ["barbell"], "execution_notes": ["Lower to chest", "Press up"], "muscles": {"primary": ["chest"]}}
→ quality_score: 0.85, issue_type: "none"

Exercise: {"name": "Bicep Curl", "equipment": ["dumbbell"], "execution_notes": [], "muscles": {}}
→ quality_score: 0.55, issue_type: "missing_fields"

Exercise: {"name": "Barbell Deadlift", "equipment": ["barbell"], ...}
→ quality_score: 0.45, issue_type: "naming" (should be "Deadlift (Barbell)")

## Your Task

Score each exercise. Respond with JSON array:
```json
[
  {"exercise_id": "...", "quality_score": 0.85, "issue_type": "none", "details": "brief note"},
  ...
]
```

Exercises to scan:
{exercises_json}

Respond with ONLY the JSON array, no markdown."""


class QualityScanner:
    """
    Tier 1 quality scanner - heuristic + Flash LLM.

    Usage:
        scanner = QualityScanner()
        result = scanner.scan_batch(exercises)
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        batch_size: int = 50,  # Larger batches OK for simple scoring
    ):
        self._llm_client = llm_client
        self.batch_size = batch_size

    def _get_llm_client(self) -> LLMClient:
        if self._llm_client is None:
            self._llm_client = get_llm_client()
        return self._llm_client

    def scan_batch(
        self,
        exercises: List[Dict[str, Any]],
    ) -> QualityScanBatchResult:
        """
        Scan a batch of exercises for quality.

        1. Apply heuristic filter first (no LLM cost)
        2. Send remaining to Flash LLM for scoring

        Returns:
            QualityScanBatchResult with all results
        """
        result = QualityScanBatchResult(total_scanned=len(exercises))

        if not exercises:
            return result

        # Phase 0: Heuristic pre-filter
        needs_llm: List[Dict[str, Any]] = []

        for ex in exercises:
            heuristic_result = heuristic_score_exercise(ex)
            if heuristic_result:
                result.results.append(heuristic_result)
                result.heuristic_passed += 1
            else:
                needs_llm.append(ex)

        logger.info(
            "Heuristic filter: %d/%d passed, %d need LLM scan",
            result.heuristic_passed,
            len(exercises),
            len(needs_llm),
        )

        # Phase 1: Flash LLM scan for remaining
        if needs_llm:
            llm_results = self._scan_with_llm(needs_llm)
            result.results.extend(llm_results)
            result.llm_scanned = len(needs_llm)

        # Count needs_full_review
        result.needs_full_review = sum(
            1 for r in result.results if r.needs_full_review
        )

        logger.info(
            "Quality scan complete: %d total, %d heuristic, %d LLM, %d need full review",
            result.total_scanned,
            result.heuristic_passed,
            result.llm_scanned,
            result.needs_full_review,
        )

        return result

    def _scan_with_llm(
        self,
        exercises: List[Dict[str, Any]],
    ) -> List[QualityScanResult]:
        """Scan exercises using Flash LLM."""
        results: List[QualityScanResult] = []

        # Process in batches
        for i in range(0, len(exercises), self.batch_size):
            batch = exercises[i:i + self.batch_size]
            batch_results = self._scan_llm_batch(batch)
            results.extend(batch_results)

        return results

    def _scan_llm_batch(
        self,
        exercises: List[Dict[str, Any]],
    ) -> List[QualityScanResult]:
        """Scan a single batch with Flash LLM."""
        # Prepare minimal exercise data for prompt
        exercises_for_prompt = []
        id_to_name: Dict[str, str] = {}

        for ex in exercises:
            ex_id = ex.get("id") or ex.get("doc_id", "")
            name = ex.get("name") or ""
            id_to_name[ex_id] = name

            # Handle None values explicitly
            equipment = ex.get("equipment") or []
            execution_notes = ex.get("execution_notes") or []
            muscles = ex.get("muscles") or {}
            primary_muscles = (muscles.get("primary") or []) or (ex.get("primary_muscles") or [])

            exercises_for_prompt.append({
                "id": ex_id,
                "name": name,
                "equipment": equipment,
                "category": ex.get("category"),
                "execution_notes": execution_notes[:3],  # Truncate
                "muscles": {
                    "primary": primary_muscles,
                },
            })

        exercises_json = json.dumps(exercises_for_prompt, indent=2)
        prompt = QUALITY_SCAN_PROMPT.format(exercises_json=exercises_json)

        try:
            llm_client = self._get_llm_client()
            # Use Flash (require_reasoning=False)
            response = llm_client.complete(
                prompt=prompt,
                require_reasoning=False,  # Use gemini-2.5-flash
            )

            results = self._parse_llm_response(response, id_to_name)

            # Handle missing results - create fallback for exercises not in response
            result_ids = {r.exercise_id for r in results}
            for ex in exercises:
                ex_id = ex.get("id") or ex.get("doc_id", "")
                if ex_id and ex_id not in result_ids:
                    logger.warning("LLM did not return result for %s, using fallback", ex_id)
                    results.append(QualityScanResult(
                        exercise_id=ex_id,
                        exercise_name=ex.get("name", ""),
                        quality_score=0.5,
                        issue_type="complex",
                        needs_full_review=True,
                        scan_method="llm_missing",
                        details="LLM response missing this exercise",
                    ))

            return results

        except Exception as e:
            logger.exception("Flash LLM scan failed: %s", e)
            # On failure, mark all as needing full review (fail safe)
            return [
                QualityScanResult(
                    exercise_id=ex.get("id") or ex.get("doc_id", ""),
                    exercise_name=ex.get("name", ""),
                    quality_score=0.5,
                    issue_type="complex",
                    needs_full_review=True,
                    scan_method="llm_error",
                    details=f"LLM scan failed: {str(e)}",
                )
                for ex in exercises
            ]

    def _parse_llm_response(
        self,
        response: str,
        id_to_name: Dict[str, str],
    ) -> List[QualityScanResult]:
        """Parse Flash LLM response."""
        results: List[QualityScanResult] = []

        # Clean response
        clean = response.strip()
        if clean.startswith("```"):
            # Extract from markdown
            lines = clean.split("\n")
            clean = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

        try:
            parsed = json.loads(clean)
            if not isinstance(parsed, list):
                parsed = [parsed]

            for item in parsed:
                ex_id = item.get("exercise_id", "")
                quality_score = float(item.get("quality_score", 0.5))
                issue_type = item.get("issue_type", "complex")

                # Determine if needs full review
                needs_full_review = (
                    quality_score < 0.7 or
                    issue_type in ("naming", "complex")
                )

                results.append(QualityScanResult(
                    exercise_id=ex_id,
                    exercise_name=id_to_name.get(ex_id, ""),
                    quality_score=quality_score,
                    issue_type=issue_type,
                    needs_full_review=needs_full_review,
                    scan_method="llm",
                    details=item.get("details"),
                ))

        except json.JSONDecodeError as e:
            logger.warning("Failed to parse LLM response: %s", e)
            # Return empty - caller should handle missing results

        return results


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def scan_exercises(
    exercises: List[Dict[str, Any]],
    batch_size: int = 50,
) -> QualityScanBatchResult:
    """
    Convenience function to scan exercises for quality.

    Args:
        exercises: List of exercise dicts from Firestore
        batch_size: Exercises per LLM batch

    Returns:
        QualityScanBatchResult with all quality scores and flags
    """
    scanner = QualityScanner(batch_size=batch_size)
    return scanner.scan_batch(exercises)


def save_scan_results(
    db,
    results: List[QualityScanResult],
    dry_run: bool = True,
) -> Dict[str, int]:
    """
    Save quality scan results to Firestore using batched writes.

    Updates each exercise with:
    - review_metadata.quality_score
    - review_metadata.needs_full_review
    - review_metadata.last_scanned_at
    - review_metadata.scanner_version
    - review_metadata.issue_type

    Args:
        db: Firestore client
        results: List of QualityScanResult
        dry_run: If True, don't actually update

    Returns:
        Summary of updates
    """
    if not db:
        logger.warning("No Firestore client - cannot save scan results")
        return {"updated": 0, "errors": 0}

    updated = 0
    errors = 0
    now = datetime.now(timezone.utc)

    # Firestore batch limit is 500 operations
    BATCH_SIZE = 400

    if dry_run:
        for result in results:
            if not result.exercise_id:
                continue
            logger.debug(
                "Would update %s: quality=%.2f, needs_review=%s, issue=%s",
                result.exercise_id,
                result.quality_score,
                result.needs_full_review,
                result.issue_type,
            )
            updated += 1
    else:
        # Process in batches for efficiency
        batch = db.batch()
        batch_count = 0

        for result in results:
            if not result.exercise_id:
                continue

            update_data = {
                "review_metadata.quality_score": result.quality_score,
                "review_metadata.needs_full_review": result.needs_full_review,
                "review_metadata.last_scanned_at": now,
                "review_metadata.scanner_version": SCANNER_VERSION,
                "review_metadata.issue_type": result.issue_type,
                "review_metadata.scan_method": result.scan_method,
            }

            doc_ref = db.collection("exercises").document(result.exercise_id)
            batch.update(doc_ref, update_data)
            batch_count += 1
            updated += 1

            # Commit batch when it reaches the limit
            if batch_count >= BATCH_SIZE:
                try:
                    batch.commit()
                    logger.debug("Committed batch of %d updates", batch_count)
                except Exception as e:
                    logger.warning("Batch commit failed: %s", e)
                    errors += batch_count
                    updated -= batch_count
                batch = db.batch()
                batch_count = 0

        # Commit remaining
        if batch_count > 0:
            try:
                batch.commit()
                logger.debug("Committed final batch of %d updates", batch_count)
            except Exception as e:
                logger.warning("Final batch commit failed: %s", e)
                errors += batch_count
                updated -= batch_count

    logger.info(
        "Saved scan results: updated=%d, errors=%d, dry_run=%s",
        updated, errors, dry_run,
    )

    return {"updated": updated, "errors": errors}


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "QualityScanner",
    "QualityScanResult",
    "QualityScanBatchResult",
    "scan_exercises",
    "save_scan_results",
    "heuristic_score_exercise",
    "check_canonical_name",
    "SCANNER_VERSION",
]
