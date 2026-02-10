"""
Tests for startd8.genai_compat — OTel GenAI dual-emit attribute handling.

Covers:
- EmitMode resolution (env var precedence, caching, invalid values)
- DualEmitAttributes.transform() in all 3 modes
- Unmapped attribute passthrough
- Input dict non-mutation
"""

import os
import pytest
from unittest.mock import patch

from startd8.genai_compat import (
    ATTRIBUTE_MAPPINGS,
    DualEmitAttributes,
    EmitMode,
    get_emit_mode,
    reset_emit_mode_cache,
)


# =========================================================================
# Fixtures
# =========================================================================

@pytest.fixture(autouse=True)
def _clear_cache():
    """Reset the emit mode cache before and after every test."""
    reset_emit_mode_cache()
    yield
    reset_emit_mode_cache()


SAMPLE_ATTRS = {
    "agent.id": "claude-1",
    "agent.model": "claude-sonnet-4-20250514",
    "agent.tokens_input": 100,
    "agent.tokens_output": 200,
    "agent.prompt_length": 450,
    "task.id": "SDK-101",
    "project.id": "myproj",
}


# =========================================================================
# EmitMode resolution
# =========================================================================

class TestGetEmitMode:
    def test_default_is_dual(self):
        with patch.dict(os.environ, {}, clear=True):
            assert get_emit_mode() == EmitMode.DUAL

    def test_startd8_emit_mode_legacy(self):
        with patch.dict(os.environ, {"STARTD8_EMIT_MODE": "legacy"}, clear=True):
            assert get_emit_mode() == EmitMode.LEGACY

    def test_startd8_emit_mode_otel(self):
        with patch.dict(os.environ, {"STARTD8_EMIT_MODE": "otel"}, clear=True):
            assert get_emit_mode() == EmitMode.OTEL

    def test_startd8_emit_mode_dual(self):
        with patch.dict(os.environ, {"STARTD8_EMIT_MODE": "dual"}, clear=True):
            assert get_emit_mode() == EmitMode.DUAL

    def test_startd8_emit_mode_case_insensitive(self):
        with patch.dict(os.environ, {"STARTD8_EMIT_MODE": "OTEL"}, clear=True):
            assert get_emit_mode() == EmitMode.OTEL

    def test_startd8_overrides_otel_opt_in(self):
        env = {
            "STARTD8_EMIT_MODE": "legacy",
            "OTEL_SEMCONV_STABILITY_OPT_IN": "gen_ai",
        }
        with patch.dict(os.environ, env, clear=True):
            assert get_emit_mode() == EmitMode.LEGACY

    def test_otel_opt_in_gen_ai(self):
        with patch.dict(os.environ, {"OTEL_SEMCONV_STABILITY_OPT_IN": "gen_ai"}, clear=True):
            assert get_emit_mode() == EmitMode.OTEL

    def test_otel_opt_in_gen_ai_dup(self):
        with patch.dict(os.environ, {"OTEL_SEMCONV_STABILITY_OPT_IN": "gen_ai/dup"}, clear=True):
            assert get_emit_mode() == EmitMode.DUAL

    def test_invalid_startd8_value_falls_through(self):
        env = {
            "STARTD8_EMIT_MODE": "bogus",
            "OTEL_SEMCONV_STABILITY_OPT_IN": "gen_ai",
        }
        with patch.dict(os.environ, env, clear=True):
            assert get_emit_mode() == EmitMode.OTEL

    def test_invalid_both_falls_to_default(self):
        env = {
            "STARTD8_EMIT_MODE": "bogus",
            "OTEL_SEMCONV_STABILITY_OPT_IN": "something_else",
        }
        with patch.dict(os.environ, env, clear=True):
            assert get_emit_mode() == EmitMode.DUAL

    def test_caching(self):
        with patch.dict(os.environ, {"STARTD8_EMIT_MODE": "legacy"}, clear=True):
            mode1 = get_emit_mode()

        # Even with env cleared, cache should return the same value
        with patch.dict(os.environ, {}, clear=True):
            mode2 = get_emit_mode()

        assert mode1 is mode2 is EmitMode.LEGACY

    def test_reset_cache_allows_recompute(self):
        with patch.dict(os.environ, {"STARTD8_EMIT_MODE": "legacy"}, clear=True):
            assert get_emit_mode() == EmitMode.LEGACY

        reset_emit_mode_cache()

        with patch.dict(os.environ, {"STARTD8_EMIT_MODE": "otel"}, clear=True):
            assert get_emit_mode() == EmitMode.OTEL


