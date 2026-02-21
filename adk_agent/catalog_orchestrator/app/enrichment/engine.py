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
  category: validated against CATEGORIES (from field guide), fallback to "compound"

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
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.enrichment.models import EnrichmentSpec, EnrichmentResult
from app.enrichment.llm_client import LLMClient, get_llm_client
from app.enrichment.validators import validate_enrichment_output, parse_llm_response
from app.enrichment.exercise_field_guide import (
    CANONICAL_ENUM_VALUES,
    CATEGORIES,
    EQUIPMENT_ALIASES,
    FIELD_SPECS,
    GOLDEN_EXAMPLES,
    MOVEMENT_SPLITS,
    MOVEMENT_TYPES,
    MUSCLE_ALIASES,
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

# Content fields that should always be present on a complete exercise.
# Used to auto-detect missing content and pass explicit hints to the LLM.
REQUIRED_CONTENT_FIELDS = [
    "description",
    "execution_notes",
    "common_mistakes",
    "suitability_notes",
    "programming_use_cases",
    "stimulus_tags",
]


def _detect_missing_content_fields(exercise: Dict[str, Any]) -> List[str]:
    """Detect which content fields are missing or empty on the exercise."""
    missing = []
    for field in REQUIRED_CONTENT_FIELDS:
        value = exercise.get(field)
        if not value:
            missing.append(field)
        elif isinstance(value, list) and len(value) == 0:
            missing.append(field)
        elif isinstance(value, str) and len(value.strip()) < 10:
            missing.append(field)
    return missing


# Patterns that indicate style violations needing rewrite
_NUMBERED_PREFIX = re.compile(r'^\d+[\.\)]\s')
_STEP_PREFIX = re.compile(r'^step\s*\d+', re.I)
_BOLD_MARKER = re.compile(r'\*\*')
_BULLET_MARKER = re.compile(r'^[-\u2022*]\s+')
_FIRST_PERSON = re.compile(r'\b(I recommend|I suggest|we should|my advice)\b', re.I)
_THIRD_PERSON_SUBJ = re.compile(
    r'^(the lifter|the athlete|the user|one should)',
    re.I,
)

# Cue-only detection: coaching cue verbs that indicate no setup/positioning context
_CUE_ONLY_START = re.compile(
    r'^(Focus|Keep|Maintain|Drive|Squeeze|Avoid|Ensure|Control|Pause|'
    r'Engage|Brace|Think|Do not|Don\'t)\b',
    re.I,
)

# "Label: Explanation" format in common_mistakes: 2+ words before colon, capital after
_LABEL_COLON = re.compile(r'^[A-Z]\w+\s+\w+[^:]*:\s+[A-Z]')

# Valid common_mistakes voice: gerund phrase, optionally preceded by "Not" / adverb.
# Matches: "Rounding...", "Not reaching...", "Not fully extending...", "Over-extending..."
_VALID_MISTAKE_START = re.compile(
    r'^('
    r'[A-Z][a-z]*ing\b'            # Direct gerund: Using, Rounding, Flaring
    r'|Not\s+\w+ing\b'             # Not + gerund: Not reaching
    r'|Not\s+\w+\s+\w+ing\b'       # Not + adverb + gerund: Not fully extending
    r'|Only\s+\w+ing\b'            # Only lifting
    r'|Over-?\w+ing\b'             # Over-extending, Overloading
    r')'
)

# Equipment words for generic description detection (word-boundary matching)
_EQUIPMENT_WORD_RE = re.compile(
    r'\b(dumbbell|barbell|cable|kettlebell|machine|band|smith)\b',
    re.I,
)


def _detect_style_violations(exercise: Dict[str, Any]) -> List[str]:
    """Detect content that exists but violates the style guide.

    Returns a list of human-readable issue descriptions to feed as
    reviewer hints so the LLM knows what to fix.
    """
    issues = []

    for field_name in ("execution_notes", "common_mistakes",
                       "suitability_notes", "programming_use_cases"):
        items = exercise.get(field_name, [])
        if not isinstance(items, list):
            continue

        for item in items:
            if not isinstance(item, str):
                continue

            if _NUMBERED_PREFIX.match(item) or _STEP_PREFIX.match(item):
                issues.append(
                    f"{field_name} has numbered/step prefixes — rewrite as plain cues"
                )
                break
            if _BOLD_MARKER.search(item):
                issues.append(
                    f"{field_name} has **bold** markdown — rewrite as plain text"
                )
                break
            if _BULLET_MARKER.match(item):
                issues.append(
                    f"{field_name} has bullet markers — rewrite as plain cues"
                )
                break

        # Voice violations in execution_notes
        if field_name == "execution_notes":
            for item in items:
                if not isinstance(item, str):
                    continue
                if _FIRST_PERSON.search(item):
                    issues.append(
                        "execution_notes uses first person voice — "
                        "rewrite in second person imperative"
                    )
                    break
                if _THIRD_PERSON_SUBJ.match(item):
                    issues.append(
                        "execution_notes uses third person ('The lifter...') — "
                        "rewrite in second person imperative"
                    )
                    break

            # Cue-only check: flag when ALL notes are coaching cues with no
            # setup/positioning context
            str_items = [i for i in items if isinstance(i, str)]
            if str_items and all(_CUE_ONLY_START.match(i) for i in str_items):
                issues.append(
                    "execution_notes contains only coaching cues with no setup "
                    "instructions — rewrite to begin with positioning/setup "
                    "steps, then technique cues"
                )

        # "Label: Explanation" format in common_mistakes
        if field_name == "common_mistakes":
            for item in items:
                if isinstance(item, str) and _LABEL_COLON.match(item):
                    issues.append(
                        "common_mistakes uses 'Label: Explanation' format — "
                        "rewrite as plain gerund phrases (e.g., 'Rounding the "
                        "lower back, which increases injury risk')"
                    )
                    break

            # Non-gerund voice in common_mistakes: imperative ("Bounce"),
            # tip/advice ("Avoid"), or other non-descriptive patterns
            str_mistakes = [i for i in items if isinstance(i, str)]
            non_gerund = [
                i for i in str_mistakes if not _VALID_MISTAKE_START.match(i)
            ]
            if non_gerund:
                issues.append(
                    f"common_mistakes has {len(non_gerund)} items not in gerund "
                    f"voice — rewrite as descriptive gerund phrases "
                    f"(e.g., 'Bouncing the weight off the chest')"
                )

        # Vague/terse items
        short_count = sum(
            1 for item in items
            if isinstance(item, str) and len(item.split()) < 4
        )
        if short_count >= 2:
            issues.append(
                f"{field_name} has {short_count} items that are too vague/short — "
                f"rewrite with specific, actionable detail"
            )

    # Description checks
    desc = exercise.get("description", "")
    if isinstance(desc, str) and 0 < len(desc) < 50:
        issues.append("description is too short — expand to 100-250 characters")

    # Generic description: mentions 3+ different equipment types
    if isinstance(desc, str) and desc:
        equip_matches = set(m.group(1).lower() for m in _EQUIPMENT_WORD_RE.finditer(desc))
        if len(equip_matches) >= 3:
            issues.append(
                f"description mentions {len(equip_matches)} equipment types — "
                f"rewrite specific to this exercise's actual equipment"
            )

    return issues


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


# Native Gemini structured output schema for holistic enrichment.
# Passed as response_schema to get deterministic JSON structure from the LLM.
HOLISTIC_ENRICHMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "changes": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["compound", "isolation", "cardio", "mobility", "core"],
                },
                "movement.type": {
                    "type": "string",
                    "enum": [
                        "push", "pull", "hinge", "squat", "carry",
                        "rotation", "flexion", "extension",
                        "abduction", "adduction", "other",
                    ],
                },
                "movement.split": {
                    "type": "string",
                    "enum": ["upper", "lower", "full_body", "core"],
                },
                "description": {"type": "string"},
                "equipment": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "muscles.primary": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "muscles.secondary": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "muscles.contribution": {
                    "type": "object",
                    "additionalProperties": {"type": "number"},
                },
                "execution_notes": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "common_mistakes": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "stimulus_tags": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "suitability_notes": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "programming_use_cases": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "muscles.category": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
        },
        "reasoning": {"type": "string"},
        "confidence": {
            "type": "string",
            "enum": ["high", "medium", "low"],
        },
    },
    "required": ["changes", "reasoning", "confidence"],
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
        - category: validated against CATEGORIES (from field guide)
        - movement.type / movement.split: mapped to canonical values

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
        # Auto-detect missing content fields and style violations
        auto_hints = []

        missing_fields = _detect_missing_content_fields(exercise)
        if missing_fields:
            auto_hints.append(
                "Missing content fields that MUST be generated: "
                + ", ".join(missing_fields)
            )

        style_issues = _detect_style_violations(exercise)
        if style_issues:
            auto_hints.append(
                "Style guide violations that MUST be fixed:\n"
                + "\n".join(f"- {issue}" for issue in style_issues)
            )

        if auto_hints:
            auto_hint_text = "\n\n".join(auto_hints)
            if reviewer_hint:
                reviewer_hint = f"{reviewer_hint}\n\n{auto_hint_text}"
            else:
                reviewer_hint = auto_hint_text

        # Build the prompt
        prompt = _build_holistic_enrichment_prompt(exercise, reviewer_hint)
        
        # Call LLM with structured output hint
        # Default to Flash (cheaper), use Pro only when explicitly requested
        raw_response = client.complete(
            prompt=prompt,
            output_schema={"type": "object"},
            response_schema=HOLISTIC_ENRICHMENT_SCHEMA,
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
        normalized_changes = validate_normalized_output(normalized_changes)

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
        CONTENT_FORMAT_RULES,
        CONTENT_STYLE_GUIDE,
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

{CONTENT_FORMAT_RULES}

{CONTENT_STYLE_GUIDE}

{CANONICAL_ENUM_VALUES}

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
3. Follow the "If it ain't broke, don't fix it" principle FOR CONTENT THAT IS ALREADY GOOD
4. Only make changes that would actually help a user

### When to UPDATE existing content (override "don't fix")

Even if content exists, REWRITE IT if any of these apply:
- **Style guide violation**: wrong voice (first/third person in execution_notes),
  numbered prefixes, markdown formatting, bullet markers
- **Too vague**: items under 6 words that lack actionable detail ("Bad form", "Too heavy")
- **Too verbose**: paragraph-style items over 30 words that should be concise cues
- **Missing fields**: any content array field is empty or absent — ALWAYS generate it

These are quality issues, not preference changes. Fix them.

### Priority Fields to Generate or Fix

Check ALL of these fields. If missing/empty, GENERATE them. If present but violating
the style guide above, REWRITE them:

1. **execution_notes** - 4-8 concise cues in second person imperative voice
   Example: `["Keep your knees tracking over your toes", "Brace your core before the lift"]`

2. **common_mistakes** - 2-5 descriptive gerund phrases of common errors
   Example: `["Rounding the lower back at the bottom", "Using momentum instead of control"]`

3. **description** - A concise 1-2 sentence description (100-250 characters)
   Example: `"A fundamental lower body compound exercise that builds strength in the quadriceps and glutes while improving core stability."`

4. **suitability_notes** - 2-4 third person declarative statements
   Example: `["Requires good hip and ankle mobility.", "Machine guidance makes it beginner-friendly."]`

5. **programming_use_cases** - 3-5 complete sentences ending with periods
   Example: `["Primary compound movement for leg-focused strength programs.", ...]`

6. **stimulus_tags** - 4-6 training stimulus tags in Title Case
   Example: `["Hypertrophy", "Compound Movement", "Strength", "Core Engagement"]`

7. **muscles.contribution** - Map of muscle name to decimal contribution (0.0-1.0), must sum to ~1.0
   Example: `{"quadriceps": 0.45, "glutes": 0.35, "hamstrings": 0.20}`

8. **category** - Must be one of: compound, isolation, cardio, mobility, core

9. **muscles.primary** - If empty, add 1-3 primary muscles (lowercase, spaces not underscores)

### IMPORTANT: Generate ALL Missing Content

Before writing your response, check which content fields are present in the exercise.
If ANY of these fields are missing or empty, you MUST include them in your changes:
- execution_notes (4-8 items)
- common_mistakes (2-5 items)
- suitability_notes (2-4 items)
- programming_use_cases (3-5 items)
- description
- stimulus_tags (4-6 items)

Do NOT skip missing content fields. Every exercise needs all of these.

### Response Format

Respond with a JSON object:

```json
{
  "reasoning": "Brief explanation of what you found and what you're changing",
  "confidence": "high" | "medium" | "low",
  "changes": {
    "execution_notes": ["Cue 1", "Cue 2", ...],
    "common_mistakes": ["Mistake 1", "Mistake 2", ...],
    "suitability_notes": ["Note 1.", "Note 2.", ...],
    "programming_use_cases": ["Sentence 1.", "Sentence 2.", ...],
    "description": "...",
    "stimulus_tags": ["Tag1", "Tag2", ...],
    "muscles.contribution": {"muscle name": 0.XX, ...},
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
            normalized[field_path] = _resolve_muscle_aliases(
                _normalize_muscle_names(value)
            )

        # Normalize muscle contribution map
        elif field_path == "muscles.contribution":
            normalized[field_path] = _normalize_contribution_map(value)

        # Normalize stimulus_tags
        elif field_path == "stimulus_tags":
            normalized[field_path] = _normalize_stimulus_tags(value)

        # Validate category
        elif field_path == "category":
            normalized[field_path] = _normalize_category(value)

        # Normalize movement type
        elif field_path == "movement.type":
            result = _normalize_movement_type(value)
            if result:
                normalized[field_path] = result
            # else: silently dropped — validation will also catch it

        # Normalize movement split
        elif field_path == "movement.split":
            result = _normalize_movement_split(value)
            if result:
                normalized[field_path] = result

        # Normalize equipment
        elif field_path == "equipment":
            normalized[field_path] = _normalize_equipment(value)

        # Normalize content arrays
        elif field_path in (
            "execution_notes", "common_mistakes",
            "suitability_notes", "programming_use_cases",
        ):
            normalized[field_path] = _normalize_content_array(value)

        # Pass through other fields
        else:
            normalized[field_path] = value

    return normalized


def _normalize_equipment(equipment: List[str]) -> List[str]:
    """Normalize equipment values: aliases, underscores → hyphens, lowercase, dedupe."""
    if not isinstance(equipment, list):
        return equipment

    normalized, seen = [], set()
    for item in equipment:
        if not isinstance(item, str):
            continue
        clean = item.strip().lower().replace("_", "-").replace(" ", "-")
        clean = EQUIPMENT_ALIASES.get(item.strip().lower(), clean)
        if clean and clean not in seen:
            normalized.append(clean)
            seen.add(clean)
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


def _resolve_muscle_aliases(muscles: List[str]) -> List[str]:
    """Resolve common muscle name aliases to canonical names."""
    if not isinstance(muscles, list):
        return muscles

    resolved = []
    seen = set()

    for muscle in muscles:
        if not isinstance(muscle, str):
            continue
        canonical = MUSCLE_ALIASES.get(muscle, muscle)
        if canonical not in seen:
            resolved.append(canonical)
            seen.add(canonical)

    return resolved


# Regex patterns for stripping bad formatting from content array items
_BOLD_LABEL_PREFIX_RE = re.compile(r'^\*\*[^*]+\*\*[:\s]*')
_NUMBERED_PREFIX_RE = re.compile(r'^\d+[\.\)]\s*')
_BULLET_PREFIX_RE = re.compile(r'^[-\u2022*]\s+')


def _normalize_content_array(items) -> List[str]:
    """
    Strip formatting artifacts from content array items.

    Removes markdown bold step prefixes, numbered prefixes, and bullet markers
    that the LLM might produce despite prompt instructions. This is a safety net.

    Also coerces string input to list (splits on sentence boundaries).
    """
    if isinstance(items, str):
        sentences = [
            s.strip()
            for s in items.replace(". ", ".\n").split("\n")
            if s.strip()
        ]
        items = [s for s in sentences if len(s) > 10]
    if not isinstance(items, list):
        return items

    normalized = []
    seen = set()

    for item in items:
        if not isinstance(item, str):
            continue

        clean = item.strip()

        # Remove **Any Label:** bold prefixes (covers **Step 1:**, **Setup:**, etc.)
        clean = _BOLD_LABEL_PREFIX_RE.sub('', clean)

        # Remove numbered prefixes: "1. " / "1) "
        clean = _NUMBERED_PREFIX_RE.sub('', clean)

        # Remove bullet markers: "- " / "* "
        clean = _BULLET_PREFIX_RE.sub('', clean)

        clean = clean.strip()

        if clean and clean not in seen:
            normalized.append(clean)
            seen.add(clean)

    return normalized


def _normalize_contribution_map(contribution: Dict[str, float]) -> Dict[str, float]:
    """Normalize contribution map keys (muscle names) and resolve aliases."""
    if not isinstance(contribution, dict):
        return contribution

    normalized = {}
    for muscle, pct in contribution.items():
        if not isinstance(muscle, str):
            continue
        # Normalize muscle name: underscores to spaces, lowercase
        clean_name = muscle.replace("_", " ").lower().strip()
        # Resolve alias to canonical name
        clean_name = MUSCLE_ALIASES.get(clean_name, clean_name)
        if clean_name:
            # Ensure percentage is float between 0 and 1
            if isinstance(pct, (int, float)):
                # If alias resolution caused a duplicate key, sum the values
                existing = normalized.get(clean_name, 0.0)
                normalized[clean_name] = min(1.0, max(0.0, existing + float(pct)))

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

    # Map dropped categories to their replacements
    _category_fallbacks = {
        "stretching": "mobility",
        "plyometric": "compound",
        "isometric": "mobility",
        "flexibility": "mobility",
        "explosive": "compound",
        "static": "mobility",
    }

    # Fix common invalid values — CATEGORIES is the single source of truth
    valid_categories = set(CATEGORIES)
    if clean in valid_categories:
        return clean
    if clean in _category_fallbacks:
        return _category_fallbacks[clean]
    if clean == "exercise":
        return "compound"  # Default fallback
    if "isol" in clean:
        return "isolation"
    if "compound" in clean or "multi" in clean:
        return "compound"

    return "compound"  # Default


def _normalize_movement_type(movement_type: str) -> Optional[str]:
    """Normalize movement.type, returning None if unmappable."""
    if not isinstance(movement_type, str):
        return None
    clean = movement_type.lower().strip()

    valid = set(MOVEMENT_TYPES)
    if clean in valid:
        return clean

    _fallbacks = {
        "press": "push", "pressing": "push", "bench press": "push",
        "squat_press": "push",
        "row": "pull", "rowing": "pull", "pulldown": "pull",
        "vertical_pull": "pull", "vertical pull": "pull",
        "pullover": "pull",
        "curl": "flexion", "crunch": "flexion",
        "core": "other", "core_flexion": "flexion",
        "core flexion": "flexion", "trunk_flexion": "flexion",
        "hip_flexion": "flexion", "hip flexion": "flexion",
        "wrist flexion": "flexion", "wrist_flexion": "flexion",
        "kickback": "extension", "pushdown": "extension",
        "back extension": "extension", "hip_extension": "extension",
        "knee extension": "extension",
        "wrist extension": "extension", "wrist_extension": "extension",
        "anti-extension": "extension",
        "raise": "abduction", "lateral": "abduction",
        "horizontal abduction": "abduction",
        "fly": "adduction", "flye": "adduction", "crossover": "adduction",
        "deadlift": "hinge", "rdl": "hinge", "hip_hinge": "hinge",
        "bridge": "hinge",
        "lunge": "squat", "leg press": "squat", "split_squat": "squat",
        "dip": "push", "push-up": "push",
        "pull_push": "push", "pull & push": "push",
        "muscle_up": "pull",
        "twist": "rotation", "woodchop": "rotation",
        "anti-rotation": "rotation", "rotate": "rotation",
        "anti-lateral flexion": "rotation",
        "farmer's walk": "carry",
        "isolation": "flexion",
        "shrug": "pull",
        "plantar_flexion": "extension", "plantarflexion": "extension",
        "plantar flexion": "extension",
        "calf_raise": "extension", "calf raise": "extension",
        "plank": "other", "isometric": "other", "static": "other",
        "stabilization": "other", "core_stabilization": "other",
        "stability": "other",
        "leg raise": "flexion", "leg_raise": "flexion",
        "knee_raise": "flexion",
        "slam": "other", "throw": "other", "jump": "other",
        "olympic_lift": "other", "olympic": "other",
        "clean and jerk": "other",
        "power": "other",
        "calisthenics_compound": "other",
    }
    return _fallbacks.get(clean)  # Returns None if unmappable


def _normalize_movement_split(split) -> Optional[str]:
    """Normalize movement.split, returning None if unmappable."""
    if isinstance(split, list):
        # Take first mappable value from list
        for s in split:
            result = _normalize_movement_split(s)
            if result:
                return result
        return None
    if not isinstance(split, str):
        return None
    clean = split.lower().strip()

    valid = set(MOVEMENT_SPLITS)
    if clean in valid:
        return clean

    _fallbacks = {
        "full body": "full_body", "full": "full_body",
        "upper body": "upper", "lower body": "lower",
        "arms": "upper", "back": "upper", "chest": "upper",
        "shoulders": "upper", "legs": "lower", "abs": "core",
        "posterior chain": "lower",
    }
    return _fallbacks.get(clean)


def validate_normalized_output(changes: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate normalized enrichment output against canonical enums.

    Drops invalid fields with a warning log (partial success model).
    Called after normalize_enrichment_output() in enrich_exercise_holistic().
    """
    from app.enrichment.exercise_field_guide import (
        MOVEMENT_TYPES, MOVEMENT_SPLITS, CATEGORIES,
        EQUIPMENT_TYPES, PRIMARY_MUSCLES, MUSCLE_ALIASES,
    )

    valid_categories = set(CATEGORIES)
    valid_movement_types = set(MOVEMENT_TYPES)
    valid_movement_splits = set(MOVEMENT_SPLITS)
    valid_equipment = set(EQUIPMENT_TYPES)
    # Build full muscle set: canonical names + alias keys
    valid_muscles = set(m.lower() for m in PRIMARY_MUSCLES)
    valid_muscles.update(k.lower() for k in MUSCLE_ALIASES.keys())

    validated = {}

    for field_path, value in changes.items():
        if field_path == "category":
            if value in valid_categories:
                validated[field_path] = value
            else:
                logger.warning(
                    "Dropping invalid category '%s' (valid: %s)",
                    value, valid_categories,
                )

        elif field_path == "movement.type":
            if value in valid_movement_types:
                validated[field_path] = value
            else:
                logger.warning(
                    "Dropping invalid movement.type '%s' (valid: %s)",
                    value, valid_movement_types,
                )

        elif field_path == "movement.split":
            if value in valid_movement_splits:
                validated[field_path] = value
            else:
                logger.warning(
                    "Dropping invalid movement.split '%s' (valid: %s)",
                    value, valid_movement_splits,
                )

        elif field_path == "equipment":
            if isinstance(value, list):
                unknown = [e for e in value if e not in valid_equipment]
                if unknown:
                    logger.info(
                        "Non-standard equipment values (keeping): %s", unknown
                    )
                validated[field_path] = value  # Keep ALL equipment
            else:
                validated[field_path] = value

        elif field_path in ("muscles.primary", "muscles.secondary"):
            if isinstance(value, list):
                invalid = [m for m in value if m.lower() not in valid_muscles]
                if invalid:
                    logger.warning(
                        "Muscle names not in canonical set (keeping anyway): %s",
                        invalid,
                    )
                # Keep all muscle names — just warn, don't drop
                validated[field_path] = value
            else:
                validated[field_path] = value

        elif field_path == "muscles.contribution":
            if isinstance(value, dict):
                total = sum(v for v in value.values() if isinstance(v, (int, float)))
                if total > 1.15 or total < 0.85:
                    logger.warning(
                        "Contribution sum %.2f out of range [0.85, 1.15], "
                        "re-normalizing", total,
                    )
                    if total > 0:
                        value = {k: round(v / total, 3) for k, v in value.items()
                                 if isinstance(v, (int, float))}
                validated[field_path] = value
            else:
                validated[field_path] = value

        elif field_path == "description":
            # Threshold aligned with quality_scanner.py (50 chars) to avoid
            # enrichment loops: scanner flags <50, so validation must also reject <50.
            if isinstance(value, str) and len(value) >= 50:
                validated[field_path] = value
            else:
                logger.warning(
                    "Dropping too-short description (%d chars, min 50)",
                    len(value) if isinstance(value, str) else 0,
                )

        else:
            # Pass through other fields unchanged
            validated[field_path] = value

    return validated


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
    "validate_normalized_output",
    "LOCKED_FIELDS",
    "ENRICHABLE_FIELD_PATHS",
]
