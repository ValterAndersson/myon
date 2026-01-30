"""
Enrichment Engine - LLM-powered field generation for exercises.

═══════════════════════════════════════════════════════════════════════════════
ENTRY POINTS
═══════════════════════════════════════════════════════════════════════════════

  enrich_exercise_holistic(exercise, reviewer_hint, llm_client) -> Dict
      PREFERRED. Pass full exercise doc, LLM decides what to update.
      Returns {"success": bool, "changes": {field: value}, "reasoning": str}

  compute_enrichment(exercise, spec, llm_client) -> EnrichmentResult
      Single-field enrichment using EnrichmentSpec.
      Legacy mode - use holistic for new code.

  enrich_field_with_guide(exercise, field_path, llm_client) -> Dict
      Single-field using ExerciseFieldGuide specs.
      Returns {"success": bool, "value": Any, "field_path": str}

═══════════════════════════════════════════════════════════════════════════════
LOCKED FIELDS (never modified by enrichment)
═══════════════════════════════════════════════════════════════════════════════

  name, name_slug, family_slug, status, created_at, updated_at, doc_id, id

  Why: These define exercise identity. Changing them would break references.
  If LLM suggests changing these, the suggestion is silently dropped.

═══════════════════════════════════════════════════════════════════════════════
OUTPUT NORMALIZATION (applied to all LLM output)
═══════════════════════════════════════════════════════════════════════════════

  muscles.primary/secondary: underscores -> spaces, lowercase, dedupe
  muscles.contribution: keys normalized, values clamped to 0.0-1.0
  stimulus_tags: title case, dedupe by lowercase
  category: validated against VALID_CATEGORIES, fallback to "compound"

  Why: LLM output is inconsistent. Normalization ensures data quality.

═══════════════════════════════════════════════════════════════════════════════
GOTCHAS
═══════════════════════════════════════════════════════════════════════════════

  • Holistic mode imports WHAT_GOOD_LOOKS_LIKE from reviewer module (at runtime)
  • LLM response parsing handles markdown code blocks, truncated JSON
  • enrich_exercise_holistic returns success=True with empty changes if nothing needed
  • Golden examples selected by matching category/equipment (may not be perfect)
  • ENRICHABLE_FIELD_PATHS is the allowlist - unlisted fields are dropped

═══════════════════════════════════════════════════════════════════════════════
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
    # Support both new schema (muscles.primary) and legacy (primary_muscles)
    muscles = exercise.get("muscles", {})
    primary_muscles = muscles.get("primary", exercise.get("primary_muscles", []))
    secondary_muscles = muscles.get("secondary", exercise.get("secondary_muscles", []))
    # Support both new schema (execution_notes) and legacy (instructions)
    instructions = exercise.get("execution_notes", exercise.get("instructions", ""))
    if isinstance(instructions, list):
        instructions = "\n".join(instructions)
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
            require_reasoning=False,  # V1.4: Flash-first for cost efficiency
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


# =============================================================================
# HOLISTIC ENRICHMENT
# =============================================================================

# Fields that are LOCKED and should never be modified by enrichment
LOCKED_FIELDS = {
    "name",
    "name_slug", 
    "family_slug",
    "status",
    "created_at",
    "updated_at",
    "doc_id",
    "id",
}

# Fields that CAN be enriched
ENRICHABLE_FIELD_PATHS = {
    # Legacy fields (still allow enrichment for backwards compatibility)
    "instructions",
    "equipment",
    "category",
    "primary_muscles",
    "secondary_muscles",
    # New schema muscle fields
    "muscles.primary",
    "muscles.secondary",
    "muscles.category",
    "muscles.contribution",
    # Metadata
    "metadata.level",
    "metadata.plane_of_motion",
    "metadata.unilateral",
    # Movement
    "movement.type",
    "movement.split",
    # Content arrays
    "execution_notes",
    "common_mistakes",
    "suitability_notes",
    "programming_use_cases",
    "stimulus_tags",
    # "coaching_cues",  # Deprecated - redundant with execution_notes
    # "tips",  # Deprecated - redundant with suitability_notes
    "description",
}


def enrich_exercise_holistic(
    exercise: Dict[str, Any],
    reviewer_hint: str = "",
    llm_client: Optional[LLMClient] = None,
    use_pro_model: bool = False,
) -> Dict[str, Any]:
    """
    Holistically enrich an exercise document using LLM.

    This is the PREFERRED enrichment method. Pass the full exercise doc,
    LLM sees everything and decides what to update coherently.

    WHY HOLISTIC:
        Single LLM call that can see relationships between fields.
        E.g., if it sets muscles.primary, it can also set muscles.contribution
        to match. Single-field mode can't do this.

    PROMPT INCLUDES:
        - WHAT_GOOD_LOOKS_LIKE (philosophy from reviewer module)
        - INSTRUCTIONS_GUIDANCE, MUSCLE_MAPPING_GUIDANCE
        - A golden example for reference
        - The full exercise document
        - reviewer_hint (what the reviewer flagged)

    LOCKED FIELDS (silently dropped if LLM suggests changes):
        name, name_slug, family_slug, status

    NORMALIZATION (applied after LLM response):
        - Muscle names: underscores -> spaces, lowercase
        - stimulus_tags: title case, dedupe
        - category: validated against VALID_CATEGORIES

    Args:
        exercise: Full exercise document
        reviewer_hint: Optional hint from the reviewer about issues found
        llm_client: LLM client (uses default if not provided)
        use_pro_model: If True, use gemini-2.5-pro; if False (default), use gemini-2.5-flash

    Returns:
        Dict with:
        - success: bool - True even if no changes needed
        - changes: Dict[str, Any] - flat dict of dotted paths to new values
        - reasoning: str - LLM's reasoning
        - confidence: str - "high", "medium", or "low"
        - error: str (only if success=False)

    CALLERS:
        - _execute_holistic_enrichment() in executor.py
        - Can also call directly for testing/debugging
    """
    from app.reviewer.what_good_looks_like import WHAT_GOOD_LOOKS_LIKE
    
    client = llm_client or get_llm_client()
    exercise_id = exercise.get("id", exercise.get("doc_id", "unknown"))
    
    try:
        # Build the prompt
        prompt = _build_holistic_enrichment_prompt(exercise, reviewer_hint)
        
        # Call LLM with structured output hint
        # Default to Flash (cheaper), use Pro only when explicitly requested
        raw_response = client.complete(
            prompt=prompt,
            output_schema={"type": "object"},
            require_reasoning=use_pro_model,
        )
        
        # Parse response
        parsed = _parse_holistic_response(raw_response)
        
        if not parsed.get("changes"):
            logger.info(
                "Holistic enrichment for %s: no changes needed (reasoning: %s)",
                exercise_id, parsed.get("reasoning", "none")[:100]
            )
            return {
                "success": True,
                "changes": {},
                "reasoning": parsed.get("reasoning", "No changes needed"),
                "confidence": parsed.get("confidence", "high"),
            }
        
        # Filter changes to only enrichable fields (as flat dotted paths)
        valid_changes = {}
        for field_path, value in parsed["changes"].items():
            # Skip locked fields
            if field_path in LOCKED_FIELDS:
                logger.warning("Skipping locked field: %s", field_path)
                continue
            
            # Check if field is enrichable
            if field_path in ENRICHABLE_FIELD_PATHS:
                valid_changes[field_path] = value
            else:
                # Check if it matches a prefix pattern
                is_valid = False
                for allowed in ENRICHABLE_FIELD_PATHS:
                    if field_path.startswith(allowed + "."):
                        is_valid = True
                        break
                
                if is_valid:
                    valid_changes[field_path] = value
                else:
                    logger.warning("Skipping non-enrichable field: %s", field_path)
        
        # Normalize the changes for consistency
        normalized_changes = normalize_enrichment_output(valid_changes)

        logger.info(
            "Holistic enrichment for %s: %d changes (confidence: %s)",
            exercise_id, len(normalized_changes), parsed.get("confidence", "unknown")
        )

        return {
            "success": True,
            "changes": normalized_changes,
            "reasoning": parsed.get("reasoning", ""),
            "confidence": parsed.get("confidence", "high"),
        }
        
    except Exception as e:
        logger.exception("Holistic enrichment failed for %s: %s", exercise_id, e)
        return {
            "success": False,
            "changes": {},
            "reasoning": f"Error: {e}",
            "confidence": "low",
            "error": str(e),
        }


def _build_holistic_enrichment_prompt(
    exercise: Dict[str, Any],
    reviewer_hint: str = "",
) -> str:
    """Build prompt for holistic exercise enrichment."""
    from app.reviewer.what_good_looks_like import (
        WHAT_GOOD_LOOKS_LIKE,
        INSTRUCTIONS_GUIDANCE,
        MUSCLE_MAPPING_GUIDANCE,
    )
    
    # Get a golden example for reference
    example = _get_relevant_golden_example(exercise, "instructions")
    example_json = json.dumps(example, indent=2) if example else "N/A"
    
    # Format current exercise data (exclude timestamps and internal fields)
    display_exercise = {k: v for k, v in exercise.items() 
                       if k not in {"created_at", "updated_at", "doc_id", "id", "_debug_project_id"}}
    exercise_json = json.dumps(display_exercise, indent=2, default=str)
    
    prompt = f"""{WHAT_GOOD_LOOKS_LIKE}

