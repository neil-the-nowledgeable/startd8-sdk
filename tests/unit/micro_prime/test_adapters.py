"""Tests for the Micro Prime workflow adapters (REQ-MP-503–504)."""

from __future__ import annotations

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
