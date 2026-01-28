"""
Unified Catalog Review Agent - LLM-powered catalog curation.

This module provides a single, unified LLM agent that reviews exercises
and makes all decisions in one comprehensive call:
- Health triage: KEEP, ENRICH, FIX, ARCHIVE
- Duplicate detection: identify and cluster duplicates
- Gap analysis: suggest missing equipment variants
- Action generation: create jobs for each decision

Design Principles (LLM Best Practices):
1. System prompt with clear role and capabilities
2. Structured JSON output schema
3. Chain of thought reasoning before decisions
4. Few-shot examples for calibration
5. Confidence scoring for human escalation
6. Batch processing for context sharing
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from app.enrichment.llm_client import get_llm_client, LLMClient

logger = logging.getLogger(__name__)


# =============================================================================
# SYSTEM PROMPT - Defines the agent's role and capabilities
# =============================================================================

SYSTEM_PROMPT = """You are the Povver Catalog Review Agent. Your role is to maintain a high-quality exercise catalog that helps users train effectively.

## Your Capabilities

1. **Health Triage**: Evaluate each exercise and decide:
   - KEEP: Exercise is good quality, no action needed
   - ENRICH: Exercise is salvageable but missing data
   - FIX_IDENTITY: Name or family_slug is malformed
   - ARCHIVE: Exercise is a mistake, test data, or unsalvageable

2. **Duplicate Detection**: Identify exercises that are:
   - True duplicates (same exercise, different names) → merge
   - Valid variants (same movement, different equipment) → keep separate

3. **Gap Analysis**: Identify missing equipment variants that would add value

## Canonical Naming Taxonomy (IMPORTANT)

The correct naming format is: "Exercise Name (Equipment)" or "Modifier Exercise Name (Equipment)"

### Examples of CORRECT names:
- Deadlift (Barbell)
- Deadlift (Dumbbell)
- Squat (Barbell)
- Underhand Lat Pulldown (Cable)
- Wide-grip Lat Pulldown (Cable)
- Neutral-grip Lat Pulldown (Cable)

### Examples of INCORRECT names that need FIX_IDENTITY:
- "Conventional Deadlift" → should be "Deadlift (Barbell)"
- "Barbell Deadlift" → should be "Deadlift (Barbell)"
- "Lat Pulldown" (when grip variants exist) → should not exist, archive it

### Single-variant exercises (no equipment qualifier needed):
- Farmers Walk (just one version)
- Plank (just one version)
- Pull-up (bodyweight, no qualifier needed)

### Duplicate/Variant Rules:
- If we have "Underhand Lat Pulldown", "Wide-grip Lat Pulldown", etc., then plain "Lat Pulldown" is redundant → ARCHIVE it
- "Conventional Deadlift" and "Deadlift (Barbell)" are duplicates → MERGE into "Deadlift (Barbell)"
- There should only be ONE Deadlift per equipment type

## Decision Framework

Before every decision, ask yourself:
1. Would this change actually help a user?
2. Is the current state causing confusion or safety issues?
3. Am I changing this because it's wrong, or just because it's different from my preference?

If the answer to #1 is "not really" → KEEP as-is.

## What Makes an Exercise "Good Enough"

- Name clearly identifies the exercise
- Instructions allow safe execution (even if not perfect)
- Primary muscles are anatomically correct
- Equipment is specified

## What Requires Action

- ARCHIVE: Gibberish name, empty data, test entries, OR a generic exercise when specific variants already exist
- FIX_IDENTITY: Truncated family_slug, wrong naming format, equipment in wrong field
- ENRICH: Missing instructions, missing muscles, missing category
- MERGE: Same exercise with different names (e.g., "Conventional Deadlift" + "Deadlift (Barbell)")
- KEEP: Everything else

## Confidence Levels