{INSTRUCTIONS_GUIDANCE}

{MUSCLE_MAPPING_GUIDANCE}

---

## Reference: What Good Data Looks Like

Here's an example of a well-enriched exercise:

```json
{example_json}
```

---

## Your Task

Review this exercise and enrich any fields that need improvement.

### Current Exercise Data

```json
{exercise_json}
```

"""

    if reviewer_hint:
        prompt += f"""### Reviewer Hint

The catalog reviewer flagged these issues:
{reviewer_hint}

This is a hint about what might need fixing, but use your judgment - you may find
other issues or decide the flagged issue isn't actually a problem.

"""

    prompt += """### Rules

1. **NEVER change**: name, name_slug, family_slug, status (these are locked)
2. **CAN change**:
   - muscles.primary, muscles.secondary, muscles.category, muscles.contribution
   - metadata.level, metadata.plane_of_motion, metadata.unilateral
   - movement.type, movement.split
   - equipment, category, description
   - execution_notes, common_mistakes, suitability_notes
   - programming_use_cases, stimulus_tags
3. Follow the "If it ain't broke, don't fix it" principle
4. Only make changes that would actually help a user

### Priority Fields to Generate (if missing)

Check these fields and ADD them if they're missing or empty:

1. **description** - A concise 1-2 sentence description of what the exercise is and its primary purpose/benefits
   Example: `"A fundamental lower body compound exercise that builds strength in the quadriceps and glutes while improving core stability."`

