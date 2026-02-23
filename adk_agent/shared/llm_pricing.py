"""Vertex AI Gemini pricing (per 1M tokens, EUR).

Updated: 2026-02-23. Source: cloud.google.com/vertex-ai/generative-ai/pricing
Update this file when Google publishes new rates.
"""

from __future__ import annotations

PRICING_EUR_PER_1M = {
    "gemini-2.5-flash": {"input": 0.15, "output": 0.60, "thinking": 0.15},
    "gemini-2.5-pro": {"input": 1.25, "output": 5.00, "thinking": 1.25},
    # Legacy models (in case they appear in historical data)
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40, "thinking": 0.0},
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30, "thinking": 0.0},
    "gemini-1.5-pro": {"input": 1.25, "output": 5.00, "thinking": 0.0},
}


def estimate_cost_eur(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    thinking_tokens: int = 0,
) -> float:
    """Estimate cost in EUR from token counts and model name.

    Args:
        model: Model identifier (e.g. "gemini-2.5-flash")
        prompt_tokens: Input token count
        completion_tokens: Output token count
        thinking_tokens: Thinking/reasoning token count (Gemini 2.5+)

    Returns:
        Estimated cost in EUR
    """
    rates = PRICING_EUR_PER_1M.get(model, {"input": 0, "output": 0, "thinking": 0})
    return (
        (prompt_tokens / 1_000_000) * rates["input"]
        + (completion_tokens / 1_000_000) * rates["output"]
        + (thinking_tokens / 1_000_000) * rates["thinking"]
    )
