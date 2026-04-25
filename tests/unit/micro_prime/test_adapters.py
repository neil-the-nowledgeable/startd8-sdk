"""Tests for the Micro Prime workflow adapters (REQ-MP-503–504, 705)."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from startd8.forward_manifest import ForwardManifest
from startd8.micro_prime.artisan_adapter import MicroPrimePrePass, PrePassResult
from startd8.micro_prime.models import MicroPrimeConfig
from startd8.micro_prime.prime_adapter import MicroPrimeCodeGenerator


class TestMicroPrimePrePass:
    """Tests for the Artisan adapter (REQ-MP-503)."""

    def test_no_manifest_skips(self):
        pre_pass = MicroPrimePrePass()
        result = pre_pass.run()
        assert result.filled_skeletons == {}
        assert result.escalated_elements == []

    def test_no_skeletons_skips(self, sample_manifest):
        pre_pass = MicroPrimePrePass(manifest=sample_manifest)
        result = pre_pass.run()
        assert result.filled_skeletons == {}

    def test_run_with_manifest_and_skeletons(self, sample_manifest, sample_skeleton):
        skeletons = {"src/mypackage/utils.py": sample_skeleton}
        pre_pass = MicroPrimePrePass(
            manifest=sample_manifest,
            skeletons=skeletons,
        )
        result = pre_pass.run()
        assert "src/mypackage/utils.py" in result.filled_skeletons
        assert isinstance(result.metrics, dict)

    def test_escalated_elements_have_context(self, sample_manifest, sample_skeleton):
        """REQ-MP-506: Escalated elements include error context."""
        skeletons = {"src/mypackage/utils.py": sample_skeleton}
        pre_pass = MicroPrimePrePass(
            manifest=sample_manifest,
            skeletons=skeletons,
        )
        result = pre_pass.run()
        for esc in result.escalated_elements:
            assert "element_name" in esc
            assert "file_path" in esc
            assert "tier" in esc
            assert "reason" in esc


class TestPrePassResult:
    """Tests for PrePassResult."""

    def test_local_success_count(self):
        result = PrePassResult(
            filled_skeletons={"a.py": "code"},
            escalated_elements=[],
            metrics={"local_success_count": 5},
        )
        assert result.local_success_count == 5

    def test_escalated_count(self):
        result = PrePassResult(
            filled_skeletons={},
            escalated_elements=[{"element_name": "foo"}],
            metrics={},
        )
        assert result.escalated_count == 1


class TestMicroPrimeCodeGenerator:
    """Tests for the Prime Contractor adapter (REQ-MP-504)."""

    def test_generate_no_manifest_delegates(self):
        fallback = MagicMock()
        fallback.generate.return_value = MagicMock(
            success=True, generated_files=[], input_tokens=0,
            output_tokens=0, model="fallback",
        )
        gen = MicroPrimeCodeGenerator(fallback=fallback)
        result = gen.generate("task desc", {}, ["src/a.py"])
        fallback.generate.assert_called_once()

    def test_generate_no_fallback_no_manifest(self):
        gen = MicroPrimeCodeGenerator()
        result = gen.generate("task desc", {}, ["src/a.py"])
        assert result.success is False
        assert "No fallback" in result.error

    def test_generate_with_manifest(self, sample_manifest, sample_skeleton):
        gen = MicroPrimeCodeGenerator(
            manifest=sample_manifest,
            skeletons={"src/mypackage/utils.py": sample_skeleton},
        )
        result = gen.generate(
            "Implement utils",
            {},
            ["src/mypackage/utils.py"],
        )
        # Should have attempted local generation
        assert result.model is not None


class TestSizeRegressionEscalation:
    """Tests for size-regression escalation guard in generate()."""

    def _make_ollama_mock(self):
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"models": [{"name": "startd8-coder:latest"}]}'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        return mock_response

    def test_escalates_when_skeleton_too_small(
        self, tmp_path, sample_manifest, sample_skeleton,
    ):
        """When filled skeleton is <60% of existing target, escalate to fallback."""
        fallback = MagicMock()
        fallback.generate.return_value = MagicMock(
            success=True,
            generated_files=[tmp_path / "fallback_out.py"],
            input_tokens=100,
            output_tokens=200,
            model="fallback-model",
            cost_usd=0.02,
        )

        gen = MicroPrimeCodeGenerator(
            manifest=sample_manifest,
            skeletons={"src/mypackage/utils.py": sample_skeleton},
            fallback=fallback,
            output_dir=tmp_path,
        )

        # Simulate existing target file with 200 lines (skeleton is ~20 lines)
        big_existing = "\n".join(f"line_{i} = {i}" for i in range(200))
        context = {
            "existing_files": {"src/mypackage/utils.py": big_existing},
        }

        with patch(
            "startd8.micro_prime.prime_adapter.urlopen",
            return_value=self._make_ollama_mock(),
        ):
            result = gen.generate(
                "Implement utils", context, ["src/mypackage/utils.py"],
            )

        # Fallback should have been called because skeleton << existing
        fallback.generate.assert_called_once()
        assert result.model is not None
        assert "fallback" in result.model

    def test_no_escalation_when_no_existing_file(
        self, tmp_path, sample_manifest, sample_skeleton,
    ):
        """When no existing file, no size-regression check — process locally."""
        gen = MicroPrimeCodeGenerator(
            manifest=sample_manifest,
            skeletons={"src/mypackage/utils.py": sample_skeleton},
            output_dir=tmp_path,
        )

        with patch(
            "startd8.micro_prime.prime_adapter.urlopen",
            return_value=self._make_ollama_mock(),
        ):
            result = gen.generate(
                "Implement utils", {}, ["src/mypackage/utils.py"],
            )

        # Should NOT have escalated — no existing file to compare against
        assert result.metadata.get("micro_prime_only", False) is True

    def test_no_escalation_when_existing_file_small(
        self, tmp_path, sample_manifest, sample_skeleton,
    ):
        """When existing file is below _MIN_EXISTING_LINES, skip the check."""
        gen = MicroPrimeCodeGenerator(
            manifest=sample_manifest,
            skeletons={"src/mypackage/utils.py": sample_skeleton},
            output_dir=tmp_path,
        )

        # Existing file has only 10 lines — below min threshold
        small_existing = "\n".join(f"x = {i}" for i in range(10))
        context = {
            "existing_files": {"src/mypackage/utils.py": small_existing},
        }

        with patch(
            "startd8.micro_prime.prime_adapter.urlopen",
            return_value=self._make_ollama_mock(),
        ):
            result = gen.generate(
                "Implement utils", context, ["src/mypackage/utils.py"],
            )

        # Should NOT have escalated — existing file too small to trigger guard
        assert result.metadata.get("micro_prime_only", False) is True


class TestSkeletonGeneration:
    """Tests for REQ-MP-702: On-the-fly skeleton generation."""

    def test_auto_generates_skeleton_when_missing(self, sample_manifest):
        """When manifest present but skeletons absent, stubs are auto-generated."""
        gen = MicroPrimeCodeGenerator(manifest=sample_manifest)
        # Call _generate_skeletons directly to verify output
        skeletons = gen._generate_skeletons(
            sample_manifest, ["src/mypackage/utils.py"],
        )
        assert "src/mypackage/utils.py" in skeletons
        source = skeletons["src/mypackage/utils.py"]
        assert "raise NotImplementedError" in source
        assert "# [STARTD8-SKELETON]" in source

    def test_only_target_files_rendered(self, sample_manifest):
        """Only files in target_files are rendered, not the entire manifest."""
        gen = MicroPrimeCodeGenerator(manifest=sample_manifest)
        # Request a file not in manifest
        skeletons = gen._generate_skeletons(
            sample_manifest, ["src/other.py"],
        )
        assert skeletons == {}

    def test_missing_file_spec_skipped(self, sample_manifest):
        """Files without a matching file_spec in the manifest are skipped."""
        gen = MicroPrimeCodeGenerator(manifest=sample_manifest)
        skeletons = gen._generate_skeletons(
            sample_manifest,
            ["src/mypackage/utils.py", "src/nonexistent.py"],
        )
        assert "src/mypackage/utils.py" in skeletons
        assert "src/nonexistent.py" not in skeletons

    def test_render_failure_skipped_gracefully(self):
        """If render_file raises, that file is skipped and others proceed."""
        gen = MicroPrimeCodeGenerator()
        # Manifest with two files: one valid, one will cause a render failure
        file_spec_good = MagicMock()
        file_spec_bad = MagicMock()

        manifest = MagicMock()
        manifest.file_specs = {
            "good.py": file_spec_good,
            "bad.py": file_spec_bad,
        }

        with patch(
            "startd8.utils.file_assembler.DeterministicFileAssembler"
        ) as MockAssembler:
            mock_assembler = MockAssembler.return_value
            # good.py renders, bad.py raises
            def side_effect(spec):
                if spec is file_spec_bad:
                    raise ValueError("Invalid element")
                return "# [STARTD8-SKELETON]\nclass Good:\n    pass\n"

            mock_assembler.render_file.side_effect = side_effect

            skeletons = gen._generate_skeletons(
                manifest, ["good.py", "bad.py"],
            )

        assert "good.py" in skeletons
        assert "bad.py" not in skeletons

    def test_generate_triggers_auto_skeleton(self, sample_manifest):
        """generate() auto-generates skeletons when manifest present but skeletons empty."""
        gen = MicroPrimeCodeGenerator(manifest=sample_manifest)
        result = gen.generate(
            "Implement utils",
            {},
            ["src/mypackage/utils.py"],
        )
        # Should have attempted local generation (not delegated)
        assert result.model is not None
        assert "fallback" not in (result.model or "").lower()

    def test_generate_context_manifest_triggers_auto_skeleton(self, sample_manifest):
        """generate() auto-generates skeletons from context-provided manifest."""
        gen = MicroPrimeCodeGenerator()  # No manifest in constructor
        result = gen.generate(
            "Implement utils",
            {"manifest": sample_manifest},
            ["src/mypackage/utils.py"],
        )
        assert result.model is not None

    def test_explicit_skeletons_not_overridden(self, sample_manifest, sample_skeleton):
        """When skeletons are already provided, auto-generation is skipped."""
        gen = MicroPrimeCodeGenerator(manifest=sample_manifest)
        explicit_skeletons = {"src/mypackage/utils.py": sample_skeleton}

        with patch.object(gen, "_generate_skeletons") as mock_gen_skel:
            gen.generate(
                "Implement utils",
                {"skeletons": explicit_skeletons},
                ["src/mypackage/utils.py"],
            )
            mock_gen_skel.assert_not_called()

    def test_skeleton_contains_correct_elements(self, sample_manifest):
        """Generated skeleton includes elements from the ForwardFileSpec."""
        gen = MicroPrimeCodeGenerator(manifest=sample_manifest)
        skeletons = gen._generate_skeletons(
            sample_manifest, ["src/mypackage/utils.py"],
        )
        source = skeletons["src/mypackage/utils.py"]
        # Should contain the class and methods from the file spec
        assert "class MyClass" in source
        assert "def get_name" in source
        assert "def get_value" in source
        assert "DEFAULT_TIMEOUT" in source


class TestOutputFileWriting:
    """Tests for REQ-MP-703: Output file writing."""

    def test_output_dir_defaults_to_cwd(self):
        gen = MicroPrimeCodeGenerator()
        assert gen._output_dir == Path(".")

    def test_output_dir_from_constructor(self, tmp_path):
        gen = MicroPrimeCodeGenerator(output_dir=tmp_path)
        assert gen._output_dir == tmp_path

    def test_writes_file_to_disk(self, tmp_path, sample_manifest, filled_skeleton):
        """Generated files are written to output_dir / file_path."""
        gen = MicroPrimeCodeGenerator(
            manifest=sample_manifest,
            skeletons={"src/mypackage/utils.py": filled_skeleton},
            output_dir=tmp_path,
        )
        result = gen.generate(
            "Implement utils", {}, ["src/mypackage/utils.py"],
        )

        expected_path = tmp_path / "src/mypackage/utils.py"
        assert expected_path.exists(), f"Expected file at {expected_path}"
        content = expected_path.read_text(encoding="utf-8")
        assert len(content) > 0

    def test_creates_parent_directories(self, tmp_path, sample_manifest, filled_skeleton):
        """Parent directories are created automatically."""
        gen = MicroPrimeCodeGenerator(
            manifest=sample_manifest,
            skeletons={"src/mypackage/utils.py": filled_skeleton},
            output_dir=tmp_path,
        )
        gen.generate("Implement utils", {}, ["src/mypackage/utils.py"])

        assert (tmp_path / "src" / "mypackage").is_dir()

    def test_generated_files_contain_absolute_paths(self, tmp_path, sample_manifest, filled_skeleton):
        """GenerationResult.generated_files contains resolved Path objects."""
        gen = MicroPrimeCodeGenerator(
            manifest=sample_manifest,
            skeletons={"src/mypackage/utils.py": filled_skeleton},
            output_dir=tmp_path,
        )
        result = gen.generate(
            "Implement utils", {}, ["src/mypackage/utils.py"],
        )

        for p in result.generated_files:
            assert isinstance(p, Path)
            # Path should be under output_dir
            assert str(p).startswith(str(tmp_path))

    def test_metadata_tracks_local_file_count(self, tmp_path, sample_manifest, filled_skeleton):
        """Metadata includes micro_prime_files_written count."""
        gen = MicroPrimeCodeGenerator(
            manifest=sample_manifest,
            skeletons={"src/mypackage/utils.py": filled_skeleton},
            output_dir=tmp_path,
        )
        result = gen.generate(
            "Implement utils", {}, ["src/mypackage/utils.py"],
        )

        assert "micro_prime_files_written" in result.metadata

    def test_stub_skeleton_escalated_to_fallback(self, tmp_path, sample_manifest):
        """Skeletons with unfillable stubs are escalated to fallback and removed from disk."""
        # Add an extra function stub NOT in the manifest — engine can't fill it,
        # so `raise NotImplementedError` remains and triggers assembly defect.
        skeleton_with_unfillable = '''from __future__ import annotations
from typing import Optional, List
from pathlib import Path
import json


DEFAULT_TIMEOUT: int = ...  # STARTD8_AUTO_STUB


class MyClass:
    """My class."""

    def get_name(self, key: str) -> str:
        """Return the name for the given key."""
        raise NotImplementedError

    def get_value(self, key: str) -> int:
        """Return the value for the given key."""
        raise NotImplementedError

    def orphan_method(self) -> None:
        """Not in manifest — cannot be filled."""
        raise NotImplementedError
'''
        fallback = MagicMock()
        fallback.generate.return_value = MagicMock(
            success=True,
            generated_files=[tmp_path / "fb.py"],
            input_tokens=50,
            output_tokens=100,
            model="fallback",
            cost_usd=0.01,
        )
        gen = MicroPrimeCodeGenerator(
            manifest=sample_manifest,
            skeletons={"src/mypackage/utils.py": skeleton_with_unfillable},
            fallback=fallback,
            output_dir=tmp_path,
        )
        result = gen.generate(
            "Implement utils", {}, ["src/mypackage/utils.py"],
        )

        expected_path = tmp_path / "src/mypackage/utils.py"
        assert not expected_path.exists(), "Skeleton with unfillable stubs should be removed when fallback available"
        fallback.generate.assert_called_once()

    def test_stub_skeleton_kept_without_fallback(self, tmp_path, sample_manifest):
        """Without fallback, unfillable stubs result in failure."""
        skeleton_with_unfillable = '''from __future__ import annotations
from typing import Optional, List
from pathlib import Path
import json


DEFAULT_TIMEOUT: int = ...  # STARTD8_AUTO_STUB


class MyClass:
    """My class."""

    def get_name(self, key: str) -> str:
        """Return the name for the given key."""
        raise NotImplementedError

    def get_value(self, key: str) -> int:
        """Return the value for the given key."""
        raise NotImplementedError

    def orphan_method(self) -> None:
        """Not in manifest — cannot be filled."""
        raise NotImplementedError
'''
        gen = MicroPrimeCodeGenerator(
            manifest=sample_manifest,
            skeletons={"src/mypackage/utils.py": skeleton_with_unfillable},
            output_dir=tmp_path,
        )
        result = gen.generate(
            "Implement utils", {}, ["src/mypackage/utils.py"],
        )

        # Unfillable stubs remain — result reports failure
        assert not result.success

    def test_fallback_files_not_rewritten(self, tmp_path, sample_manifest):
        """Files delegated to fallback are NOT written by the adapter.

        FR-DFA-001: src/other.py has no file_spec → bypass_files (not
        escalated).  Bypass files always delegate to fallback regardless
        of escalation_enabled.
        """
        fallback = MagicMock()
        fallback_path = tmp_path / "fallback" / "other.py"
        fallback.generate.return_value = MagicMock(
            success=True,
            generated_files=[fallback_path],
            input_tokens=50,
            output_tokens=50,
            model="fallback-model",
            cost_usd=0.01,
            metadata={},
        )

        # Manifest has one file, but we request two — the second has no spec
        gen = MicroPrimeCodeGenerator(
            manifest=sample_manifest,
            fallback=fallback,
            output_dir=tmp_path,
        )
        result = gen.generate(
            "Implement utils",
            {},
            ["src/mypackage/utils.py", "src/other.py"],
        )

        # Fallback was called — at least once for bypass (src/other.py),
        # possibly also for element escalation of src/mypackage/utils.py
        assert fallback.generate.call_count >= 1
        # FR-DFA-001: metadata tracks bypass files separately
        assert result.metadata["bypass_file_count"] == 1

    def test_metadata_mixed_local_and_fallback(self, tmp_path, sample_manifest, filled_skeleton):
        """Metadata correctly separates local vs fallback file counts."""
        fallback = MagicMock()
        fallback.generate.return_value = MagicMock(
            success=True,
            generated_files=[Path("fallback_out.py")],
            input_tokens=0,
            output_tokens=0,
            model="fallback",
        )

        gen = MicroPrimeCodeGenerator(
            manifest=sample_manifest,
            skeletons={"src/mypackage/utils.py": filled_skeleton},
            fallback=fallback,
            output_dir=tmp_path,
        )
        result = gen.generate(
            "Implement",
            {},
            ["src/mypackage/utils.py", "src/missing.py"],
        )

        assert result.metadata["micro_prime_files_written"] >= 0
        assert result.metadata["fallback_files_written"] == 1


    def test_bypass_only_success_when_fallback_succeeds(self, tmp_path, sample_manifest):
        """When ALL target files are bypass (non-Python) and fallback succeeds,
        overall result must be success=True.

        Regression: run-038 PI-005 — HTML template file was bypass, fallback
        generated it, but effective_file_count was never incremented so
        MicroPrime reported success=False.
        """
        fallback = MagicMock()
        fallback_path = tmp_path / "generated" / "confirmation.html"
        fallback.generate.return_value = MagicMock(
            success=True,
            generated_files=[fallback_path],
            input_tokens=100,
            output_tokens=200,
            model="fallback-model",
            cost_usd=0.005,
            metadata={},
        )

        gen = MicroPrimeCodeGenerator(
            manifest=sample_manifest,
            fallback=fallback,
            output_dir=tmp_path,
        )
        # Request only a file with no manifest entry — pure bypass
        result = gen.generate(
            "Generate HTML template",
            {},
            ["src/emailservice/templates/confirmation.html"],
        )

        assert result.success, (
            f"Expected success=True when fallback generated bypass file, "
            f"got error={result.error}"
        )
        assert fallback_path in result.generated_files

    def test_bypass_fallback_failure_propagates_error(self, tmp_path, sample_manifest):
        """When fallback fails for bypass files, error message propagates.

        Regression: run-038 — fallback failure returned success=False with
        no error, producing generic 'Code generation failed' message.
        """
        fallback = MagicMock()
        fallback.generate.return_value = MagicMock(
            success=False,
            generated_files=[],
            input_tokens=50,
            output_tokens=0,
            model="fallback-model",
            cost_usd=0.001,
            error="search_replace extraction failed",
        )

        gen = MicroPrimeCodeGenerator(
            manifest=sample_manifest,
            fallback=fallback,
            output_dir=tmp_path,
        )
        result = gen.generate(
            "Generate HTML template",
            {},
            ["src/emailservice/templates/confirmation.html"],
        )

        assert not result.success
        assert result.error is not None
        assert "search_replace" in result.error


class TestCostTracking:
    """Tests for REQ-MP-704: Cost and token tracking polish."""

    def test_local_only_cost_is_zero(self, tmp_path, sample_manifest, sample_skeleton):
        """Local-only generation reports cost_usd == 0.0."""
        gen = MicroPrimeCodeGenerator(
            manifest=sample_manifest,
            skeletons={"src/mypackage/utils.py": sample_skeleton},
            output_dir=tmp_path,
        )
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"models": [{"name": "startd8-coder:latest"}]}'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        with patch("startd8.micro_prime.prime_adapter.urlopen", return_value=mock_response):
            result = gen.generate(
                "Implement utils", {}, ["src/mypackage/utils.py"],
            )
        assert result.cost_usd == 0.0

    def test_fallback_cost_forwarded(self, tmp_path, sample_manifest, sample_skeleton):
        """Fallback cost_usd is forwarded to the final GenerationResult."""
        fallback = MagicMock()
        fallback.generate.return_value = MagicMock(
            success=True,
            generated_files=[Path("fb_out.py")],
            input_tokens=100,
            output_tokens=200,
            model="fallback-model",
            cost_usd=0.05,
        )

        gen = MicroPrimeCodeGenerator(
            manifest=sample_manifest,
            skeletons={"src/mypackage/utils.py": sample_skeleton},
            fallback=fallback,
            output_dir=tmp_path,
        )
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"models": [{"name": "startd8-coder:latest"}]}'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        with patch("startd8.micro_prime.prime_adapter.urlopen", return_value=mock_response):
            result = gen.generate(
                "Implement utils",
                {},
                ["src/mypackage/utils.py", "src/unknown.py"],
            )
        assert result.cost_usd == 0.05

    def test_metadata_element_counts(self, tmp_path, sample_manifest, sample_skeleton):
        """Metadata contains element-level counter keys."""
        gen = MicroPrimeCodeGenerator(
            manifest=sample_manifest,
            skeletons={"src/mypackage/utils.py": sample_skeleton},
            output_dir=tmp_path,
        )
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"models": [{"name": "startd8-coder:latest"}]}'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        with patch("startd8.micro_prime.prime_adapter.urlopen", return_value=mock_response):
            result = gen.generate(
                "Implement utils", {}, ["src/mypackage/utils.py"],
            )
        assert "micro_prime_elements" in result.metadata
        assert "micro_prime_template_hits" in result.metadata
        assert "micro_prime_ollama_generations" in result.metadata


class TestOllamaAvailabilityGuard:
    """Tests for REQ-MP-711: Runtime Ollama availability guard."""

    def _make_gen(self, fallback=None, **kwargs):
        fb = fallback or MagicMock()
        fb.generate.return_value = MagicMock(
            success=True, generated_files=[], input_tokens=0,
            output_tokens=0, model="fallback",
        )
        return MicroPrimeCodeGenerator(fallback=fb, **kwargs), fb

    def test_ollama_unavailable_delegates_to_fallback(self, sample_manifest, sample_skeleton):
        """When Ollama is unreachable, all elements are delegated to fallback."""
        gen, fb = self._make_gen(
            manifest=sample_manifest,
            skeletons={"src/mypackage/utils.py": sample_skeleton},
        )
        with patch(
            "startd8.micro_prime.prime_adapter.urlopen",
            side_effect=ConnectionRefusedError("Connection refused"),
        ):
            result = gen.generate("task", {}, ["src/mypackage/utils.py"])

        fb.generate.assert_called_once()
        assert gen._ollama_available is False

    def test_ollama_available_processes_locally(self, sample_manifest, sample_skeleton, tmp_path):
        """When Ollama is reachable with the model present, local processing proceeds."""
        gen, fb = self._make_gen(
            manifest=sample_manifest,
            skeletons={"src/mypackage/utils.py": sample_skeleton},
            output_dir=tmp_path,
        )
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"models": [{"name": "startd8-coder:latest"}]}'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("startd8.micro_prime.prime_adapter.urlopen", return_value=mock_response):
            result = gen.generate("task", {}, ["src/mypackage/utils.py"])

        assert gen._ollama_available is True
        # Local processing attempted — fallback not called for the initial generate
        # (it may still be called if escalations occur, but the guard didn't trigger)

    def test_ollama_check_cached(self, sample_manifest, sample_skeleton, tmp_path):
        """The Ollama check runs only once; subsequent generate() calls use cached result."""
        gen, fb = self._make_gen(
            manifest=sample_manifest,
            skeletons={"src/mypackage/utils.py": sample_skeleton},
            output_dir=tmp_path,
        )
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"models": [{"name": "startd8-coder:latest"}]}'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("startd8.micro_prime.prime_adapter.urlopen", return_value=mock_response) as mock_url:
            gen.generate("task", {}, ["src/mypackage/utils.py"])
            gen._ollama_available = True  # ensure cached
            gen.generate("task", {}, ["src/mypackage/utils.py"])
            # urlopen should have been called only once (first generate)
            assert mock_url.call_count == 1

    def test_ollama_model_not_found_delegates(self, sample_manifest, sample_skeleton):
        """When Ollama is reachable but model is missing, delegate to fallback."""
        gen, fb = self._make_gen(
            manifest=sample_manifest,
            skeletons={"src/mypackage/utils.py": sample_skeleton},
        )
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"models": [{"name": "llama2:latest"}]}'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("startd8.micro_prime.prime_adapter.urlopen", return_value=mock_response):
            result = gen.generate("task", {}, ["src/mypackage/utils.py"])

        fb.generate.assert_called_once()
        assert gen._ollama_available is False


class TestEnableDisableMicroPrime:
    """Tests for REQ-MP-710: Workflow-level Micro Prime activation."""

    def _make_workflow(self):
        from startd8.contractors.prime_contractor import PrimeContractorWorkflow

        mock_generator = MagicMock()
        mock_generator.output_dir = Path("generated")
        workflow = PrimeContractorWorkflow.__new__(PrimeContractorWorkflow)
        # Manually set the minimum required state
        workflow.code_generator = mock_generator
        workflow._micro_prime_enabled = False
        workflow._original_code_generator = None
        workflow._complexity_routing_enabled = False
        workflow._complexity_config = None
        workflow._complexity_router = None
        return workflow, mock_generator

    def test_enable_micro_prime_wraps_generator(self):
        """enable_micro_prime() replaces code_generator with MicroPrimeCodeGenerator."""
        workflow, original = self._make_workflow()
        workflow.enable_micro_prime()

        assert workflow._micro_prime_enabled is True
        assert type(workflow.code_generator).__name__ == "MicroPrimeCodeGenerator"
        assert workflow._original_code_generator is original

    def test_disable_micro_prime_restores_generator(self):
        """disable_micro_prime() restores the original code generator."""
        workflow, original = self._make_workflow()
        workflow.enable_micro_prime()
        workflow.disable_micro_prime()

        assert workflow._micro_prime_enabled is False
        assert workflow.code_generator is original
        assert workflow._original_code_generator is None

    def test_enable_micro_prime_with_custom_config(self):
        """Custom MicroPrimeConfig is forwarded to the adapter."""
        workflow, _ = self._make_workflow()
        config = MicroPrimeConfig(
            model="custom-model",
            max_tokens=1024,
            templates_enabled=False,
        )
        workflow.enable_micro_prime(config=config)

        assert workflow.code_generator._config.model == "custom-model"
        assert workflow.code_generator._config.max_tokens == 1024
        assert workflow.code_generator._config.templates_enabled is False


class TestObservabilityLogging:
    """Tests for REQ-MP-705: Observability and Logging."""

    def _make_ollama_mock(self):
        """Create a mock urlopen that reports startd8-coder:latest as available."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"models": [{"name": "startd8-coder:latest"}]}'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        return mock_response

    def test_per_feature_summary_logged(
        self, sample_manifest, sample_skeleton, tmp_path, caplog,
    ):
        """generate() emits an INFO log summarising local vs escalated element counts."""
        gen = MicroPrimeCodeGenerator(
            manifest=sample_manifest,
            skeletons={"src/mypackage/utils.py": sample_skeleton},
            output_dir=tmp_path,
        )

        with caplog.at_level(logging.INFO), patch(
            "startd8.micro_prime.prime_adapter.urlopen",
            return_value=self._make_ollama_mock(),
        ):
            gen.generate("Implement utils", {}, ["src/mypackage/utils.py"])

        summary_messages = [
            r.message
            for r in caplog.records
            if "elements local" in r.message and "escalated" in r.message
        ]
        assert len(summary_messages) >= 1, (
            f"Expected summary log with 'elements local ... escalated', "
            f"got: {[r.message for r in caplog.records]}"
        )

    def test_otel_counters_not_required(
        self, sample_manifest, sample_skeleton, tmp_path,
    ):
        """generate() succeeds when OTel counters are None (no opentelemetry installed)."""
        import startd8.micro_prime.prime_adapter as pa

        saved_local = pa._elements_local_counter
        saved_escalated = pa._elements_escalated_counter
        saved_template = pa._template_hits_counter
        try:
            pa._elements_local_counter = None
            pa._elements_escalated_counter = None
            pa._template_hits_counter = None

            gen = MicroPrimeCodeGenerator(
                manifest=sample_manifest,
                skeletons={"src/mypackage/utils.py": sample_skeleton},
                output_dir=tmp_path,
            )

            with patch(
                "startd8.micro_prime.prime_adapter.urlopen",
                return_value=self._make_ollama_mock(),
            ):
                result = gen.generate("Implement utils", {}, ["src/mypackage/utils.py"])

            # Should complete without AttributeError
            assert result is not None
        finally:
            pa._elements_local_counter = saved_local
            pa._elements_escalated_counter = saved_escalated
            pa._template_hits_counter = saved_template


