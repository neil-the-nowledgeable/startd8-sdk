"""Tests for dashboard_creator.workflow — DashboardCreatorWorkflow."""

import json
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


# ---------------------------------------------------------------------------
# Phase 3 integration tests
# ---------------------------------------------------------------------------


class TestPhase3Layout:
    """DC-108, DC-109: Layout integration in workflow."""

    def test_grouped_spec_gets_layout_step(
        self, workflow, mock_mixin, mock_toolchain, grouped_spec_dict
    ):
        with patch("startd8.dashboard_creator.workflow.discover_mixin", return_value=mock_mixin), \
             patch("startd8.dashboard_creator.workflow.detect_toolchain", return_value=mock_toolchain):
            result = workflow.run({"spec": grouped_spec_dict, "dry_run": True})
            assert result.success is True
            step_names = [s.step_name for s in result.steps]
            assert "layout" in step_names

    def test_spec_without_groups_skips_layout(
        self, workflow, valid_spec, mock_mixin, mock_toolchain
    ):
        with patch("startd8.dashboard_creator.workflow.discover_mixin", return_value=mock_mixin), \
             patch("startd8.dashboard_creator.workflow.detect_toolchain", return_value=mock_toolchain):
            result = workflow.run({"spec": valid_spec, "dry_run": True})
            assert result.success is True
            step_names = [s.step_name for s in result.steps]
            # Layout is applied because panel has no gridPos
            assert "layout" in step_names


class TestPhase3ManifestSync:
    """DC-201: Manifest sync integration in workflow."""

    def test_manifest_synced_when_path_provided(
        self, workflow, valid_spec, mock_mixin, mock_toolchain, compiled_json, tmp_path
    ):
        import yaml as _yaml
        manifest = tmp_path / "manifest.yaml"
        manifest.write_text(_yaml.dump({"dashboards": []}))

        with patch("startd8.dashboard_creator.workflow.discover_mixin", return_value=mock_mixin), \
             patch("startd8.dashboard_creator.workflow.detect_toolchain", return_value=mock_toolchain), \
             patch("startd8.dashboard_creator.workflow.compile_jsonnet_string") as mock_compile:
            mock_compile.return_value = MagicMock(
                json_str=compiled_json, duration_ms=10, backend="binary",
            )
            result = workflow.run({
                "spec": valid_spec,
                "output_dir": str(tmp_path),
                "manifest_path": str(manifest),
            })
            assert result.success is True
            step_names = [s.step_name for s in result.steps]
            assert "manifest_sync" in step_names

            data = _yaml.safe_load(manifest.read_text())
            assert len(data["dashboards"]) == 1
            assert data["dashboards"][0]["uid"] == "cc-startd8-test-dashboard"

    def test_no_manifest_path_skips_sync(
        self, workflow, valid_spec, mock_mixin, mock_toolchain, compiled_json, tmp_path
    ):
        with patch("startd8.dashboard_creator.workflow.discover_mixin", return_value=mock_mixin), \
             patch("startd8.dashboard_creator.workflow.detect_toolchain", return_value=mock_toolchain), \
             patch("startd8.dashboard_creator.workflow.compile_jsonnet_string") as mock_compile:
            mock_compile.return_value = MagicMock(
                json_str=compiled_json, duration_ms=10, backend="binary",
            )
            result = workflow.run({
                "spec": valid_spec,
                "output_dir": str(tmp_path),
            })
            assert result.success is True
            step_names = [s.step_name for s in result.steps]
            assert "manifest_sync" not in step_names


class TestPhase3MixinUpdate:
    """DC-204: Mixin auto-update integration in workflow."""

    def test_mixin_updated_when_persist_source(
        self, workflow, valid_spec, mock_mixin, mock_toolchain, compiled_json, tmp_path
    ):
        mixin_content = "{\n  grafanaDashboards+:: {\n  },\n}\n"
        mock_mixin.mixin_libsonnet.write_text(mixin_content)

        with patch("startd8.dashboard_creator.workflow.discover_mixin", return_value=mock_mixin), \
             patch("startd8.dashboard_creator.workflow.detect_toolchain", return_value=mock_toolchain), \
             patch("startd8.dashboard_creator.workflow.compile_jsonnet_string") as mock_compile:
            mock_compile.return_value = MagicMock(
                json_str=compiled_json, duration_ms=10, backend="binary",
            )
            result = workflow.run({
                "spec": valid_spec,
                "output_dir": str(tmp_path),
                "persist_source": True,
            })
            assert result.success is True
            step_names = [s.step_name for s in result.steps]
            assert "mixin_update" in step_names

            content = mock_mixin.mixin_libsonnet.read_text()
            assert "cc-startd8-test-dashboard.json" in content


class TestPhase3OTelSpans:
    """DC-205: OTel span emission (graceful when OTel unavailable)."""

    def test_workflow_succeeds_without_otel(
        self, workflow, valid_spec, mock_mixin, mock_toolchain
    ):
        """OTel is optional; workflow must succeed without it installed."""
        with patch("startd8.dashboard_creator.workflow.discover_mixin", return_value=mock_mixin), \
             patch("startd8.dashboard_creator.workflow.detect_toolchain", return_value=mock_toolchain):
            result = workflow.run({"spec": valid_spec, "dry_run": True})
            assert result.success is True


class TestPhase3ContextCore:
    """DC-207: ContextCore project context."""

    def test_load_contextcore_absent(self, workflow, tmp_path, monkeypatch):
        """When .contextcore.yaml is absent, returns None gracefully."""
        monkeypatch.chdir(tmp_path)
        ctx = workflow._load_contextcore_context()
        assert ctx is None

    def test_load_contextcore_present(self, workflow, tmp_path, monkeypatch):
        """When .contextcore.yaml exists, extracts project.id and project.name."""
        import yaml as _yaml
        cc = tmp_path / ".contextcore.yaml"
        cc.write_text(_yaml.dump({
            "spec": {
                "project": {"id": "proj-123", "name": "My Project"},
            },
        }))
        monkeypatch.chdir(tmp_path)
        ctx = workflow._load_contextcore_context()
        assert ctx is not None
        assert ctx["project.id"] == "proj-123"
        assert ctx["project.name"] == "My Project"


class TestParseSpecMarkdown:
    """_parse_spec routes .md files through requirements_parser."""

    def test_md_file_calls_parse_requirements(self, workflow, tmp_path):
        """When spec input is a .md file path, _parse_spec delegates to parse_requirements."""
        md_file = tmp_path / "test-requirements.md"
        md_file.write_text("# placeholder")

        from startd8.dashboard_creator.models import DashboardSpec
        from unittest.mock import patch

        fake_spec = DashboardSpec(
            title="From MD",
            panels=[{"type": "stat", "title": "P1", "expr": "up"}],
        )
        with patch(
            "startd8.dashboard_creator.requirements_parser.parse_requirements",
            return_value=fake_spec,
        ) as mock_parse:
            result = workflow._parse_spec(str(md_file))

        mock_parse.assert_called_once_with(md_file)
        assert result.title == "From MD"

    def test_yaml_file_not_routed_to_parser(self, workflow, tmp_path):
        """YAML files continue through the existing YAML parsing path."""
        yaml_file = tmp_path / "test.spec.yaml"
        yaml_file.write_text("title: From YAML\npanels:\n  - type: stat\n    title: P1\n    expr: up\n")

        result = workflow._parse_spec(str(yaml_file))
        assert result.title == "From YAML"
