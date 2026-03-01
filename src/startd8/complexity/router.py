"""Complexity-based code generator and agent routing.

Maps ``ComplexityTier`` values to tier-specific code generators and
agent specs, with fallback to the MODERATE tier.
"""

from __future__ import annotations

from typing import Any, Optional

from .models import ComplexityTier


class ComplexityRouter:
    """Route tasks to tier-appropriate code generators or agent specs.

    Constructor accepts optional per-tier generators and agent specs.
    ``select()`` and ``select_agent_spec()`` fall back to the
    ``moderate`` tier when no tier-specific value is configured.
    """

    def __init__(
        self,
        *,
        trivial_generator: Optional[Any] = None,
        simple_generator: Optional[Any] = None,
        moderate_generator: Optional[Any] = None,
        complex_generator: Optional[Any] = None,
        trivial_agent_spec: Optional[str] = None,
        simple_agent_spec: Optional[str] = None,
        moderate_agent_spec: Optional[str] = None,
        complex_agent_spec: Optional[str] = None,
    ) -> None:
        self._generators = {
            ComplexityTier.TRIVIAL: trivial_generator,
            ComplexityTier.SIMPLE: simple_generator,
            ComplexityTier.MODERATE: moderate_generator,
            ComplexityTier.COMPLEX: complex_generator,
        }
        self._agent_specs = {
            ComplexityTier.TRIVIAL: trivial_agent_spec,
            ComplexityTier.SIMPLE: simple_agent_spec,
            ComplexityTier.MODERATE: moderate_agent_spec,
            ComplexityTier.COMPLEX: complex_agent_spec,
        }

    def select(self, tier: ComplexityTier) -> Any:
        """Return the code generator for *tier*, falling back to MODERATE."""
        gen = self._generators.get(tier)
        if gen is not None:
            return gen
        return self._generators.get(ComplexityTier.MODERATE)

    def select_agent_spec(self, tier: ComplexityTier) -> Optional[str]:
        """Return the agent spec for *tier*, falling back to MODERATE."""
        spec = self._agent_specs.get(tier)
        if spec is not None:
            return spec
        return self._agent_specs.get(ComplexityTier.MODERATE)