2. **muscles.contribution** - Map of muscle name to decimal contribution (0.0-1.0), must sum to ~1.0
   Example: `{"quadriceps": 0.45, "glutes": 0.35, "hamstrings": 0.20}`

3. **stimulus_tags** - 4-6 training stimulus tags in Title Case
   Example: `["Hypertrophy", "Compound Movement", "Strength", "Core Engagement"]`

4. **programming_use_cases** - 3-5 complete sentences about when to use this exercise
   Example: `["Primary compound movement for leg-focused strength programs.", ...]`

5. **suitability_notes** - 2-4 notes about who this exercise is suitable for
   Example: `["Excellent for building posterior chain strength.", "Requires good hip mobility."]`

6. **category** - Must be one of: compound, isolation, cardio, mobility, core
   If currently "exercise", change it to "compound" or "isolation" as appropriate

7. **muscles.primary** - If empty, add 1-3 primary muscles (use lowercase, spaces not underscores)
   Example: `["quadriceps", "gluteus maximus"]` NOT `["Quadriceps", "gluteus_maximus"]`

### Response Format

Respond with a JSON object:

```json
{
  "reasoning": "Brief explanation of what you found and what you're changing",
  "confidence": "high" | "medium" | "low",
  "changes": {
    "muscles.contribution": {"muscle name": 0.XX, ...},
    "stimulus_tags": ["Tag1", "Tag2", ...],
    "programming_use_cases": ["Sentence 1.", "Sentence 2.", ...],
    "suitability_notes": ["Note 1.", "Note 2.", ...],
    "category": "compound",
    ...
  }
}
```

If no changes are needed, return `"changes": {}`

Use flat dotted paths for nested fields (e.g., "muscles.primary" not {"muscles": {"primary": ...}})