- HIGH: You are certain this needs action (or doesn't)
- MEDIUM: Fairly sure but could be wrong
- LOW: Unsure → recommend human review instead of action
"""

# =============================================================================
# OUTPUT SCHEMA - Structured response format
# =============================================================================

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "exercises": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "exercise_id": {"type": "string"},
                    "decision": {"type": "string", "enum": ["KEEP", "ENRICH", "FIX_IDENTITY", "ARCHIVE", "MERGE"]},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                    "reasoning": {"type": "string"},
                    "fix_details": {"type": "object"},
                    "merge_into": {"type": "string"}
                }
            }
        },
        "duplicates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "canonical_id": {"type": "string"},
                    "canonical_name": {"type": "string"},
                    "duplicate_ids": {"type": "array", "items": {"type": "string"}},
                    "reasoning": {"type": "string"}
                }
            }
        },
        "gaps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "family_slug": {"type": "string"},
                    "missing_equipment": {"type": "string"},
                    "suggested_name": {"type": "string"},
                    "reasoning": {"type": "string"},
                    "confidence": {"type": "string"}
                }
            }
        }
    }
}

# =============================================================================
# FEW-SHOT EXAMPLES
# =============================================================================

FEW_SHOT_EXAMPLES = """
## Example Decisions

### Example 1: Good Exercise - KEEP
```json
{
  "id": "squat_barbell",
  "name": "Back Squat (Barbell)",
  "equipment": ["barbell"],
  "instructions": "1. Set barbell on squat rack at shoulder height...",
  "muscles": {"primary": ["quadriceps", "glutes"]}
}
```
Decision: KEEP
Reasoning: "Exercise has clear name, correct muscles, and usable instructions. No changes needed."

### Example 2: Malformed Entry - ARCHIVE
```json
{
  "id": "test123",
  "name": "asdfasdf",
  "equipment": [],
  "instructions": "",
  "muscles": {}
}
```
Decision: ARCHIVE
Reasoning: "This appears to be test data. Name is gibberish, no useful content. Archive it."

### Example 3: Truncated Family Slug - FIX_IDENTITY
```json
{
  "id": "dead_bug_1",
  "name": "Dead Bug",
  "family_slug": "bug",  // Wrong! Should be "dead_bug"
  "equipment": ["bodyweight"]
}
```
Decision: FIX_IDENTITY
Reasoning: "family_slug 'bug' is truncated. Should be 'dead_bug' to match the exercise name."
fix_details: {"family_slug": "dead_bug"}

### Example 4: Missing Data - ENRICH
```json
{
  "id": "curl_001",
  "name": "Bicep Curl (Dumbbell)",
  "equipment": ["dumbbell"],
  "instructions": "",
  "muscles": {}
}
```
Decision: ENRICH
Reasoning: "Valid exercise but missing instructions and muscle mapping. Needs enrichment."

### Example 5: True Duplicate - MERGE
Two exercises in batch:
- "Barbell Deadlift" (id: deadlift_barbell)
- "Deadlift (Barbell)" (id: deadlift_001)

Decision for deadlift_001: MERGE
merge_into: "deadlift_barbell"
Reasoning: "These are the same exercise with different naming. Keep the one with canonical naming format."
"""

# =============================================================================
# DATA MODELS
# =============================================================================

@dataclass
class ExerciseDecision:
    """Decision for a single exercise."""
    exercise_id: str
    exercise_name: str
    decision: str  # KEEP, ENRICH, FIX_IDENTITY, ARCHIVE, MERGE
    confidence: str  # high, medium, low
    reasoning: str
    fix_details: Optional[Dict[str, Any]] = None
    merge_into: Optional[str] = None


@dataclass
class DuplicateCluster:
    """A cluster of duplicate exercises."""
    canonical_id: str
    canonical_name: str
    duplicate_ids: List[str]
    reasoning: str


@dataclass
class GapSuggestion:
    """A suggested missing exercise."""
    family_slug: str
    missing_equipment: str
    suggested_name: str
    reasoning: str
    confidence: str


@dataclass
class BatchReviewResult:
    """Result of reviewing a batch of exercises."""
    exercises_reviewed: int = 0
    decisions: List[ExerciseDecision] = field(default_factory=list)
    duplicates: List[DuplicateCluster] = field(default_factory=list)
    gaps: List[GapSuggestion] = field(default_factory=list)
    
    # Summary counts
    keep_count: int = 0
    enrich_count: int = 0
    fix_count: int = 0
    archive_count: int = 0
    merge_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "exercises_reviewed": self.exercises_reviewed,
            "decisions": [
                {
                    "exercise_id": d.exercise_id,
                    "exercise_name": d.exercise_name,
                    "decision": d.decision,
                    "confidence": d.confidence,
                    "reasoning": d.reasoning,
                    "fix_details": d.fix_details,
                    "merge_into": d.merge_into,
                }
                for d in self.decisions
            ],
            "duplicates": [
                {
                    "canonical_id": dc.canonical_id,
                    "canonical_name": dc.canonical_name,
                    "duplicate_ids": dc.duplicate_ids,
                    "reasoning": dc.reasoning,
                }
                for dc in self.duplicates
            ],
            "gaps": [
                {
                    "family_slug": g.family_slug,
                    "missing_equipment": g.missing_equipment,
                    "suggested_name": g.suggested_name,
                    "reasoning": g.reasoning,
                    "confidence": g.confidence,
                }
                for g in self.gaps
            ],
            "summary": {
                "keep": self.keep_count,
                "enrich": self.enrich_count,
                "fix": self.fix_count,
                "archive": self.archive_count,
                "merge": self.merge_count,
            },
        }


# =============================================================================
# REVIEW AGENT
# =============================================================================

class CatalogReviewAgent:
    """
    Unified LLM agent for catalog review.
    
    Reviews batches of exercises and returns comprehensive decisions:
    - Health triage for each exercise
    - Duplicate clusters
    - Equipment gap suggestions
    """
    
    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        batch_size: int = 20,
        include_gap_analysis: bool = True,
    ):
        """
        Initialize the review agent.
        
        Args:
            llm_client: LLM client (uses default if not provided)
            batch_size: Exercises per LLM call
            include_gap_analysis: Whether to analyze equipment gaps
        """
        self._llm_client = llm_client
        self.batch_size = batch_size
        self.include_gap_analysis = include_gap_analysis
    
    def _get_llm_client(self) -> LLMClient:
        if self._llm_client is None:
            self._llm_client = get_llm_client()
        return self._llm_client
    
    def _build_review_prompt(
        self,
        exercises: List[Dict[str, Any]],
        family_context: Optional[Dict[str, List[str]]] = None,
    ) -> str:
        """Build the review prompt for a batch of exercises."""
        
        # Format exercises for prompt
        exercises_json = json.dumps(exercises, indent=2, default=str)
        
        # Build family context if provided
        family_section = ""
        if family_context and self.include_gap_analysis:
            family_section = "\n## Current Equipment Coverage by Family\n"
            for family, equipment in family_context.items():
                family_section += f"- {family}: {', '.join(equipment)}\n"
        
        prompt = f"""{SYSTEM_PROMPT}

{FEW_SHOT_EXAMPLES}

---

## Your Task

Review the following batch of exercises and provide:
1. A decision for each exercise (KEEP, ENRICH, FIX_IDENTITY, ARCHIVE, or MERGE)
2. Any duplicate clusters you identify
3. Any equipment gap suggestions (if families have obvious missing variants)

Think through each exercise systematically:
- First assess what's there
- Then decide if action is needed
- Explain your reasoning clearly
{family_section}
## Exercises to Review

{exercises_json}

---

## Response Format

Respond with a JSON object containing:
1. "exercises": array of decisions for each exercise
2. "duplicates": array of duplicate clusters (if any found)
3. "gaps": array of gap suggestions (if obvious gaps found)

Think carefully. If an exercise is fine, say KEEP. Don't over-engineer.
Only suggest gaps for common equipment that would genuinely help users.

Respond with ONLY the JSON object, no markdown code blocks."""

        return prompt
    
    def review_batch(
        self,
        exercises: List[Dict[str, Any]],
        family_context: Optional[Dict[str, List[str]]] = None,
    ) -> BatchReviewResult:
        """
        Review a batch of exercises.
        
        Args:
            exercises: List of exercise dicts
            family_context: Optional dict of family_slug -> existing equipment
            
        Returns:
            BatchReviewResult with all decisions
        """
        result = BatchReviewResult(exercises_reviewed=len(exercises))
        
        if not exercises:
            return result
        
        # Build family context from exercises if not provided
        if family_context is None and self.include_gap_analysis:
            family_context = {}
            for ex in exercises:
                family = ex.get("family_slug", "")
                if family:
                    if family not in family_context:
                        family_context[family] = []
                    equipment = ex.get("equipment", [])
                    if equipment:
                        primary = equipment[0] if isinstance(equipment, list) else equipment
                        if primary not in family_context[family]:
                            family_context[family].append(primary)
        
        # Build and execute prompt
        prompt = self._build_review_prompt(exercises, family_context)
        
        try:
            llm_client = self._get_llm_client()
            response = llm_client.complete(
                prompt=prompt,
                output_schema=OUTPUT_SCHEMA,
                require_reasoning=True,
            )
            
            # Parse response
            parsed = self._parse_response(response)
            
            # Map exercise IDs to names for enrichment
            id_to_name = {ex.get("id", ex.get("doc_id", "")): ex.get("name", "") for ex in exercises}
            
            # Process exercise decisions
            for ex_decision in parsed.get("exercises", []):
                exercise_id = ex_decision.get("exercise_id", "")
                decision_str = ex_decision.get("decision", "KEEP").upper()
                
                decision = ExerciseDecision(
                    exercise_id=exercise_id,
                    exercise_name=id_to_name.get(exercise_id, ""),
                    decision=decision_str,
                    confidence=ex_decision.get("confidence", "medium"),
                    reasoning=ex_decision.get("reasoning", ""),
                    fix_details=ex_decision.get("fix_details"),
                    merge_into=ex_decision.get("merge_into"),
                )
                result.decisions.append(decision)
                
                # Update counts
                if decision_str == "KEEP":
                    result.keep_count += 1
                elif decision_str == "ENRICH":
                    result.enrich_count += 1
                elif decision_str == "FIX_IDENTITY":
                    result.fix_count += 1
                elif decision_str == "ARCHIVE":
                    result.archive_count += 1
                elif decision_str == "MERGE":
                    result.merge_count += 1
            
            # Process duplicates
            for dup in parsed.get("duplicates", []):
                cluster = DuplicateCluster(
                    canonical_id=dup.get("canonical_id", ""),
                    canonical_name=dup.get("canonical_name", ""),
                    duplicate_ids=dup.get("duplicate_ids", []),
                    reasoning=dup.get("reasoning", ""),
                )
                result.duplicates.append(cluster)
            
            # Process gaps
            for gap in parsed.get("gaps", []):
                suggestion = GapSuggestion(
                    family_slug=gap.get("family_slug", ""),
                    missing_equipment=gap.get("missing_equipment", ""),
                    suggested_name=gap.get("suggested_name", ""),
                    reasoning=gap.get("reasoning", ""),
                    confidence=gap.get("confidence", "medium"),
                )
                result.gaps.append(suggestion)
            
            logger.info(
                "Reviewed batch: %d exercises | KEEP=%d ENRICH=%d FIX=%d ARCHIVE=%d MERGE=%d | %d gaps",
                result.exercises_reviewed,
                result.keep_count,
                result.enrich_count,
                result.fix_count,
                result.archive_count,
                result.merge_count,
                len(result.gaps),
            )
            
        except Exception as e:
            logger.exception("Review batch failed: %s", e)
            # On failure, mark all as KEEP to be safe
            for ex in exercises:
                result.decisions.append(ExerciseDecision(
                    exercise_id=ex.get("id", ex.get("doc_id", "")),
                    exercise_name=ex.get("name", ""),
                    decision="KEEP",
                    confidence="low",
                    reasoning=f"LLM review failed: {str(e)}",
                ))
                result.keep_count += 1
        
        return result
    
    def _parse_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM response to JSON."""
        import re
        
        # Clean response
        clean = response.strip()
        
        # First, try to extract JSON from markdown code blocks using regex
        # This handles both ```json\n{...}\n``` and ```\n{...}\n``` patterns
        code_block_pattern = r'```(?:json)?\s*\n?([\s\S]*?)\n?\s*```'
        code_match = re.search(code_block_pattern, clean)
        if code_match:
            clean = code_match.group(1).strip()
            logger.debug("Extracted JSON from markdown code block: %d chars", len(clean))
        elif clean.startswith('```'):
            # Fallback: Manual extraction if regex didn't match
            # Find the end of the opening line (```json or ```)
            first_newline = clean.find('\n')
            if first_newline != -1:
                # Find closing ``` - search from the end
                closing_idx = clean.rfind('```')
                if closing_idx > first_newline:
                    clean = clean[first_newline + 1:closing_idx].strip()
                    logger.debug("Manual code block extraction: %d chars", len(clean))
                else:
                    # No closing ``` found, just strip the opening line
                    clean = clean[first_newline + 1:].strip()
        
        # Try parsing as-is first
        try:
            return json.loads(clean)
        except json.JSONDecodeError as e:
            logger.debug("First JSON parse attempt failed at pos %d: %s", e.pos if hasattr(e, 'pos') else -1, e.msg if hasattr(e, 'msg') else str(e))
        
        # Try to find JSON object in response (handles any prefix/suffix text)
        # Use a more robust approach: find matching braces
        start_idx = clean.find('{')
        if start_idx != -1:
            # Count braces to find the matching closing brace
            brace_count = 0
            end_idx = start_idx
            in_string = False
            escape_next = False
            
            for i, char in enumerate(clean[start_idx:], start=start_idx):
                if escape_next:
                    escape_next = False
                    continue
                if char == '\\' and in_string:
                    escape_next = True
                    continue
                if char == '"' and not escape_next:
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                    
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end_idx = i + 1
                        break
            
            if end_idx > start_idx:
                json_str = clean[start_idx:end_idx]
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError as e:
                    logger.warning("JSON parse error at position %d: %s", e.pos, e.msg)
                    # Try to repair truncated JSON
                    repaired = self._repair_truncated_json(json_str)
                    if repaired:
                        try:
                            return json.loads(repaired)
                        except json.JSONDecodeError:
                            pass
        
        # Log more context for debugging parse failures
        logger.warning(
            "Failed to parse LLM response (len=%d). First 500 chars: %s",
            len(response),
            response[:500]
        )
        if len(response) > 500:
            logger.warning("Last 200 chars of response: ...%s", response[-200:])
        return {"exercises": [], "duplicates": [], "gaps": []}
    
    def _repair_truncated_json(self, json_str: str) -> Optional[str]:
        """Attempt to repair truncated JSON by closing open structures."""
        # Count open braces/brackets
        brace_count = 0
        bracket_count = 0
        in_string = False
        escape_next = False
        
        for char in json_str:
            if escape_next:
                escape_next = False
                continue
            if char == '\\' and in_string:
                escape_next = True
                continue
            if char == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
            elif char == '[':
                bracket_count += 1
            elif char == ']':
                bracket_count -= 1
        
        # If we're inside a string, close it
        if in_string:
            json_str += '"'
        
        # Remove trailing comma if present
        json_str = json_str.rstrip()
        if json_str.endswith(','):
            json_str = json_str[:-1]
        
        # Close open brackets and braces
        json_str += ']' * bracket_count
        json_str += '}' * brace_count
        
        return json_str
    
    async def review_batch_async(
        self,
        exercises: List[Dict[str, Any]],
        family_context: Optional[Dict[str, List[str]]] = None,
    ) -> BatchReviewResult:
        """Async version of review_batch for concurrent processing."""
        # Run in thread pool since LLM client may be synchronous
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self.review_batch,
            exercises,
            family_context,
        )


