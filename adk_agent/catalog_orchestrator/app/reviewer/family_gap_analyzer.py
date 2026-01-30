"""
Family Gap Analyzer - LLM-powered detection of missing equipment variants.

This module analyzes exercise families to identify:
1. Which equipment variants exist within a family (e.g., Squat has Barbell, Dumbbell)
2. Which common equipment variants are missing (uses LLM reasoning)
3. Creates EXERCISE_ADD jobs to fill the gaps

Uses gemini-2.5-pro for reasoning about:
- What equipment variants are biomechanically feasible for each movement
- What equipment is commonly available in gyms
- Whether a missing variant would add training value
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from app.jobs.models import JobType, JobQueue
from app.reviewer.what_good_looks_like import (
    WHAT_GOOD_LOOKS_LIKE,
    FAMILY_EXPANSION_GUIDANCE,
)

logger = logging.getLogger(__name__)


# =============================================================================
# DATA MODELS
# =============================================================================

@dataclass
class EquipmentVariant:
    """An equipment variant within a family."""
    equipment: str
    exercise_id: str
    exercise_name: str
    variant_key: str
    approved: bool = False


@dataclass
class FamilyAnalysis:
    """Analysis result for a single exercise family."""
    family_slug: str
    canonical_name: str  # e.g., "Squat", "Bench Press"
    
    # Existing variants
    existing_variants: List[EquipmentVariant] = field(default_factory=list)
    existing_equipment: Set[str] = field(default_factory=set)
    
    # Gap analysis (from LLM)
    missing_equipment: List[str] = field(default_factory=list)
    
    # Suggestions
    suggested_exercises: List[Dict[str, Any]] = field(default_factory=list)
    
    # Metrics
    completeness_score: float = 1.0  # % of expected equipment covered
    
    # LLM reasoning
    llm_reasoning: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "family_slug": self.family_slug,
            "canonical_name": self.canonical_name,
            "existing_equipment": list(self.existing_equipment),
            "missing_equipment": self.missing_equipment,
            "completeness_score": self.completeness_score,
            "suggested_exercises": self.suggested_exercises,
            "llm_reasoning": self.llm_reasoning,
        }


@dataclass 
class GapAnalysisResult:
    """Result of analyzing multiple families for gaps."""
    families_analyzed: int = 0
    families_with_gaps: int = 0
    total_missing_variants: int = 0
    suggestions: List[Dict[str, Any]] = field(default_factory=list)
    family_results: List[FamilyAnalysis] = field(default_factory=list)


# =============================================================================
# LLM GAP ANALYZER
# =============================================================================

class FamilyGapAnalyzer:
    """
    LLM-powered analyzer to detect missing equipment variants.
    
    Uses gemini-2.5-pro to reason about what equipment variants 
    should exist for each exercise family based on:
    - Biomechanical feasibility
    - Common gym equipment availability
    - Training value
    """
    
    def __init__(
        self,
        max_suggestions_per_family: int = 3,
        llm_client = None,
    ):
        """
        Initialize the analyzer.
        
        Args:
            max_suggestions_per_family: Max suggested exercises per family
            llm_client: LLM client (uses default if not provided)
        """
        self.max_suggestions_per_family = max_suggestions_per_family
        self._llm_client = llm_client
    
    def _get_llm_client(self):
        """Get or create LLM client."""
        if self._llm_client is None:
            from app.enrichment.llm_client import get_llm_client
            self._llm_client = get_llm_client()
        return self._llm_client
    
    def _build_gap_analysis_prompt(
        self,
        family_slug: str,
        canonical_name: str,
        existing_equipment: List[str],
        sample_exercises: List[Dict[str, Any]],
    ) -> str:
        """Build LLM prompt for gap analysis with reasoning guidelines."""
        
        # Format exercise samples
        exercise_examples = []
        for ex in sample_exercises[:5]:
            exercise_examples.append(f"- {ex.get('name', 'Unknown')} (equipment: {ex.get('equipment', [])})")
        
        prompt = f"""{WHAT_GOOD_LOOKS_LIKE}

{FAMILY_EXPANSION_GUIDANCE}

---

## Current Task: Analyze Exercise Family for Missing Equipment Variants

### Exercise Family: {canonical_name}
Family Slug: {family_slug}

### Existing Equipment Variants
{', '.join(existing_equipment) if existing_equipment else 'None'}

### Sample Exercises in Family
{chr(10).join(exercise_examples) if exercise_examples else 'No examples available'}

---

## Your Reasoning Process

Before suggesting any new variants, ask yourself:
1. Does this family already have good coverage for common gym equipment?
2. Would a typical gym user actually look for the variants I'm considering?
3. Am I suggesting variants just for "completeness" or because they'd genuinely help users?

If the family already has 3-4 common equipment variants, it's probably complete enough.

## Response Format
{{
    "needs_action": true/false,
    "reasoning": "Why this family does/doesn't need more variants",
    "confidence": "high" | "medium" | "low",
    "missing_equipment": ["equipment1"] or []
}}

