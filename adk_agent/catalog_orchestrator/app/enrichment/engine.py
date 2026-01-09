"""
Enrichment Engine - Compute field values using LLM.

This module provides the core enrichment logic:
- Prompt construction from exercise data and spec
- LLM invocation with appropriate model selection
- Response parsing and validation
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.enrichment.models import EnrichmentSpec, EnrichmentResult
from app.enrichment.llm_client import LLMClient, get_llm_client
from app.enrichment.validators import validate_enrichment_output, parse_llm_response

logger = logging.getLogger(__name__)


def build_enrichment_prompt(
    exercise: Dict[str, Any],
    spec: EnrichmentSpec,
) -> str:
    """
    Build LLM prompt for enriching a single exercise.
    
    Args:
        exercise: Exercise data (minimal fields for token safety)
        spec: Enrichment specification
        
    Returns:
        Formatted prompt string
    """
    # Extract relevant exercise fields
    name = exercise.get("name", "Unknown")
    equipment = exercise.get("equipment", [])
    primary_muscles = exercise.get("primary_muscles", [])
    secondary_muscles = exercise.get("secondary_muscles", [])
    instructions = exercise.get("instructions", "")
    category = exercise.get("category", "")
    
    # Build exercise context
    exercise_context = f"""Exercise: {name}
Equipment: {', '.join(equipment) if equipment else 'None'}
Primary Muscles: {', '.join(primary_muscles) if primary_muscles else 'None'}
Secondary Muscles: {', '.join(secondary_muscles) if secondary_muscles else 'None'}
Category: {category}"""
    
    if instructions:
        # Truncate instructions to save tokens
        truncated = instructions[:500] + "..." if len(instructions) > 500 else instructions
        exercise_context += f"\nInstructions: {truncated}"
    
    # Build output format section
    output_format = ""
    if spec.output_type == "enum" and spec.allowed_values:
        output_format = f"Respond with exactly one of: {', '.join(str(v) for v in spec.allowed_values)}"
    elif spec.output_type == "number":
        if spec.allowed_values and len(spec.allowed_values) == 2:
            output_format = f"Respond with a number between {spec.allowed_values[0]} and {spec.allowed_values[1]}"
        else:
            output_format = "Respond with a single number"
    elif spec.output_type == "boolean":
        output_format = "Respond with 'true' or 'false'"
    elif spec.output_type == "object":
        output_format = "Respond with a JSON object"
    else:
        output_format = "Respond with a brief value"
    
    prompt = f"""You are analyzing an exercise to compute a specific field value.

{exercise_context}

Task: {spec.instructions}

Field to compute: {spec.field_path}

{output_format}

Respond with ONLY the value, no explanation or formatting."""
    
    return prompt


def compute_enrichment(
    exercise: Dict[str, Any],
    spec: EnrichmentSpec,
    llm_client: Optional[LLMClient] = None,
) -> EnrichmentResult:
    """
    Compute enrichment value for a single exercise.
    
    Args:
        exercise: Exercise data
        spec: Enrichment specification
        llm_client: LLM client (creates default if not provided)
        
    Returns:
        EnrichmentResult with computed value and validation status
    """
    exercise_id = exercise.get("id", exercise.get("doc_id", "unknown"))
    
    result = EnrichmentResult(
        exercise_id=exercise_id,
        spec_id=spec.spec_id,
        spec_version=spec.spec_version,
        computed_at=datetime.utcnow(),
    )
    
    # Get LLM client
    client = llm_client or get_llm_client()
    
    # Determine if this needs reasoning model
    require_reasoning = spec.requires_reasoning()
    result.model_used = client.get_model_name(require_reasoning)
    
    try:
        # Build prompt
        prompt = build_enrichment_prompt(exercise, spec)
        
        # Build output schema for structured output hint
        output_schema = None
        if spec.output_type == "enum" and spec.allowed_values:
            output_schema = {"type": "string", "enum": spec.allowed_values}
        elif spec.output_type == "number":
            output_schema = {"type": "number"}
        elif spec.output_type == "boolean":
            output_schema = {"type": "boolean"}
        elif spec.output_type == "object":
            output_schema = {"type": "object"}
        
        # Call LLM
        raw_response = client.complete(
            prompt=prompt,
            output_schema=output_schema,
            require_reasoning=require_reasoning,
        )
        
        # Parse response
        parsed_value = parse_llm_response(raw_response, spec)
        
        # Validate output
        validation = validate_enrichment_output(parsed_value, spec)
        
        result.validation_passed = validation.valid
        result.validation_errors = validation.errors
        
        if validation.valid:
            result.success = True
            result.value = validation.value
        else:
            result.success = False
            logger.warning(
                "Enrichment validation failed for %s: %s",
                exercise_id, validation.errors
            )
        
    except Exception as e:
        logger.exception("Enrichment failed for %s: %s", exercise_id, e)
        result.success = False
        result.validation_errors = [str(e)]
    
    return result


def validate_enrichment(
    value: Any,
    spec: EnrichmentSpec,
) -> "ValidationResult":
    """
    Validate an enrichment value against its spec.
    
    Convenience wrapper around validate_enrichment_output.
    
    Args:
        value: Value to validate
        spec: Enrichment specification
        
    Returns:
        ValidationResult
    """
    return validate_enrichment_output(value, spec)


def compute_enrichment_batch(
    exercises: List[Dict[str, Any]],
    spec: EnrichmentSpec,
    llm_client: Optional[LLMClient] = None,
) -> List[EnrichmentResult]:
    """
    Compute enrichment values for a batch of exercises.
    
    Processes exercises sequentially (parallel processing can be added later).
    
    Args:
        exercises: List of exercise data dicts
        spec: Enrichment specification
        llm_client: LLM client
        
    Returns:
        List of EnrichmentResults
    """
    client = llm_client or get_llm_client()
    results = []
    
    for exercise in exercises:
        result = compute_enrichment(exercise, spec, client)
        results.append(result)
    
    # Log summary
    succeeded = sum(1 for r in results if r.success)
    logger.info(
        "Batch enrichment complete: %d/%d succeeded (spec=%s)",
        succeeded, len(results), spec.spec_id
    )
    
    return results


__all__ = [
    "build_enrichment_prompt",
    "compute_enrichment",
    "validate_enrichment",
    "compute_enrichment_batch",
]