# ── Micro Prime chunk wiring tests ──────────────────────────────────


class TestMicroPrimeChunkWiring:
    """Tests for Micro Prime pre-pass ↔ chunk executor wiring."""

    def _make_chunk(self, metadata=None, file_targets=None):
        """Build a minimal DevelopmentChunk for testing."""
        from startd8.contractors.artisan_phases.development import DevelopmentChunk

        return DevelopmentChunk(
            chunk_id="task-001",
            description="Implement utils",
            dependencies=[],
            file_targets=file_targets or ["src/utils.py"],
            implementation_prompt="Implement the module",
            test_commands=[],
            metadata=metadata or {},
        )

    @staticmethod
    def _make_seed_task(target_files, **overrides):
        """Build a minimal mock SeedTask for _tasks_to_chunks tests."""
        task = MagicMock()
        task.task_id = overrides.get("task_id", "t1")
        task.description = overrides.get("description", "desc")
        task.target_files = target_files
        task.feature_id = overrides.get("feature_id", "f1")
        task.domain = overrides.get("domain", "sdk")
        task.estimated_loc = overrides.get("estimated_loc", 50)
        task.post_generation_validators = []
        task.title = overrides.get("title", "Task 1")
        task.requirements_text = None
        task.complexity_tier_override = None
        task.artifact_types_addressed = []
        return task

    def test_chunk_metadata_micro_prime_complete(self):
        """Chunk gets _micro_prime_complete=True when all targets are filled and none escalated."""
        from startd8.contractors.context_seed_handlers import ImplementPhaseHandler

        micro_prime_result = {
            "filled_skeletons": {"src/a.py": "# filled a", "src/b.py": "# filled b"},
            "escalated_elements": [],
            "metrics": {"local_success_count": 2},
        }
        task = self._make_seed_task(["src/a.py", "src/b.py"])

        chunks, _ = ImplementPhaseHandler._tasks_to_chunks(
            [task], micro_prime_result=micro_prime_result,
        )

        assert len(chunks) == 1
        meta = chunks[0].metadata
        assert meta["_micro_prime_complete"] is True
        assert meta["_micro_prime_filled_skeletons"] == {
            "src/a.py": "# filled a",
            "src/b.py": "# filled b",
        }
        assert meta["_micro_prime_escalated"] is None or len(meta["_micro_prime_escalated"]) == 0

    def test_chunk_metadata_micro_prime_partial(self):
        """_micro_prime_complete=False when some elements are escalated."""
        from startd8.contractors.context_seed_handlers import ImplementPhaseHandler

        micro_prime_result = {
            "filled_skeletons": {"src/a.py": "# filled a"},
            "escalated_elements": [
                {"file_path": "src/a.py", "element_name": "complex_fn", "tier": "COMPLEX", "reason": "too complex"},
            ],
            "metrics": {"local_success_count": 1},
        }
        task = self._make_seed_task(["src/a.py"])

        chunks, _ = ImplementPhaseHandler._tasks_to_chunks(
            [task], micro_prime_result=micro_prime_result,
        )

        assert len(chunks) == 1
        meta = chunks[0].metadata
        assert meta["_micro_prime_complete"] is False
        assert meta["_micro_prime_filled_skeletons"] == {"src/a.py": "# filled a"}
        assert len(meta["_micro_prime_escalated"]) == 1

    @pytest.mark.asyncio
    async def test_executor_skips_llm_for_complete_chunk(self, tmp_path):
        """agenerate() is NOT called when _micro_prime_complete=True."""
        from startd8.contractors.artisan_phases.development import ArtisanChunkExecutor

        executor = ArtisanChunkExecutor(
            output_dir=tmp_path,
        )
        chunk = self._make_chunk(
            metadata={
                "_micro_prime_complete": True,
                "_micro_prime_filled_skeletons": {"src/utils.py": "# filled content"},
            },
            file_targets=["src/utils.py"],
        )
        context: dict = {}

        with patch.object(executor, "_build_generation_context") as mock_ctx:
            success, msg = await executor.execute(chunk, context)

        assert success is True
        assert "Micro Prime" in msg
        # _build_generation_context should NOT be called — skipped entirely
        mock_ctx.assert_not_called()
        # Verify the file was actually written to staging
        assert (tmp_path / "src/utils.py").exists()

    def test_executor_writes_filled_skeletons_to_staging(self, tmp_path):
        """_write_micro_prime_files writes correct files to output_dir."""
        from startd8.contractors.artisan_phases.development import ArtisanChunkExecutor

        executor = ArtisanChunkExecutor(output_dir=tmp_path)
        filled = {"src/utils.py": "def hello():\n    return 'world'\n"}
        chunk = self._make_chunk(file_targets=["src/utils.py"])

        written = executor._write_micro_prime_files(filled, chunk)

        assert len(written) == 1
        expected = tmp_path / "src/utils.py"
        assert expected.exists()
        assert expected.read_text(encoding="utf-8") == "def hello():\n    return 'world'\n"

    def test_partial_chunk_injects_existing_files(self, tmp_path):
        """Pre-filled skeleton flows into _build_generation_context() as existing file content."""
        from startd8.contractors.artisan_phases.development import ArtisanChunkExecutor

        executor = ArtisanChunkExecutor(output_dir=tmp_path)
        chunk = self._make_chunk(
            metadata={
                "_micro_prime_complete": False,
                "_micro_prime_filled_skeletons": {"src/utils.py": "# partial skeleton"},
                "_micro_prime_escalated": [
                    {"file_path": "src/utils.py", "element_name": "hard_fn"},
                ],
                "feature_id": "f1",
                "domain": "sdk",
                "estimated_loc": 50,
            },
            file_targets=["src/utils.py"],
        )
        context: dict = {}

        gen_ctx = executor._build_generation_context(chunk, context)

        existing = gen_ctx.get("existing_files", {})
        assert "src/utils.py" in existing
        assert existing["src/utils.py"] == "# partial skeleton"


