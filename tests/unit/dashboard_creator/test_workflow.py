"""Tests for dashboard_creator.workflow — DashboardCreatorWorkflow."""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from startd8.dashboard_creator.workflow import DashboardCreatorWorkflow
from startd8.dashboard_creator.discovery import MixinContext, ToolchainInfo


@pytest.fixture
def workflow():
    return DashboardCreatorWorkflow()


@pytest.fixture
def mock_mixin(tmp_path):
    mixin = tmp_path / "startd8-mixin"
    (mixin / "lib").mkdir(parents=True)
    (mixin / "dashboards").mkdir()
    vendor = mixin / "vendor"
    vendor.mkdir()
    (vendor / "grafonnet").mkdir()
    (mixin / "config.libsonnet").write_text("{ _config+:: {} }")
    (mixin / "lib" / "panels.libsonnet").write_text("{}")
    (mixin / "lib" / "variables.libsonnet").write_text("{}")
    (mixin / "mixin.libsonnet").write_text("{}")
    return MixinContext(
        mixin_dir=mixin,
        panels_path=mixin / "lib" / "panels.libsonnet",
        variables_path=mixin / "lib" / "variables.libsonnet",
        config_path=mixin / "config.libsonnet",
        dashboards_dir=mixin / "dashboards",
        vendor_dir=vendor,
        mixin_libsonnet=mixin / "mixin.libsonnet",
    )


@pytest.fixture
def mock_toolchain():
    return ToolchainInfo(backend="binary", version="v0.20.0", binary_path="/usr/local/bin/jsonnet")


@pytest.fixture
def valid_spec():
    return {
        "title": "Test Dashboard",
        "panels": [
            {"type": "stat", "title": "Test Metric", "expr": "up"}
        ],
    }


@pytest.fixture
def compiled_json():
    return json.dumps({
        "title": "Test Dashboard",
        "uid": "cc-startd8-test-dashboard",
        "panels": [{"id": 1, "type": "stat", "title": "Test Metric"}],
        "schemaVersion": 39,
        "templating": {"list": []},
    })


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


class TestWorkflowMetadata:
    def test_workflow_id(self, workflow):
        assert workflow.metadata.workflow_id == "dashboard-create"

    def test_requires_no_agents(self, workflow):
        assert workflow.metadata.requires_agents is False

    def test_has_required_spec_input(self, workflow):
        input_names = [i.name for i in workflow.metadata.inputs]
        assert "spec" in input_names

    def test_has_optional_inputs(self, workflow):
        input_names = [i.name for i in workflow.metadata.inputs]
        assert "persist_source" in input_names
        assert "dry_run" in input_names
        assert "check" in input_names


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestWorkflowValidation:
    def test_missing_spec_returns_error(self, workflow):
        result = workflow.validate_config({})
        assert not result.valid
        assert any("spec" in e for e in result.errors)

    def test_valid_spec_passes(self, workflow, valid_spec):
        result = workflow.validate_config({"spec": valid_spec})
        assert result.valid

    def test_dry_run_and_check_mutually_exclusive(self, workflow, valid_spec):
        result = workflow.validate_config({
            "spec": valid_spec,
            "dry_run": True,
            "check": True,
        })
        assert not result.valid
        assert any("dry-run" in e or "check" in e for e in result.errors)


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


class TestWorkflowExecution:
    def test_dry_run_returns_jsonnet_source(
        self, workflow, valid_spec, mock_mixin, mock_toolchain
    ):
        with patch("startd8.dashboard_creator.workflow.discover_mixin", return_value=mock_mixin):
            with patch("startd8.dashboard_creator.workflow.detect_toolchain", return_value=mock_toolchain):
                result = workflow.run({"spec": valid_spec, "dry_run": True})
                assert result.success is True
                assert "jsonnet_source" in result.output
                assert "uid" in result.output

    def test_check_mode_compiles_but_no_write(
        self, workflow, valid_spec, mock_mixin, mock_toolchain, compiled_json
    ):
        with patch("startd8.dashboard_creator.workflow.discover_mixin", return_value=mock_mixin):
            with patch("startd8.dashboard_creator.workflow.detect_toolchain", return_value=mock_toolchain):
                with patch("startd8.dashboard_creator.workflow.compile_jsonnet_string") as mock_compile:
                    mock_compile.return_value = MagicMock(
                        json_str=compiled_json,
                        duration_ms=10,
                        backend="binary",
                    )
                    result = workflow.run({"spec": valid_spec, "check": True})
                    assert result.success is True
                    assert result.output["check"] == "passed"

    def test_full_run_produces_json_file(
        self, workflow, valid_spec, mock_mixin, mock_toolchain, compiled_json, tmp_path
    ):
        with patch("startd8.dashboard_creator.workflow.discover_mixin", return_value=mock_mixin):
            with patch("startd8.dashboard_creator.workflow.detect_toolchain", return_value=mock_toolchain):
                with patch("startd8.dashboard_creator.workflow.compile_jsonnet_string") as mock_compile:
                    mock_compile.return_value = MagicMock(
                        json_str=compiled_json,
                        duration_ms=10,
                        backend="binary",
                    )
                    result = workflow.run({
                        "spec": valid_spec,
                        "output_dir": str(tmp_path),
                    })
                    assert result.success is True
                    json_path = Path(result.output["json_path"])
                    assert json_path.is_file()
                    data = json.loads(json_path.read_text())
                    assert data["title"] == "Test Dashboard"

    def test_progress_callback_invoked(
        self, workflow, valid_spec, mock_mixin, mock_toolchain
    ):
        progress_calls = []

        def on_progress(current, total, message):
            progress_calls.append((current, total, message))

        with patch("startd8.dashboard_creator.workflow.discover_mixin", return_value=mock_mixin):
            with patch("startd8.dashboard_creator.workflow.detect_toolchain", return_value=mock_toolchain):
                workflow.run(
                    {"spec": valid_spec, "dry_run": True},
                    on_progress=on_progress,
                )
                assert len(progress_calls) > 0
                # First call should be step 0
                assert progress_calls[0][0] == 0

    def test_spec_from_yaml_file(
        self, workflow, valid_spec, mock_mixin, mock_toolchain, tmp_path
    ):
        import yaml
        spec_path = tmp_path / "spec.yaml"
        spec_path.write_text(yaml.dump(valid_spec))

        with patch("startd8.dashboard_creator.workflow.discover_mixin", return_value=mock_mixin):
            with patch("startd8.dashboard_creator.workflow.detect_toolchain", return_value=mock_toolchain):
                result = workflow.run({"spec": str(spec_path), "dry_run": True})
                assert result.success is True

    def test_invalid_spec_returns_error(self, workflow):
        result = workflow.run({"spec": {"panels": []}})  # Empty panels
        assert result.success is False
        assert "failed" in result.error.lower() or "validation" in result.error.lower()

    def test_full_run_includes_panel_count(
        self, workflow, valid_spec, mock_mixin, mock_toolchain, compiled_json, tmp_path
    ):
        with patch("startd8.dashboard_creator.workflow.discover_mixin", return_value=mock_mixin):
            with patch("startd8.dashboard_creator.workflow.detect_toolchain", return_value=mock_toolchain):
                with patch("startd8.dashboard_creator.workflow.compile_jsonnet_string") as mock_compile:
                    mock_compile.return_value = MagicMock(
                        json_str=compiled_json,
                        duration_ms=10,
                        backend="binary",
                    )
                    result = workflow.run({
                        "spec": valid_spec,
                        "output_dir": str(tmp_path),
                    })
                    assert result.success is True
                    assert result.output["panel_count"] == 1
                    assert result.output["dashboard_url"] is None


