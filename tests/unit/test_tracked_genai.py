"""
Integration tests for TrackedAgentMixin OTel GenAI dual-emit.

Verifies that TrackedAgentMixin emits the correct span attributes
under each EmitMode, including:
- SpanKind.CLIENT on every span
- gen_ai.system per concrete class
- gen_ai.operation.name = "chat"
- gen_ai.response.finish_reasons as array
- Correct span naming per mode
"""

import os
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from startd8.models import TokenUsage
from startd8.genai_compat import EmitMode, DualEmitAttributes, reset_emit_mode_cache


# =========================================================================
# Helpers
# =========================================================================

def _make_mock_agent(gen_ai_system="unknown", model="test-model", name="test-agent"):
    """
    Build a minimal TrackedAgentMixin-based object with a mocked super().agenerate().

    We can't directly instantiate TrackedClaudeAgent without provider deps,
    so we build a concrete subclass using MockAgent.
    """
    from startd8.agents.mock import MockAgent
    from startd8.agents.tracked import TrackedAgentMixin

    class _TrackedMock(TrackedAgentMixin, MockAgent):
        GEN_AI_SYSTEM = gen_ai_system

    agent = _TrackedMock(
        name=name,
        model=model,
        project_id="test-proj",
        emit_spans=True,
    )
    return agent


def _make_mock_agent_with_usage(
    finish_reason="end_turn",
    was_truncated=False,
    **kwargs,
):
    """Build a tracked mock agent whose super().agenerate returns controlled token usage."""
    agent = _make_mock_agent(**kwargs)

    usage = TokenUsage(
        input=50,
        output=100,
        total=150,
        model_name=kwargs.get("model", "test-model"),
        finish_reason=finish_reason,
    )

    async def fake_agenerate(prompt, **kw):
        return "Hello world", 42, usage

    # Patch the parent (MockAgent) agenerate so TrackedAgentMixin calls it
    from startd8.agents.mock import MockAgent
    agent.__class__.__bases__[1].agenerate = fake_agenerate

    return agent, usage


@pytest.fixture(autouse=True)
def _clear_cache():
    reset_emit_mode_cache()
    yield
    reset_emit_mode_cache()


# =========================================================================
# SpanKind.CLIENT
# =========================================================================

class TestSpanKindClient:
    @pytest.mark.asyncio
    async def test_span_kind_is_client(self):
        agent = _make_mock_agent(gen_ai_system="anthropic")

        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_span.__enter__ = MagicMock(return_value=mock_span)
        mock_span.__exit__ = MagicMock(return_value=False)
        mock_tracer.start_as_current_span.return_value = mock_span

        with patch("startd8.agents.tracked._tracer", mock_tracer), \
             patch("startd8.agents.tracked._OTEL_AVAILABLE", True):
            await agent.agenerate("Hello")

        call_kwargs = mock_tracer.start_as_current_span.call_args[1]
        from opentelemetry.trace import SpanKind
        assert call_kwargs["kind"] == SpanKind.CLIENT


# =========================================================================
# GEN_AI_SYSTEM per concrete class
# =========================================================================

class TestGenAISystem:
    def test_claude_system(self):
        from startd8.agents.tracked import TrackedClaudeAgent
        assert TrackedClaudeAgent.GEN_AI_SYSTEM == "anthropic"

    def test_gpt4_system(self):
        from startd8.agents.tracked import TrackedGPT4Agent
        assert TrackedGPT4Agent.GEN_AI_SYSTEM == "openai"

    def test_gemini_system(self):
        from startd8.agents.tracked import TrackedGeminiAgent
        assert TrackedGeminiAgent.GEN_AI_SYSTEM == "google"

    def test_base_mixin_system(self):
        from startd8.agents.tracked import TrackedAgentMixin
        assert TrackedAgentMixin.GEN_AI_SYSTEM == "unknown"


# =========================================================================
# Dual mode attributes
# =========================================================================