class TestElementLevelEscalation:
    """Tests for element-level (not file-level) escalation."""

    def _make_ollama_mock(self):
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"models": [{"name": "startd8-coder:latest"}]}'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        return mock_response

    def test_partial_success_with_stubs_escalates_to_fallback(
        self, tmp_path, sample_manifest, sample_skeleton,
    ):
        """When some elements succeed locally but stubs remain, the file
        is escalated to fallback rather than writing a partial skeleton."""
        from startd8.micro_prime.models import (
            ElementResult,
            EscalationResult,
            EscalationReason,
            FileResult,
            TierClassification,
        )

        fallback = MagicMock()
        fallback.generate.return_value = MagicMock(
            success=True,
            generated_files=[tmp_path / "fb.py"],
            input_tokens=50,
            output_tokens=100,
            model="fallback",
            cost_usd=0.01,
        )

        gen = MicroPrimeCodeGenerator(
            manifest=sample_manifest,
            skeletons={"src/mypackage/utils.py": sample_skeleton},
            fallback=fallback,
            output_dir=tmp_path,
        )

        # Mock engine to return mixed results: 1 success + 1 escalated
        partial_result = FileResult(file_path="src/mypackage/utils.py")
        partial_result.element_results = [
            ElementResult(
                element_name="get_name",
                file_path="src/mypackage/utils.py",
                tier=TierClassification.SIMPLE,
                success=True,
                code="return key.upper()",
            ),
            ElementResult(
                element_name="get_value",
                file_path="src/mypackage/utils.py",
                tier=TierClassification.MODERATE,
                success=False,
                escalation=EscalationResult(
                    reason=EscalationReason.TIER_TOO_HIGH,
                    detail="Too complex",
                ),
            ),
        ]
        partial_result.filled_skeleton = sample_skeleton  # stubs remain

        with patch.object(gen._engine, "process_file", return_value=partial_result), \
             patch(
                 "startd8.micro_prime.prime_adapter.urlopen",
                 return_value=self._make_ollama_mock(),
             ):
            result = gen.generate(
                "Implement utils", {}, ["src/mypackage/utils.py"],
            )

        # File with remaining stubs is escalated to fallback
        fallback.generate.assert_called_once()
        # Skeleton file NOT written to disk
        assert not (tmp_path / "src/mypackage/utils.py").exists()

    def test_partial_success_cloud_fills_remaining_stub(
        self, tmp_path, sample_manifest,
    ):
        """When some elements succeed locally and one is escalated, the
        cloud fills the remaining stub. Element-level escalation uses
        direct cloud LLM calls per element (REQ-MP-505/512)."""
        from startd8.micro_prime.models import (
            ElementResult,
            EscalationResult,
            EscalationReason,
            FileResult,
            TierClassification,
        )

        # Partially-filled skeleton: get_name implemented, get_value still stubbed
        partial_skeleton = '''# [STARTD8-SKELETON]
from __future__ import annotations
from typing import Optional, List
from pathlib import Path
import json


DEFAULT_TIMEOUT: int = 30


class MyClass:
    """My class."""

    def get_name(self, key: str) -> str:
        """Return the name for the given key."""
        return str(key)

    def get_value(self, key: str) -> int:
        """Return the value for the given key."""
        raise NotImplementedError
'''

        mock_agent = MagicMock()
        mock_token_usage = MagicMock()
        mock_token_usage.input = 150
        mock_token_usage.output = 50
        mock_agent.generate.return_value = ("        return len(key)", 100, mock_token_usage)

        gen = MicroPrimeCodeGenerator(
            manifest=sample_manifest,
            skeletons={"src/mypackage/utils.py": partial_skeleton},
            cloud_agent_spec="anthropic:claude-haiku-4-5-20251001",
            output_dir=tmp_path,
        )

        # Mock engine to return mixed results: 1 success + 1 escalated
        partial_result = FileResult(file_path="src/mypackage/utils.py")
        partial_result.element_results = [
            ElementResult(
                element_name="get_name",
                file_path="src/mypackage/utils.py",
                tier=TierClassification.SIMPLE,
                success=True,
                code="return str(key)",
            ),
            ElementResult(
                element_name="get_value",
                file_path="src/mypackage/utils.py",
                tier=TierClassification.MODERATE,
                success=False,
                escalation=EscalationResult(
                    reason=EscalationReason.TIER_TOO_HIGH,
                    detail="Too complex",
                ),
            ),
        ]
        partial_result.filled_skeleton = partial_skeleton

        with patch.object(gen._engine, "process_file", return_value=partial_result), \
             patch(
                 "startd8.micro_prime.prime_adapter.urlopen",
                 return_value=self._make_ollama_mock(),
             ), \
             patch(
                 "startd8.micro_prime.prime_adapter.MicroPrimeCodeGenerator._get_cloud_agent",
                 return_value=mock_agent,
             ):
            result = gen.generate(
                "Implement utils", {}, ["src/mypackage/utils.py"],
            )

        # Cloud agent called for the escalated element
        assert mock_agent.generate.call_count >= 1
        call_prompt = mock_agent.generate.call_args_list[0][0][0]
        assert "get_value" in call_prompt
        assert "tier_too_high" in call_prompt
        # File was written (cloud splice filled the stub)
        assert len(result.generated_files) >= 1
        assert result.metadata["element_escalation_count"] == 1

    def test_zero_success_delegates_to_fallback(
        self, tmp_path, sample_manifest, sample_skeleton,
    ):
        """When all elements fail, the file IS sent to fallback."""
        from startd8.micro_prime.models import (
            ElementResult,
            EscalationResult,
            EscalationReason,
            FileResult,
            TierClassification,
        )

        fallback = MagicMock()
        fallback.generate.return_value = MagicMock(
            success=True,
            generated_files=[tmp_path / "fb.py"],
            input_tokens=50,
            output_tokens=100,
            model="fallback",
            cost_usd=0.05,
        )

        gen = MicroPrimeCodeGenerator(
            manifest=sample_manifest,
            skeletons={"src/mypackage/utils.py": sample_skeleton},
            fallback=fallback,
            output_dir=tmp_path,
        )

        # All elements escalated
        all_fail_result = FileResult(file_path="src/mypackage/utils.py")
        all_fail_result.element_results = [
            ElementResult(
                element_name="get_name",
                file_path="src/mypackage/utils.py",
                tier=TierClassification.MODERATE,
                success=False,
                escalation=EscalationResult(
                    reason=EscalationReason.TIER_TOO_HIGH,
                    detail="Too complex",
                ),
            ),
            ElementResult(
                element_name="get_value",
                file_path="src/mypackage/utils.py",
                tier=TierClassification.COMPLEX,
                success=False,
                escalation=EscalationResult(
                    reason=EscalationReason.TIER_TOO_HIGH,
                    detail="Too complex",
                ),
            ),
        ]
        all_fail_result.filled_skeleton = sample_skeleton

        with patch.object(gen._engine, "process_file", return_value=all_fail_result), \
             patch(
                 "startd8.micro_prime.prime_adapter.urlopen",
                 return_value=self._make_ollama_mock(),
             ):
            result = gen.generate(
                "Implement utils", {}, ["src/mypackage/utils.py"],
            )

        # Fallback should be called — zero local successes
        fallback.generate.assert_called_once()


    def test_cloud_escalation_retry_same_prompt(
        self, tmp_path, sample_manifest, sample_skeleton,
    ):
        """Retries cloud escalation when direct call fails (same_prompt)."""
        from startd8.micro_prime.models import (
            ElementResult,
            EscalationResult,
            EscalationReason,
            FileResult,
            TierClassification,
        )

        config = MicroPrimeConfig(
            cloud_escalation_max_attempts=2,
            cloud_escalation_retry_strategy="same_prompt",
        )
        gen = MicroPrimeCodeGenerator(
            config=config,
            manifest=sample_manifest,
            skeletons={"src/mypackage/utils.py": sample_skeleton},
            cloud_agent_spec="anthropic:claude-haiku-4-5-20251001",
            output_dir=tmp_path,
        )

        partial_result = FileResult(file_path="src/mypackage/utils.py")
        partial_result.element_results = [
            ElementResult(
                element_name="get_name",
                file_path="src/mypackage/utils.py",
                tier=TierClassification.SIMPLE,
                success=True,
                code="return key.upper()",
            ),
            ElementResult(
                element_name="get_value",
                file_path="src/mypackage/utils.py",
                tier=TierClassification.MODERATE,
                success=False,
                escalation=EscalationResult(
                    reason=EscalationReason.TIER_TOO_HIGH,
                    detail="Too complex",
                    last_error="bad_local",
                ),
            ),
        ]
        partial_result.filled_skeleton = sample_skeleton

        mock_direct = MagicMock(
            side_effect=[None, ("return len(key)", 10, 5)],
        )

        with patch.object(gen._engine, "process_file", return_value=partial_result), \
             patch(
                 "startd8.micro_prime.prime_adapter.urlopen",
                 return_value=self._make_ollama_mock(),
             ), \
             patch.object(
                 gen, "_direct_cloud_generate", mock_direct,
             ), \
             patch.object(gen, "_run_post_generation_repair", return_value=0):
            result = gen.generate(
                "Implement utils", {}, ["src/mypackage/utils.py"],
            )

        assert mock_direct.call_count == 2
        retry_contexts = [
            call.kwargs.get("retry_context", None)
            for call in mock_direct.call_args_list
        ]
        assert retry_contexts == ["", ""]

        er = partial_result.element_results[1]
        assert er.cloud_retry_attempts == 2
        assert er.cloud_retry_success is True
        assert er.cloud_retry_strategy == "same_prompt"
        assert er.cloud_retry_last_error == "empty_response"

        assert result.metadata["element_escalation_attempt_count"] == 1
        assert result.metadata["element_escalation_count"] == 1

    def test_cloud_escalation_retry_append_error_truncates(
        self, tmp_path, sample_manifest, sample_skeleton,
    ):
        """Retry context is appended and truncated for append_error strategy."""
        from startd8.micro_prime.models import (
            ElementResult,
            EscalationResult,
            EscalationReason,
            FileResult,
            TierClassification,
        )

        config = MicroPrimeConfig(
            cloud_escalation_max_attempts=2,
            cloud_escalation_retry_strategy="append_error",
            cloud_escalation_retry_max_chars=10,
        )
        gen = MicroPrimeCodeGenerator(
            config=config,
            manifest=sample_manifest,
            skeletons={"src/mypackage/utils.py": sample_skeleton},
            cloud_agent_spec="anthropic:claude-haiku-4-5-20251001",
            output_dir=tmp_path,
        )

        partial_result = FileResult(file_path="src/mypackage/utils.py")
        partial_result.element_results = [
            ElementResult(
                element_name="get_name",
                file_path="src/mypackage/utils.py",
                tier=TierClassification.SIMPLE,
                success=True,
                code="return key.upper()",
            ),
            ElementResult(
                element_name="get_value",
                file_path="src/mypackage/utils.py",
                tier=TierClassification.MODERATE,
                success=False,
                escalation=EscalationResult(
                    reason=EscalationReason.TIER_TOO_HIGH,
                    detail="Too complex",
                    last_error="bad_local",
                ),
            ),
        ]
        partial_result.filled_skeleton = sample_skeleton

        mock_direct = MagicMock(
            side_effect=[None, ("return len(key)", 10, 5)],
        )

        with patch.object(gen._engine, "process_file", return_value=partial_result), \
             patch(
                 "startd8.micro_prime.prime_adapter.urlopen",
                 return_value=self._make_ollama_mock(),
             ), \
             patch.object(
                 gen, "_direct_cloud_generate", mock_direct,
             ), \
             patch.object(gen, "_run_post_generation_repair", return_value=0):
            result = gen.generate(
                "Implement utils", {}, ["src/mypackage/utils.py"],
            )

        assert mock_direct.call_count == 2
        retry_contexts = [
            call.kwargs.get("retry_context", None)
            for call in mock_direct.call_args_list
        ]
        assert retry_contexts[0] == ""
        assert retry_contexts[1]
        assert len(retry_contexts[1]) <= 10

        er = partial_result.element_results[1]
        assert er.cloud_retry_attempts == 2
        assert er.cloud_retry_success is True
        assert er.cloud_retry_strategy == "append_error"

        assert result.metadata["element_escalation_attempt_count"] == 1
        assert result.metadata["element_escalation_count"] == 1


