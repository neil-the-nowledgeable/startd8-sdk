"""Tests for complexity.signals — cross-file edges and feature signal extraction."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from startd8.complexity.signals import (
    detect_cross_file_edges,
    extract_signals_from_feature,
)


# ── detect_cross_file_edges ──────────────────────────────────────────


class TestDetectCrossFileEdges:
    def test_finds_cross_file_call(self):
        registry = MagicMock()
        registry.call_graph.return_value = {
            "mod_a.func_a": {"mod_b.func_b"},
        }
        manifest_a = MagicMock()
        elem_a = MagicMock()
        elem_a.fqn = "mod_a.func_a"
        manifest_a.elements = [elem_a]

        manifest_b = MagicMock()
        elem_b = MagicMock()
        elem_b.fqn = "mod_b.func_b"
        manifest_b.elements = [elem_b]

        registry.get.side_effect = lambda path: {
            "a.py": manifest_a,
            "b.py": manifest_b,
        }.get(path)

        flatten = lambda elems: elems  # noqa: E731

        assert detect_cross_file_edges(["a.py", "b.py"], registry, flatten)

    def test_no_cross_file_call(self):
        registry = MagicMock()
        registry.call_graph.return_value = {
            "mod_a.func_a": {"mod_a.func_a2"},
        }
        manifest_a = MagicMock()
        elem_a = MagicMock()
        elem_a.fqn = "mod_a.func_a"
        elem_a2 = MagicMock()
        elem_a2.fqn = "mod_a.func_a2"
        manifest_a.elements = [elem_a, elem_a2]

        registry.get.side_effect = lambda path: {
            "a.py": manifest_a,
        }.get(path)

        flatten = lambda elems: elems  # noqa: E731

        assert not detect_cross_file_edges(["a.py", "b.py"], registry, flatten)

    def test_graceful_on_registry_error(self):
        registry = MagicMock()
        registry.call_graph.side_effect = AttributeError("no call_graph")
        assert not detect_cross_file_edges(["a.py", "b.py"], registry, None)


# ── extract_signals_from_feature ─────────────────────────────────────


class TestExtractSignalsFromFeature:
    def test_basic_create_mode(self, tmp_path):
        """Non-existent target files → edit_mode='create'."""
        feature = MagicMock()
        feature.target_files = ["new_module.py"]
        feature.description = "Implement a new module with some logic"
        feature.metadata = {}

        signals = extract_signals_from_feature(feature, tmp_path)
        assert signals.edit_mode == "create"
        assert signals.target_file_count == 1
        assert signals.estimated_loc > 0

    def test_edit_mode_when_file_exists(self, tmp_path):
        """Existing target file → edit_mode='edit'."""
        (tmp_path / "existing.py").write_text("pass\n")
        feature = MagicMock()
        feature.target_files = ["existing.py"]
        feature.description = "Update existing module"
        feature.metadata = {}

        signals = extract_signals_from_feature(feature, tmp_path)
        assert signals.edit_mode == "edit"

    def test_estimated_loc_from_metadata(self, tmp_path):
        feature = MagicMock()
        feature.target_files = ["mod.py"]
        feature.description = "Short"
        feature.metadata = {"estimated_loc": 250}

        signals = extract_signals_from_feature(feature, tmp_path)
        assert signals.estimated_loc == 250

    def test_estimated_loc_fallback_from_description(self, tmp_path):
        feature = MagicMock()
        feature.target_files = ["mod.py"]
        feature.description = "x" * 300  # 300 chars → ~100 loc
        feature.metadata = {}

        signals = extract_signals_from_feature(feature, tmp_path)
        assert signals.estimated_loc == 100

    def test_blast_radius_detection(self, tmp_path):
        """A file that imports a target should count toward blast_radius."""
        (tmp_path / "target.py").write_text("def foo(): pass\n")
        (tmp_path / "importer.py").write_text("import target\n")

        feature = MagicMock()
        feature.target_files = ["target.py"]
        feature.description = "Update target"
        feature.metadata = {}

        signals = extract_signals_from_feature(feature, tmp_path)
        assert signals.blast_radius >= 1

    def test_never_raises(self, tmp_path):
        """Even with a completely broken feature object, no exception."""
        feature = MagicMock()
        feature.target_files = None
        feature.description = None
        feature.metadata = None

        signals = extract_signals_from_feature(feature, tmp_path)
        assert signals.target_file_count >= 1
        assert signals.edit_mode == "create"

    def test_multi_file_cross_imports(self, tmp_path):
        (tmp_path / "a.py").write_text("import b\n")
        (tmp_path / "b.py").write_text("def helper(): pass\n")

        feature = MagicMock()
        feature.target_files = ["a.py", "b.py"]
        feature.description = "Update both"
        feature.metadata = {}

        signals = extract_signals_from_feature(feature, tmp_path)
        assert signals.target_file_count == 2
        assert signals.has_cross_file_edges is True

    def test_manifest_coverage_full(self, tmp_path):
        manifest = MagicMock()
        manifest.get.return_value = MagicMock()  # always found

        feature = MagicMock()
        feature.target_files = ["a.py"]
        feature.description = "test"
        feature.metadata = {}

        signals = extract_signals_from_feature(feature, tmp_path, manifest=manifest)
        assert signals.manifest_coverage == "full"

    def test_manifest_coverage_none_when_missing(self, tmp_path):
        manifest = MagicMock()
        manifest.get.return_value = None  # not found

        feature = MagicMock()
        feature.target_files = ["a.py"]
        feature.description = "test"
        feature.metadata = {}

        signals = extract_signals_from_feature(feature, tmp_path, manifest=manifest)
        assert signals.manifest_coverage == "none"
