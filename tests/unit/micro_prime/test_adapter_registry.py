"""Tests for ElementRegistry integration in MicroPrimeCodeGenerator (REQ-MP-1103)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from startd8.element_registry import ElementRegistry
from startd8.micro_prime.models import (
    ElementResult,
    EscalationResult,
    FileResult,
    MicroPrimeConfig,
    TierClassification,
)
from startd8.micro_prime.prime_adapter import MicroPrimeCodeGenerator


def _make_ollama_mock():
    """Create a mock urlopen context manager for Ollama availability check."""
    mock_response = MagicMock()
    mock_response.read.return_value = b'{"models": [{"name": "startd8-coder:latest"}]}'
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)
    return mock_response


class TestRegistryPassThrough:
    """Verify that element_registry is passed through to the engine."""

    def test_registry_stored_on_instance(self):
        registry = ElementRegistry()
        gen = MicroPrimeCodeGenerator(element_registry=registry)
        assert gen._element_registry is registry

    def test_registry_passed_to_engine(self):
        registry = ElementRegistry()
        gen = MicroPrimeCodeGenerator(element_registry=registry)
        assert gen._engine._element_registry is registry

    def test_none_registry_accepted(self):
        gen = MicroPrimeCodeGenerator(element_registry=None)
        assert gen._element_registry is None
        assert gen._engine._element_registry is None


class TestRegistryAfterValidation:
    """Verify element registration after post-assembly validation."""

    def test_successful_generation_registers_elements(
        self, tmp_path, sample_manifest, sample_skeleton,
    ):
        """Elements from files passing post-assembly validation are registered."""
        registry = ElementRegistry(state_dir=tmp_path / "registry")
        gen = MicroPrimeCodeGenerator(
            manifest=sample_manifest,
            skeletons={"src/mypackage/utils.py": sample_skeleton},
            output_dir=tmp_path,
            element_registry=registry,
        )

        with patch(
            "startd8.micro_prime.prime_adapter.urlopen",
            return_value=_make_ollama_mock(),
        ):
            result = gen.generate(
                "Implement utils", {}, ["src/mypackage/utils.py"],
            )

        # If any elements were locally generated and the file passed
        # validation, they should have been registered.
        meta = result.metadata or {}
        local_count = meta.get("micro_prime_elements", 0)
        if local_count > 0 and result.success:
            assert len(registry) > 0, (
                "Expected elements to be registered after successful generation"
            )

    def test_registry_errors_do_not_abort_generation(
        self, tmp_path, sample_manifest, sample_skeleton,
    ):
        """Registry errors should be non-fatal -- generation continues."""
        # Use a registry whose put() always raises
        registry = MagicMock(spec=ElementRegistry)
        registry.get.side_effect = RuntimeError("disk full")
        registry.put.side_effect = RuntimeError("disk full")
        registry.set_phase_status.side_effect = RuntimeError("disk full")

        gen = MicroPrimeCodeGenerator(
            manifest=sample_manifest,
            skeletons={"src/mypackage/utils.py": sample_skeleton},
            output_dir=tmp_path,
            element_registry=registry,
        )

        with patch(
            "startd8.micro_prime.prime_adapter.urlopen",
            return_value=_make_ollama_mock(),
        ):
            # Should NOT raise despite registry errors
            result = gen.generate(
                "Implement utils", {}, ["src/mypackage/utils.py"],
            )

        # Generation should complete (success depends on Ollama, but no crash)
        assert result is not None


class TestRegistryHitMissCounts:
    """Verify hit/miss counts in generation metadata."""

    def test_counts_present_in_metadata(
        self, tmp_path, sample_manifest, sample_skeleton,
    ):
        """prime.element_registry_hit and prime.element_registry_miss
        must appear in generation metadata."""
        gen = MicroPrimeCodeGenerator(
            manifest=sample_manifest,
            skeletons={"src/mypackage/utils.py": sample_skeleton},
            output_dir=tmp_path,
        )

        with patch(
            "startd8.micro_prime.prime_adapter.urlopen",
            return_value=_make_ollama_mock(),
        ):
            result = gen.generate(
                "Implement utils", {}, ["src/mypackage/utils.py"],
            )

        meta = result.metadata or {}
        assert "prime.element_registry_hit" in meta
        assert "prime.element_registry_miss" in meta
        assert isinstance(meta["prime.element_registry_hit"], int)
        assert isinstance(meta["prime.element_registry_miss"], int)

    def test_counts_in_fallback_metadata(
        self, tmp_path, sample_manifest, sample_skeleton,
    ):
        """Hit/miss counts should appear when some files are escalated to fallback."""
        fallback = MagicMock()
        fallback.generate.return_value = MagicMock(
            success=True,
            generated_files=[],
            input_tokens=0,
            output_tokens=0,
            model="fallback",
            cost_usd=0.0,
        )
        # Provide manifest so we go through the main code path, but use
        # a target file NOT in the manifest so it gets escalated.
        gen = MicroPrimeCodeGenerator(
            manifest=sample_manifest,
            skeletons={"src/mypackage/utils.py": sample_skeleton},
            fallback=fallback,
            output_dir=tmp_path,
        )

        with patch(
            "startd8.micro_prime.prime_adapter.urlopen",
            return_value=_make_ollama_mock(),
        ):
            result = gen.generate(
                "Implement utils",
                {},
                ["src/mypackage/utils.py", "src/other.py"],
            )

        meta = result.metadata or {}
        assert "prime.element_registry_hit" in meta
        assert "prime.element_registry_miss" in meta

    def test_hit_count_from_registry_source(self):
        """_count_registry_hits_misses correctly identifies registry-sourced elements."""
        gen = MicroPrimeCodeGenerator()

        hit_element = ElementResult(
            element_name="cached_func",
            file_path="a.py",
            tier=TierClassification.TRIVIAL,
            success=True,
            code="return 42",
            decomposition_metadata={"source": "element_registry"},
        )
        miss_element = ElementResult(
            element_name="new_func",
            file_path="a.py",
            tier=TierClassification.SIMPLE,
            success=True,
            code="return 1",
        )
        failed_element = ElementResult(
            element_name="bad_func",
            file_path="a.py",
            tier=TierClassification.MODERATE,
            success=False,
        )

        file_results = [
            FileResult(
                file_path="a.py",
                element_results=[hit_element, miss_element, failed_element],
            ),
        ]

        hits, misses = gen._count_registry_hits_misses(file_results)
        assert hits == 1
        assert misses == 1  # failed element is not counted

    def test_zero_counts_when_no_results(self):
        gen = MicroPrimeCodeGenerator()
        hits, misses = gen._count_registry_hits_misses([])
        assert hits == 0
        assert misses == 0