class TestPostGenerationRepair:
    """Tests for post-generation file-level repair."""

    def _make_ollama_mock(self):
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"models": [{"name": "startd8-coder:latest"}]}'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        return mock_response

    def test_repair_called_after_file_writes(
        self, tmp_path, sample_manifest, filled_skeleton,
    ):
        """_run_post_generation_repair is invoked on generated files."""
        gen = MicroPrimeCodeGenerator(
            manifest=sample_manifest,
            skeletons={"src/mypackage/utils.py": filled_skeleton},
            output_dir=tmp_path,
        )

        with patch(
            "startd8.micro_prime.prime_adapter.urlopen",
            return_value=self._make_ollama_mock(),
        ), patch.object(
            gen, "_run_post_generation_repair", return_value=0,
        ) as mock_repair:
            result = gen.generate(
                "Implement utils", {}, ["src/mypackage/utils.py"],
            )

        # Repair should have been called with the generated file paths
        mock_repair.assert_called_once()
        call_args = mock_repair.call_args[0][0]
        assert len(call_args) >= 1
        assert all(isinstance(p, Path) for p in call_args)

    def test_repair_import_error_caught_gracefully(self, tmp_path):
        """ImportError on repair imports is caught — generation is not blocked."""
        gen = MicroPrimeCodeGenerator(output_dir=tmp_path)
        test_file = tmp_path / "test.py"
        test_file.write_text("x = 1\n")

        with patch(
            "builtins.__import__",
            side_effect=lambda name, *a, **kw: (
                __builtins__["__import__"](name, *a, **kw)
                if not name.startswith("startd8.contractors.checkpoint")
                else (_ for _ in ()).throw(ImportError("no checkpoint"))
            ),
        ):
            # Use direct call — ImportError should be caught
            result = gen._run_post_generation_repair([test_file])
        assert result == 0

    def test_repair_import_error_via_mock(self, tmp_path):
        """ImportError on repair imports caught gracefully (mock approach)."""
        gen = MicroPrimeCodeGenerator(output_dir=tmp_path)
        test_file = tmp_path / "test.py"
        test_file.write_text("x = 1\n")

        with patch.dict("sys.modules", {"startd8.contractors.checkpoint": None}):
            result = gen._run_post_generation_repair([test_file])
        assert result == 0

    def test_repair_skipped_on_empty_files(self, tmp_path):
        """No repair when generated_files is empty."""
        gen = MicroPrimeCodeGenerator(output_dir=tmp_path)
        result = gen._run_post_generation_repair([])
        assert result == 0

    def test_repair_skips_vue_only_paths(self, tmp_path):
        """REQ-VUE-B-006: Python checkpoint must not run on ``.vue`` outputs."""
        from unittest.mock import patch

        gen = MicroPrimeCodeGenerator(output_dir=tmp_path)
        vue = tmp_path / "App.vue"
        vue.write_text('<script setup>const x = 1</script>\n')
        with patch(
            "startd8.contractors.checkpoint.IntegrationCheckpoint",
        ) as mock_cp:
            result = gen._run_post_generation_repair([vue])
        assert result == 0
        mock_cp.assert_not_called()