# ---------------------------------------------------------------------------
# Provisioning integration
# ---------------------------------------------------------------------------


class TestWorkflowProvisioning:
    def test_provision_without_token_fails_validation(self, workflow, valid_spec, monkeypatch):
        monkeypatch.delenv("GRAFANA_API_TOKEN", raising=False)
        result = workflow.validate_config({
            "spec": valid_spec,
            "provision": True,
        })
        assert not result.valid
        assert any("GRAFANA_API_TOKEN" in e for e in result.errors)

    def test_provision_calls_grafana(
        self, workflow, valid_spec, mock_mixin, mock_toolchain, compiled_json,
        tmp_path, monkeypatch,
    ):
        monkeypatch.setenv("GRAFANA_API_TOKEN", "test-token")

        mock_prov_result = MagicMock()
        mock_prov_result.success = True
        mock_prov_result.dashboard_url = "https://grafana.local/d/test-uid/test"

        with patch("startd8.dashboard_creator.workflow.discover_mixin", return_value=mock_mixin), \
             patch("startd8.dashboard_creator.workflow.detect_toolchain", return_value=mock_toolchain), \
             patch("startd8.dashboard_creator.workflow.compile_jsonnet_string") as mock_compile, \
             patch("startd8.dashboard_creator.grafana_client.GrafanaClient") as MockClient, \
             patch("startd8.dashboard_creator.provisioning.provision_dashboard", return_value=mock_prov_result):
            mock_compile.return_value = MagicMock(
                json_str=compiled_json, duration_ms=10, backend="binary",
            )
            result = workflow.run({
                "spec": valid_spec,
                "output_dir": str(tmp_path),
                "provision": True,
                "grafana_url": "https://grafana.local",
            })
            assert result.success is True
            assert result.output["dashboard_url"] == "https://grafana.local/d/test-uid/test"
            assert any(s.step_name == "provision" for s in result.steps)

    def test_provision_failure_does_not_fail_workflow(
        self, workflow, valid_spec, mock_mixin, mock_toolchain, compiled_json,
        tmp_path, monkeypatch,
    ):
        monkeypatch.setenv("GRAFANA_API_TOKEN", "test-token")

        mock_prov_result = MagicMock()
        mock_prov_result.success = False
        mock_prov_result.error = "Connection refused"

        with patch("startd8.dashboard_creator.workflow.discover_mixin", return_value=mock_mixin), \
             patch("startd8.dashboard_creator.workflow.detect_toolchain", return_value=mock_toolchain), \
             patch("startd8.dashboard_creator.workflow.compile_jsonnet_string") as mock_compile, \
             patch("startd8.dashboard_creator.grafana_client.GrafanaClient") as MockClient, \
             patch("startd8.dashboard_creator.provisioning.provision_dashboard", return_value=mock_prov_result):
            mock_compile.return_value = MagicMock(
                json_str=compiled_json, duration_ms=10, backend="binary",
            )
            result = workflow.run({
                "spec": valid_spec,
                "output_dir": str(tmp_path),
                "provision": True,
                "grafana_url": "https://grafana.local",
            })
            # Workflow succeeds even though provisioning failed
            assert result.success is True
            assert result.output["dashboard_url"] is None
            prov_step = [s for s in result.steps if s.step_name == "provision"]
            assert len(prov_step) == 1
            assert "failed" in prov_step[0].output.lower()
