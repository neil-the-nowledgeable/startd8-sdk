"""Context resolution strategies for PrimeContractorWorkflow.

Custom strategy implementations MUST provide all three protocol members:
  - mode (property) -> str
  - resolve_context(*, base_context, pipeline_context) -> dict
  - post_generation_validate(*, generated_code, resolved_context) -> list[str]

The runtime duck-type check in PrimeContractorWorkflow.__init__ enforces
this, but static type checkers will also flag missing members if the
ContextResolutionStrategy protocol is used as a type annotation.
"""

from __future__ import annotations

import dataclasses
import typing

from startd8.logging_config import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Provenance dataclass — stored separately from prompt context
# ---------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class GenerationProvenance:
    """Immutable record of which strategy resolved context for a generation.

    Attributes:
        strategy_mode: The mode string from the strategy ("standalone" or "pipeline")
        strategy_class: The class name of the strategy (e.g., "StandaloneContextStrategy")
    """

    strategy_mode: str
    strategy_class: str


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

@typing.runtime_checkable
class ContextResolutionStrategy(typing.Protocol):
    """Protocol for context resolution strategies.

    Any object implementing this protocol can be passed to
    PrimeContractorWorkflow as the context_strategy parameter.
    """

    @property
    def mode(self) -> str:
        """Return 'standalone' or 'pipeline'."""
        ...

    def resolve_context(
        self,
        *,
        base_context: typing.Dict[str, typing.Any],
        pipeline_context: typing.Optional[typing.Dict[str, typing.Any]] = None,
    ) -> typing.Dict[str, typing.Any]:
        """Build the full context dict for code generation.

        Args:
            base_context: Base context dict with existing keys/values
            pipeline_context: Optional enrichment data (onboarding, architectural, etc.)

        Returns:
            Enriched context dict (base_context + strategy additions)
        """
        ...

    def post_generation_validate(
        self,
        *,
        generated_code: str,
        resolved_context: typing.Dict[str, typing.Any],
    ) -> typing.List[str]:
        """Validate generation against resolved context.

        Called after the LLM returns generated_code to perform
        post-generation checks (e.g., enrichment field presence,
        code compliance with pipeline constraints).

        Args:
            generated_code: The code returned by the LLM
            resolved_context: The context dict used for generation

        Returns:
            List of warning strings (empty list = pass)
        """
        ...


# ---------------------------------------------------------------------------
# Concrete strategies
# ---------------------------------------------------------------------------

class StandaloneContextStrategy:
    """Preserves exact existing inline context-building behavior.

    Returns base_context unmodified, ensuring that existing workflows
    that do not supply a custom strategy see zero behavioral change.
    """

    @property
    def mode(self) -> str:
        """Return 'standalone' mode identifier."""
        return "standalone"

    def resolve_context(
        self,
        *,
        base_context: typing.Dict[str, typing.Any],
        pipeline_context: typing.Optional[typing.Dict[str, typing.Any]] = None,
    ) -> typing.Dict[str, typing.Any]:
        """Return base_context unmodified (legacy path)."""
        return dict(base_context)

    def post_generation_validate(
        self,
        *,
        generated_code: str,
        resolved_context: typing.Dict[str, typing.Any],
    ) -> typing.List[str]:
        """No validation in standalone mode."""
        return []

    def __repr__(self) -> str:
        return "StandaloneContextStrategy()"


class PipelineContextStrategy:
    """Enriches base context with pipeline payload fields.

    Merges onboarding_metadata, architectural_context, and design_calibration
    from the pipeline_context under a "pipeline." namespace prefix to prevent
    silent collisions with base context keys.

    Enrichment fields are only included if their value is not None.
    """

    ENRICHMENT_FIELDS: typing.Tuple[str, ...] = (
        "onboarding_metadata",
        "architectural_context",
        "design_calibration",
    )
    ENRICHMENT_NAMESPACE: str = "pipeline"

    @property
    def mode(self) -> str:
        """Return 'pipeline' mode identifier."""
        return "pipeline"

    def resolve_context(
        self,
        *,
        base_context: typing.Dict[str, typing.Any],
        pipeline_context: typing.Optional[typing.Dict[str, typing.Any]] = None,
    ) -> typing.Dict[str, typing.Any]:
        """Enriches base_context with pipeline fields under namespace prefix."""
        ctx = dict(base_context)
        if pipeline_context is None:
            return ctx

        for field in self.ENRICHMENT_FIELDS:
            value = pipeline_context.get(field)
            if value is not None:
                namespaced_key = f"{self.ENRICHMENT_NAMESPACE}.{field}"
                # Collision detection: warn if base_context already contains
                # the namespaced key
                if namespaced_key in ctx:
                    logger.warning(
                        "Enrichment key '%s' collides with existing base_context key; "
                        "overwriting with pipeline value",
                        namespaced_key,
                    )
                ctx[namespaced_key] = value
        return ctx

    def post_generation_validate(
        self,
        *,
        generated_code: str,
        resolved_context: typing.Dict[str, typing.Any],
    ) -> typing.List[str]:
        """Warn if pipeline fields are missing from resolved context."""
        warnings_list: typing.List[str] = []
        for field in self.ENRICHMENT_FIELDS:
            namespaced_key = f"{self.ENRICHMENT_NAMESPACE}.{field}"
            if namespaced_key not in resolved_context:
                warnings_list.append(
                    f"Pipeline mode but '{namespaced_key}' was not in resolved context"
                )
        return warnings_list

    def __repr__(self) -> str:
        return (
            f"PipelineContextStrategy("
            f"namespace={self.ENRICHMENT_NAMESPACE!r}, "
            f"fields={self.ENRICHMENT_FIELDS!r})"
        )