# =============================================================================
# CATALOG-WIDE REVIEW
# =============================================================================

async def review_catalog_async(
    exercises: List[Dict[str, Any]],
    batch_size: int = 20,
    max_concurrent: int = 3,
    include_gap_analysis: bool = True,
) -> List[BatchReviewResult]:
    """
    Review entire catalog with concurrent batch processing.
    
    Args:
        exercises: All exercises to review
        batch_size: Exercises per batch
        max_concurrent: Maximum concurrent LLM calls
        include_gap_analysis: Whether to include gap suggestions
        
    Returns:
        List of BatchReviewResult for each batch
    """
    agent = CatalogReviewAgent(
        batch_size=batch_size,
        include_gap_analysis=include_gap_analysis,
    )
    
    # Split into batches
    batches = [exercises[i:i + batch_size] for i in range(0, len(exercises), batch_size)]
    
    # Build global family context
    family_context: Dict[str, List[str]] = {}
    for ex in exercises:
        family = ex.get("family_slug", "")
        if family:
            if family not in family_context:
                family_context[family] = []
            equipment = ex.get("equipment", [])
            if equipment:
                primary = equipment[0] if isinstance(equipment, list) else equipment
                if primary not in family_context[family]:
                    family_context[family].append(primary)
    
    logger.info("Starting catalog review: %d exercises in %d batches", len(exercises), len(batches))
    
    # Process batches with semaphore for concurrency control
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def review_with_semaphore(batch):
        async with semaphore:
            return await agent.review_batch_async(batch, family_context)
    
    tasks = [review_with_semaphore(batch) for batch in batches]
    results = await asyncio.gather(*tasks)
    
    return list(results)


def review_catalog(
    exercises: List[Dict[str, Any]],
    batch_size: int = 20,
    include_gap_analysis: bool = True,
) -> List[BatchReviewResult]:
    """
    Synchronous wrapper for review_catalog_async.
    
    For use in non-async contexts.
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(
            review_catalog_async(exercises, batch_size, include_gap_analysis=include_gap_analysis)
        )
    finally:
        loop.close()


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "CatalogReviewAgent",
    "BatchReviewResult",
    "ExerciseDecision",
    "DuplicateCluster",
    "GapSuggestion",
    "review_catalog",
    "review_catalog_async",
]
