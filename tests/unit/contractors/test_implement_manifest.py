"""
Unit tests for IMPLEMENT phase manifest enrichment (Step 5 + Step 12).

Tests that:
- Prompt contains '## Code Structure' when manifest data is available (AC-5)
- Prompt omits it when manifest is None
- Section respects budget (AC-6, AC-11)
- Existing callers without manifest_registry in HandlerConfig continue to work
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest


class FakeChunk:
    """Minimal stub matching DevelopmentChunk interface for testing."""

    def __init__(
        self,
        file_targets: List[str] | None = None,
        metadata: Dict[str, Any] | None = None,
        description: str = "Implement the feature.",
    ) -> None:
        self.file_targets = file_targets or []
        self.metadata = metadata or {}
        self.description = description
        self.chunk_id = "test-chunk"
        self.task_id = "T-001"


class TestBuildManifestContext:
    """Tests for DevelopmentPhase._build_manifest_context."""

    def _get_build_method(self):
        """Import the static method under test."""
        from startd8.contractors.artisan_phases.development import LeadContractorChunkExecutor
        return LeadContractorChunkExecutor._build_manifest_context

    def test_includes_code_structure_header_when_manifest_present(self) -> None:
        build = self._get_build_method()
        chunk = FakeChunk(
            metadata={"_manifest_context": "- mod.func(x: int) -> str  [1-5]"}
        )
        result = build(chunk)
        combined = "\n".join(result)
        assert "## Code Structure" in combined
        assert "mod.func" in combined

    def test_omits_when_no_manifest(self) -> None:
        build = self._get_build_method()
        chunk = FakeChunk(metadata={})
        result = build(chunk)
        assert result == []

    def test_omits_when_manifest_context_is_empty_string(self) -> None:
        build = self._get_build_method()
        chunk = FakeChunk(metadata={"_manifest_context": ""})
        result = build(chunk)
        assert result == []

    def test_preserves_manifest_content(self) -> None:
        build = self._get_build_method()
        content = "### src/foo.py\n- foo.bar(x: int)  [10-20]\n- foo.baz()  [25-30]"
        chunk = FakeChunk(metadata={"_manifest_context": content})
        result = build(chunk)
        combined = "\n".join(result)
        assert "foo.bar(x: int)" in combined
        assert "foo.baz()" in combined


class TestHandlerConfigManifestFields:
    """Tests that HandlerConfig accepts manifest fields without breaking existing callers."""

    def test_default_manifest_fields(self) -> None:
        from startd8.contractors.context_seed_handlers import HandlerConfig
        config = HandlerConfig()
        assert config.manifest_consumption_enabled is True
        assert config.manifest_context_budget == 4000
        assert config.manifest_registry is None

    def test_existing_callers_unaffected(self) -> None:
        """Callers that don't pass manifest fields should work normally."""
        from startd8.contractors.context_seed_handlers import HandlerConfig
        config = HandlerConfig(lead_agent="mock:test", drafter_agent="mock:test")
        assert config.manifest_registry is None
        assert config.manifest_consumption_enabled is True

    def test_kill_switch_disables(self) -> None:
        from startd8.contractors.context_seed_handlers import HandlerConfig
        config = HandlerConfig(manifest_consumption_enabled=False)
        assert config.manifest_consumption_enabled is False

    def test_manifest_registry_injectable(self) -> None:
        from startd8.contractors.context_seed_handlers import HandlerConfig
        mock_registry = MagicMock()
        config = HandlerConfig(manifest_registry=mock_registry)
        assert config.manifest_registry is mock_registry


