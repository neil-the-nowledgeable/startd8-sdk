# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0
# See LICENSE.md for complete terms.

"""
Tests for OpenLLMetry integration.

Verifies:
- Discovery and initialization of OpenLLMetry instrumentors
- TrackedAgentMixin attribute split when OpenLLMetry is active vs inactive
- Graceful degradation when OpenLLMetry packages are not installed
"""

import os
import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from startd8.models import TokenUsage
from startd8.genai_compat import DualEmitAttributes, EmitMode, reset_emit_mode_cache


# =========================================================================
# Helpers
# =========================================================================

def _make_mock_agent(gen_ai_system="anthropic", model="test-model", name="test-agent"):
    """Build a minimal TrackedAgentMixin-based object with MockAgent backend."""
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


def _make_span_capturing_agent(
    gen_ai_system="anthropic",
    model="test-model",
    name="test-agent",
    finish_reason="end_turn",
    was_truncated=False,
    input_tokens=50,
    output_tokens=100,
):
    """Build an agent with controlled token usage and return (agent, tracer, span) for inspection."""
    agent = _make_mock_agent(gen_ai_system=gen_ai_system, model=model, name=name)

    usage = TokenUsage(
        input=input_tokens,
        output=output_tokens,
        total=input_tokens + output_tokens,
        model_name=model,
        finish_reason=finish_reason,
        was_truncated=was_truncated,
    )

    mock_tracer = MagicMock()
    mock_span = MagicMock()
    mock_span.__enter__ = MagicMock(return_value=mock_span)
    mock_span.__exit__ = MagicMock(return_value=False)
    mock_tracer.start_as_current_span.return_value = mock_span

    from startd8.agents.mock import MockAgent

    async def fake_agenerate(self_inner, prompt, **kw):
        return "Hello world", 42, usage

    # Patch MockAgent.agenerate for controlled output
    MockAgent.agenerate = fake_agenerate

    return agent, mock_tracer, mock_span


@pytest.fixture(autouse=True)
def _clear_caches():
    reset_emit_mode_cache()
    yield
    reset_emit_mode_cache()


# =========================================================================
# TestOpenLLMetryDiscovery
# =========================================================================

class TestOpenLLMetryDiscovery:
    def test_active_false_when_not_initialized(self):
        from startd8.openllmetry import is_openllmetry_active, uninstrument_openllmetry
        uninstrument_openllmetry()
        assert is_openllmetry_active() is False

    def test_mode_default_auto(self):
        from startd8.openllmetry import get_openllmetry_mode
        with patch.dict(os.environ, {}, clear=True):
            # Remove STARTD8_OPENLLMETRY if set
            os.environ.pop("STARTD8_OPENLLMETRY", None)
            assert get_openllmetry_mode() == "auto"

    def test_mode_disabled_skips(self):
        from startd8.openllmetry import (
            get_openllmetry_mode,
            initialize_openllmetry,
            is_openllmetry_active,
            uninstrument_openllmetry,
        )
        uninstrument_openllmetry()

        with patch.dict(os.environ, {"STARTD8_OPENLLMETRY": "disabled"}):
            assert get_openllmetry_mode() == "disabled"
            result = initialize_openllmetry()
            assert result is False
            assert is_openllmetry_active() is False

    def test_mode_enabled_value(self):
        from startd8.openllmetry import get_openllmetry_mode
        with patch.dict(os.environ, {"STARTD8_OPENLLMETRY": "enabled"}):
            assert get_openllmetry_mode() == "enabled"

    def test_mode_invalid_defaults_to_auto(self):
        from startd8.openllmetry import get_openllmetry_mode
        with patch.dict(os.environ, {"STARTD8_OPENLLMETRY": "garbage"}):
            assert get_openllmetry_mode() == "auto"

    def test_initialize_with_mock_instrumentor(self):
        from startd8.openllmetry import (
            initialize_openllmetry,
            is_openllmetry_active,
            uninstrument_openllmetry,
        )
        uninstrument_openllmetry()

        mock_instrumentor = MagicMock()
        mock_instrumentor_cls = MagicMock(return_value=mock_instrumentor)

        with patch.dict(os.environ, {"STARTD8_OPENLLMETRY": "auto"}), \
             patch(
                 "startd8.openllmetry.AnthropicInstrumentor",
                 mock_instrumentor_cls,
                 create=True,
             ):
            # Patch the import inside initialize_openllmetry
            import startd8.openllmetry as ollm_mod

            original_code = ollm_mod.initialize_openllmetry.__code__

            # Use a simpler approach: mock the import mechanism
            mock_anthropic_mod = MagicMock()
            mock_anthropic_mod.AnthropicInstrumentor = mock_instrumentor_cls

            with patch.dict(
                "sys.modules",
                {"opentelemetry.instrumentation.anthropic": mock_anthropic_mod},
            ):
                result = initialize_openllmetry()

            assert result is True
            assert is_openllmetry_active() is True
            mock_instrumentor.instrument.assert_called_once()

            # Verify enrich_token_usage was passed
            call_kwargs = mock_instrumentor.instrument.call_args[1]
            assert call_kwargs["enrich_token_usage"] is True

        uninstrument_openllmetry()

    def test_uninstrument_resets_state(self):
        from startd8.openllmetry import (
            is_openllmetry_active,
            uninstrument_openllmetry,
        )
        import startd8.openllmetry as ollm_mod

        # Manually set active state
        ollm_mod._active = True
        mock_inst = MagicMock()
        ollm_mod._instrumentors = [mock_inst]

        assert is_openllmetry_active() is True

        uninstrument_openllmetry()

        assert is_openllmetry_active() is False
        mock_inst.uninstrument.assert_called_once()


