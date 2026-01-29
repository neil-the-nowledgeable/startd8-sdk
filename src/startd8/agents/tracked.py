# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0
# See LICENSE.md for complete terms.

"""
Tracked agents that emit OpenTelemetry spans for ContextCore observability.

These agents extend StartD8 agents with:
- Span emission for each generation call
- Task status updates (when linked to a ContextCore task)
- Token usage as span attributes
- Truncation detection as span events
- Cost tracking integration

Usage:
    from startd8.agents.tracked import TrackedClaudeAgent

    agent = TrackedClaudeAgent(
        name="my-claude",
        model="claude-sonnet-4-20250514",
        project_id="my-project",  # Optional: for ContextCore linking
    )

    # Calls emit spans automatically
    response, time_ms, usage = await agent.agenerate("Hello")

    # Or link to a specific task
    response, time_ms, usage = await agent.agenerate(
        "Implement rate limiter",
        task_id="SDK-101",  # Links span to ContextCore task
    )
"""

from typing import Optional, Any, Dict, Tuple
from datetime import datetime, timezone
import logging

from .base import BaseAgent
from .claude import ClaudeAgent
from .openai import GPT4Agent
from .gemini import GeminiAgent
from ..models import TokenUsage

logger = logging.getLogger(__name__)

# Lazy-load OpenTelemetry to avoid hard dependency
_tracer = None
_OTEL_AVAILABLE = False


def _get_tracer():
    """Get or create the OpenTelemetry tracer."""
    global _tracer, _OTEL_AVAILABLE
    if _tracer is None:
        try:
            from opentelemetry import trace
            _tracer = trace.get_tracer("startd8.agents")
            _OTEL_AVAILABLE = True
        except ImportError:
            logger.debug("OpenTelemetry not installed - span emission disabled")
            _OTEL_AVAILABLE = False
            _tracer = None
    return _tracer


class TrackedAgentMixin:
    """
    Mixin that adds OpenTelemetry span tracking to StartD8 agents.

    When mixed into an agent class, each call to agenerate() creates an
    OpenTelemetry span with:
    - Agent and model information
    - Prompt length and response metrics
    - Token usage (input, output, total)
    - Truncation detection events
    - Optional task linking for ContextCore integration

    Attributes:
        project_id: ContextCore project ID for span attributes
        emit_spans: Whether to emit spans (default: True)
        _tracker: Optional TaskTracker for ContextCore integration
        _insight_emitter: Optional InsightEmitter for decision/lesson emission
    """

    def __init__(
        self,
        *args,
        project_id: Optional[str] = None,
        emit_spans: bool = True,
        tracker: Optional[Any] = None,
        insight_emitter: Optional[Any] = None,
        **kwargs
    ):
        """
        Initialize tracked agent.

        Args:
            project_id: ContextCore project ID for span attributes
            emit_spans: Whether to emit OpenTelemetry spans
            tracker: Optional ContextCore TaskTracker instance
            insight_emitter: Optional ContextCore InsightEmitter instance
            *args, **kwargs: Passed to parent agent class
        """
        self.project_id = project_id
        self.emit_spans = emit_spans
        self._tracker = tracker
        self._insight_emitter = insight_emitter
        super().__init__(*args, **kwargs)

    async def agenerate(
        self,
        prompt: str,
        task_id: Optional[str] = None,
        emit_insight: bool = False,
        **kwargs
    ) -> Tuple[str, int, TokenUsage]:
        """
        Generate with OpenTelemetry span tracking.

        Args:
            prompt: The prompt to send to the agent
            task_id: Optional task ID to link this generation to
            emit_insight: If True, emit the response as a decision insight
            **kwargs: Additional arguments passed to parent agenerate

        Returns:
            Tuple of (response_text, response_time_ms, token_usage)
        """
        tracer = _get_tracer()

        # Update task status if linked
        if task_id and self._tracker:
            try:
                self._tracker.update_status(task_id, "in_progress")
            except Exception as e:
                logger.debug(f"Failed to update task status: {e}")

        # Create span for this generation
        if self.emit_spans and tracer and _OTEL_AVAILABLE:
            from opentelemetry import trace

            with tracer.start_as_current_span(
                f"agent.generate:{self.name}",
                attributes={
                    "agent.id": self.name,
                    "agent.model": getattr(self, 'model', 'unknown'),
                    "agent.prompt_length": len(prompt),
                    "task.id": task_id or "",
                    "project.id": self.project_id or "",
                }
            ) as span:
                # Call parent implementation
                response_text, response_time_ms, token_usage = await super().agenerate(
                    prompt, **kwargs
                )

                # Add response attributes
                span.set_attribute("agent.response_time_ms", response_time_ms)
                span.set_attribute("agent.response_length", len(response_text))

                if token_usage:
                    span.set_attribute("agent.tokens_input", token_usage.input or 0)
                    span.set_attribute("agent.tokens_output", token_usage.output or 0)
                    span.set_attribute("agent.tokens_total",
                                       (token_usage.input or 0) + (token_usage.output or 0))
                    span.set_attribute("agent.truncated", token_usage.was_truncated or False)

                    if token_usage.was_truncated:
                        span.add_event("truncation_detected", attributes={
                            "finish_reason": token_usage.finish_reason or "unknown",
                            "output_tokens": token_usage.output or 0,
                        })

                # Set span status based on response
                if response_text:
                    span.set_status(trace.StatusCode.OK)
                else:
                    span.set_status(trace.StatusCode.ERROR, "Empty response")
        else:
            # No tracing - direct call
            response_text, response_time_ms, token_usage = await super().agenerate(
                prompt, **kwargs
            )

        # Emit insight if requested
        if emit_insight and self._insight_emitter:
            try:
                self._insight_emitter.emit_decision(
                    summary=response_text[:500] if len(response_text) > 500 else response_text,
                    confidence=0.8,
                    rationale=f"agent={self.name}, model={getattr(self, 'model', 'unknown')}, task_id={task_id}",
                )
            except Exception as e:
                logger.debug(f"Failed to emit insight: {e}")

        return response_text, response_time_ms, token_usage

    def with_task_context(
        self,
        task_id: str,
        project_id: Optional[str] = None,
    ) -> "TrackedAgentMixin":
        """
        Create a copy of this agent bound to a specific task.

        Useful for workflows where you want all agent calls to be
        automatically linked to a task without passing task_id each time.

        Args:
            task_id: ContextCore task ID to bind to
            project_id: Optional project ID override

        Returns:
            New agent instance with task context set

        Example:
            agent = TrackedClaudeAgent(name="claude", model="claude-sonnet-4-20250514")
            task_agent = agent.with_task_context("SDK-101", project_id="my-project")

            # All calls now linked to SDK-101
            response = await task_agent.agenerate("Implement feature X")
        """
        # Create a wrapper that injects task_id
        original_agenerate = self.agenerate

        class TaskBoundAgent:
            def __init__(self, parent, task_id, project_id):
                self._parent = parent
                self._task_id = task_id
                self._project_id = project_id or parent.project_id

                # Copy relevant attributes
                self.name = parent.name
                self.model = parent.model
                self.project_id = self._project_id

            async def agenerate(self, prompt: str, **kwargs) -> Tuple[str, int, TokenUsage]:
                kwargs.setdefault('task_id', self._task_id)
                return await original_agenerate(prompt, **kwargs)

            def generate(self, prompt: str, **kwargs) -> Tuple[str, int, TokenUsage]:
                kwargs.setdefault('task_id', self._task_id)
                return self._parent.generate(prompt, **kwargs)

            def __getattr__(self, name):
                return getattr(self._parent, name)

        return TaskBoundAgent(self, task_id, project_id)


