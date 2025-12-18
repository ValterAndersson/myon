import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from vertexai.preview.generative_models import GenerativeModel, GenerationConfig


logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    raw_text: str
    data: Dict[str, Any]


class LLMClient:
    """Thin wrapper around Vertex GenerativeModel that always returns JSON."""

    def __init__(
        self,
        model_name: str,
        temperature: float = 0.4,
        max_output_tokens: int = 1024,
    ) -> None:
        self._model = GenerativeModel(model_name)
        self._config = GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            response_mime_type="application/json",
        )

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        fallback: Optional[Dict[str, Any]] = None,
    ) -> LLMResponse:
        """Execute the model and decode the JSON response."""
        try:
            response = self._model.generate_content(
                [
                    system_prompt.strip(),
                    user_prompt.strip(),
                ],
                generation_config=self._config,
            )
            text = _collect_text(response)
            data = json.loads(text)
            return LLMResponse(raw_text=text, data=data)
        except Exception as exc:
            logger.exception("LLM call failed: %s", exc)
            if fallback is None:
                raise
            return LLMResponse(raw_text=json.dumps(fallback), data=fallback)


def _collect_text(response: Any) -> str:
    """Extract plain text from a Vertex response object."""
    parts: List[str] = []
    try:
        for candidate in response.candidates or []:
            content = getattr(candidate, "content", None)
            if not content:
                continue
            for part in getattr(content, "parts", []):
                text = getattr(part, "text", None)
                if text:
                    parts.append(text)
    except Exception:
        pass

    if not parts and hasattr(response, "text"):
        parts.append(getattr(response, "text"))

    payload = "\n".join(part.strip() for part in parts if part.strip())
    if not payload:
        raise ValueError("LLM response contained no text payload")
    return payload



