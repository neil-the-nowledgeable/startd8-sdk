# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0
# See LICENSE.md for complete terms.

"""
OpenLLMetry integration for automatic LLM SDK instrumentation.

This module discovers and initializes OpenLLMetry instrumentors for
supported LLM providers (Anthropic, OpenAI). When active, OpenLLMetry
handles low-level gen_ai.* attribute emission while TrackedAgentMixin
focuses on ContextCore-specific concerns (task linking, project context,
insight emission, truncation detection).

Configuration via environment variable:
    STARTD8_OPENLLMETRY=auto     (default) Enable if packages installed
    STARTD8_OPENLLMETRY=enabled  Force enable (error if packages missing)
    STARTD8_OPENLLMETRY=disabled Skip initialization entirely

Resulting trace hierarchy when active:
    [INTERNAL] agent.generate:my-claude       <- TrackedAgentMixin
      +-- [CLIENT] anthropic.chat             <- OpenLLMetry
"""

import logging
import os
from typing import Any, List, Optional

logger = logging.getLogger(__name__)

# Module-level state
_active: bool = False
_instrumentors: List[Any] = []


def get_openllmetry_mode() -> str:
    """
    Read the OpenLLMetry mode from environment.

    Returns:
        One of "auto", "enabled", or "disabled".
    """
    mode = os.environ.get("STARTD8_OPENLLMETRY", "auto").lower().strip()
    if mode not in ("auto", "enabled", "disabled"):
        logger.warning(
            "Invalid STARTD8_OPENLLMETRY value '%s', defaulting to 'auto'", mode
        )
        return "auto"
    return mode


def initialize_openllmetry(
    tracer_provider: Optional[Any] = None,
    meter_provider: Optional[Any] = None,
) -> bool:
    """
    Discover installed OpenLLMetry instrumentors and activate them.

    Auto-discovers which LLM provider SDKs are installed and instruments
    only those. Passes ``use_legacy_attributes=False`` so OpenLLMetry
    emits only ``gen_ai.*`` attributes (TrackedAgentMixin handles
    ``agent.*`` via DualEmitAttributes).

    Args:
        tracer_provider: Optional TracerProvider to pass to instrumentors.
            If None, instrumentors use the global provider set by
            ``configure_tracing()`` in otel.py.
        meter_provider: Optional MeterProvider to pass to instrumentors.
            If None, instrumentors use the global provider.

    Returns:
        True if at least one instrumentor was activated.
    """
    global _active, _instrumentors

    mode = get_openllmetry_mode()
    if mode == "disabled":
        logger.debug("OpenLLMetry disabled via STARTD8_OPENLLMETRY=disabled")
        return False

    activated = []

    # --- Anthropic ---
    try:
        from opentelemetry.instrumentation.anthropic import AnthropicInstrumentor

        instrumentor = AnthropicInstrumentor()
        kwargs = {
            "enrich_token_usage": True,
        }
        if tracer_provider is not None:
            kwargs["tracer_provider"] = tracer_provider
        if meter_provider is not None:
            kwargs["meter_provider"] = meter_provider

        instrumentor.instrument(**kwargs)
        activated.append(instrumentor)
        logger.info("OpenLLMetry: Anthropic instrumentor activated")
    except ImportError:
        logger.debug("OpenLLMetry: anthropic instrumentor not installed, skipping")
    except Exception as exc:
        if mode == "enabled":
            raise
        logger.warning("OpenLLMetry: Anthropic instrumentor failed: %s", exc)

    # --- OpenAI ---
    try:
        from opentelemetry.instrumentation.openai import OpenAIInstrumentor

        instrumentor = OpenAIInstrumentor()
        kwargs = {
            "enrich_token_usage": True,
        }
        if tracer_provider is not None:
            kwargs["tracer_provider"] = tracer_provider
        if meter_provider is not None:
            kwargs["meter_provider"] = meter_provider

        instrumentor.instrument(**kwargs)
        activated.append(instrumentor)
        logger.info("OpenLLMetry: OpenAI instrumentor activated")
    except ImportError:
        logger.debug("OpenLLMetry: openai instrumentor not installed, skipping")
    except Exception as exc:
        if mode == "enabled":
            raise
        logger.warning("OpenLLMetry: OpenAI instrumentor failed: %s", exc)

    if activated:
        _active = True
        _instrumentors = activated
        logger.info(
            "OpenLLMetry initialized with %d instrumentor(s)", len(activated)
        )
        return True

    if mode == "enabled":
        raise RuntimeError(
            "STARTD8_OPENLLMETRY=enabled but no instrumentor packages found. "
            "Install with: pip install startd8[openllmetry]"
        )

    logger.debug("OpenLLMetry: no instrumentors activated (auto mode)")
    return False


def is_openllmetry_active() -> bool:
    """Return True if OpenLLMetry instrumentors are active."""
    return _active


def uninstrument_openllmetry() -> None:
    """
    Uninstrument all active OpenLLMetry instrumentors.

    Resets module state. Primarily used in tests.
    """
    global _active, _instrumentors

    for instrumentor in _instrumentors:
        try:
            instrumentor.uninstrument()
        except Exception as exc:
            logger.debug("OpenLLMetry: uninstrument failed: %s", exc)

    _active = False
    _instrumentors = []
