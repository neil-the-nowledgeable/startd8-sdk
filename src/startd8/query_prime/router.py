"""Tier-to-model routing with T3→T2→T1 escalation — REQ-QP-400.

Maps query complexity tiers to model agent specs with automatic
escalation when generation fails verification.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from startd8.complexity.models import ComplexityTier
from startd8.logging_config import get_logger

logger = get_logger(__name__)

# Default agent specs per tier (cheapest first)
_DEFAULT_T3_SPEC = "anthropic:claude-haiku-4-5-20251008"
_DEFAULT_T2_SPEC = "anthropic:claude-sonnet-4-6"
_DEFAULT_T1_SPEC = "anthropic:claude-opus-4-6"


@dataclass(frozen=True)
class QueryRouterConfig:
    """Configuration for query tier routing."""

    t3_agent_spec: str = _DEFAULT_T3_SPEC
    t2_agent_spec: str = _DEFAULT_T2_SPEC
    t1_agent_spec: str = _DEFAULT_T1_SPEC
    max_escalations: int = 2
    max_retries_per_tier: int = 1


# Escalation order: cheapest → most expensive
_ESCALATION_ORDER: List[ComplexityTier] = [
    ComplexityTier.SIMPLE,
    ComplexityTier.MODERATE,
    ComplexityTier.COMPLEX,
]


def get_agent_spec_for_tier(
    tier: ComplexityTier,
    config: Optional[QueryRouterConfig] = None,
) -> str:
    """Return the agent spec string for a given complexity tier.

    Args:
        tier: The complexity tier to route.
        config: Optional routing configuration.

    Returns:
        Agent spec string (e.g. "anthropic:claude-haiku-4-5-20251008").
    """
    cfg = config or QueryRouterConfig()
    mapping = {
        ComplexityTier.TRIVIAL: cfg.t3_agent_spec,  # shouldn't reach LLM, but just in case
        ComplexityTier.SIMPLE: cfg.t3_agent_spec,
        ComplexityTier.MODERATE: cfg.t2_agent_spec,
        ComplexityTier.COMPLEX: cfg.t1_agent_spec,
    }
    return mapping.get(tier, cfg.t2_agent_spec)


def get_escalation_tier(
    current_tier: ComplexityTier,
) -> Optional[ComplexityTier]:
    """Return the next tier to escalate to, or None if already at max.

    Escalation path: SIMPLE → MODERATE → COMPLEX → None.

    Args:
        current_tier: The current complexity tier.

    Returns:
        Next tier, or None if at COMPLEX (no further escalation).
    """
    try:
        idx = _ESCALATION_ORDER.index(current_tier)
    except ValueError:
        # TRIVIAL or unknown — escalate to SIMPLE
        return ComplexityTier.SIMPLE

    if idx >= len(_ESCALATION_ORDER) - 1:
        return None  # Already at COMPLEX
    return _ESCALATION_ORDER[idx + 1]
