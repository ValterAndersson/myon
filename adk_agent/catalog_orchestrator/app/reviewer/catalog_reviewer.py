"""
Catalog Reviewer - Periodic LLM-powered catalog quality auditor.

This module scans the exercise catalog, evaluates quality using LLM and
deterministic benchmarks, and queues jobs for exercises that need improvement.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from app.reviewer.what_good_looks_like import (
    WHAT_GOOD_LOOKS_LIKE,
    INSTRUCTIONS_GUIDANCE,
    MUSCLE_MAPPING_GUIDANCE,
)

logger = logging.getLogger(__name__)


# =============================================================================
# QUALITY BENCHMARKS
# =============================================================================

QUALITY_BENCHMARKS = {
    "name": {
        "min_words": 2,
        "max_words": 8,
        # Taxonomy: exercises must include equipment variant in parentheses
        # e.g., "Deadlift (Barbell)", "Lateral Raise (Cable)"
        "must_have_equipment_suffix": True,
        "bad_patterns": [
            r"^[A-Z][a-z]+$",  # Single word like "Squat"
            r"\bexercise\b",   # Generic term
        ],
    },
    "instructions": {
        "min_length": 100,
        "must_have_structure": True,  # Numbered steps or bullets
        # Avoid overly fancy/ambiguous jargon
        "bad_patterns": [
            r"sagittal plane",
            r"receptacles",
            r"adequate force",
            r"proprioceptive",  # unless explained
        ],
    },
    # New schema: muscles.primary, muscles.secondary, muscles.category, muscles.contribution
    "muscles.primary": {
        "min_count": 1,
        "max_count": 3,
    },
    "muscles.secondary": {
        "should_exist": True,  # Not required but flagged
    },
    "muscles.contribution": {
        "required": False,  # Nice to have
    },
    "equipment": {
        "must_match_name": True,  # If name says "(Dumbbell)", equipment must include dumbbell
    },
    "category": {
        "allowed_values": [
            "compound", "isolation", "cardio", "mobility", "core"
        ],
    },
}

# "What Good Looks Like" examples for LLM context
QUALITY_EXAMPLES = """
## What Good Looks Like

### Exercise Name (GOOD)
- "Deadlift (Barbell)" ✓ (movement + equipment variant)
- "Lateral Raise (Cable)" ✓ (movement + equipment variant)
- "Plank" ✓ (no equipment variants exist, non-parenthesized OK)

### Exercise Name (BAD)
- "Deadlift" ✗ (missing equipment variant when multiple exist)
- "Barbell Deadlift" ✗ (wrong format - use parentheses)
- "Back Exercise" ✗ (too vague)

### Instructions (GOOD)
1. Stand with feet shoulder-width apart, toes slightly pointed out.
2. Grip the bar with hands just outside your knees, arms straight.
3. Drive through your heels, keeping the bar close to your body.
4. Squeeze your glutes at the top, then lower with control.

### Instructions (BAD)
- "Do the exercise properly" ✗ (no specificity)
- "While in a sagittal plane, elevate receptacles with adequate force" ✗ (overly fancy, ambiguous jargon)
- Single paragraph without structure ✗
"""


class IssueSeverity(str, Enum):
    """Severity of quality issues."""
    CRITICAL = "critical"  # Blocks approval
    HIGH = "high"          # Should be fixed soon
    MEDIUM = "medium"      # Worth improving
    LOW = "low"            # Nice to have


class IssueCategory(str, Enum):
    """Category of quality issue - maps to specialist agents."""
    CONTENT = "content"           # Name, instructions, descriptions
    ANATOMY = "anatomy"           # Muscle mappings
    BIOMECHANICS = "biomechanics" # Movement patterns, equipment
    TAXONOMY = "taxonomy"         # Family/variant, naming convention


@dataclass
class QualityIssue:
    """A quality issue found during review."""
    field: str
    category: IssueCategory
    severity: IssueSeverity
    message: str
    current_value: Any = None
    suggested_fix: Optional[str] = None


@dataclass
class ReviewResult:
    """Result of reviewing a single exercise."""
    exercise_id: str
    exercise_name: str
    family_slug: Optional[str] = None
    
    # Quality assessment
    quality_score: float = 1.0  # 0.0-1.0
    issues: List[QualityIssue] = field(default_factory=list)
    
    # Flags
    needs_enrichment: bool = False
    needs_human_review: bool = False
    
    reviewed_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for storage."""
        return {
            "exercise_id": self.exercise_id,
            "exercise_name": self.exercise_name,
            "family_slug": self.family_slug,
            "quality_score": self.quality_score,
            "issues": [
                {
                    "field": i.field,
                    "category": i.category.value,
                    "severity": i.severity.value,
                    "message": i.message,
                    "current_value": i.current_value,
                    "suggested_fix": i.suggested_fix,
                }
                for i in self.issues
            ],
            "needs_enrichment": self.needs_enrichment,
            "needs_human_review": self.needs_human_review,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
        }


