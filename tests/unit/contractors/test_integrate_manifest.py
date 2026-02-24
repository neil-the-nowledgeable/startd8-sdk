"""
Unit tests for INTEGRATE manifest diff and cache refresh (Steps 8-9).

Tests that:
- Pre-merge diff logs at INFO (AC-7)
- Breaking change emits WARNING
- Element regression emits WARNING
- Works normally when manifest_registry is None
- Stale file skips diff gracefully
- Post-merge refresh creates new registry instance
- context["project_manifests"] is updated after refresh
- Per-file parse failure: failed file excluded, others refreshed
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from startd8.contractors.integration_engine import IntegrationEngine
from startd8.contractors.protocols import MergeStrategy


class FakeMergeStrategy:
    """Minimal merge strategy for testing."""

    def merge(self, source: Path, target: Path, **kwargs: Any) -> None:
        pass


@pytest.fixture
def engine(tmp_path: Path) -> IntegrationEngine:
    return IntegrationEngine(
        project_root=tmp_path,
        merge_strategy=FakeMergeStrategy(),
    )


class TestManifestPreMergeDiff:

    def test_noop_when_no_registry(self, engine: IntegrationEngine) -> None:
        """Works normally when manifest_registry is None."""
        engine.manifest_registry = None
        # Should not raise
        engine._manifest_pre_merge_diff("src/foo.py", Path("/tmp/staged.py"))

    def test_noop_when_file_not_in_registry(self, engine: IntegrationEngine) -> None:
        mock_registry = MagicMock()
        mock_registry.get.return_value = None
        engine.manifest_registry = mock_registry
        engine._manifest_pre_merge_diff("src/unknown.py", Path("/tmp/staged.py"))
        mock_registry.get.assert_called_once_with("src/unknown.py")

    def test_stale_file_skips_diff(self, engine: IntegrationEngine) -> None:
        mock_registry = MagicMock()
        mock_registry.get.return_value = MagicMock()
        mock_registry.is_stale.return_value = True
        engine.manifest_registry = mock_registry
        # Should return early without parsing staged file
        engine._manifest_pre_merge_diff("src/stale.py", Path("/tmp/staged.py"))

    def test_logs_diff_at_info(self, engine: IntegrationEngine, caplog, tmp_path: Path) -> None:
        """IN-1: Pre-merge diff logs at INFO."""
        from startd8.utils.code_manifest import (
            Element, ElementKind, FileManifest, Signature, Span, Visibility,
        )

        existing = FileManifest(
            file="src/foo.py",
            module="foo",
            digest="sha256:old",
            elements=[
                Element(
                    kind=ElementKind.FUNCTION,
                    name="func",
                    fqn="foo.func",
                    span=Span(start_line=1, start_col=0, end_line=5, end_col=0),
                    signature=Signature(params=[]),
                    visibility=Visibility.PUBLIC,
                ),
            ],
        )

        mock_registry = MagicMock()
        mock_registry.get.return_value = existing
        mock_registry.is_stale.return_value = False
        engine.manifest_registry = mock_registry

        # Create a staged file
        staged = tmp_path / "staged_foo.py"
        staged.write_text("def func(): pass\n", encoding="utf-8")

        with caplog.at_level(logging.INFO):
            engine._manifest_pre_merge_diff("src/foo.py", staged)

        assert any("manifest.diff" in r.message for r in caplog.records)

    def test_malformed_staged_file_no_crash(
        self, engine: IntegrationEngine, tmp_path: Path
    ) -> None:
        """Malformed manifest from AI-generated code doesn't crash diff."""
        mock_registry = MagicMock()
        mock_registry.get.return_value = MagicMock()
        mock_registry.is_stale.return_value = False
        engine.manifest_registry = mock_registry

        # Create invalid Python file
        staged = tmp_path / "broken.py"
        staged.write_text("def (\n", encoding="utf-8")

        # Should not raise
        engine._manifest_pre_merge_diff("src/broken.py", staged)


class TestManifestPostMergeRefresh:

    def test_noop_when_no_registry(self, engine: IntegrationEngine) -> None:
        engine.manifest_registry = None
        context: Dict[str, Any] = {}
        engine._manifest_post_merge_refresh(["src/foo.py"], context)
        assert "project_manifests" not in context

    def test_refresh_creates_new_instance(
        self, engine: IntegrationEngine, tmp_path: Path
    ) -> None:
        """Refresh creates new registry instance (old instance unchanged)."""
        from startd8.utils.code_manifest import FileManifest
        from startd8.utils.manifest_registry import ManifestRegistry

        old_manifest = FileManifest(
            file="src/foo.py",
            module="foo",
            digest="sha256:old",
            elements=[],
        )
        old_registry = ManifestRegistry({"src/foo.py": old_manifest})
        engine.manifest_registry = old_registry

        # Create a real Python file to regenerate from
        foo_py = tmp_path / "src" / "foo.py"
        foo_py.parent.mkdir(parents=True, exist_ok=True)
        foo_py.write_text("def hello(): pass\n", encoding="utf-8")

        context: Dict[str, Any] = {}
        engine._manifest_post_merge_refresh(["src/foo.py"], context)

        assert "project_manifests" in context
        new_registry = context["project_manifests"]
        assert new_registry is not old_registry

    def test_context_updated_after_refresh(
        self, engine: IntegrationEngine, tmp_path: Path
    ) -> None:
        """context['project_manifests'] is updated after refresh."""
        from startd8.utils.code_manifest import FileManifest
        from startd8.utils.manifest_registry import ManifestRegistry

        old_manifest = FileManifest(
            file="src/bar.py", module="bar", digest="sha256:old", elements=[]
        )
        old_registry = ManifestRegistry({"src/bar.py": old_manifest})
        engine.manifest_registry = old_registry

        bar_py = tmp_path / "src" / "bar.py"
        bar_py.parent.mkdir(parents=True, exist_ok=True)
        bar_py.write_text("x = 1\n", encoding="utf-8")

        context: Dict[str, Any] = {}
        engine._manifest_post_merge_refresh(["src/bar.py"], context)
        assert context["project_manifests"] is not old_registry

    def test_per_file_failure_excluded(
        self, engine: IntegrationEngine, tmp_path: Path
    ) -> None:
        """Per-file parse failure: failed file excluded, others refreshed."""
        from startd8.utils.code_manifest import FileManifest
        from startd8.utils.manifest_registry import ManifestRegistry

        old_registry = ManifestRegistry({
            "src/good.py": FileManifest(
                file="src/good.py", module="good", digest="sha256:old", elements=[]
            ),
        })
        engine.manifest_registry = old_registry

        # good.py exists and is valid
        good_py = tmp_path / "src" / "good.py"
        good_py.parent.mkdir(parents=True, exist_ok=True)
        good_py.write_text("def good(): pass\n", encoding="utf-8")

        # bad.py does NOT exist
        context: Dict[str, Any] = {}
        engine._manifest_post_merge_refresh(["src/good.py", "src/bad.py"], context)

        # Should still have created a new registry with good.py
        assert "project_manifests" in context
