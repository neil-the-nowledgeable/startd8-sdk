"""
Design Documentation Phase: Design document generation support.

This module provides the LLM backend adapter and data models for design
document generation.  The dual-review orchestration (Reviewer + Arbiter +
disagreement detection + escalation/resolution) was removed in the DESIGN
phase simplification (REQ-DSR-001).  Quality iteration now happens in the
IMPLEMENT inner loop (spec → drafter → reviewer score loop).

Kept exports:
    - ``DesignDocument`` — wraps raw design text
    - ``DesignSectionV2`` / ``V2_DESIGN_SECTIONS`` — V2 section enum
    - ``LLMBackend`` — async generate protocol
    - ``AgentLLMBackend`` — concrete adapter wrapping a startd8 BaseAgent
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol, runtime_checkable

# OTel instrumentation (graceful degradation when unavailable)
try:
    from opentelemetry import trace as _trace
    _HAS_OTEL = True
except ImportError:
    _HAS_OTEL = False
from startd8.utils.token_usage import token_usage_cost, token_usage_input, token_usage_output


def _get_design_tracer() -> Any:
    """Lazy tracer for design phase spans."""
    if _HAS_OTEL:
        return _trace.get_tracer("startd8.artisan.design")
    from startd8.contractors.artisan_contractor import _NoOpTracer
    return _NoOpTracer()


__all__ = [
    # Enums
    "DesignSectionV2",
    "V2_DESIGN_SECTIONS",
    # Data models
    "DesignDocument",
    # Protocols
    "LLMBackend",
    # Concrete implementations
    "AgentLLMBackend",
]


# ============================================================================
# ENUMS
# ============================================================================


class DesignSectionV2(Enum):
    """Sections of a v2 design contract (4 sections — shorter, directive)."""

    WHAT_TO_BUILD = "What to Build"
    FILES = "Files"
    API_SURFACE = "API Surface"
    CONSTRAINTS = "Constraints"


#: Section names for v2 design contracts.
V2_DESIGN_SECTIONS = [s.value for s in DesignSectionV2]


# ============================================================================
# DATA MODELS
# ============================================================================


@dataclass
class DesignDocument:
    """A generated design document.

    Attributes:
        feature_name: Name of the feature this document covers.
        sections: Mapping of section name to section content text.
        raw_text: The original, unparsed text returned by the LLM.
        generated_at: UTC timestamp of generation.
        iteration: Always 1 after dual-review removal; retained for
            serialization compatibility.
    """

    feature_name: str
    sections: dict[str, str]
    raw_text: str
    generated_at: datetime
    iteration: int


# ============================================================================
# PROTOCOLS
# ============================================================================


@runtime_checkable
class LLMBackend(Protocol):
    """Protocol for LLM backends.

    Any object that implements an async ``generate`` method with the correct
    signature can serve as the LLM backend — no inheritance required.
    """

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Generate text from the LLM.

        Args:
            prompt: The user prompt.
            system_prompt: Optional system prompt to set context.
            max_tokens: Optional output token limit override.

        Returns:
            Generated text from the LLM.
        """
        ...


# ============================================================================
# CONCRETE LLM BACKEND
# ============================================================================


class AgentLLMBackend:
    """Concrete ``LLMBackend`` adapter wrapping a startd8 ``BaseAgent``.

    Bridges the ``LLMBackend`` protocol (async ``generate(prompt, system_prompt)``)
    to the SDK's ``BaseAgent.agenerate(prompt)`` interface.

    Because ``BaseAgent.agenerate`` does not natively accept a separate
    ``system_prompt`` parameter, this adapter prepends the system prompt to
    the user prompt with a clear separator.

    Usage::

        backend = AgentLLMBackend(VALIDATE_MODEL_CLAUDE_SONNET.agent_spec)
        text = await backend.generate(
            "Write a design doc",
            system_prompt="You are an architect",
        )

    Args:
        agent_spec: Agent specification string (e.g.
            ``VALIDATE_MODEL_CLAUDE_SONNET.agent_spec``).  Ignored when
            *agent* is provided.
        agent: Pre-built ``BaseAgent`` instance.  Takes precedence over
            *agent_spec* when both are supplied.
        **agent_kwargs: Additional keyword arguments forwarded to
            ``resolve_agent_spec`` (e.g. ``max_tokens``).
    """

    def __init__(
        self,
        agent_spec: str | None = None,
        agent: Any = None,
        **agent_kwargs: Any,
    ) -> None:
        if agent is None and agent_spec is None:
            raise ValueError("Either agent_spec or agent must be provided")
        self._agent = agent
        self._agent_spec = agent_spec
        self._agent_kwargs = agent_kwargs
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0
        self.total_cost_usd: float = 0.0

    def _resolve_agent(self) -> Any:
        """Lazily resolve the agent from its spec string."""
        if self._agent is not None:
            return self._agent

        from startd8.utils.agent_resolution import resolve_agent_spec

        self._agent = resolve_agent_spec(
            self._agent_spec,  # type: ignore[arg-type]
            **self._agent_kwargs,
        )
        return self._agent

    def get_model_spec(self) -> str | None:
        """Return the model spec string for forensic logging (OT-714)."""
        return self._agent_spec

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Generate text from the LLM.

        Satisfies the ``LLMBackend`` protocol.

        Uses the native ``system_prompt`` parameter supported by all agent
        types (claude, openai, gemini, mock).

        Args:
            prompt: The user prompt.
            system_prompt: Optional system prompt to set context.
            max_tokens: Optional output token limit override.

        Returns:
            Generated text from the LLM.
        """
        agent = self._resolve_agent()

        # Temporarily override max_tokens if calibrated
        original_max = getattr(agent, "max_tokens", None)
        if max_tokens is not None and hasattr(agent, "max_tokens"):
            agent.max_tokens = max_tokens
        try:
            if _HAS_OTEL:
                span = _trace.get_current_span()
                if span and span.is_recording():
                    span.add_event("llm.call.start", attributes={
                        "llm.prompt_length": len(prompt),
                        "llm.max_tokens": max_tokens or -1,
                    })
            # Use native system_prompt parameter (all agents support it)
            response_text, response_time_ms, token_usage = await agent.agenerate(
                prompt, system_prompt=system_prompt,
            )
            self.total_input_tokens += token_usage_input(token_usage)
            self.total_output_tokens += token_usage_output(token_usage)
            self.total_cost_usd += token_usage_cost(token_usage)
            if _HAS_OTEL:
                span = _trace.get_current_span()
                if span and span.is_recording():
                    span.add_event("llm.call.complete", attributes={
                        "llm.response_time_ms": response_time_ms,
                        "llm.tokens_input": token_usage_input(token_usage),
                        "llm.tokens_output": token_usage_output(token_usage),
                        "llm.cost_usd": token_usage_cost(token_usage),
                    })
            return response_text
        finally:
            if max_tokens is not None and original_max is not None:
                agent.max_tokens = original_max