@dataclass
class BatchReviewResult:
    """Result of reviewing a batch of exercises."""
    total_reviewed: int = 0
    issues_found: int = 0
    exercises_needing_enrichment: int = 0
    exercises_needing_human_review: int = 0
    results: List[ReviewResult] = field(default_factory=list)
    
    # Aggregates
    issues_by_severity: Dict[str, int] = field(default_factory=dict)
    issues_by_category: Dict[str, int] = field(default_factory=dict)


class CatalogReviewer:
    """
    LLM-powered catalog quality auditor.
    
    Combines deterministic benchmark checks with LLM analysis to identify
    exercises that need improvement.
    """
    
    def __init__(
        self,
        llm_client=None,
        analyst_agent=None,
        dry_run: bool = True,
        enable_llm_review: bool = False,
    ):
        """
        Initialize the catalog reviewer.
        
        Args:
            llm_client: LLM client for analysis (optional)
            analyst_agent: Existing AnalystAgent to reuse (optional)
            dry_run: If True, only report issues without creating jobs
            enable_llm_review: If True, use LLM for semantic quality analysis
        """
        self.llm_client = llm_client
        self.analyst_agent = analyst_agent
        self.dry_run = dry_run
        self.enable_llm_review = enable_llm_review
        
    def review_exercise(self, exercise: Dict[str, Any]) -> ReviewResult:
        """
        Review a single exercise for quality issues.
        
        Applies both deterministic benchmarks and LLM analysis.
        """
        result = ReviewResult(
            exercise_id=exercise.get("id", exercise.get("doc_id", "unknown")),
            exercise_name=exercise.get("name", "Unknown"),
            family_slug=exercise.get("family_slug"),
            reviewed_at=datetime.utcnow(),
        )
        
        # Phase 1: Deterministic benchmark checks
        self._check_name(exercise, result)
        self._check_instructions(exercise, result)
        self._check_muscles(exercise, result)
        self._check_equipment(exercise, result)
        self._check_taxonomy(exercise, result)
        self._check_schema_migration(exercise, result)
        self._check_category(exercise, result)
        self._check_content_completeness(exercise, result)

        # Phase 2: LLM semantic analysis (if enabled)
        if self.enable_llm_review:
            self._apply_llm_analysis(exercise, result)
        
        # Compute quality score
        result.quality_score = self._compute_quality_score(result.issues)
        
        # Determine action needed
        critical_issues = [i for i in result.issues if i.severity == IssueSeverity.CRITICAL]
        high_issues = [i for i in result.issues if i.severity == IssueSeverity.HIGH]
        
        result.needs_human_review = len(critical_issues) > 0
        result.needs_enrichment = len(high_issues) > 0 or result.quality_score < 0.7
        
        return result
    
    def review_batch(self, exercises: List[Dict[str, Any]]) -> BatchReviewResult:
        """
        Review a batch of exercises.
        """
        batch_result = BatchReviewResult()
        
        for exercise in exercises:
            try:
                result = self.review_exercise(exercise)
                batch_result.results.append(result)
                batch_result.total_reviewed += 1
                batch_result.issues_found += len(result.issues)
                
                if result.needs_enrichment:
                    batch_result.exercises_needing_enrichment += 1
                if result.needs_human_review:
                    batch_result.exercises_needing_human_review += 1
                
                # Aggregate by severity
                for issue in result.issues:
                    sev = issue.severity.value
                    batch_result.issues_by_severity[sev] = batch_result.issues_by_severity.get(sev, 0) + 1
                    cat = issue.category.value
                    batch_result.issues_by_category[cat] = batch_result.issues_by_category.get(cat, 0) + 1
                    
            except Exception as e:
                logger.exception("Error reviewing exercise %s: %s", exercise.get("id"), e)
        
        return batch_result
    
    # =========================================================================
    # DETERMINISTIC BENCHMARK CHECKS
    # =========================================================================
    
    def _check_name(self, exercise: Dict[str, Any], result: ReviewResult):
        """Check exercise name against benchmarks."""
        name = exercise.get("name", "")
        benchmarks = QUALITY_BENCHMARKS["name"]
        
        # Word count check
        words = name.split()
        if len(words) < benchmarks["min_words"]:
            result.issues.append(QualityIssue(
                field="name",
                category=IssueCategory.CONTENT,
                severity=IssueSeverity.HIGH,
                message=f"Name too short: '{name}' has {len(words)} word(s), needs at least {benchmarks['min_words']}",
                current_value=name,
            ))
        
        # Equipment suffix check - taxonomy requires "(Equipment)" format
        equipment = exercise.get("equipment", [])
        if equipment and benchmarks.get("must_have_equipment_suffix"):
            # Check if name has equipment in parentheses
            import re
            has_suffix = bool(re.search(r"\([^)]+\)\s*$", name))
            if not has_suffix:
                result.issues.append(QualityIssue(
                    field="name",
                    category=IssueCategory.TAXONOMY,
                    severity=IssueSeverity.HIGH,
                    message=f"Name missing equipment variant: should be '{name} ({equipment[0].title()})' format",
                    current_value=name,
                    suggested_fix=f"{name} ({equipment[0].title()})" if equipment else None,
                ))
    
    def _check_instructions(self, exercise: Dict[str, Any], result: ReviewResult):
        """Check exercise instructions against benchmarks."""
        instructions = exercise.get("instructions", "")
        benchmarks = QUALITY_BENCHMARKS["instructions"]
        
        # Length check
        if len(instructions) < benchmarks["min_length"]:
            result.issues.append(QualityIssue(
                field="instructions",
                category=IssueCategory.CONTENT,
                severity=IssueSeverity.HIGH,
                message=f"Instructions too short: {len(instructions)} chars, needs at least {benchmarks['min_length']}",
                current_value=instructions[:100] + "..." if len(instructions) > 100 else instructions,
            ))
        
        # Structure check - should have numbered steps or bullets
        import re
        has_structure = bool(re.search(r"(^|\n)\s*(\d+\.|[-•*])\s+", instructions))
        if instructions and not has_structure:
            result.issues.append(QualityIssue(
                field="instructions",
                category=IssueCategory.CONTENT,
                severity=IssueSeverity.MEDIUM,
                message="Instructions lack structure: add numbered steps or bullet points",
                current_value=instructions[:100] + "..." if len(instructions) > 100 else instructions,
            ))
        
        # Bad pattern check - overly fancy language
        for pattern in benchmarks.get("bad_patterns", []):
            if re.search(pattern, instructions, re.IGNORECASE):
                result.issues.append(QualityIssue(
                    field="instructions",
                    category=IssueCategory.CONTENT,
                    severity=IssueSeverity.MEDIUM,
                    message=f"Instructions contain overly fancy/ambiguous jargon: '{pattern}'",
                    current_value=instructions[:100] + "..." if len(instructions) > 100 else instructions,
                ))
    
    def _check_muscles(self, exercise: Dict[str, Any], result: ReviewResult):
        """Check muscle mappings against new schema (muscles.primary, etc)."""
        muscles = exercise.get("muscles", {}) or {}
        primary = muscles.get("primary", [])
        secondary = muscles.get("secondary", [])
        contribution = muscles.get("contribution", {})
        benchmarks_primary = QUALITY_BENCHMARKS["muscles.primary"]
        benchmarks_secondary = QUALITY_BENCHMARKS["muscles.secondary"]

        # Check for legacy-only fields (no new schema)
        has_legacy_primary = exercise.get("primary_muscles")
        has_legacy_secondary = exercise.get("secondary_muscles")
        has_new_schema = bool(primary)

        if has_legacy_primary and not has_new_schema:
            result.issues.append(QualityIssue(
                field="muscles.primary",
                category=IssueCategory.ANATOMY,
                severity=IssueSeverity.HIGH,
                message="Exercise uses legacy primary_muscles field, needs migration to muscles.primary",
                current_value=has_legacy_primary,
            ))
            # Don't check further - needs migration first
            return

        # Primary muscles check (new schema)
        if len(primary) < benchmarks_primary["min_count"]:
            result.issues.append(QualityIssue(
                field="muscles.primary",
                category=IssueCategory.ANATOMY,
                severity=IssueSeverity.HIGH,
                message=f"Missing muscles.primary: needs at least {benchmarks_primary['min_count']}",
                current_value=primary,
            ))
        elif len(primary) > benchmarks_primary["max_count"]:
            result.issues.append(QualityIssue(
                field="muscles.primary",
                category=IssueCategory.ANATOMY,
                severity=IssueSeverity.MEDIUM,
                message=f"Too many primary muscles ({len(primary)}): max {benchmarks_primary['max_count']}",
                current_value=primary,
            ))

        # Secondary muscles check
        if benchmarks_secondary.get("should_exist") and not secondary:
            result.issues.append(QualityIssue(
                field="muscles.secondary",
                category=IssueCategory.ANATOMY,
                severity=IssueSeverity.LOW,
                message="No muscles.secondary defined",
                current_value=secondary,
            ))

        # Contribution check - nice to have
        if not contribution and (primary or secondary):
            result.issues.append(QualityIssue(
                field="muscles.contribution",
                category=IssueCategory.ANATOMY,
                severity=IssueSeverity.LOW,
                message="Missing muscles.contribution percentages",
                current_value=None,
            ))
    
    def _check_equipment(self, exercise: Dict[str, Any], result: ReviewResult):
        """Check equipment matches name."""
        name = exercise.get("name", "").lower()
        equipment = exercise.get("equipment", [])
        
        # Extract equipment from name (in parentheses)
        import re
        match = re.search(r"\(([^)]+)\)", name)
        if match:
            name_equipment = match.group(1).lower()
            equipment_lower = [e.lower() for e in equipment]
            
            if name_equipment not in equipment_lower and not any(name_equipment in e for e in equipment_lower):
                result.issues.append(QualityIssue(
                    field="equipment",
                    category=IssueCategory.BIOMECHANICS,
                    severity=IssueSeverity.HIGH,
                    message=f"Equipment mismatch: name says '{name_equipment}' but equipment list is {equipment}",
                    current_value=equipment,
                    suggested_fix=f"Add '{name_equipment}' to equipment list",
                ))
    
    def _check_taxonomy(self, exercise: Dict[str, Any], result: ReviewResult):
        """Check family/variant assignment."""
        family_slug = exercise.get("family_slug")
        variant_key = exercise.get("variant_key")
        approved = exercise.get("approved", False)
        
        if not family_slug:
            result.issues.append(QualityIssue(
                field="family_slug",
                category=IssueCategory.TAXONOMY,
                severity=IssueSeverity.CRITICAL,
                message="Missing family_slug - exercise is unnormalized",
                current_value=None,
            ))
        
        if family_slug and not variant_key:
            result.issues.append(QualityIssue(
                field="variant_key",
                category=IssueCategory.TAXONOMY,
                severity=IssueSeverity.HIGH,
                message="Has family_slug but missing variant_key",
                current_value=None,
            ))

    def _check_schema_migration(self, exercise: Dict[str, Any], result: ReviewResult):
        """Check if exercise needs schema migration from legacy to new format."""
        # Legacy fields that should be migrated
        legacy_fields = {
            "primary_muscles": "muscles.primary",
            "secondary_muscles": "muscles.secondary",
            "instructions": "execution_notes",
        }

        muscles = exercise.get("muscles", {}) or {}
        legacy_issues = []

        for legacy_field, new_field in legacy_fields.items():
            has_legacy = exercise.get(legacy_field) is not None

            # Determine if new field exists
            if "." in new_field:
                parts = new_field.split(".")
                new_value = muscles.get(parts[1]) if parts[0] == "muscles" else None
            else:
                new_value = exercise.get(new_field)

            has_new = bool(new_value)

            if has_legacy and not has_new:
                # Legacy only - needs migration
                legacy_issues.append(f"{legacy_field} -> {new_field}")
            elif has_legacy and has_new:
                # Both exist - needs cleanup (delete legacy)
                pass  # This is handled by SCHEMA_CLEANUP job

        if legacy_issues:
            result.issues.append(QualityIssue(
                field="schema",
                category=IssueCategory.TAXONOMY,
                severity=IssueSeverity.HIGH,
                message=f"Exercise needs schema migration: {', '.join(legacy_issues)}",
                current_value=None,
            ))

    def _check_category(self, exercise: Dict[str, Any], result: ReviewResult):
        """Check category value is valid."""
        category = exercise.get("category", "")
        allowed_values = QUALITY_BENCHMARKS["category"]["allowed_values"]

        if not category:
            result.issues.append(QualityIssue(
                field="category",
                category=IssueCategory.TAXONOMY,
                severity=IssueSeverity.HIGH,
                message="Missing category field",
                current_value=None,
            ))
        elif category not in allowed_values:
            result.issues.append(QualityIssue(
                field="category",
                category=IssueCategory.TAXONOMY,
                severity=IssueSeverity.HIGH,
                message=f"Invalid category '{category}': must be one of {allowed_values}",
                current_value=category,
                suggested_fix="compound" if "exercise" in category.lower() else None,
            ))

    def _check_content_completeness(self, exercise: Dict[str, Any], result: ReviewResult):
        """Check for missing content arrays that should be enriched."""
        # Required content arrays (HIGH priority if missing)
        required_arrays = {
            "execution_notes": "Step-by-step execution instructions",
            "common_mistakes": "Common form errors to avoid",
        }

        # Nice-to-have content arrays (MEDIUM priority if missing)
        optional_arrays = {
            "suitability_notes": "Who the exercise is suitable for",
            "programming_use_cases": "When to program this exercise",
            "stimulus_tags": "Training stimulus tags (Hypertrophy, Strength, etc.)",
        }

        for field, description in required_arrays.items():
            value = exercise.get(field)
            if not value or (isinstance(value, list) and len(value) == 0):
                result.issues.append(QualityIssue(
                    field=field,
                    category=IssueCategory.CONTENT,
                    severity=IssueSeverity.HIGH,
                    message=f"Missing {field}: {description}",
                    current_value=value,
                ))

        for field, description in optional_arrays.items():
            value = exercise.get(field)
            if not value or (isinstance(value, list) and len(value) == 0):
                result.issues.append(QualityIssue(
                    field=field,
                    category=IssueCategory.CONTENT,
                    severity=IssueSeverity.MEDIUM,
                    message=f"Missing {field}: {description}",
                    current_value=value,
                ))

    def _get_llm_client(self):
        """Get or create LLM client."""
        if self.llm_client is None:
            from app.enrichment.llm_client import get_llm_client
            self.llm_client = get_llm_client()
        return self.llm_client
    
    def _build_llm_review_prompt(self, exercise: Dict[str, Any]) -> str:
        """Build prompt for LLM quality review with reasoning guidelines."""
        name = exercise.get("name", "Unknown")
        equipment = exercise.get("equipment", [])
        primary_muscles = exercise.get("primary_muscles", [])
        secondary_muscles = exercise.get("secondary_muscles", [])
        instructions = exercise.get("instructions", "")
        category = exercise.get("category", "")
        
        prompt = f"""{WHAT_GOOD_LOOKS_LIKE}

{INSTRUCTIONS_GUIDANCE}

{MUSCLE_MAPPING_GUIDANCE}

---

## Current Task: Review Exercise Quality

### Exercise Data
Name: {name}
Equipment: {', '.join(equipment) if equipment else 'None'}
Category: {category}
Primary Muscles: {', '.join(primary_muscles) if primary_muscles else 'None'}
Secondary Muscles: {', '.join(secondary_muscles) if secondary_muscles else 'None'}
Instructions: {instructions[:500] + '...' if len(instructions) > 500 else instructions}

---

## Your Reasoning Process

Before flagging any issues, ask yourself:
1. Would a gym user be harmed or confused by the current content?
2. Is this a genuine problem or just my personal preference?
3. If instructions are understandable and safe, they're good enough - don't change them.
4. If muscle mappings are anatomically reasonable, they're good enough - don't change them.

## Response Format
{{
    "needs_action": true/false,
    "reasoning": "Why this exercise does/doesn't need changes",
    "confidence": "high" | "medium" | "low",
    "issues": [
        {{
            "field": "primary_muscles" | "secondary_muscles" | "instructions" | "name",
            "category": "anatomy" | "content" | "biomechanics",
            "severity": "high" | "medium" | "low",
            "message": "Brief description of the issue",
            "suggested_fix": "Optional suggestion"
        }}
    ]
}}

## Rules
- Only flag genuine problems that affect user safety or understanding
- If you're unsure whether something is wrong, don't flag it
- Better to miss a minor issue than to create unnecessary work
- If exercise looks good enough, return empty issues array

Respond with ONLY the JSON object."""

        return prompt
    
    def _apply_llm_analysis(self, exercise: Dict[str, Any], result: ReviewResult):
        """Apply LLM-based semantic quality analysis."""
        import json
        
        # Use llm_client directly if available
        try:
            llm_client = self._get_llm_client()
            
            prompt = self._build_llm_review_prompt(exercise)
            
            # Call LLM with reasoning model for quality analysis
            response = llm_client.complete(
                prompt=prompt,
                output_schema={"type": "object"},
                require_reasoning=False,  # V1.4: Flash-first for cost efficiency
            )
            
            # Parse response - handle markdown code blocks
            try:
                # Strip markdown code block wrappers if present
                clean_response = response.strip()
                if clean_response.startswith("```json"):
                    clean_response = clean_response[7:]  # Remove ```json
                if clean_response.startswith("```"):
                    clean_response = clean_response[3:]  # Remove ```
                if clean_response.endswith("```"):
                    clean_response = clean_response[:-3]  # Remove trailing ```
                clean_response = clean_response.strip()
                
                analysis = json.loads(clean_response)
            except json.JSONDecodeError:
                # Try to extract JSON from response
                import re
                json_match = re.search(r'\{.*\}', response, re.DOTALL)
                if json_match:
                    try:
                        analysis = json.loads(json_match.group())
                    except json.JSONDecodeError:
                        logger.warning("Could not parse LLM review response for %s: %s", result.exercise_id, response[:200])
                        return
                else:
                    logger.warning("Could not parse LLM review response for %s: %s", result.exercise_id, response[:200])
                    return
            
            # Convert LLM issues to our format
            if analysis and analysis.get("issues"):
                severity_map = {
                    "critical": IssueSeverity.CRITICAL,
                    "high": IssueSeverity.HIGH,
                    "medium": IssueSeverity.MEDIUM,
                    "low": IssueSeverity.LOW,
                }
                category_map = {
                    "content": IssueCategory.CONTENT,
                    "anatomy": IssueCategory.ANATOMY,
                    "biomechanics": IssueCategory.BIOMECHANICS,
                    "taxonomy": IssueCategory.TAXONOMY,
                }
                
                for issue in analysis["issues"]:
                    result.issues.append(QualityIssue(
                        field=issue.get("field", "general"),
                        category=category_map.get(issue.get("category", "content"), IssueCategory.CONTENT),
                        severity=severity_map.get(issue.get("severity", "medium"), IssueSeverity.MEDIUM),
                        message=f"[LLM] {issue.get('message', '')}",
                        suggested_fix=issue.get("suggested_fix"),
                    ))
                    
            logger.debug(
                "LLM review for %s: %d issues found", 
                result.exercise_id, 
                len(analysis.get("issues", []))
            )
            
        except Exception as e:
            logger.warning("LLM analysis failed for %s: %s", result.exercise_id, e)
    
    def _compute_quality_score(self, issues: List[QualityIssue]) -> float:
        """Compute overall quality score from issues."""
        if not issues:
            return 1.0
        
        # Severity weights
        weights = {
            IssueSeverity.CRITICAL: 0.4,
            IssueSeverity.HIGH: 0.2,
            IssueSeverity.MEDIUM: 0.1,
            IssueSeverity.LOW: 0.05,
        }
        
        penalty = sum(weights.get(i.severity, 0.1) for i in issues)
        return max(0.0, 1.0 - penalty)
