"""Tests for Ollama-whole-first strategy on MODERATE elements.

Validates that MODERATE elements try single-shot Ollama generation before
decomposition, with signal-based eligibility gating and config toggle.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from startd8.forward_manifest import (
    ForwardElementSpec,
    ForwardFileSpec,
    ForwardImportSpec,
    ForwardManifest,
    InterfaceContract,
)
from startd8.micro_prime.engine import MicroPrimeEngine
from startd8.micro_prime.models import (
    EscalationReason,
    MicroPrimeConfig,
    TierClassification,
)
from startd8.utils.code_manifest import ElementKind, Param, Signature


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def moderate_element() -> ForwardElementSpec:
    """A function element that classifies as MODERATE (class definition)."""
    return ForwardElementSpec(
        kind=ElementKind.CLASS,
        name="DataProcessor",
        signature=Signature(params=[]),
        docstring_hint="Processes incoming data records.",
    )


@pytest.fixture()
def orchestrator_element() -> ForwardElementSpec:
    """A function element with orchestrator signal (should skip Ollama-whole)."""
    return ForwardElementSpec(
        kind=ElementKind.FUNCTION,
        name="run_server",
        signature=Signature(params=[], return_annotation="None"),
    )


@pytest.fixture()
def simple_moderate_element() -> ForwardElementSpec:
    """A MODERATE function without skip signals (eligible for Ollama-whole)."""
    return ForwardElementSpec(
        kind=ElementKind.FUNCTION,
        name="process_batch",
        signature=Signature(
            params=[
                Param(name="items", annotation="list[str]"),
                Param(name="config", annotation="dict"),
                Param(name="output_dir", annotation="Path"),
                Param(name="dry_run", annotation="bool"),
                Param(name="verbose", annotation="bool"),
            ],
            return_annotation="list[str]",
        ),
        docstring_hint="Process a batch of items with the given configuration.",
    )


@pytest.fixture()
def sample_file_spec() -> ForwardFileSpec:
    return ForwardFileSpec(
        file="src/pkg/processor.py",
        imports=[
            ForwardImportSpec(kind="from", module="pathlib", names=["Path"]),
        ],
        elements=[],
    )


@pytest.fixture()
def sample_skeleton() -> str:
    return (
        "# [STARTD8-SKELETON]\n"
        "from pathlib import Path\n\n"
        "class DataProcessor:\n"
        "    pass\n"
    )


# ---------------------------------------------------------------------------
# Test: Ollama-whole success for MODERATE
# ---------------------------------------------------------------------------


class TestModerateOllamaWholeSuccess:
    """MODERATE elements resolved by Ollama-whole skip decomposition."""

    @patch("startd8.micro_prime.engine.MicroPrimeEngine._generate_ollama")
    def test_ollama_whole_succeeds(
        self, mock_generate, simple_moderate_element, sample_file_spec, sample_skeleton,
    ):
        """When Ollama produces valid code, MODERATE element succeeds without decomposition."""
        mock_generate.return_value = (
            "def process_batch(items, config, output_dir, dry_run, verbose):\n"
            "    results = []\n"
            "    for item in items:\n"
            "        results.append(item.upper())\n"
            "    return results",
            100,
            50,
            "stop",
        )
        config = MicroPrimeConfig(
            moderate_ollama_whole_enabled=True,
            semantic_verification_enabled=False,
        )
        engine = MicroPrimeEngine(config=config)
        result = engine.process_element(
            simple_moderate_element, sample_file_spec, sample_skeleton,
        )
        assert result.success is True
        assert result.tier == TierClassification.MODERATE
        assert result.decomposition_metadata is not None
        assert result.decomposition_metadata.get("strategy") == "ollama_whole"

    @patch("startd8.micro_prime.engine.MicroPrimeEngine._generate_ollama")
    def test_ollama_whole_stamps_moderate_tier(
        self, mock_generate, simple_moderate_element, sample_file_spec, sample_skeleton,
    ):
        """Successful Ollama-whole re-stamps tier as MODERATE (not SIMPLE)."""
        mock_generate.return_value = (
            "def process_batch(items, config, output_dir, dry_run, verbose):\n"
            "    return [i.upper() for i in items]",
            80, 30,
            "stop",
        )
        config = MicroPrimeConfig(
            moderate_ollama_whole_enabled=True,
            semantic_verification_enabled=False,
        )
        engine = MicroPrimeEngine(config=config)
        result = engine.process_element(
            simple_moderate_element, sample_file_spec, sample_skeleton,
        )
        assert result.tier == TierClassification.MODERATE


# ---------------------------------------------------------------------------
# Test: Ollama-whole failure falls through to decomposition/escalation
# ---------------------------------------------------------------------------


class TestModerateOllamaWholeFallthrough:
    """When Ollama-whole fails, decomposition is still attempted."""

    @patch("startd8.micro_prime.engine.MicroPrimeEngine._generate_ollama")
    def test_ollama_whole_failure_falls_through(
        self, mock_generate, simple_moderate_element, sample_file_spec, sample_skeleton,
    ):
        """Empty Ollama response falls through to decomposition (then escalation)."""
        mock_generate.return_value = ("", 50, 0, None)
        config = MicroPrimeConfig(
            moderate_ollama_whole_enabled=True,
            semantic_verification_enabled=False,
        )
        engine = MicroPrimeEngine(config=config)
        result = engine.process_element(
            simple_moderate_element, sample_file_spec, sample_skeleton,
        )
        # Should fail (no manifest for decomposition in process_element path)
        assert result.success is False
        assert result.escalation is not None

    @patch("startd8.micro_prime.engine.MicroPrimeEngine._generate_ollama")
    def test_ollama_connection_error_falls_through(
        self, mock_generate, simple_moderate_element, sample_file_spec, sample_skeleton,
    ):
        """Ollama connection error falls through to decomposition."""
        mock_generate.side_effect = ConnectionError("Ollama offline")
        config = MicroPrimeConfig(
            moderate_ollama_whole_enabled=True,
            semantic_verification_enabled=False,
        )
        engine = MicroPrimeEngine(config=config)
        result = engine.process_element(
            simple_moderate_element, sample_file_spec, sample_skeleton,
        )
        assert result.success is False


# ---------------------------------------------------------------------------
# Test: Signal-based eligibility gating
# ---------------------------------------------------------------------------


class TestOllamaWholeEligibility:
    """Elements with skip signals bypass Ollama-whole."""

    def test_orchestrator_skips_ollama_whole(
        self, orchestrator_element, sample_file_spec, sample_skeleton,
    ):
        """Orchestrator elements skip Ollama-whole due to signal skip list."""
        config = MicroPrimeConfig(moderate_ollama_whole_enabled=True)
        engine = MicroPrimeEngine(config=config)
        result = engine.process_element(
            orchestrator_element, sample_file_spec, sample_skeleton,
        )
        # Should escalate without attempting Ollama (no _generate_ollama mock needed)
        assert result.success is False
        assert result.tier == TierClassification.MODERATE

    def test_is_ollama_whole_eligible_no_signals(self):
        """No classification signals → eligible (optimistic)."""
        engine = MicroPrimeEngine()
        assert engine._is_ollama_whole_eligible(None) is True

    def test_is_ollama_whole_eligible_no_overlap(self):
        """Signals present but no overlap with skip list → eligible."""
        engine = MicroPrimeEngine()
        assert engine._is_ollama_whole_eligible({"class_definition", "async"}) is True

    def test_is_ollama_whole_eligible_with_overlap(self):
        """Signals overlapping skip list → not eligible."""
        engine = MicroPrimeEngine()
        assert engine._is_ollama_whole_eligible({"external_api", "async"}) is False

    def test_is_ollama_whole_eligible_orchestrator(self):
        """Orchestrator signal → not eligible."""
        engine = MicroPrimeEngine()
        assert engine._is_ollama_whole_eligible({"orchestrator"}) is False


# ---------------------------------------------------------------------------
# Test: Config toggle
# ---------------------------------------------------------------------------


class TestOllamaWholeConfigToggle:
    """moderate_ollama_whole_enabled=False preserves legacy behavior."""

    def test_disabled_skips_ollama_whole(
        self, orchestrator_element, sample_file_spec, sample_skeleton,
    ):
        """With Ollama-whole disabled, MODERATE goes straight to decomposition/escalation."""
        config = MicroPrimeConfig(moderate_ollama_whole_enabled=False)
        engine = MicroPrimeEngine(config=config)
        result = engine.process_element(
            orchestrator_element, sample_file_spec, sample_skeleton,
        )
        assert result.success is False
        assert result.escalation is not None
        assert result.escalation.reason == EscalationReason.TIER_TOO_HIGH
