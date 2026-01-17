"""
Enrichment Engine - Compute field values using LLM.

This module provides the core enrichment logic:
- Prompt construction from exercise data and spec
- LLM invocation with appropriate model selection
- Response parsing and validation
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.enrichment.models import EnrichmentSpec, EnrichmentResult
from app.enrichment.llm_client import LLMClient, get_llm_client
from app.enrichment.validators import validate_enrichment_output, parse_llm_response
from app.enrichment.exercise_field_guide import (
    FIELD_SPECS,
    GOLDEN_EXAMPLES,
    NAMING_TAXONOMY,
    get_field_spec,
    get_enrichable_fields,
)

logger = logging.getLogger(__name__)


# =============================================================================
# ENRICHMENT PHILOSOPHY GUIDELINES
# =============================================================================

ENRICHMENT_GUIDELINES = """
## Enrichment Guidelines

You are generating field values for an exercise. Follow these principles:

### Core Principle: Generate Quality, Not Quantity
- If the exercise already has reasonable content, don't override it
- Focus on accuracy over verbosity
- Simple, clear values are better than complex ones

### Instructions Generation
- Write instructions a gym-goer can actually follow
- Include key safety cues (back position, joint alignment)
- Use numbered steps or clear paragraphs
- Avoid overly technical jargon ("sagittal plane", "proprioceptive")
- Keep it practical and actionable

### Muscle Mapping
- Primary muscles = the 1-3 muscles doing most of the work
- Don't list every muscle that's slightly activated
- Be anatomically accurate for the movement pattern
- Common compound movements have predictable primary muscles

### Difficulty Rating
- Consider: coordination required, injury risk, prerequisite strength
- "beginner" = bodyweight, machine-assisted, simple movements
- "intermediate" = free weights, moderate coordination
- "advanced" = complex movements, high load, high skill requirement

### When Unsure
If you're not confident about a value, use the most common/default option
rather than guessing something unusual.
"""


def build_enrichment_prompt(
    exercise: Dict[str, Any],
    spec: EnrichmentSpec,
    include_guidelines: bool = True,
) -> str:
    """
    Build LLM prompt for enriching a single exercise.
    
    Args:
        exercise: Exercise data (minimal fields for token safety)
        spec: Enrichment specification
        include_guidelines: Whether to include reasoning guidelines
        
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
        exercise_context += f"\nCurrent Instructions: {truncated}"
    
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
    
    # Build prompt with optional guidelines
    guidelines_section = ENRICHMENT_GUIDELINES if include_guidelines else ""
    
    prompt = f"""{guidelines_section}

---

## Current Task: Generate Field Value

{exercise_context}

### Task
{spec.instructions}

### Field to compute
{spec.field_path}

### Output Format
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


# =============================================================================
# FIELD GUIDE BASED ENRICHMENT
# =============================================================================

def build_field_guide_prompt(
    exercise: Dict[str, Any],
    field_path: str,
    include_example: bool = True,
) -> str:
    """
    Build an LLM prompt using the exercise field guide specifications.
    
    This uses the canonical field specs, valid values, and golden examples
    to create a well-structured prompt.
    
    Args:
        exercise: Exercise data dict
        field_path: The field to enrich (e.g., "instructions", "muscles.primary")
        include_example: Whether to include a golden example
        
    Returns:
        Formatted prompt string
    """
    field_spec = get_field_spec(field_path)
    if not field_spec:
        raise ValueError(f"Unknown field: {field_path}")
    
    if not field_spec.enrichable:
        raise ValueError(f"Field {field_path} is not enrichable")
    
    # Build exercise context
    name = exercise.get("name", "Unknown")
    equipment = exercise.get("equipment", [])
    category = exercise.get("category", "")
    
    exercise_section = f"""## Exercise to Enrich

Name: {name}
Equipment: {', '.join(equipment) if equipment else 'None'}
Category: {category}"""
    
    # Add current field value if exists
    current_value = _get_nested_field(exercise, field_path)
    if current_value:
        exercise_section += f"\nCurrent {field_spec.name}: {current_value}"
    
    # Build field specification section
    field_section = f"""## Field to Generate: {field_spec.name}

Path: {field_spec.field_path}
Type: {field_spec.field_type}
Description: {field_spec.description.strip()}"""
    
    if field_spec.valid_values:
        field_section += f"\n\nValid values: {', '.join(str(v) for v in field_spec.valid_values)}"
    
    if field_spec.min_length:
        field_section += f"\nMinimum length: {field_spec.min_length} characters"
    
    if field_spec.max_length:
        field_section += f"\nMaximum length: {field_spec.max_length} items/characters"
    
    # Add good/bad examples from field spec
    if field_spec.good_example:
        field_section += f"\n\n✓ Good example: {field_spec.good_example}"
    if field_spec.bad_example:
        field_section += f"\n✗ Bad example: {field_spec.bad_example}"
    
    # Build golden example section (optional)
    example_section = ""
    if include_example:
        # Pick a relevant golden example
        example = _get_relevant_golden_example(exercise, field_path)
        if example:
            example_value = _get_nested_field(example, field_path)
            if example_value:
                example_section = f"""
## Reference Example

Exercise: {example.get('name')}
{field_spec.name}: {json.dumps(example_value, indent=2) if isinstance(example_value, (list, dict)) else example_value}
"""
    
    # Build the prompt
    prompt = f"""{ENRICHMENT_GUIDELINES}

