"""Tests for dashboard_creator.manifest_sync — DC-201."""

from pathlib import Path

import pytest
import yaml

from startd8.dashboard_creator.manifest_sync import (
    build_dashboard_ref,
    extract_metrics_used,
    sync_manifest,
)
from startd8.dashboard_creator.models import DashboardSpec, PanelSpec, PanelType, TargetSpec


# ---------------------------------------------------------------------------
# extract_metrics_used
# ---------------------------------------------------------------------------


class TestExtractMetricsUsed:
    def test_single_metric_ref(self):
        spec = DashboardSpec(
            title="Test",
            panels=[
                PanelSpec(
                    type=PanelType.STAT, title="A",
                    expr="rate(${metrics.requestsTotal}[5m])",
                ),
            ],
        )
        assert extract_metrics_used(spec) == ["requestsTotal"]

    def test_multiple_metric_refs_deduped(self):
        spec = DashboardSpec(
            title="Test",
            panels=[
                PanelSpec(
                    type=PanelType.STAT, title="A",
                    expr="${metrics.requestsTotal}",
                ),
                PanelSpec(
                    type=PanelType.STAT, title="B",
                    expr="${metrics.requestsTotal}",
                ),
                PanelSpec(
                    type=PanelType.STAT, title="C",
                    expr="${metrics.tokensTotal}",
                ),
            ],
        )
        assert extract_metrics_used(spec) == ["requestsTotal", "tokensTotal"]

    def test_metric_refs_in_targets(self):
        spec = DashboardSpec(
            title="Test",
            panels=[
                PanelSpec(
                    type=PanelType.TIMESERIES, title="TS",
                    targets=[
                        TargetSpec(expr="rate(${metrics.costTotal}[5m])"),
                        TargetSpec(expr="${metrics.activeSessions}"),
                    ],
                ),
            ],
        )
        result = extract_metrics_used(spec)
        assert "costTotal" in result
        assert "activeSessions" in result

    def test_no_metric_refs_returns_empty(self):
        spec = DashboardSpec(
            title="Test",
            panels=[
                PanelSpec(type=PanelType.STAT, title="A", expr="up"),
            ],
        )
        assert extract_metrics_used(spec) == []

    def test_selector_refs_not_included(self):
        spec = DashboardSpec(
            title="Test",
            panels=[
                PanelSpec(
                    type=PanelType.STAT, title="A",
                    expr="${selectors.serviceName}",
                ),
            ],
        )
        assert extract_metrics_used(spec) == []


# ---------------------------------------------------------------------------
# build_dashboard_ref
# ---------------------------------------------------------------------------


class TestBuildDashboardRef:
    def test_builds_with_all_fields(self, tmp_path):
        json_path = tmp_path / "test.json"
        spec = DashboardSpec(
            title="My Dashboard",
            uid="cc-startd8-my-dashboard",
            tags=["test", "dev"],
            panels=[
                PanelSpec(
                    type=PanelType.STAT, title="A",
                    expr="${metrics.requestsTotal}",
                ),
            ],
            datasources={"prometheus": "mimir", "tempo": "tempo"},
        )
        ref = build_dashboard_ref(spec, json_path)
        assert ref.uid == "cc-startd8-my-dashboard"
        assert ref.title == "My Dashboard"
        assert ref.file_path == str(json_path)
        assert ref.tags == ["test", "dev"]
        assert ref.metrics_used == ["requestsTotal"]
        assert sorted(ref.datasources) == ["prometheus", "tempo"]


# ---------------------------------------------------------------------------
# sync_manifest
# ---------------------------------------------------------------------------


class TestSyncManifest:
    def _write_manifest(self, tmp_path, data):
        path = tmp_path / "observability-manifest.yaml"
        path.write_text(yaml.dump(data, default_flow_style=False))
        return path

    def test_new_dashboard_appended(self, tmp_path):
        manifest = self._write_manifest(tmp_path, {"dashboards": []})
        spec = DashboardSpec(
            title="New",
            uid="cc-startd8-new",
            panels=[PanelSpec(type=PanelType.STAT, title="A", expr="up")],
            tags=["tag1"],
        )
        result = sync_manifest(spec, tmp_path / "new.json", manifest)
        assert result is True
        data = yaml.safe_load(manifest.read_text())
        assert len(data["dashboards"]) == 1
        assert data["dashboards"][0]["uid"] == "cc-startd8-new"
        assert data["dashboards"][0]["tags"] == ["tag1"]

    def test_existing_dashboard_updated(self, tmp_path):
        manifest = self._write_manifest(tmp_path, {
            "dashboards": [
                {"uid": "cc-startd8-old", "title": "Old Title", "file_path": "old.json",
                 "datasources": [], "metrics_used": []},
            ],
        })
        spec = DashboardSpec(
            title="Updated Title",
            uid="cc-startd8-old",
            panels=[PanelSpec(type=PanelType.STAT, title="A", expr="up")],
        )
        result = sync_manifest(spec, tmp_path / "old.json", manifest)
        assert result is True
        data = yaml.safe_load(manifest.read_text())
        assert len(data["dashboards"]) == 1
        assert data["dashboards"][0]["title"] == "Updated Title"

    def test_missing_manifest_skips_without_error(self, tmp_path):
        spec = DashboardSpec(
            title="Test",
            uid="cc-startd8-test",
            panels=[PanelSpec(type=PanelType.STAT, title="A", expr="up")],
        )
        result = sync_manifest(spec, tmp_path / "test.json", tmp_path / "missing.yaml")
        assert result is False

    def test_none_manifest_path_skips(self, tmp_path):
        spec = DashboardSpec(
            title="Test",
            uid="cc-startd8-test",
            panels=[PanelSpec(type=PanelType.STAT, title="A", expr="up")],
        )
        result = sync_manifest(spec, tmp_path / "test.json", None)
        assert result is False

    def test_idempotent_resync(self, tmp_path):
        manifest = self._write_manifest(tmp_path, {"dashboards": []})
        spec = DashboardSpec(
            title="Idem",
            uid="cc-startd8-idem",
            panels=[PanelSpec(type=PanelType.STAT, title="A", expr="up")],
        )
        sync_manifest(spec, tmp_path / "idem.json", manifest)
        sync_manifest(spec, tmp_path / "idem.json", manifest)
        data = yaml.safe_load(manifest.read_text())
        assert len(data["dashboards"]) == 1

    def test_tags_propagated(self, tmp_path):
        manifest = self._write_manifest(tmp_path, {"dashboards": []})
        spec = DashboardSpec(
            title="Tagged",
            uid="cc-startd8-tagged",
            tags=["infra", "cost"],
            panels=[PanelSpec(type=PanelType.STAT, title="A", expr="up")],
        )
        sync_manifest(spec, tmp_path / "tagged.json", manifest)
        data = yaml.safe_load(manifest.read_text())
        assert data["dashboards"][0]["tags"] == ["infra", "cost"]