class TestDualModeAttributes:
    @pytest.mark.asyncio
    async def test_dual_mode_emits_both_namespaces(self):
        agent = _make_mock_agent(gen_ai_system="anthropic", model="claude-sonnet")
        agent._dual_emit = DualEmitAttributes(mode=EmitMode.DUAL)

        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_span.__enter__ = MagicMock(return_value=mock_span)
        mock_span.__exit__ = MagicMock(return_value=False)
        mock_tracer.start_as_current_span.return_value = mock_span

        with patch("startd8.agents.tracked._tracer", mock_tracer), \
             patch("startd8.agents.tracked._OTEL_AVAILABLE", True):
            await agent.agenerate("Hello")

        # Check initial attributes passed to start_as_current_span
        call_kwargs = mock_tracer.start_as_current_span.call_args[1]
        init_attrs = call_kwargs["attributes"]

        # Legacy keys
        assert init_attrs["agent.id"] == "test-agent"
        assert init_attrs["agent.model"] == "claude-sonnet"

        # OTel keys
        assert init_attrs["gen_ai.agent.id"] == "test-agent"
        assert init_attrs["gen_ai.request.model"] == "claude-sonnet"
        assert init_attrs["gen_ai.system"] == "anthropic"
        assert init_attrs["gen_ai.operation.name"] == "chat"

    @pytest.mark.asyncio
    async def test_dual_mode_span_name_is_legacy(self):
        agent = _make_mock_agent(gen_ai_system="anthropic", model="claude-sonnet", name="my-claude")
        agent._dual_emit = DualEmitAttributes(mode=EmitMode.DUAL)

        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_span.__enter__ = MagicMock(return_value=mock_span)
        mock_span.__exit__ = MagicMock(return_value=False)
        mock_tracer.start_as_current_span.return_value = mock_span

        with patch("startd8.agents.tracked._tracer", mock_tracer), \
             patch("startd8.agents.tracked._OTEL_AVAILABLE", True):
            await agent.agenerate("Hello")

        span_name = mock_tracer.start_as_current_span.call_args[0][0]
        assert span_name == "agent.generate:my-claude"


# =========================================================================
# OTEL mode attributes
# =========================================================================

class TestOtelModeAttributes:
    @pytest.mark.asyncio
    async def test_otel_mode_removes_mapped_legacy_keys(self):
        agent = _make_mock_agent(gen_ai_system="openai", model="gpt-4o")
        agent._dual_emit = DualEmitAttributes(mode=EmitMode.OTEL)

        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_span.__enter__ = MagicMock(return_value=mock_span)
        mock_span.__exit__ = MagicMock(return_value=False)
        mock_tracer.start_as_current_span.return_value = mock_span

        with patch("startd8.agents.tracked._tracer", mock_tracer), \
             patch("startd8.agents.tracked._OTEL_AVAILABLE", True):
            await agent.agenerate("Hello")

        init_attrs = mock_tracer.start_as_current_span.call_args[1]["attributes"]

        # Mapped legacy keys should NOT be present
        assert "agent.id" not in init_attrs
        assert "agent.model" not in init_attrs

        # OTel keys should be present
        assert init_attrs["gen_ai.agent.id"] == "test-agent"
        assert init_attrs["gen_ai.request.model"] == "gpt-4o"
        assert init_attrs["gen_ai.system"] == "openai"
        assert init_attrs["gen_ai.operation.name"] == "chat"

        # Unmapped keys pass through
        assert "agent.prompt_length" in init_attrs

    @pytest.mark.asyncio
    async def test_otel_mode_span_name_is_chat(self):
        agent = _make_mock_agent(gen_ai_system="openai", model="gpt-4o")
        agent._dual_emit = DualEmitAttributes(mode=EmitMode.OTEL)

        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_span.__enter__ = MagicMock(return_value=mock_span)
        mock_span.__exit__ = MagicMock(return_value=False)
        mock_tracer.start_as_current_span.return_value = mock_span

        with patch("startd8.agents.tracked._tracer", mock_tracer), \
             patch("startd8.agents.tracked._OTEL_AVAILABLE", True):
            await agent.agenerate("Hello")

        span_name = mock_tracer.start_as_current_span.call_args[0][0]
        assert span_name == "chat gpt-4o"