class TrackedClaudeAgent(TrackedAgentMixin, ClaudeAgent):
    """
    Claude agent with OpenTelemetry span tracking.

    Extends ClaudeAgent with automatic span emission for each generation call.

    Example:
        agent = TrackedClaudeAgent(
            name="claude",
            model="claude-sonnet-4-20250514",
            project_id="my-project",
        )

        # Each call emits a span
        response, time_ms, usage = await agent.agenerate("Hello, Claude!")
    """
    pass


class TrackedGPT4Agent(TrackedAgentMixin, GPT4Agent):
    """
    GPT-4 agent with OpenTelemetry span tracking.

    Extends GPT4Agent with automatic span emission for each generation call.

    Example:
        agent = TrackedGPT4Agent(
            name="gpt4",
            model="gpt-4o",
            project_id="my-project",
        )

        response, time_ms, usage = await agent.agenerate("Hello, GPT!")
    """
    pass


class TrackedGeminiAgent(TrackedAgentMixin, GeminiAgent):
    """
    Gemini agent with OpenTelemetry span tracking.

    Extends GeminiAgent with automatic span emission for each generation call.

    Example:
        agent = TrackedGeminiAgent(
            name="gemini",
            model="gemini-1.5-pro",
            project_id="my-project",
        )

        response, time_ms, usage = await agent.agenerate("Hello, Gemini!")
    """
    pass


# Factory function for creating tracked agents
def create_tracked_agent(
    agent_spec: str,
    project_id: Optional[str] = None,
    emit_spans: bool = True,
    **kwargs
) -> BaseAgent:
    """
    Create a tracked agent from an agent spec string.

    Args:
        agent_spec: Agent specification in "provider:model" format
        project_id: ContextCore project ID for span attributes
        emit_spans: Whether to emit OpenTelemetry spans
        **kwargs: Additional arguments passed to agent constructor

    Returns:
        Tracked agent instance

    Example:
        agent = create_tracked_agent(
            "anthropic:claude-sonnet-4-20250514",
            project_id="my-project",
        )
    """
    from ..utils.agent_resolution import resolve_agent_spec

    # Parse spec
    if ":" in agent_spec:
        provider, model = agent_spec.split(":", 1)
    else:
        provider = agent_spec
        model = None

    provider_lower = provider.lower()

    # Resolve to tracked agent class
    if provider_lower in ("anthropic", "claude"):
        agent_class = TrackedClaudeAgent
        model = model or "claude-sonnet-4-20250514"
    elif provider_lower in ("openai", "gpt", "gpt4"):
        agent_class = TrackedGPT4Agent
        model = model or "gpt-4o"
    elif provider_lower in ("gemini", "google"):
        agent_class = TrackedGeminiAgent
        model = model or "gemini-1.5-pro"
    else:
        # Fall back to non-tracked agent via resolution
        logger.warning(f"No tracked agent for provider '{provider}', using base agent")
        return resolve_agent_spec(agent_spec)

    return agent_class(
        name=kwargs.pop('name', f"{provider_lower}-tracked"),
        model=model,
        project_id=project_id,
        emit_spans=emit_spans,
        **kwargs
    )
