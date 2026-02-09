"""
LLM Client - Abstraction for Vertex AI / mock LLM backends.

Model selection:
- gemini-2.5-pro: Complex reasoning tasks (difficulty, fatigue, analysis)
- gemini-2.5-flash: Simple extraction / classification

Uses ADK/Vertex pattern consistent with canvas_orchestrator.
"""

from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Model configuration
MODEL_REASONING = "gemini-2.5-pro"   # For complex reasoning
MODEL_FAST = "gemini-2.5-flash"       # For simple tasks


class LLMClient(ABC):
    """
    Abstract LLM client interface.
    
    Implementations:
    - VertexLLMClient: Production Vertex AI
    - MockLLMClient: Tests and dry-run stubs
    """
    
    @abstractmethod
    def complete(
        self,
        prompt: str,
        output_schema: Optional[Dict[str, Any]] = None,
        response_schema: Optional[Dict[str, Any]] = None,
        require_reasoning: bool = False,
    ) -> str:
        """
        Generate completion for prompt.

        Args:
            prompt: Input prompt
            output_schema: Expected output schema (appended as text to prompt)
            response_schema: Native Gemini structured output schema (preferred
                over output_schema when supported)
            require_reasoning: If True, use reasoning model (gemini-2.5-pro)

        Returns:
            Generated text response
        """
        pass
    
    @abstractmethod
    def get_model_name(self, require_reasoning: bool = False) -> str:
        """Get the model name that would be used."""
        pass


class VertexLLMClient(LLMClient):
    """
    Production LLM client using Vertex AI.
    
    Uses ADK/Vertex pattern from canvas_orchestrator.
    """
    
    def __init__(
        self,
        project_id: Optional[str] = None,
        location: str = "us-central1",
    ):
        """
        Initialize Vertex AI client.
        
        Args:
            project_id: GCP project ID (from env if not provided)
            location: Vertex AI location
        """
        self.project_id = project_id or os.environ.get("GOOGLE_CLOUD_PROJECT")
        self.location = location
        self._initialized = False
    
    def _ensure_initialized(self) -> None:
        """Lazy initialization of Vertex AI."""
        if self._initialized:
            return
        
        try:
            import vertexai
            vertexai.init(project=self.project_id, location=self.location)
            self._initialized = True
            logger.info("Vertex AI initialized: project=%s, location=%s",
                       self.project_id, self.location)
        except Exception as e:
            logger.error("Failed to initialize Vertex AI: %s", e)
            raise
    
    def get_model_name(self, require_reasoning: bool = False) -> str:
        """Get model name based on task complexity."""
        return MODEL_REASONING if require_reasoning else MODEL_FAST
    
    def complete(
        self,
        prompt: str,
        output_schema: Optional[Dict[str, Any]] = None,
        response_schema: Optional[Dict[str, Any]] = None,
        require_reasoning: bool = False,
    ) -> str:
        """
        Generate completion using Vertex AI.

        Args:
            prompt: Input prompt
            output_schema: Expected output schema (appended as text to prompt)
            response_schema: Native Gemini structured output schema (preferred)
            require_reasoning: If True, use gemini-2.5-pro

        Returns:
            Generated text
        """
        self._ensure_initialized()

        from vertexai.generative_models import GenerativeModel, GenerationConfig

        model_name = self.get_model_name(require_reasoning)
        logger.debug("Using model: %s (reasoning=%s)", model_name, require_reasoning)

        model = GenerativeModel(model_name)

        # Configure generation - higher token limit for structured JSON responses
        config_kwargs = {
            "temperature": 0.1 if require_reasoning else 0.0,
            "max_output_tokens": 16384,
        }

        if response_schema:
            config_kwargs["response_mime_type"] = "application/json"
            config_kwargs["response_schema"] = response_schema

        config = GenerationConfig(**config_kwargs)

        # Text-append fallback only when no native response_schema
        if output_schema and not response_schema:
            schema_json = json.dumps(output_schema, indent=2)
            prompt = f"{prompt}\n\nRespond with valid JSON matching this schema:\n{schema_json}"
        
        try:
            response = model.generate_content(
                prompt,
                generation_config=config,
            )
            
            # Debug: Log response structure for thinking models
            if hasattr(response, 'candidates') and response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, 'finish_reason'):
                    logger.debug("Finish reason: %s", candidate.finish_reason)
                if hasattr(candidate, 'content') and candidate.content.parts:
                    # Get all text parts (thinking models may have multiple)
                    all_text = []
                    for part in candidate.content.parts:
                        if hasattr(part, 'text') and part.text:
                            all_text.append(part.text)
                    if len(all_text) > 1:
                        logger.debug("Response has %d text parts", len(all_text))
                        # Use last part which is typically the final answer
                        result = all_text[-1].strip()
                    else:
                        result = response.text.strip()
                else:
                    result = response.text.strip()
            else:
                result = response.text.strip()
            
            logger.debug("LLM response length: %d chars", len(result))
            
            return result
            
        except Exception as e:
            logger.error("LLM completion failed: %s", e)
            raise


class MockLLMClient(LLMClient):
    """
    Mock LLM client for tests and dry-run stubs.
    
    Returns predefined responses based on output type.
    """
    
    def __init__(
        self,
        default_enum_value: str = "intermediate",
        default_string_value: str = "generated_value",
        default_number_value: float = 5.0,
        default_object_value: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize mock client.
        
        Args:
            default_enum_value: Default for enum types
            default_string_value: Default for string types
            default_number_value: Default for number types
            default_object_value: Default for object types
        """
        self.default_enum_value = default_enum_value
        self.default_string_value = default_string_value
        self.default_number_value = default_number_value
        self.default_object_value = default_object_value or {"mock": True}
        self.call_count = 0
        self.last_prompt: Optional[str] = None
    
    def get_model_name(self, require_reasoning: bool = False) -> str:
        """Return mock model name."""
        return "mock-model"
    
    def complete(
        self,
        prompt: str,
        output_schema: Optional[Dict[str, Any]] = None,
        response_schema: Optional[Dict[str, Any]] = None,
        require_reasoning: bool = False,
    ) -> str:
        """
        Return mock response.

        Infers output type from schema if provided.
        """
        self.call_count += 1
        self.last_prompt = prompt
        
        # Infer output type from schema
        if output_schema:
            output_type = output_schema.get("type", "string")
            
            if output_type == "string":
                # Check if enum
                if "enum" in output_schema:
                    enum_values = output_schema["enum"]
                    return enum_values[0] if enum_values else self.default_enum_value
                return self.default_string_value
            
            elif output_type == "number" or output_type == "integer":
                return str(self.default_number_value)
            
            elif output_type == "boolean":
                return "true"
            
            elif output_type == "object":
                return json.dumps(self.default_object_value)
            
            elif output_type == "array":
                return "[]"
        
        # Default: return enum value (most common enrichment case)
        return self.default_enum_value


def get_llm_client(use_mock: bool = False) -> LLMClient:
    """
    Factory function to get appropriate LLM client.
    
    Args:
        use_mock: If True, return MockLLMClient
        
    Returns:
        LLMClient instance
    """
    if use_mock or os.environ.get("USE_MOCK_LLM", "").lower() == "true":
        logger.info("Using MockLLMClient")
        return MockLLMClient()
    
    logger.info("Using VertexLLMClient")
    return VertexLLMClient()


__all__ = [
    "LLMClient",
    "VertexLLMClient",
    "MockLLMClient",
    "get_llm_client",
    "MODEL_REASONING",
    "MODEL_FAST",
]