class TestFillRateSuccessCriteria:
    """Tests for element fill-rate success criteria."""

    def _make_ollama_mock(self):
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"models": [{"name": "startd8-coder:latest"}]}'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        return mock_response

    def _make_file_result(self, file_path, successes, failures):
        """Create a FileResult with the specified success/failure counts."""
        from startd8.micro_prime.models import (
            ElementResult,
            EscalationResult,
            EscalationReason,
            FileResult,
            TierClassification,
        )

        elements = []
        for i in range(successes):
            elements.append(ElementResult(
                element_name=f"ok_{i}",
                file_path=file_path,
                tier=TierClassification.SIMPLE,
                success=True,
                code="pass",
            ))
        for i in range(failures):
            elements.append(ElementResult(
                element_name=f"fail_{i}",
                file_path=file_path,
                tier=TierClassification.MODERATE,
                success=False,
                escalation=EscalationResult(
                    reason=EscalationReason.TIER_TOO_HIGH,
                    detail="Too complex",
                ),
            ))

        fr = FileResult(file_path=file_path)
        fr.element_results = elements
        fr.filled_skeleton = "# skeleton\nclass Foo:\n    pass\n"
        return fr

    def test_low_fill_rate_returns_failure(
        self, tmp_path, sample_manifest, sample_skeleton,
    ):
        """1/10 elements → success=False (10% < 50% threshold)."""
        gen = MicroPrimeCodeGenerator(
            manifest=sample_manifest,
            skeletons={"src/mypackage/utils.py": sample_skeleton},
            output_dir=tmp_path,
        )

        fr = self._make_file_result("src/mypackage/utils.py", 1, 9)

        with patch.object(gen._engine, "process_file", return_value=fr), \
             patch(
                 "startd8.micro_prime.prime_adapter.urlopen",
                 return_value=self._make_ollama_mock(),
             ), \
             patch.object(gen, "_run_post_generation_repair", return_value=0):
            result = gen.generate(
                "Implement utils", {}, ["src/mypackage/utils.py"],
            )

        assert result.success is False
        assert "src/mypackage/utils.py" in result.metadata["incomplete_files"]

    def test_high_fill_rate_returns_success(
        self, tmp_path, sample_manifest, sample_skeleton,
    ):
        """8/10 elements → success=True (80% >= 50% threshold)."""
        gen = MicroPrimeCodeGenerator(
            manifest=sample_manifest,
            skeletons={"src/mypackage/utils.py": sample_skeleton},
            output_dir=tmp_path,
        )

        fr = self._make_file_result("src/mypackage/utils.py", 8, 2)

        with patch.object(gen._engine, "process_file", return_value=fr), \
             patch(
                 "startd8.micro_prime.prime_adapter.urlopen",
                 return_value=self._make_ollama_mock(),
             ), \
             patch.object(gen, "_run_post_generation_repair", return_value=0):
            result = gen.generate(
                "Implement utils", {}, ["src/mypackage/utils.py"],
            )

        assert result.success is True
        assert result.metadata["incomplete_files"] == []

    def test_boundary_fill_rate_returns_success(
        self, tmp_path, sample_manifest, sample_skeleton,
    ):
        """5/10 elements → success=True (50% == 50% threshold, >=)."""
        gen = MicroPrimeCodeGenerator(
            manifest=sample_manifest,
            skeletons={"src/mypackage/utils.py": sample_skeleton},
            output_dir=tmp_path,
        )

        fr = self._make_file_result("src/mypackage/utils.py", 5, 5)

        with patch.object(gen._engine, "process_file", return_value=fr), \
             patch(
                 "startd8.micro_prime.prime_adapter.urlopen",
                 return_value=self._make_ollama_mock(),
             ), \
             patch.object(gen, "_run_post_generation_repair", return_value=0):
            result = gen.generate(
                "Implement utils", {}, ["src/mypackage/utils.py"],
            )

        assert result.success is True

    def test_full_fill_rate_unchanged(
        self, tmp_path, sample_manifest, sample_skeleton,
    ):
        """100% fill rate still passes (existing behavior preserved)."""
        gen = MicroPrimeCodeGenerator(
            manifest=sample_manifest,
            skeletons={"src/mypackage/utils.py": sample_skeleton},
            output_dir=tmp_path,
        )

        with patch(
            "startd8.micro_prime.prime_adapter.urlopen",
            return_value=self._make_ollama_mock(),
        ), patch.object(gen, "_run_post_generation_repair", return_value=0):
            result = gen.generate(
                "Implement utils", {}, ["src/mypackage/utils.py"],
            )

        # Default engine processes elements — should succeed with default fill rate
        assert result.metadata.get("effective_file_count") is not None

    def test_metadata_includes_fill_rate_fields(
        self, tmp_path, sample_manifest, sample_skeleton,
    ):
        """Metadata contains effective_file_count and incomplete_files."""
        gen = MicroPrimeCodeGenerator(
            manifest=sample_manifest,
            skeletons={"src/mypackage/utils.py": sample_skeleton},
            output_dir=tmp_path,
        )

        with patch(
            "startd8.micro_prime.prime_adapter.urlopen",
            return_value=self._make_ollama_mock(),
        ), patch.object(gen, "_run_post_generation_repair", return_value=0):
            result = gen.generate(
                "Implement utils", {}, ["src/mypackage/utils.py"],
            )

        assert "effective_file_count" in result.metadata
        assert "incomplete_files" in result.metadata


