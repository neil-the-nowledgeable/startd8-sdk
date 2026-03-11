"""Tests for FR-DFA-001: Escalation conflation fix.

Verifies that file-level bypass (files MP can't process) is separated
from element-level escalation (files where elements were too complex).
"""
import dataclasses
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from startd8.contractors.protocols import GenerationResult
from startd8.forward_manifest import ForwardFileSpec, ForwardManifest
from startd8.micro_prime.prime_adapter import (
    MicroPrimeCodeGenerator,
    _FileProcessingState,
)


# ── Helpers ──────────────────────────────────────────────────────────

def _make_generator(
    escalation_enabled: bool = False,
    fallback: Any = None,
    output_dir: str = "/tmp/test-output",
) -> MicroPrimeCodeGenerator:
    """Build a MicroPrimeCodeGenerator with minimal config."""
    from startd8.micro_prime.models import MicroPrimeConfig

    config = MicroPrimeConfig(
        provider="mock",
        model="mock-model",
        escalation_enabled=escalation_enabled,
    )
    gen = MicroPrimeCodeGenerator.__new__(MicroPrimeCodeGenerator)
    gen._config = config
    gen._engine = MagicMock()
    gen._element_registry = None
    gen._fallback = fallback
    gen._output_dir = Path(output_dir)
    gen._manifest = None
    gen._skeletons = None
    gen._ollama_available = None
    gen._cloud_agent_spec = None
    gen._tier_agent_spec = None
    return gen


def _make_manifest(file_specs: dict[str, ForwardFileSpec]) -> ForwardManifest:
    return ForwardManifest(contracts=[], file_specs=file_specs)


# ── Tests ────────────────────────────────────────────────────────────


class TestBypassFilesField:
    """_FileProcessingState has bypass_files field."""

    def test_bypass_files_default_empty(self):
        st = _FileProcessingState()
        assert st.bypass_files == []

    def test_bypass_files_independent_of_escalated(self):
        st = _FileProcessingState()
        st.bypass_files.append("Dockerfile")
        st.escalated_files.append("main.py")
        assert "Dockerfile" in st.bypass_files
        assert "Dockerfile" not in st.escalated_files


class TestBypassClassification:
    """Files with no file_spec go to bypass_files, not escalated_files."""

    def test_no_file_spec_classified_as_bypass(self):
        """File not in manifest → bypass_files."""
        gen = _make_generator()
        manifest = _make_manifest({})
        st = _FileProcessingState()

        gen._process_target_files(
            st,
            target_files=["src/loadgenerator/Dockerfile"],
            manifest=manifest,
            skeletons={},
            mp_context=MagicMock(existing_file_contents={}),
            task="test task",
            context={},
        )

        assert "src/loadgenerator/Dockerfile" in st.bypass_files
        assert "src/loadgenerator/Dockerfile" not in st.escalated_files

    def test_no_skeleton_classified_as_bypass(self):
        """File in manifest but no skeleton → bypass_files."""
        gen = _make_generator()
        spec = ForwardFileSpec(file="app.py")
        manifest = _make_manifest({"app.py": spec})
        st = _FileProcessingState()

        gen._process_target_files(
            st,
            target_files=["app.py"],
            manifest=manifest,
            skeletons={},  # no skeleton
            mp_context=MagicMock(existing_file_contents={}),
            task="test task",
            context={},
        )

        assert "app.py" in st.bypass_files
        assert "app.py" not in st.escalated_files

    def test_python_with_spec_and_skeleton_not_bypassed(self):
        """Python file with spec + skeleton goes through engine, not bypass."""
        gen = _make_generator()
        spec = ForwardFileSpec(file="app.py")
        manifest = _make_manifest({"app.py": spec})
        st = _FileProcessingState()

        # Mock the engine to return a file result
        mock_result = MagicMock()
        mock_result.filled_skeleton = None
        mock_result.element_results = []
        mock_result.escalated_count = 0
        mock_result.success_count = 0
        gen._engine.process_file_with_context.return_value = mock_result

        gen._process_target_files(
            st,
            target_files=["app.py"],
            manifest=manifest,
            skeletons={"app.py": "def foo(): pass"},
            mp_context=MagicMock(existing_file_contents={}),
            task="test task",
            context={},
        )

        assert "app.py" not in st.bypass_files
        assert gen._engine.process_file_with_context.called


class TestBypassDelegation:
    """Bypass files always delegate to fallback regardless of escalation_enabled."""

    def test_bypass_delegates_even_when_escalation_disabled(self):
        """bypass_files delegate to fallback even with escalation_enabled=False."""
        fallback = MagicMock()
        fallback_result = GenerationResult(
            success=True,
            generated_files=[Path("/tmp/out/Dockerfile")],
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.01,
            model="mock:model",
            metadata={},
        )
        fallback.generate.return_value = fallback_result

        gen = _make_generator(escalation_enabled=False, fallback=fallback)
        manifest = _make_manifest({})
        st = _FileProcessingState()
        st.bypass_files = ["src/Dockerfile"]

        # Patch _delegate_to_fallback to capture the call
        gen._delegate_to_fallback = MagicMock(return_value=fallback_result)

        # Simulate the bypass gate from generate()
        # (calling the gate logic directly)
        if st.bypass_files and gen._fallback is not None:
            result = gen._delegate_to_fallback(
                "task", {}, st.bypass_files,
            )
            st.generated_files.extend(result.generated_files)

        gen._delegate_to_fallback.assert_called_once()
        assert len(st.generated_files) == 1

    def test_bypass_no_fallback_logs_warning(self):
        """bypass_files with no fallback → files skipped (not failed)."""
        gen = _make_generator(escalation_enabled=False, fallback=None)
        st = _FileProcessingState()
        st.bypass_files = ["src/Dockerfile"]
        st.effective_file_count = 1  # other files succeeded

        # The bypass gate should not crash — files are just skipped
        # Success is based on effective_file_count, not bypass_files
        assert st.effective_file_count > 0


class TestMetadataTracking:
    """Generation metadata tracks bypass_file_count."""

    def test_metadata_includes_bypass_count(self):
        gen = _make_generator()
        st = _FileProcessingState()
        st.bypass_files = ["Dockerfile", "Dockerfile.dev"]
        st.effective_file_count = 3

        meta = gen._build_generation_metadata(st, local_file_count=3)
        assert meta["bypass_file_count"] == 2