Respond with ONLY the JSON object."""

    return prompt


def _parse_holistic_response(raw_response: str) -> Dict[str, Any]:
    """Parse LLM response from holistic enrichment."""
    response = raw_response.strip()
    
    # Handle markdown code blocks
    if "```" in response:
        parts = response.split("```")
        if len(parts) >= 2:
            response = parts[1]
            if response.startswith("json"):
                response = response[4:]
            response = response.strip()
    
    try:
        parsed = json.loads(response)
        return {
            "reasoning": parsed.get("reasoning", ""),
            "confidence": parsed.get("confidence", "medium"),
            "changes": parsed.get("changes", {}),
        }
    except json.JSONDecodeError as e:
        logger.warning("Failed to parse holistic response: %s", e)
        # Try to extract JSON from the response
        import re
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            try:
                parsed = json.loads(json_match.group())
                return {
                    "reasoning": parsed.get("reasoning", ""),
                    "confidence": parsed.get("confidence", "medium"),
                    "changes": parsed.get("changes", {}),
                }
            except:
                pass
        
        return {
            "reasoning": f"Failed to parse: {response[:200]}",
            "confidence": "low",
            "changes": {},
        }


# =============================================================================
# OUTPUT NORMALIZATION
# =============================================================================

# Valid category values
VALID_CATEGORIES = {"compound", "isolation", "cardio", "mobility", "core"}


def normalize_enrichment_output(changes: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize enrichment output to ensure consistent formatting.

    Fixes:
    - Muscle names: underscores → spaces, lowercase
    - stimulus_tags: dedupe, title case
    - category: validate against allowed values
    - programming_use_cases, suitability_notes: ensure proper formatting
    """
    normalized = {}

    for field_path, value in changes.items():
        if value is None:
            continue

        # Normalize muscle arrays
        if field_path in ("muscles.primary", "muscles.secondary"):
            normalized[field_path] = _normalize_muscle_names(value)

        # Normalize muscle contribution map
        elif field_path == "muscles.contribution":
            normalized[field_path] = _normalize_contribution_map(value)

        # Normalize stimulus_tags
        elif field_path == "stimulus_tags":
            normalized[field_path] = _normalize_stimulus_tags(value)

        # Validate category
        elif field_path == "category":
            normalized[field_path] = _normalize_category(value)

        # Pass through other fields
        else:
            normalized[field_path] = value

    return normalized


def _normalize_muscle_names(muscles: List[str]) -> List[str]:
    """Normalize muscle names: underscores → spaces, lowercase."""
    if not isinstance(muscles, list):
        return muscles

    normalized = []
    seen = set()

    for muscle in muscles:
        if not isinstance(muscle, str):
            continue
        # Underscores to spaces, lowercase, strip
        clean = muscle.replace("_", " ").lower().strip()
        if clean and clean not in seen:
            normalized.append(clean)
            seen.add(clean)

    return normalized


def _normalize_contribution_map(contribution: Dict[str, float]) -> Dict[str, float]:
    """Normalize contribution map keys (muscle names)."""
    if not isinstance(contribution, dict):
        return contribution

    normalized = {}
    for muscle, pct in contribution.items():
        if not isinstance(muscle, str):
            continue
        # Normalize muscle name
        clean_name = muscle.replace("_", " ").lower().strip()
        if clean_name:
            # Ensure percentage is float between 0 and 1
            if isinstance(pct, (int, float)):
                normalized[clean_name] = min(1.0, max(0.0, float(pct)))

    return normalized


def _normalize_stimulus_tags(tags: List[str]) -> List[str]:
    """Normalize stimulus tags: dedupe, title case."""
    if not isinstance(tags, list):
        return tags

    normalized = []
    seen = set()

    for tag in tags:
        if not isinstance(tag, str):
            continue
        # Title case, strip
        clean = tag.strip().title()
        # Normalize common variations
        clean = clean.replace("_", " ")
        lower = clean.lower()

        if clean and lower not in seen:
            normalized.append(clean)
            seen.add(lower)

    return normalized


def _normalize_category(category: str) -> str:
    """Normalize category value."""
    if not isinstance(category, str):
        return "compound"  # Default

    clean = category.lower().strip()

    # Fix common invalid values
    if clean in VALID_CATEGORIES:
        return clean
    if clean == "exercise":
        return "compound"  # Default fallback
    if "isol" in clean:
        return "isolation"
    if "compound" in clean or "multi" in clean:
        return "compound"

    return "compound"  # Default


__all__ = [
    "build_enrichment_prompt",
    "compute_enrichment",
    "validate_enrichment",
    "compute_enrichment_batch",
    # Field guide based enrichment
    "build_field_guide_prompt",
    "enrich_field_with_guide",
    "enrich_all_missing_fields",
    # Holistic enrichment
    "enrich_exercise_holistic",
    "normalize_enrichment_output",
    "LOCKED_FIELDS",
    "ENRICHABLE_FIELD_PATHS",
]
