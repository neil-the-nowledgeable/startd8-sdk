"""
Shared token-usage normalization helpers.

These helpers normalize token counts and cost extraction across
different SDK versions and provider implementations.
"""

from typing import Any

__all__ = [
    "token_usage_input",
    "token_usage_output",
    "token_usage_cost",
]


def token_usage_input(token_usage: Any) -> int:
    """
    Normalize token usage input count across SDK versions/providers.

    StartD8 TokenUsage uses ``input``/``output``.  Some older callers
    used ``input_tokens``/``output_tokens``.
    """
    return int(getattr(token_usage, "input_tokens", getattr(token_usage, "input", 0)) or 0)


def token_usage_output(token_usage: Any) -> int:
    """Normalize token usage output count across SDK versions/providers."""
    return int(getattr(token_usage, "output_tokens", getattr(token_usage, "output", 0)) or 0)


def token_usage_cost(token_usage: Any) -> float:
    """Extract cost from a token usage object, preferring explicit cost over estimate."""
    if hasattr(token_usage, "cost") and getattr(token_usage, "cost") is not None:
        return float(getattr(token_usage, "cost"))
    if hasattr(token_usage, "cost_estimate"):
        try:
            return float(getattr(token_usage, "cost_estimate"))
        except Exception:
            return 0.0
    return 0.0
