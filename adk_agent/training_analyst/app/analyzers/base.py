"""Base analyzer with shared LLM call pattern.

Uses google-genai SDK (not google-generativeai) for GCP service account auth.
"""

import json
import logging
import re
from typing import Any, Dict, Optional

from google import genai
from google.genai.types import GenerateContentConfig

from app.config import PROJECT_ID

logger = logging.getLogger(__name__)

# Matches dot-path keys like "weeks.2025-01-06.sets" or "weeks.2025-01-06.reps_bucket.6-10"
_WEEKS_DOT_RE = re.compile(r"^weeks\.(\d{4}-\d{2}-\d{2})\.(.+)$")

# Singleton GenAI client (reused across analyzers)
_client: Optional[genai.Client] = None


def _get_genai_client() -> genai.Client:
    """Get or create the GenAI client with GCP project auth."""
    global _client
    if _client is None:
        _client = genai.Client(
            vertexai=True,
            project=PROJECT_ID,
            location="europe-west1",
        )
    return _client


class BaseAnalyzer:
    """Base class for training analyzers.

    Provides shared LLM call pattern with JSON response mode.
    Subclasses implement analyze() with domain-specific logic.
    """

    def __init__(self, model_name: str):
        self.model_name = model_name

    def call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        required_keys: Optional[list] = None,
    ) -> Dict[str, Any]:
        """
        Call LLM and parse JSON response.

        No max_output_tokens cap — response_mime_type="application/json" ensures
        the model produces well-formed JSON and stops when the object closes.
        Actual outputs are small (300-2000 tokens). A hard cap risks truncation
        which produces invalid JSON or cut-off sentences.

        Args:
            system_prompt: System instructions
            user_prompt: User input with data
            temperature: Generation temperature (default 0.2 for consistency)
            required_keys: Optional list of top-level keys to validate in the
                response. If any are missing, raises ValueError.

        Returns:
            Parsed JSON response dict

        Raises:
            ValueError: If response is empty, truncated, or missing required keys
            json.JSONDecodeError: If response is not valid JSON
        """
        client = _get_genai_client()

        try:
            response = client.models.generate_content(
                model=self.model_name,
                contents=[
                    system_prompt.strip(),
                    user_prompt.strip(),
                ],
                config=GenerateContentConfig(
                    temperature=temperature,
                    response_mime_type="application/json",
                ),
            )

            # Check for truncation before parsing
            finish_reason = None
            if response.candidates:
                finish_reason = response.candidates[0].finish_reason
            if finish_reason and str(finish_reason) == "MAX_TOKENS":
                logger.error(
                    "LLM response truncated (MAX_TOKENS), model=%s",
                    self.model_name,
                )
                raise ValueError(
                    "LLM response was truncated (MAX_TOKENS). "
                    "Output exceeded model limit."
                )

            text = response.text.strip()
            if not text:
                raise ValueError("LLM response contained no text")

            data = json.loads(text)

            # Validate required top-level keys
            if required_keys:
                missing = [k for k in required_keys if k not in data]
                if missing:
                    logger.error(
                        "LLM response missing required keys %s, model=%s",
                        missing, self.model_name,
                    )
                    raise ValueError(
                        f"LLM response missing required keys: {missing}"
                    )

            logger.info("LLM call succeeded, model=%s", self.model_name)
            return data

        except Exception as e:
            logger.error("LLM call failed (model=%s): %s", self.model_name, e)
            raise

    @staticmethod
    def extract_weeks_map(data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Extract weeks map from a series document, handling both formats.

        Series docs can store weekly data in two ways:
        1. Nested map: data["weeks"]["2025-01-06"]["sets"] = 5
        2. Dot-path keys: data["weeks.2025-01-06.sets"] = 5

        Some docs have both (older docs migrated). This merges them,
        preferring nested map values when both exist for the same field.
        """
        weeks_map = {}

        # Source 1: nested map (if present and populated)
        nested = data.get("weeks")
        if isinstance(nested, dict) and nested:
            for week_id, week_data in nested.items():
                if isinstance(week_data, dict):
                    weeks_map[week_id] = dict(week_data)

        # Source 2: dot-path top-level keys
        for key, value in data.items():
            m = _WEEKS_DOT_RE.match(key)
            if not m:
                continue
            week_id = m.group(1)
            field_path = m.group(2)

            if week_id not in weeks_map:
                weeks_map[week_id] = {}

            # Handle nested dot-paths like "reps_bucket.6-10"
            parts = field_path.split(".")
            if len(parts) == 1:
                # Only set if not already present from nested map
                if parts[0] not in weeks_map[week_id]:
                    weeks_map[week_id][parts[0]] = value
            else:
                # Nested field (e.g., reps_bucket.6-10)
                parent = parts[0]
                child = ".".join(parts[1:])
                if parent not in weeks_map[week_id]:
                    weeks_map[week_id][parent] = {}
                if isinstance(weeks_map[week_id][parent], dict):
                    if child not in weeks_map[week_id][parent]:
                        weeks_map[week_id][parent][child] = value

        return weeks_map

    def log_event(self, event: str, **kwargs):
        """Log structured event for Cloud Logging."""
        record = {
            "event": event,
            "analyzer": self.__class__.__name__,
        }
        record.update(kwargs)
        logger.info(json.dumps(record))