# =========================================================================
# TestTrackedAgentAttributeSplit
# =========================================================================

class TestTrackedAgentAttributeSplit:

    @pytest.mark.asyncio
    async def test_span_kind_internal_when_active(self):
        """When OpenLLMetry is active, parent span should be INTERNAL."""
        agent, mock_tracer, mock_span = _make_span_capturing_agent()

        with patch("startd8.agents.tracked._tracer", mock_tracer), \
             patch("startd8.agents.tracked._OTEL_AVAILABLE", True), \
             patch("startd8.agents.tracked._is_openllmetry_active", return_value=True):
            await agent.agenerate("Hello")

        from opentelemetry.trace import SpanKind
        call_kwargs = mock_tracer.start_as_current_span.call_args[1]
        assert call_kwargs["kind"] == SpanKind.INTERNAL

    @pytest.mark.asyncio
    async def test_span_kind_client_when_inactive(self):
        """When OpenLLMetry is inactive, span should be CLIENT (backward compat)."""
        agent, mock_tracer, mock_span = _make_span_capturing_agent()

        with patch("startd8.agents.tracked._tracer", mock_tracer), \
             patch("startd8.agents.tracked._OTEL_AVAILABLE", True), \
             patch("startd8.agents.tracked._is_openllmetry_active", return_value=False):
            await agent.agenerate("Hello")

        from opentelemetry.trace import SpanKind
        call_kwargs = mock_tracer.start_as_current_span.call_args[1]
        assert call_kwargs["kind"] == SpanKind.CLIENT

    @pytest.mark.asyncio
    async def test_duplicate_attrs_skipped_when_active(self):
        """When OpenLLMetry active, parent span must NOT have gen_ai.* or token attrs."""
        agent, mock_tracer, mock_span = _make_span_capturing_agent()
        agent._dual_emit = DualEmitAttributes(mode=EmitMode.DUAL)

        with patch("startd8.agents.tracked._tracer", mock_tracer), \
             patch("startd8.agents.tracked._OTEL_AVAILABLE", True), \
             patch("startd8.agents.tracked._is_openllmetry_active", return_value=True):
            await agent.agenerate("Hello")

        # Check initial attributes
        init_attrs = mock_tracer.start_as_current_span.call_args[1]["attributes"]

        # These should NOT be on the parent span (OpenLLMetry child handles them)
        assert "gen_ai.system" not in init_attrs
        assert "gen_ai.operation.name" not in init_attrs
        assert "agent.model" not in init_attrs
        assert "gen_ai.request.model" not in init_attrs

        # Check set_attribute calls for response attrs
        set_attr_calls = {
            call.args[0]: call.args[1]
            for call in mock_span.set_attribute.call_args_list
        }

        # Token usage should NOT be on parent span
        assert "agent.tokens_input" not in set_attr_calls
        assert "agent.tokens_output" not in set_attr_calls
        assert "agent.tokens_total" not in set_attr_calls
        assert "gen_ai.usage.input_tokens" not in set_attr_calls
        assert "gen_ai.usage.output_tokens" not in set_attr_calls
        assert "gen_ai.response.finish_reasons" not in set_attr_calls

    @pytest.mark.asyncio
    async def test_contextcore_attrs_always_present_when_active(self):
        """When OpenLLMetry active, ContextCore-specific attrs MUST still be present."""
        agent, mock_tracer, mock_span = _make_span_capturing_agent(
            name="my-claude",
        )
        agent._dual_emit = DualEmitAttributes(mode=EmitMode.DUAL)

        with patch("startd8.agents.tracked._tracer", mock_tracer), \
             patch("startd8.agents.tracked._OTEL_AVAILABLE", True), \
             patch("startd8.agents.tracked._is_openllmetry_active", return_value=True):
            await agent.agenerate("Hello", task_id="TASK-1")

        # Check initial attributes
        init_attrs = mock_tracer.start_as_current_span.call_args[1]["attributes"]

        # These MUST be present (ContextCore concerns)
        assert init_attrs["agent.id"] == "my-claude"
        assert init_attrs["gen_ai.agent.id"] == "my-claude"  # dual-emit
        assert init_attrs["agent.prompt_length"] == 5
        assert init_attrs["task.id"] == "TASK-1"
        assert init_attrs["project.id"] == "test-proj"

        # Check response attributes
        set_attr_calls = {
            call.args[0]: call.args[1]
            for call in mock_span.set_attribute.call_args_list
        }

        assert set_attr_calls["agent.response_length"] == 11  # len("Hello world")
        assert set_attr_calls["agent.response_time_ms"] == 42
        assert set_attr_calls["agent.truncated"] is False

    @pytest.mark.asyncio
    async def test_all_attrs_when_inactive(self):
        """Without OpenLLMetry, all attributes should be present (full backward compat)."""
        agent, mock_tracer, mock_span = _make_span_capturing_agent()
        agent._dual_emit = DualEmitAttributes(mode=EmitMode.DUAL)

        with patch("startd8.agents.tracked._tracer", mock_tracer), \
             patch("startd8.agents.tracked._OTEL_AVAILABLE", True), \
             patch("startd8.agents.tracked._is_openllmetry_active", return_value=False):
            await agent.agenerate("Hello")

        # Check initial attributes - all should be present
        init_attrs = mock_tracer.start_as_current_span.call_args[1]["attributes"]

        assert "agent.id" in init_attrs
        assert "agent.model" in init_attrs
        assert "gen_ai.agent.id" in init_attrs
        assert "gen_ai.request.model" in init_attrs
        assert "gen_ai.system" in init_attrs
        assert "gen_ai.operation.name" in init_attrs
        assert "agent.prompt_length" in init_attrs

        # Check response attributes
        set_attr_calls = {
            call.args[0]: call.args[1]
            for call in mock_span.set_attribute.call_args_list
        }

        assert "agent.tokens_input" in set_attr_calls
        assert "agent.tokens_output" in set_attr_calls
        assert "agent.tokens_total" in set_attr_calls
        assert "gen_ai.usage.input_tokens" in set_attr_calls
        assert "gen_ai.usage.output_tokens" in set_attr_calls
        assert "gen_ai.response.finish_reasons" in set_attr_calls

    @pytest.mark.asyncio
    async def test_truncation_event_always_fires(self):
        """Truncation span event fires regardless of OpenLLMetry mode."""
        agent, mock_tracer, mock_span = _make_span_capturing_agent(
            was_truncated=True,
            finish_reason="max_tokens",
        )

        with patch("startd8.agents.tracked._tracer", mock_tracer), \
             patch("startd8.agents.tracked._OTEL_AVAILABLE", True), \
             patch("startd8.agents.tracked._is_openllmetry_active", return_value=True):
            await agent.agenerate("Hello")

        # Truncation event should always fire
        mock_span.add_event.assert_called_once_with(
            "truncation_detected",
            attributes={
                "finish_reason": "max_tokens",
                "output_tokens": 100,
            },
        )

    @pytest.mark.asyncio
    async def test_truncation_attr_present_when_active(self):
        """agent.truncated attribute is set even when OpenLLMetry active."""
        agent, mock_tracer, mock_span = _make_span_capturing_agent(
            was_truncated=True,
            finish_reason="max_tokens",
        )
        agent._dual_emit = DualEmitAttributes(mode=EmitMode.DUAL)

        with patch("startd8.agents.tracked._tracer", mock_tracer), \
             patch("startd8.agents.tracked._OTEL_AVAILABLE", True), \
             patch("startd8.agents.tracked._is_openllmetry_active", return_value=True):
            await agent.agenerate("Hello")

        set_attr_calls = {
            call.args[0]: call.args[1]
            for call in mock_span.set_attribute.call_args_list
        }
        assert set_attr_calls["agent.truncated"] is True