# =========================================================================
# DualEmitAttributes — LEGACY mode
# =========================================================================

class TestLegacyMode:
    def test_returns_only_legacy_attrs(self):
        de = DualEmitAttributes(mode=EmitMode.LEGACY)
        result = de.transform(SAMPLE_ATTRS)

        assert result == SAMPLE_ATTRS
        for otel_key in ATTRIBUTE_MAPPINGS.values():
            assert otel_key not in result

    def test_empty_dict(self):
        de = DualEmitAttributes(mode=EmitMode.LEGACY)
        assert de.transform({}) == {}


# =========================================================================
# DualEmitAttributes — DUAL mode
# =========================================================================

class TestDualMode:
    def test_has_both_namespaces(self):
        de = DualEmitAttributes(mode=EmitMode.DUAL)
        result = de.transform(SAMPLE_ATTRS)

        # Legacy keys still present
        assert result["agent.id"] == "claude-1"
        assert result["agent.model"] == "claude-sonnet-4-20250514"
        assert result["agent.tokens_input"] == 100
        assert result["agent.tokens_output"] == 200

        # OTel keys added
        assert result["gen_ai.agent.id"] == "claude-1"
        assert result["gen_ai.request.model"] == "claude-sonnet-4-20250514"
        assert result["gen_ai.usage.input_tokens"] == 100
        assert result["gen_ai.usage.output_tokens"] == 200

    def test_unmapped_attrs_pass_through(self):
        de = DualEmitAttributes(mode=EmitMode.DUAL)
        result = de.transform(SAMPLE_ATTRS)

        assert result["agent.prompt_length"] == 450
        assert result["task.id"] == "SDK-101"
        assert result["project.id"] == "myproj"

    def test_empty_dict(self):
        de = DualEmitAttributes(mode=EmitMode.DUAL)
        assert de.transform({}) == {}


# =========================================================================
# DualEmitAttributes — OTEL mode
# =========================================================================

class TestOtelMode:
    def test_mapped_keys_replaced(self):
        de = DualEmitAttributes(mode=EmitMode.OTEL)
        result = de.transform(SAMPLE_ATTRS)

        # Legacy mapped keys removed
        assert "agent.id" not in result
        assert "agent.model" not in result
        assert "agent.tokens_input" not in result
        assert "agent.tokens_output" not in result

        # OTel keys present
        assert result["gen_ai.agent.id"] == "claude-1"
        assert result["gen_ai.request.model"] == "claude-sonnet-4-20250514"
        assert result["gen_ai.usage.input_tokens"] == 100
        assert result["gen_ai.usage.output_tokens"] == 200

    def test_unmapped_attrs_pass_through(self):
        de = DualEmitAttributes(mode=EmitMode.OTEL)
        result = de.transform(SAMPLE_ATTRS)

        assert result["agent.prompt_length"] == 450
        assert result["task.id"] == "SDK-101"
        assert result["project.id"] == "myproj"

    def test_empty_dict(self):
        de = DualEmitAttributes(mode=EmitMode.OTEL)
        assert de.transform({}) == {}


# =========================================================================
# Input dict non-mutation
# =========================================================================

class TestNonMutation:
    @pytest.mark.parametrize("mode", list(EmitMode))
    def test_input_dict_not_mutated(self, mode):
        original = dict(SAMPLE_ATTRS)
        frozen = dict(SAMPLE_ATTRS)

        de = DualEmitAttributes(mode=mode)
        de.transform(original)

        assert original == frozen, f"Input dict was mutated in {mode.value} mode"


# =========================================================================
# DualEmitAttributes uses get_emit_mode() by default
# =========================================================================

class TestModeFromEnv:
    def test_uses_env_when_no_mode_given(self):
        with patch.dict(os.environ, {"STARTD8_EMIT_MODE": "otel"}, clear=True):
            de = DualEmitAttributes()
            result = de.transform({"agent.id": "x"})
            assert "agent.id" not in result
            assert result["gen_ai.agent.id"] == "x"

    def test_explicit_mode_overrides_env(self):
        with patch.dict(os.environ, {"STARTD8_EMIT_MODE": "otel"}, clear=True):
            de = DualEmitAttributes(mode=EmitMode.LEGACY)
            result = de.transform({"agent.id": "x"})
            assert result["agent.id"] == "x"
            assert "gen_ai.agent.id" not in result
