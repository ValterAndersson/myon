"""
Enrichment Module - LLM-backed field population for catalog exercises.

This module provides:
- EnrichmentSpec model for defining enrichment jobs
- LLMClient abstraction for Vertex AI / mock backends
- Enrichment engine for computing and validating field values
- Output validators for schema compliance

Model selection:
- gemini-2.5-pro: Complex reasoning tasks (difficulty, fatigue, analysis)
- gemini-2.5-flash: Simple extraction / classification
"""

from app.enrichment.models import EnrichmentSpec, EnrichmentResult, ShardResult
from app.enrichment.llm_client import (
    LLMClient,
    VertexLLMClient,
    MockLLMClient,
    get_llm_client,
    MODEL_REASONING,
    MODEL_FAST,
)
from app.enrichment.engine import (
    compute_enrichment,
    validate_enrichment,
    compute_enrichment_batch,
    build_enrichment_prompt,
)
from app.enrichment.validators import (
    validate_enrichment_output,
    parse_llm_response,
    ValidationResult,
)

__all__ = [
    # Models
    "EnrichmentSpec",
    "EnrichmentResult",
    "ShardResult",
    # LLM Client
    "LLMClient",
    "VertexLLMClient",
    "MockLLMClient",
    "get_llm_client",
    "MODEL_REASONING",
    "MODEL_FAST",
    # Engine
    "compute_enrichment",
    "validate_enrichment",
    "compute_enrichment_batch",
    "build_enrichment_prompt",
    # Validators
    "validate_enrichment_output",
    "parse_llm_response",
    "ValidationResult",
]