## Rules
- Only suggest equipment that a typical gym user would have access to
- Barbell, dumbbell, kettlebell, cable, machine, bodyweight are common
- Trap bar, landmine, specialty bars are NOT common - skip unless asked
- If you're unsure whether a variant would help, return empty array
- Better to suggest nothing than to suggest unnecessary variants

Respond with ONLY the JSON object."""

        return prompt
    
    def analyze_family(
        self,
        family_slug: str,
        exercises: List[Dict[str, Any]],
    ) -> FamilyAnalysis:
        """
        Analyze a single exercise family for missing equipment variants using LLM.
        
        Args:
            family_slug: The family slug (e.g., "squat", "bench_press")
            exercises: All exercises in this family
            
        Returns:
            FamilyAnalysis with existing variants and LLM suggestions
        """
        # Derive canonical name from family slug
        canonical_name = family_slug.replace("_", " ").title()
        
        result = FamilyAnalysis(
            family_slug=family_slug,
            canonical_name=canonical_name,
        )
        
        # Extract existing equipment variants
        for ex in exercises:
            equipment_list = ex.get("equipment", [])
            variant_key = ex.get("variant_key", "")
            
            # Get primary equipment (usually first in list or from variant_key)
            primary_equipment = None
            if equipment_list:
                primary_equipment = equipment_list[0].lower().replace(" ", "_")
            elif variant_key:
                primary_equipment = variant_key.lower()
            
            if primary_equipment:
                result.existing_equipment.add(primary_equipment)
                result.existing_variants.append(EquipmentVariant(
                    equipment=primary_equipment,
                    exercise_id=ex.get("id", ex.get("doc_id", "")),
                    exercise_name=ex.get("name", ""),
                    variant_key=variant_key,
                    approved=ex.get("approved", False),
                ))
        
        # Skip families with only 1 exercise or very small families
        if len(exercises) < 1:
            result.completeness_score = 1.0
            return result
        
        # Use LLM for gap analysis
        try:
            llm_client = self._get_llm_client()
            
            prompt = self._build_gap_analysis_prompt(
                family_slug=family_slug,
                canonical_name=canonical_name,
                existing_equipment=list(result.existing_equipment),
                sample_exercises=exercises,
            )
            
            # Call LLM with reasoning model
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
                
                llm_result = json.loads(clean_response)
            except json.JSONDecodeError:
                # Try to extract JSON from response
                import re
                json_match = re.search(r'\{.*\}', response, re.DOTALL)
                if json_match:
                    try:
                        llm_result = json.loads(json_match.group())
                    except json.JSONDecodeError:
                        logger.warning("Could not parse LLM response for %s: %s", family_slug, response[:200])
                        llm_result = {"missing_equipment": [], "reasoning": "Parse error"}
                else:
                    logger.warning("Could not parse LLM response for %s: %s", family_slug, response[:200])
                    llm_result = {"missing_equipment": [], "reasoning": "Parse error"}
            
            missing = llm_result.get("missing_equipment", [])
            result.missing_equipment = missing[:self.max_suggestions_per_family]
            result.llm_reasoning = llm_result.get("reasoning", "")
            
            logger.debug(
                "LLM gap analysis for %s: %d missing variants (confidence: %s)",
                family_slug, len(result.missing_equipment), llm_result.get("confidence", "unknown")
            )
            
        except Exception as e:
            logger.exception("LLM gap analysis failed for %s: %s", family_slug, e)
            # Return empty suggestions on LLM failure
            result.missing_equipment = []
            result.llm_reasoning = f"LLM analysis failed: {str(e)}"
        
        # Compute completeness score
        total_expected = len(result.existing_equipment) + len(result.missing_equipment)
        if total_expected > 0:
            result.completeness_score = len(result.existing_equipment) / total_expected
        
        # Generate suggestions for missing variants
        for equipment in result.missing_equipment[:self.max_suggestions_per_family]:
            # Format equipment nicely for suggestion
            equipment_display = equipment.replace("_", " ").title()
            suggested_name = f"{canonical_name} ({equipment_display})"
            
            result.suggested_exercises.append({
                "suggested_name": suggested_name,
                "family_slug": family_slug,
                "equipment": [equipment],
                "variant_key": equipment,
                "source": "llm_family_gap_analysis",
                "reason": result.llm_reasoning or f"LLM identified {equipment_display} as missing variant",
            })
        
        return result
    
    def analyze_catalog(
        self,
        exercises: List[Dict[str, Any]],
    ) -> GapAnalysisResult:
        """
        Analyze entire catalog grouped by family.
        
        Args:
            exercises: All exercises in the catalog
            
        Returns:
            GapAnalysisResult with all family analyses
        """
        result = GapAnalysisResult()
        
        # Group by family
        families: Dict[str, List[Dict[str, Any]]] = {}
        for ex in exercises:
            family_slug = ex.get("family_slug")
            if not family_slug:
                continue
            if family_slug not in families:
                families[family_slug] = []
            families[family_slug].append(ex)
        
        logger.info("Analyzing %d families for equipment gaps with LLM", len(families))
        
        # Analyze each family
        for family_slug, family_exercises in families.items():
            analysis = self.analyze_family(family_slug, family_exercises)
            result.family_results.append(analysis)
            result.families_analyzed += 1
            
            # Track gaps
            if analysis.missing_equipment:
                result.families_with_gaps += 1
                result.total_missing_variants += len(analysis.missing_equipment)
                result.suggestions.extend(analysis.suggested_exercises)
        
        logger.info(
            "LLM gap analysis complete: %d families, %d with gaps, %d missing variants",
            result.families_analyzed,
            result.families_with_gaps,
            result.total_missing_variants,
        )
        
        return result
    
    def create_jobs_from_gaps(
        self,
        gap_result: GapAnalysisResult,
        dry_run: bool = True,
        max_jobs: int = 20,
    ) -> Dict[str, Any]:
        """
        Create EXERCISE_ADD jobs from gap analysis.
        
        Now checks if exercise with expected slug already exists BEFORE creating job.
        
        Args:
            gap_result: Result from analyze_catalog
            dry_run: If True, don't actually create jobs
            max_jobs: Maximum jobs to create
            
        Returns:
            Summary of jobs created
        """
        from app.jobs.queue import create_job
        from app.family.taxonomy import derive_name_slug, derive_canonical_name
        from google.cloud import firestore
        
        jobs_created = []
        jobs_skipped_existing = []
        
        # Get Firestore client for duplicate check
        db = firestore.Client() if not dry_run else None
        
        for suggestion in gap_result.suggestions[:max_jobs]:
            job_info = {
                "suggested_name": suggestion["suggested_name"],
                "family_slug": suggestion["family_slug"],
                "equipment": suggestion["equipment"],
                "reason": suggestion["reason"],
            }
            
            # Compute expected slug (same logic as executor)
            equipment = suggestion["equipment"][0] if suggestion.get("equipment") else None
            exercise_name = derive_canonical_name(suggestion["suggested_name"], equipment) if equipment else suggestion["suggested_name"]
            expected_slug = derive_name_slug(exercise_name)
            
            # Check if exercise with this slug already exists
            if not dry_run and db:
                existing_doc_id = self._find_exercise_by_slug(db, expected_slug)
                if existing_doc_id:
                    logger.info(
                        "Skipping EXERCISE_ADD for '%s' (slug: %s) - already exists: %s",
                        suggestion["suggested_name"], expected_slug, existing_doc_id
                    )
                    jobs_skipped_existing.append({
                        "suggested_name": suggestion["suggested_name"],
                        "expected_slug": expected_slug,
                        "existing_doc_id": existing_doc_id,
                        "reason": "Exercise with this slug already exists",
                    })
                    continue
            
            if not dry_run:
                try:
                    job = create_job(
                        job_type=JobType.EXERCISE_ADD,
                        queue=JobQueue.MAINTENANCE,
                        priority=30,  # Lower priority for gap-filling
                        family_slug=suggestion["family_slug"],
                        enrichment_spec={
                            "type": "exercise_add",
                            "suggested_name": suggestion["suggested_name"],
                            "equipment": suggestion["equipment"],
                            "variant_key": suggestion["variant_key"],
                            "source": "llm_family_gap_analysis",
                        },
                    )
                    job_info["job_id"] = job.id
                except Exception as e:
                    logger.exception("Failed to create job for %s: %s", suggestion["suggested_name"], e)
                    job_info["error"] = str(e)
            else:
                job_info["job_id"] = f"dry-run-{suggestion['family_slug']}-{suggestion['variant_key']}"
            
            jobs_created.append(job_info)
        
        return {
            "jobs_created": len(jobs_created),
            "jobs_skipped_existing": len(jobs_skipped_existing),
            "dry_run": dry_run,
            "jobs": jobs_created,
            "skipped_existing": jobs_skipped_existing,
            "total_suggestions": len(gap_result.suggestions),
            "families_with_gaps": gap_result.families_with_gaps,
        }
    
    def _find_exercise_by_slug(self, db, name_slug: str) -> Optional[str]:
        """
        Check if any exercise with this name_slug exists.
        
        Returns the doc_id if found, None otherwise.
        """
        from google.cloud.firestore_v1 import FieldFilter
        query = db.collection('exercises').where(
            filter=FieldFilter('name_slug', '==', name_slug)
        ).limit(1)
        docs = list(query.stream())
        return docs[0].id if docs else None


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def analyze_family_gaps(
    exercises: List[Dict[str, Any]],
    llm_client = None,
) -> GapAnalysisResult:
    """
    Convenience function to analyze exercise families for gaps using LLM.
    
    Args:
        exercises: All exercises in catalog
        llm_client: Optional LLM client (uses default if not provided)
        
    Returns:
        GapAnalysisResult
    """
    analyzer = FamilyGapAnalyzer(llm_client=llm_client)
    return analyzer.analyze_catalog(exercises)