# =========================================================================
# Legacy mode attributes
# =========================================================================

class TestLegacyModeAttributes:
    @pytest.mark.asyncio
    async def test_legacy_mode_no_genai_keys(self):
        agent = _make_mock_agent(gen_ai_system="anthropic", model="claude-sonnet")
        agent._dual_emit = DualEmitAttributes(mode=EmitMode.LEGACY)

        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_span.__enter__ = MagicMock(return_value=mock_span)
        mock_span.__exit__ = MagicMock(return_value=False)
        mock_tracer.start_as_current_span.return_value = mock_span

        with patch("startd8.agents.tracked._tracer", mock_tracer), \
             patch("startd8.agents.tracked._OTEL_AVAILABLE", True):
            await agent.agenerate("Hello")

        init_attrs = mock_tracer.start_as_current_span.call_args[1]["attributes"]

        # Legacy keys present
        assert init_attrs["agent.id"] == "test-agent"
        assert init_attrs["agent.model"] == "claude-sonnet"

        # No gen_ai keys
        genai_keys = [k for k in init_attrs if k.startswith("gen_ai.")]
        assert genai_keys == []

    @pytest.mark.asyncio
    async def test_legacy_mode_span_name_is_legacy(self):
        agent = _make_mock_agent(name="my-agent")
        agent._dual_emit = DualEmitAttributes(mode=EmitMode.LEGACY)

        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_span.__enter__ = MagicMock(return_value=mock_span)
        mock_span.__exit__ = MagicMock(return_value=False)
        mock_tracer.start_as_current_span.return_value = mock_span

        with patch("startd8.agents.tracked._tracer", mock_tracer), \
             patch("startd8.agents.tracked._OTEL_AVAILABLE", True):
            await agent.agenerate("Hello")

        span_name = mock_tracer.start_as_current_span.call_args[0][0]
        assert span_name == "agent.generate:my-agent"


# =========================================================================
# gen_ai.response.finish_reasons
# =========================================================================

