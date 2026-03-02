"""Tests for dashboard_creator.output — output persistence."""

import json
from pathlib import Path

import pytest

from startd8.dashboard_creator.output import PersistenceResult, persist_dashboard


class TestPersistDashboard:
    def test_json_written_to_correct_path(self, tmp_path):
        dashboard = {"title": "Test", "uid": "cc-startd8-test", "panels": []}
        result = persist_dashboard(dashboard, "cc-startd8-test", output_dir=tmp_path)
        assert result.json_path == tmp_path / "cc-startd8-test.json"
        assert result.json_path.is_file()

    def test_deterministic_output(self, tmp_path):
        dashboard = {"b_key": 2, "a_key": 1, "panels": [{"z": 1, "a": 2}]}
        persist_dashboard(dashboard, "test1", output_dir=tmp_path)
        content1 = (tmp_path / "test1.json").read_text()
        # Write again — should be identical
        persist_dashboard(dashboard, "test1", output_dir=tmp_path)
        content2 = (tmp_path / "test1.json").read_text()
        assert content1 == content2

    def test_sort_keys(self, tmp_path):
        dashboard = {"z_key": 1, "a_key": 2}
        persist_dashboard(dashboard, "sorted", output_dir=tmp_path)
        content = (tmp_path / "sorted.json").read_text()
        parsed = json.loads(content)
        keys = list(parsed.keys())
        assert keys == sorted(keys)

    def test_trailing_newline(self, tmp_path):
        persist_dashboard({"title": "T"}, "uid", output_dir=tmp_path)
        content = (tmp_path / "uid.json").read_text()
        assert content.endswith("\n")

    def test_parent_directories_created(self, tmp_path):
        deep_dir = tmp_path / "a" / "b" / "c"
        persist_dashboard({"title": "T"}, "uid", output_dir=deep_dir)
        assert (deep_dir / "uid.json").is_file()

    def test_existing_file_overwritten(self, tmp_path):
        persist_dashboard({"version": 1}, "uid", output_dir=tmp_path)
        persist_dashboard({"version": 2}, "uid", output_dir=tmp_path)
        data = json.loads((tmp_path / "uid.json").read_text())
        assert data["version"] == 2

    def test_libsonnet_written_when_provided(self, tmp_path):
        lib_dir = tmp_path / "mixin" / "dashboards"
        result = persist_dashboard(
            {"title": "T"},
            "cc-startd8-my-dash",
            output_dir=tmp_path,
            libsonnet_source="local x = 1; x",
            libsonnet_dir=lib_dir,
        )
        assert result.libsonnet_path is not None
        assert result.libsonnet_path.is_file()
        assert result.libsonnet_path.read_text() == "local x = 1; x"

    def test_libsonnet_not_written_without_dir(self, tmp_path):
        result = persist_dashboard(
            {"title": "T"},
            "cc-startd8-test",
            output_dir=tmp_path,
            libsonnet_source="local x = 1;",
            libsonnet_dir=None,
        )
        assert result.libsonnet_path is None

    def test_libsonnet_not_written_without_source(self, tmp_path):
        result = persist_dashboard(
            {"title": "T"},
            "cc-startd8-test",
            output_dir=tmp_path,
            libsonnet_source=None,
            libsonnet_dir=tmp_path,
        )
        assert result.libsonnet_path is None
