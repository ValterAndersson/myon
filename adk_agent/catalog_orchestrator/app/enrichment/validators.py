"""
Enrichment Validators - Output validation for LLM-computed field values.

Validates that enrichment outputs conform to the EnrichmentSpec:
- Type checking (enum, string, number, boolean, object)
- Enum value validation
- Range validation for numbers
- Schema validation for objects
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.enrichment.models import EnrichmentSpec

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of validating an enrichment output."""
    valid: bool = True
    value: Any = None  # Parsed/normalized value
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    def add_error(self, error: str) -> None:
        """Add an error and mark as invalid."""
        self.errors.append(error)
        self.valid = False
    
    def add_warning(self, warning: str) -> None:
        """Add a warning (doesn't affect validity)."""
        self.warnings.append(warning)


def validate_enrichment_output(
    raw_value: Any,
    spec: EnrichmentSpec,
) -> ValidationResult:
    """
    Validate an enrichment output against its spec.
    
    Args:
        raw_value: Raw output from LLM (may be string, dict, etc.)
        spec: Enrichment specification
        
    Returns:
        ValidationResult with parsed value and any errors
    """
    result = ValidationResult()
    
    # Handle None/empty
    if raw_value is None or raw_value == "":
        result.add_error("Empty value returned from LLM")
        return result
    
    # Parse based on output type
    if spec.output_type == "enum":
        result = _validate_enum(raw_value, spec)
    elif spec.output_type == "string":
        result = _validate_string(raw_value, spec)
    elif spec.output_type == "number":
        result = _validate_number(raw_value, spec)
    elif spec.output_type == "boolean":
        result = _validate_boolean(raw_value, spec)
    elif spec.output_type == "object":
        result = _validate_object(raw_value, spec)
    else:
        result.add_warning(f"Unknown output_type: {spec.output_type}, treating as string")
        result.value = str(raw_value)
    
    return result


def _validate_enum(raw_value: Any, spec: EnrichmentSpec) -> ValidationResult:
    """Validate enum value."""
    result = ValidationResult()
    
    # Normalize to string
    value = str(raw_value).strip().lower()
    
    # Check against allowed values
    if spec.allowed_values:
        # Normalize allowed values for comparison
        normalized_allowed = {str(v).lower(): v for v in spec.allowed_values}
        
        if value in normalized_allowed:
            result.value = normalized_allowed[value]  # Use original case
        else:
            result.add_error(
                f"Value '{raw_value}' not in allowed values: {spec.allowed_values}"
            )
    else:
        result.add_warning("No allowed_values specified for enum, accepting any string")
        result.value = value
    
    return result


def _validate_string(raw_value: Any, spec: EnrichmentSpec) -> ValidationResult:
    """Validate string value."""
    result = ValidationResult()
    
    value = str(raw_value).strip()
    
    if not value:
        result.add_error("Empty string value")
        return result
    
    # If allowed_values specified, check against them
    if spec.allowed_values:
        if value not in spec.allowed_values:
            result.add_warning(f"Value '{value}' not in suggested values: {spec.allowed_values}")
    
    result.value = value
    return result


def _validate_number(raw_value: Any, spec: EnrichmentSpec) -> ValidationResult:
    """Validate number value."""
    result = ValidationResult()
    
    try:
        if isinstance(raw_value, (int, float)):
            value = float(raw_value)
        else:
            value = float(str(raw_value).strip())
        
        # If allowed_values specifies a range [min, max]
        if spec.allowed_values and len(spec.allowed_values) == 2:
            min_val, max_val = spec.allowed_values
            if value < min_val or value > max_val:
                result.add_error(f"Value {value} outside range [{min_val}, {max_val}]")
                return result
        
        result.value = value
        
    except ValueError:
        result.add_error(f"Cannot parse '{raw_value}' as number")
    
    return result


def _validate_boolean(raw_value: Any, spec: EnrichmentSpec) -> ValidationResult:
    """Validate boolean value."""
    result = ValidationResult()
    
    if isinstance(raw_value, bool):
        result.value = raw_value
        return result
    
    value_str = str(raw_value).strip().lower()
    
    if value_str in ("true", "yes", "1"):
        result.value = True
    elif value_str in ("false", "no", "0"):
        result.value = False
    else:
        result.add_error(f"Cannot parse '{raw_value}' as boolean")
    
    return result


def _validate_object(raw_value: Any, spec: EnrichmentSpec) -> ValidationResult:
    """Validate object/dict value."""
    result = ValidationResult()
    
    if isinstance(raw_value, dict):
        result.value = raw_value
        return result
    
    # Try to parse as JSON
    if isinstance(raw_value, str):
        try:
            parsed = json.loads(raw_value)
            if isinstance(parsed, dict):
                result.value = parsed
            else:
                result.add_error(f"Parsed JSON is not an object: {type(parsed)}")
        except json.JSONDecodeError as e:
            result.add_error(f"Invalid JSON: {e}")
    else:
        result.add_error(f"Cannot parse {type(raw_value)} as object")
    
    return result


def parse_llm_response(
    raw_response: str,
    spec: EnrichmentSpec,
) -> Any:
    """
    Parse raw LLM response text to appropriate type.
    
    Handles common LLM quirks:
    - JSON wrapped in markdown code blocks
    - Extra whitespace
    - Quoted strings for enums
    
    Args:
        raw_response: Raw text from LLM
        spec: Enrichment specification
        
    Returns:
        Parsed value (may still need validation)
    """
    response = raw_response.strip()
    
    # Remove markdown code blocks
    if response.startswith("```"):
        lines = response.split("\n")
        # Remove first and last lines if they're fence markers
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        response = "\n".join(lines).strip()
    
    # For object types, parse as JSON
    if spec.output_type == "object":
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            return response
    
    # For simple types, just return cleaned string
    # Remove surrounding quotes
    if response.startswith('"') and response.endswith('"'):
        response = response[1:-1]
    
    return response


__all__ = [
    "ValidationResult",
    "validate_enrichment_output",
    "parse_llm_response",
]