class TestFinishReasons:
    @pytest.mark.asyncio
    async def test_finish_reasons_emitted_in_dual_mode(self):
        agent = _make_mock_agent(gen_ai_system="anthropic", model="claude-sonnet")
        agent._dual_emit = DualEmitAttributes(mode=EmitMode.DUAL)

        usage = TokenUsage(
            input=10, output=20, total=30,
            model_name="claude-sonnet",
            finish_reason="end_turn",
        )

        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_span.__enter__ = MagicMock(return_value=mock_span)
        mock_span.__exit__ = MagicMock(return_value=False)
        mock_tracer.start_as_current_span.return_value = mock_span

        # Patch MockAgent.agenerate to return our controlled usage
        from startd8.agents.mock import MockAgent
        original = MockAgent.agenerate

        async def fake_agenerate(self_inner, prompt, **kw):
            return "response", 42, usage

        with patch("startd8.agents.tracked._tracer", mock_tracer), \
             patch("startd8.agents.tracked._OTEL_AVAILABLE", True), \
             patch.object(MockAgent, "agenerate", fake_agenerate):
            await agent.agenerate("Hello")

        # Find the set_attribute call for gen_ai.response.finish_reasons
        set_attr_calls = {
            call.args[0]: call.args[1]
            for call in mock_span.set_attribute.call_args_list
        }
        assert set_attr_calls.get("gen_ai.response.finish_reasons") == ["end_turn"]

    @pytest.mark.asyncio
    async def test_finish_reasons_not_emitted_in_legacy_mode(self):
        agent = _make_mock_agent(gen_ai_system="anthropic")
        agent._dual_emit = DualEmitAttributes(mode=EmitMode.LEGACY)

        usage = TokenUsage(
            input=10, output=20, total=30,
            finish_reason="end_turn",
        )

        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_span.__enter__ = MagicMock(return_value=mock_span)
        mock_span.__exit__ = MagicMock(return_value=False)
        mock_tracer.start_as_current_span.return_value = mock_span

        from startd8.agents.mock import MockAgent

        async def fake_agenerate(self_inner, prompt, **kw):
            return "response", 42, usage

        with patch("startd8.agents.tracked._tracer", mock_tracer), \
             patch("startd8.agents.tracked._OTEL_AVAILABLE", True), \
             patch.object(MockAgent, "agenerate", fake_agenerate):
            await agent.agenerate("Hello")

        set_attr_calls = {
            call.args[0]: call.args[1]
            for call in mock_span.set_attribute.call_args_list
        }
        assert "gen_ai.response.finish_reasons" not in set_attr_calls

    @pytest.mark.asyncio
    async def test_finish_reasons_not_emitted_when_none(self):
        agent = _make_mock_agent(gen_ai_system="anthropic")
        agent._dual_emit = DualEmitAttributes(mode=EmitMode.DUAL)

        usage = TokenUsage(
            input=10, output=20, total=30,
            finish_reason=None,
        )

        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_span.__enter__ = MagicMock(return_value=mock_span)
        mock_span.__exit__ = MagicMock(return_value=False)
        mock_tracer.start_as_current_span.return_value = mock_span

        from startd8.agents.mock import MockAgent

        async def fake_agenerate(self_inner, prompt, **kw):
            return "response", 42, usage

        with patch("startd8.agents.tracked._tracer", mock_tracer), \
             patch("startd8.agents.tracked._OTEL_AVAILABLE", True), \
             patch.object(MockAgent, "agenerate", fake_agenerate):
            await agent.agenerate("Hello")

        set_attr_calls = {
            call.args[0]: call.args[1]
            for call in mock_span.set_attribute.call_args_list
        }
        assert "gen_ai.response.finish_reasons" not in set_attr_calls


# =========================================================================
# Response attributes transform
# =========================================================================

class TestResponseAttributeTransform:
    @pytest.mark.asyncio
    async def test_response_attrs_transformed_in_dual_mode(self):
        agent = _make_mock_agent(gen_ai_system="anthropic")
        agent._dual_emit = DualEmitAttributes(mode=EmitMode.DUAL)

        usage = TokenUsage(
            input=50, output=100, total=150,
            finish_reason="end_turn",
        )

        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_span.__enter__ = MagicMock(return_value=mock_span)
        mock_span.__exit__ = MagicMock(return_value=False)
        mock_tracer.start_as_current_span.return_value = mock_span

        from startd8.agents.mock import MockAgent

        async def fake_agenerate(self_inner, prompt, **kw):
            return "response", 42, usage

        with patch("startd8.agents.tracked._tracer", mock_tracer), \
             patch("startd8.agents.tracked._OTEL_AVAILABLE", True), \
             patch.object(MockAgent, "agenerate", fake_agenerate):
            await agent.agenerate("Hello")

        set_attr_calls = {
            call.args[0]: call.args[1]
            for call in mock_span.set_attribute.call_args_list
        }

        # Legacy response attrs
        assert set_attr_calls["agent.tokens_input"] == 50
        assert set_attr_calls["agent.tokens_output"] == 100

        # OTel response attrs
        assert set_attr_calls["gen_ai.usage.input_tokens"] == 50
        assert set_attr_calls["gen_ai.usage.output_tokens"] == 100

        # Unmapped response attrs pass through
        assert set_attr_calls["agent.response_time_ms"] == 42
        assert set_attr_calls["agent.tokens_total"] == 150
