# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
# See LICENSE for complete terms.

"""
OTel GenAI semantic convention compatibility for StartD8.

Provides dual-emit support for agent.* (legacy) and gen_ai.* (OTel standard)
attributes. Self-contained—no contextcore dependency.

Controlled by env vars:
  STARTD8_EMIT_MODE          - "legacy", "dual", "otel" (highest priority)
  OTEL_SEMCONV_STABILITY_OPT_IN - "gen_ai" or "gen_ai/dup" (fallback)
  Default: DUAL

Attribute mapping (startd8-specific):
  agent.id           -> gen_ai.agent.id
  agent.model        -> gen_ai.request.model
  agent.tokens_input -> gen_ai.usage.input_tokens
  agent.tokens_output -> gen_ai.usage.output_tokens

Unmapped attributes (agent.prompt_length, task.id, etc.) pass through unchanged.
"""

import os
from enum import Enum
from typing import Dict

_emit_mode_cache: "EmitMode | None" = None

# Mapping from legacy agent.* keys to gen_ai.* equivalents.
ATTRIBUTE_MAPPINGS: Dict[str, str] = {
    "agent.id": "gen_ai.agent.id",
    "agent.model": "gen_ai.request.model",
    "agent.tokens_input": "gen_ai.usage.input_tokens",
    "agent.tokens_output": "gen_ai.usage.output_tokens",
}


class EmitMode(Enum):
    """Controls which attribute namespaces are emitted."""
    LEGACY = "legacy"
    DUAL = "dual"
    OTEL = "otel"


def get_emit_mode() -> EmitMode:
    """
    Resolve the emit mode from environment variables.

    Precedence:
      1. STARTD8_EMIT_MODE (explicit per-SDK override)
      2. OTEL_SEMCONV_STABILITY_OPT_IN (community standard)
      3. Default: DUAL
    """
    global _emit_mode_cache
    if _emit_mode_cache is not None:
        return _emit_mode_cache

    # 1. STARTD8_EMIT_MODE takes precedence
    raw = os.environ.get("STARTD8_EMIT_MODE", "").strip().lower()
    if raw:
        try:
            _emit_mode_cache = EmitMode(raw)
            return _emit_mode_cache
        except ValueError:
            pass  # fall through to next check

    # 2. OTEL_SEMCONV_STABILITY_OPT_IN
    otel_opt_in = os.environ.get("OTEL_SEMCONV_STABILITY_OPT_IN", "").strip().lower()
    if otel_opt_in == "gen_ai":
        _emit_mode_cache = EmitMode.OTEL
        return _emit_mode_cache
    if otel_opt_in == "gen_ai/dup":
        _emit_mode_cache = EmitMode.DUAL
        return _emit_mode_cache

    # 3. Default
    _emit_mode_cache = EmitMode.DUAL
    return _emit_mode_cache


def reset_emit_mode_cache() -> None:
    """Clear the cached emit mode. For testing only."""
    global _emit_mode_cache
    _emit_mode_cache = None


class DualEmitAttributes:
    """
    Transforms a dict of span attributes according to the active EmitMode.

    - LEGACY: returns only agent.* keys (drops any gen_ai.* that would be added)
    - DUAL:   returns agent.* keys AND their gen_ai.* equivalents
    - OTEL:   returns gen_ai.* equivalents, removes mapped agent.* keys
    """

    def __init__(self, mode: EmitMode | None = None):
        self._mode = mode

    @property
    def mode(self) -> EmitMode:
        if self._mode is not None:
            return self._mode
        return get_emit_mode()

    def transform(self, attrs: Dict[str, object]) -> Dict[str, object]:
        """
        Transform attributes according to the emit mode.

        The input dict is NOT mutated; a new dict is returned.
        """
        mode = self.mode

        if mode == EmitMode.LEGACY:
            return dict(attrs)

        result = dict(attrs)

        if mode == EmitMode.DUAL:
            for legacy_key, otel_key in ATTRIBUTE_MAPPINGS.items():
                if legacy_key in result:
                    result[otel_key] = result[legacy_key]
            return result

        # OTEL mode: replace mapped keys, keep unmapped
        if mode == EmitMode.OTEL:
            for legacy_key, otel_key in ATTRIBUTE_MAPPINGS.items():
                if legacy_key in result:
                    result[otel_key] = result.pop(legacy_key)
            return result

        return result