# =========================================================================
# TestGracefulDegradation
# =========================================================================

class TestGracefulDegradation:

    def test_no_error_without_openllmetry_package(self):
        """_is_openllmetry_active() returns False when openllmetry module not importable."""
        from startd8.agents.tracked import _is_openllmetry_active

        with patch(
            "startd8.agents.tracked.is_openllmetry_active",
            side_effect=ImportError("no module"),
            create=True,
        ):
            # The function catches ImportError internally
            result = _is_openllmetry_active()

        # Should gracefully return False, never raise
        assert result is False

    def test_no_error_on_instrumentor_failure(self):
        """initialize_openllmetry() handles instrumentor exceptions in auto mode."""
        from startd8.openllmetry import (
            initialize_openllmetry,
            is_openllmetry_active,
            uninstrument_openllmetry,
        )
        uninstrument_openllmetry()

        # Create a mock instrumentor that raises on .instrument()
        mock_cls = MagicMock()
        mock_cls.return_value.instrument.side_effect = RuntimeError("boom")
        mock_mod = MagicMock()
        mock_mod.AnthropicInstrumentor = mock_cls

        with patch.dict(os.environ, {"STARTD8_OPENLLMETRY": "auto"}), \
             patch.dict(
                 "sys.modules",
                 {"opentelemetry.instrumentation.anthropic": mock_mod},
             ):
            # Should not raise in auto mode
            result = initialize_openllmetry()

        assert result is False
        assert is_openllmetry_active() is False

    def test_enabled_mode_raises_on_instrumentor_failure(self):
        """In enabled mode, instrumentor failures should propagate."""
        from startd8.openllmetry import (
            initialize_openllmetry,
            uninstrument_openllmetry,
        )
        uninstrument_openllmetry()

        mock_cls = MagicMock()
        mock_cls.return_value.instrument.side_effect = RuntimeError("boom")
        mock_mod = MagicMock()
        mock_mod.AnthropicInstrumentor = mock_cls

        with patch.dict(os.environ, {"STARTD8_OPENLLMETRY": "enabled"}), \
             patch.dict(
                 "sys.modules",
                 {"opentelemetry.instrumentation.anthropic": mock_mod},
             ):
            with pytest.raises(RuntimeError, match="boom"):
                initialize_openllmetry()

    @pytest.mark.asyncio
    async def test_agenerate_works_without_openllmetry_module(self):
        """agenerate() works normally when openllmetry module doesn't exist."""
        agent, mock_tracer, mock_span = _make_span_capturing_agent()

        # _is_openllmetry_active returns False (the real function handles ImportError)
        with patch("startd8.agents.tracked._tracer", mock_tracer), \
             patch("startd8.agents.tracked._OTEL_AVAILABLE", True), \
             patch("startd8.agents.tracked._is_openllmetry_active", return_value=False):
            response, time_ms, usage = await agent.agenerate("Hello")

        assert response == "Hello world"
        assert time_ms == 42
        # Span was created successfully
        mock_tracer.start_as_current_span.assert_called_once()


# =========================================================================
# TestConfigureOtelWithOpenLLMetry
# =========================================================================

class TestConfigureOtelWithOpenLLMetry:

    def test_convenience_function_exists(self):
        from startd8.otel import configure_otel_with_openllmetry
        assert callable(configure_otel_with_openllmetry)

    def test_returns_openllmetry_active_key(self):
        from startd8.otel import configure_otel_with_openllmetry, OTelConfig

        config = OTelConfig(enable_traces=False, enable_metrics=False)

        with patch.dict(os.environ, {"STARTD8_OPENLLMETRY": "disabled"}):
            result = configure_otel_with_openllmetry(config)

        assert "openllmetry_active" in result
        assert result["openllmetry_active"] is False

    def test_skips_openllmetry_when_disabled_param(self):
        from startd8.otel import configure_otel_with_openllmetry, OTelConfig

        config = OTelConfig(enable_traces=False, enable_metrics=False)

        result = configure_otel_with_openllmetry(config, enable_openllmetry=False)

        assert result["openllmetry_active"] is False