class TestDesignDocSectionsPassedToEngine:
    """REQ-DDS-002: Adapter extracts design_doc_sections from context and forwards."""

    def test_design_sections_forwarded(self, sample_manifest, sample_skeleton):
        """Engine.process_file called with design_doc_sections from context."""
        gen = MicroPrimeCodeGenerator(
            manifest=sample_manifest,
            skeletons={"src/mypackage/utils.py": sample_skeleton},
        )
        sections = ["Stage 1: Use ChatGPT for embeddings", "Error handling"]
        context = {
            "manifest": sample_manifest,
            "skeletons": {"src/mypackage/utils.py": sample_skeleton},
            "design_doc_sections": sections,
        }
        with patch.object(gen._engine, "process_file", wraps=gen._engine.process_file) as mock_pf:
            gen.generate(
                "implement features",
                context,
                ["src/mypackage/utils.py"],
            )
            if mock_pf.called:
                call_kwargs = mock_pf.call_args
                # Check that design_doc_sections was passed
                assert call_kwargs.kwargs.get("design_doc_sections") == sections


class TestDetectAssemblyDefect:
    """Tests for the _detect_assembly_defect helper."""

    def test_clean_file_returns_none(self) -> None:
        from startd8.micro_prime.prime_adapter import _detect_assembly_defect

        code = "def greet():\n    return 'hello'\n"
        assert _detect_assembly_defect(code, "greet.py") is None

    def test_detects_not_implemented_stubs(self) -> None:
        from startd8.micro_prime.prime_adapter import _detect_assembly_defect

        code = "def greet():\n    raise NotImplementedError\n"
        result = _detect_assembly_defect(code, "greet.py")
        assert result is not None
        assert "NotImplementedError" in result

    def test_detects_skeleton_marker(self) -> None:
        from startd8.micro_prime.prime_adapter import _detect_assembly_defect

        code = "# [STARTD8-SKELETON]\ndef greet():\n    return 'hello'\n"
        result = _detect_assembly_defect(code, "greet.py")
        assert result is not None
        assert "SKELETON" in result

    def test_detects_nested_duplicate_function(self) -> None:
        from startd8.micro_prime.prime_adapter import _detect_assembly_defect

        code = (
            "def foo():\n"
            "    import os\n"
            "    def foo():\n"
            "        return 1\n"
        )
        result = _detect_assembly_defect(code, "foo.py")
        assert result is not None
        assert "nested duplicate" in result
        assert "foo" in result

    def test_allows_differently_named_nested_function(self) -> None:
        from startd8.micro_prime.prime_adapter import _detect_assembly_defect

        code = "def foo():\n    def bar():\n        return 1\n    return bar()\n"
        assert _detect_assembly_defect(code, "foo.py") is None

    def test_syntax_error_returns_defect(self) -> None:
        from startd8.micro_prime.prime_adapter import _detect_assembly_defect

        code = "def foo(\n"  # invalid syntax
        result = _detect_assembly_defect(code, "foo.py")
        assert result is not None
        assert "SyntaxError" in result

    def test_non_python_skips_ast_checks(self) -> None:
        from startd8.micro_prime.prime_adapter import _detect_assembly_defect

        # Non-.py file with nested function text should not trigger AST check
        code = "def foo():\n    def foo():\n        pass\n"
        assert _detect_assembly_defect(code, "foo.html") is None

    def test_detects_nested_duplicate_class(self) -> None:
        """Nested duplicate class definitions are caught (splicer over-generation)."""
        from startd8.micro_prime.prime_adapter import _detect_assembly_defect

        code = (
            "class EmailService:\n"
            "    class EmailService:\n"
            "        def send(self):\n"
            "            pass\n"
            "    def send(self):\n"
            "        pass\n"
        )
        result = _detect_assembly_defect(code, "email.py")
        assert result is not None
        assert "nested duplicate" in result
        assert "class" in result
        assert "EmailService" in result

    def test_allows_differently_named_nested_class(self) -> None:
        """A nested class with a different name is not a defect."""
        from startd8.micro_prime.prime_adapter import _detect_assembly_defect

        code = (
            "class Outer:\n"
            "    class Inner:\n"
            "        pass\n"
        )
        assert _detect_assembly_defect(code, "nested.py") is None