---

{exercise_section}

---

{field_section}
{example_section}
---

## Task

{field_spec.enrichment_prompt if field_spec.enrichment_prompt else f'Generate the {field_spec.name} for this exercise.'}

Respond with ONLY the value, no explanation."""
    
    return prompt


def _get_nested_field(data: Dict[str, Any], field_path: str) -> Any:
    """Get a nested field value from a dict using dot notation."""
    parts = field_path.split(".")
    current = data
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def _get_relevant_golden_example(exercise: Dict[str, Any], field_path: str) -> Optional[Dict[str, Any]]:
    """Find a relevant golden example based on exercise characteristics."""
    exercise_category = exercise.get("category", "")
    exercise_equipment = exercise.get("equipment", [])
    
    # Try to match by category and equipment
    for key, example in GOLDEN_EXAMPLES.items():
        if example.get("category") == exercise_category:
            return example
        if any(eq in example.get("equipment", []) for eq in exercise_equipment):
            return example
    
    # Return first example as fallback
    return next(iter(GOLDEN_EXAMPLES.values()), None)


def enrich_field_with_guide(
    exercise: Dict[str, Any],
    field_path: str,
    llm_client: Optional[LLMClient] = None,
) -> Dict[str, Any]:
    """
    Enrich a single field using the exercise field guide.
    
    Args:
        exercise: Exercise data dict
        field_path: The field to enrich (e.g., "instructions", "muscles.primary")
        llm_client: Optional LLM client
        
    Returns:
        Dict with 'success', 'value', 'field_path', and optional 'error'
    """
    client = llm_client or get_llm_client()
    
    try:
        # Build prompt using field guide
        prompt = build_field_guide_prompt(exercise, field_path)
        
        # Get field spec for validation
        field_spec = get_field_spec(field_path)
        
        # Build output schema hint
        output_schema = None
        if field_spec.valid_values:
            output_schema = {"type": "string", "enum": field_spec.valid_values}
        elif field_spec.field_type == "boolean":
            output_schema = {"type": "boolean"}
        elif "array" in field_spec.field_type:
            output_schema = {"type": "array"}
        
        # Call LLM
        raw_response = client.complete(
            prompt=prompt,
            output_schema=output_schema,
            require_reasoning=True,
        )
        
        # Parse response based on field type
        value = _parse_field_response(raw_response, field_spec)
        
        return {
            "success": True,
            "value": value,
            "field_path": field_path,
        }
        
    except Exception as e:
        logger.exception(f"Failed to enrich {field_path}: {e}")
        return {
            "success": False,
            "error": str(e),
            "field_path": field_path,
        }


def _parse_field_response(raw_response: str, field_spec) -> Any:
    """Parse LLM response based on field type."""
    response = raw_response.strip()
    
    # Handle markdown code blocks
    if "```" in response:
        parts = response.split("```")
        if len(parts) >= 2:
            response = parts[1]
            if response.startswith("json"):
                response = response[4:]
            response = response.strip()
    
    # Parse based on type
    if field_spec.field_type == "boolean":
        return response.lower() in ("true", "yes", "1")
    
    if "array" in field_spec.field_type:
        # Try to parse as JSON array
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            # Try to split by comma if not valid JSON
            items = [item.strip().strip('"\'') for item in response.split(",")]
            return [item for item in items if item]
    
    if field_spec.field_type == "string" and field_spec.valid_values:
        # Enum - find best match
        response_lower = response.lower()
        for valid_value in field_spec.valid_values:
            if valid_value.lower() == response_lower:
                return valid_value
        return response  # Return as-is if no match
    
    return response


def enrich_all_missing_fields(
    exercise: Dict[str, Any],
    llm_client: Optional[LLMClient] = None,
) -> Dict[str, Any]:
    """
    Enrich all missing required fields for an exercise.
    
    Args:
        exercise: Exercise data dict
        llm_client: Optional LLM client
        
    Returns:
        Dict with enriched field values
    """
    client = llm_client or get_llm_client()
    enriched = {}
    
    for field_spec in get_enrichable_fields():
        if not field_spec.required:
            continue
        
        current_value = _get_nested_field(exercise, field_spec.field_path)
        
        # Check if field needs enrichment
        needs_enrichment = False
        if current_value is None:
            needs_enrichment = True
        elif isinstance(current_value, str) and len(current_value) == 0:
            needs_enrichment = True
        elif isinstance(current_value, list) and len(current_value) == 0:
            needs_enrichment = True
        elif field_spec.min_length and isinstance(current_value, str):
            if len(current_value) < field_spec.min_length:
                needs_enrichment = True
        
        if needs_enrichment:
            result = enrich_field_with_guide(exercise, field_spec.field_path, client)
            if result["success"]:
                enriched[field_spec.field_path] = result["value"]
                logger.info(f"Enriched {field_spec.field_path} for {exercise.get('name')}")
            else:
                logger.warning(f"Failed to enrich {field_spec.field_path}: {result.get('error')}")
    
    return enriched


__all__ = [
    "build_enrichment_prompt",
    "compute_enrichment",
    "validate_enrichment",
    "compute_enrichment_batch",
    # Field guide based enrichment
    "build_field_guide_prompt",
    "enrich_field_with_guide",
    "enrich_all_missing_fields",
]