class TestPostGenerateManifestDiff:
    """Step 12 (IM-5): Post-generation manifest comparison."""

    def _make_executor(self, tmp_path: Path):
        from startd8.contractors.artisan_phases.development import (
            LeadContractorChunkExecutor,
        )
        return LeadContractorChunkExecutor(
            lead_agent="mock:lead",
            drafter_agent="mock:drafter",
            output_dir=tmp_path,
            project_root=tmp_path,
        )

    def test_noop_when_no_registry(self, tmp_path: Path) -> None:
        executor = self._make_executor(tmp_path)
        chunk = FakeChunk(file_targets=["src/foo.py"])
        context: Dict[str, Any] = {}  # No project_manifests
        # Should not raise
        executor._manifest_post_generate_diff([], chunk, context)

    def test_noop_for_new_file(self, tmp_path: Path) -> None:
        """New file (not in registry) produces no diff."""
        executor = self._make_executor(tmp_path)
        mock_registry = MagicMock()
        mock_registry.get.return_value = None  # Not in registry
        context = {"project_manifests": mock_registry}

        gen_file = tmp_path / "src" / "new.py"
        gen_file.parent.mkdir(parents=True, exist_ok=True)
        gen_file.write_text("def hello(): pass\n", encoding="utf-8")

        chunk = FakeChunk(file_targets=["src/new.py"])
        executor._manifest_post_generate_diff([gen_file], chunk, context)
        assert "_manifest_removed_public" not in chunk.metadata

    def test_warns_on_removed_public_elements(self, tmp_path: Path) -> None:
        """If generated code removes public elements, logs WARNING."""
        from startd8.utils.code_manifest import (
            Element, ElementKind, FileManifest, Signature, Span, Visibility,
        )
        from startd8.utils.manifest_registry import ManifestDiff

        executor = self._make_executor(tmp_path)

        # Original manifest has a public function
        original = FileManifest(
            file="src/foo.py",
            module="foo",
            digest="sha256:old",
            elements=[
                Element(
                    kind=ElementKind.FUNCTION,
                    name="public_func",
                    fqn="foo.public_func",
                    span=Span(start_line=1, start_col=0, end_line=5, end_col=0),
                    signature=Signature(params=[]),
                    visibility=Visibility.PUBLIC,
                ),
            ],
        )

        mock_registry = MagicMock()
        mock_registry.get.return_value = original
        context = {"project_manifests": mock_registry}

        # Generated file is empty (removed the public function)
        gen_file = tmp_path / "src" / "foo.py"
        gen_file.parent.mkdir(parents=True, exist_ok=True)
        gen_file.write_text("# empty\n", encoding="utf-8")

        chunk = FakeChunk(file_targets=["src/foo.py"])
        executor._manifest_post_generate_diff([gen_file], chunk, context)
        assert "_manifest_removed_public" in chunk.metadata
        assert "src/foo.py" in chunk.metadata["_manifest_removed_public"]
        assert "foo.public_func" in chunk.metadata["_manifest_removed_public"]["src/foo.py"]

    def test_no_warning_when_elements_preserved(self, tmp_path: Path) -> None:
        """If generated code preserves public elements, no warning."""
        from startd8.utils.code_manifest import (
            Element, ElementKind, FileManifest, Signature, Span, Visibility,
        )

        executor = self._make_executor(tmp_path)

        original = FileManifest(
            file="src/foo.py",
            module="foo",
            digest="sha256:old",
            elements=[
                Element(
                    kind=ElementKind.FUNCTION,
                    name="my_func",
                    fqn="foo.my_func",
                    span=Span(start_line=1, start_col=0, end_line=3, end_col=0),
                    signature=Signature(params=[]),
                    visibility=Visibility.PUBLIC,
                ),
            ],
        )

        mock_registry = MagicMock()
        mock_registry.get.return_value = original
        context = {"project_manifests": mock_registry}

        # Generated file keeps the function
        gen_file = tmp_path / "src" / "foo.py"
        gen_file.parent.mkdir(parents=True, exist_ok=True)
        gen_file.write_text("def my_func():\n    pass\n", encoding="utf-8")

        chunk = FakeChunk(file_targets=["src/foo.py"])
        executor._manifest_post_generate_diff([gen_file], chunk, context)
        assert "_manifest_removed_public" not in chunk.metadata

    def test_parse_failure_does_not_crash(self, tmp_path: Path) -> None:
        """If generate_file_manifest fails, method doesn't crash."""
        executor = self._make_executor(tmp_path)

        mock_registry = MagicMock()
        mock_registry.get.return_value = MagicMock()
        context = {"project_manifests": mock_registry}

        # Write an invalid Python file
        gen_file = tmp_path / "src" / "bad.py"
        gen_file.parent.mkdir(parents=True, exist_ok=True)
        gen_file.write_text("def (:\n", encoding="utf-8")

        chunk = FakeChunk(file_targets=["src/bad.py"])
        # Should not raise
        executor._manifest_post_generate_diff([gen_file], chunk, context)
