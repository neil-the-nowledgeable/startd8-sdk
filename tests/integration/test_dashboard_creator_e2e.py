"""End-to-end integration tests for dashboard_creator pipeline.

These tests exercise the full pipeline: spec → generate → compile → validate → persist.
They require either the `jsonnet` binary or the `_gojsonnet` Python package.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from startd8.dashboard_creator.models import DashboardSpec
from startd8.dashboard_creator.workflow import DashboardCreatorWorkflow


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _has_jsonnet_binary() -> bool:
    """Check if the jsonnet CLI binary is available."""
    import shutil
    return shutil.which("jsonnet") is not None


def _has_gojsonnet() -> bool:
    """Check if the _gojsonnet Python package is available."""
    try:
        import _gojsonnet  # noqa: F401
        return True
    except ImportError:
        return False


_HAS_JSONNET = _has_jsonnet_binary() or _has_gojsonnet()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def spec_dict():
    """Minimal valid DashboardSpec dict."""
    return {
        "title": "E2E Test Dashboard",
        "panels": [
            {"type": "stat", "title": "Uptime", "expr": "up"},
        ],
    }


@pytest.fixture
def spec_yaml(tmp_path, spec_dict):
    """Write spec dict to a YAML file."""
    path = tmp_path / "e2e-spec.yaml"
    path.write_text(yaml.dump(spec_dict))
    return path


@pytest.fixture
def mock_mixin_dir(tmp_path):
    """Create a realistic mock mixin directory for e2e tests."""
    mixin = tmp_path / "startd8-mixin"
    (mixin / "lib").mkdir(parents=True)
    (mixin / "dashboards").mkdir()
    vendor = mixin / "vendor"
    vendor.mkdir()
    (vendor / "grafonnet").mkdir()
    (mixin / "config.libsonnet").write_text("{ _config+:: {} }")
    (mixin / "lib" / "panels.libsonnet").write_text("{}")
    (mixin / "lib" / "variables.libsonnet").write_text("{}")
    (mixin / "lib" / "dashboards.libsonnet").write_text("{}")
    (mixin / "mixin.libsonnet").write_text("{}")
    return mixin


@pytest.fixture
def mock_toolchain():
    """A mock toolchain for tests that don't need real compilation."""
    from startd8.dashboard_creator.discovery import ToolchainInfo
    return ToolchainInfo(backend="binary", version="v0.20.0", binary_path="/usr/local/bin/jsonnet")


# ---------------------------------------------------------------------------
# Schema export test
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestSchemaExport:
    """Verify the JSON schema export is valid and current."""

    def test_schema_file_exists(self):
        schema_path = Path(__file__).resolve().parents[2] / "docs" / "schemas" / "dashboard-spec.schema.json"
        assert schema_path.is_file(), f"Schema file not found at {schema_path}"

    def test_schema_matches_model(self):
        schema_path = Path(__file__).resolve().parents[2] / "docs" / "schemas" / "dashboard-spec.schema.json"
        if not schema_path.is_file():
            pytest.skip("Schema file not found")
        stored = json.loads(schema_path.read_text())
        current = DashboardSpec.model_json_schema()
        assert stored == current, "Schema file is out of date — regenerate with DashboardSpec.model_json_schema()"

    def test_schema_has_required_fields(self):
        schema = DashboardSpec.model_json_schema()
        assert "title" in schema["required"]
        assert "panels" in schema["required"]

    def test_schema_defines_all_panel_types(self):
        schema = DashboardSpec.model_json_schema()
        panel_type_enum = schema["$defs"]["PanelType"]["enum"]
        assert len(panel_type_enum) == 16

    def test_schema_defines_all_variable_types(self):
        schema = DashboardSpec.model_json_schema()
        var_type_enum = schema["$defs"]["VariableType"]["enum"]
        assert len(var_type_enum) == 9


# ---------------------------------------------------------------------------
# Workflow pipeline e2e tests (mocked compilation)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestDashboardCreatorPipeline:
    """Full pipeline tests with mocked Jsonnet compilation."""

    def test_dry_run_pipeline(self, spec_dict, mock_mixin_dir, mock_toolchain):
        """Dry run: spec → generate Jsonnet → return source."""
        workflow = DashboardCreatorWorkflow()

        with patch("startd8.dashboard_creator.workflow.discover_mixin") as mock_discover:
            from startd8.dashboard_creator.discovery import MixinContext
            mock_discover.return_value = MixinContext(
                mixin_dir=mock_mixin_dir,
                panels_path=mock_mixin_dir / "lib" / "panels.libsonnet",
                variables_path=mock_mixin_dir / "lib" / "variables.libsonnet",
                config_path=mock_mixin_dir / "config.libsonnet",
                dashboards_dir=mock_mixin_dir / "dashboards",
                vendor_dir=mock_mixin_dir / "vendor",
                mixin_libsonnet=mock_mixin_dir / "mixin.libsonnet",
            )
            with patch("startd8.dashboard_creator.workflow.detect_toolchain", return_value=mock_toolchain):
                result = workflow.run({"spec": spec_dict, "dry_run": True})

        assert result.success is True
        assert "jsonnet_source" in result.output
        assert "uid" in result.output
        # UID should follow convention
        assert result.output["uid"].startswith("cc-")

    def test_full_pipeline_with_mocked_compile(
        self, spec_dict, mock_mixin_dir, mock_toolchain, tmp_path
    ):
        """Full pipeline: spec → generate → compile (mocked) → validate → persist."""
        workflow = DashboardCreatorWorkflow()

        compiled_json = json.dumps({
            "title": "E2E Test Dashboard",
            "uid": "cc-startd8-e2e-test-dashboard",
            "panels": [{"id": 1, "type": "stat", "title": "Uptime"}],
            "schemaVersion": 39,
            "templating": {"list": []},
        })

        with patch("startd8.dashboard_creator.workflow.discover_mixin") as mock_discover:
            from startd8.dashboard_creator.discovery import MixinContext
            mock_discover.return_value = MixinContext(
                mixin_dir=mock_mixin_dir,
                panels_path=mock_mixin_dir / "lib" / "panels.libsonnet",
                variables_path=mock_mixin_dir / "lib" / "variables.libsonnet",
                config_path=mock_mixin_dir / "config.libsonnet",
                dashboards_dir=mock_mixin_dir / "dashboards",
                vendor_dir=mock_mixin_dir / "vendor",
                mixin_libsonnet=mock_mixin_dir / "mixin.libsonnet",
            )
            with patch("startd8.dashboard_creator.workflow.detect_toolchain", return_value=mock_toolchain):
                with patch("startd8.dashboard_creator.workflow.compile_jsonnet_string") as mock_compile:
                    mock_compile.return_value = MagicMock(
                        json_str=compiled_json,
                        duration_ms=15,
                        backend="binary",
                    )
                    result = workflow.run({
                        "spec": spec_dict,
                        "output_dir": str(tmp_path),
                    })

        assert result.success is True
        json_path = Path(result.output["json_path"])
        assert json_path.is_file()
        data = json.loads(json_path.read_text())
        assert data["title"] == "E2E Test Dashboard"
        assert data["uid"] == "cc-startd8-e2e-test-dashboard"
        assert len(data["panels"]) == 1
        assert data["schemaVersion"] == 39

    def test_yaml_file_input(
        self, spec_yaml, mock_mixin_dir, mock_toolchain
    ):
        """Pipeline accepts YAML file path as spec input."""
        workflow = DashboardCreatorWorkflow()

        with patch("startd8.dashboard_creator.workflow.discover_mixin") as mock_discover:
            from startd8.dashboard_creator.discovery import MixinContext
            mock_discover.return_value = MixinContext(
                mixin_dir=mock_mixin_dir,
                panels_path=mock_mixin_dir / "lib" / "panels.libsonnet",
                variables_path=mock_mixin_dir / "lib" / "variables.libsonnet",
                config_path=mock_mixin_dir / "config.libsonnet",
                dashboards_dir=mock_mixin_dir / "dashboards",
                vendor_dir=mock_mixin_dir / "vendor",
                mixin_libsonnet=mock_mixin_dir / "mixin.libsonnet",
            )
            with patch("startd8.dashboard_creator.workflow.detect_toolchain", return_value=mock_toolchain):
                result = workflow.run({"spec": str(spec_yaml), "dry_run": True})

        assert result.success is True
        assert "jsonnet_source" in result.output

    def test_progress_tracking(self, spec_dict, mock_mixin_dir, mock_toolchain):
        """Pipeline emits progress callbacks through the full flow."""
        workflow = DashboardCreatorWorkflow()
        progress_calls = []

        def on_progress(current, total, message):
            progress_calls.append((current, total, message))

        with patch("startd8.dashboard_creator.workflow.discover_mixin") as mock_discover:
            from startd8.dashboard_creator.discovery import MixinContext
            mock_discover.return_value = MixinContext(
                mixin_dir=mock_mixin_dir,
                panels_path=mock_mixin_dir / "lib" / "panels.libsonnet",
                variables_path=mock_mixin_dir / "lib" / "variables.libsonnet",
                config_path=mock_mixin_dir / "config.libsonnet",
                dashboards_dir=mock_mixin_dir / "dashboards",
                vendor_dir=mock_mixin_dir / "vendor",
                mixin_libsonnet=mock_mixin_dir / "mixin.libsonnet",
            )
            with patch("startd8.dashboard_creator.workflow.detect_toolchain", return_value=mock_toolchain):
                workflow.run(
                    {"spec": spec_dict, "dry_run": True},
                    on_progress=on_progress,
                )

        assert len(progress_calls) >= 3
        # First call starts at 0
        assert progress_calls[0][0] == 0
        # Last call should be 10/10
        assert progress_calls[-1][0] == 10
        assert progress_calls[-1][1] == 10

    def test_invalid_spec_returns_error(self):
        """Invalid spec should return error without crashing."""
        workflow = DashboardCreatorWorkflow()
        result = workflow.run({"spec": {"panels": []}})
        assert result.success is False
        assert result.error is not None

    def test_check_mode_validates_without_writing(
        self, spec_dict, mock_mixin_dir, mock_toolchain, tmp_path
    ):
        """Check mode compiles but does not write files."""
        workflow = DashboardCreatorWorkflow()

        compiled_json = json.dumps({
            "title": "E2E Test Dashboard",
            "uid": "cc-startd8-e2e-test-dashboard",
            "panels": [{"id": 1, "type": "stat", "title": "Uptime"}],
            "schemaVersion": 39,
            "templating": {"list": []},
        })

        with patch("startd8.dashboard_creator.workflow.discover_mixin") as mock_discover:
            from startd8.dashboard_creator.discovery import MixinContext
            mock_discover.return_value = MixinContext(
                mixin_dir=mock_mixin_dir,
                panels_path=mock_mixin_dir / "lib" / "panels.libsonnet",
                variables_path=mock_mixin_dir / "lib" / "variables.libsonnet",
                config_path=mock_mixin_dir / "config.libsonnet",
                dashboards_dir=mock_mixin_dir / "dashboards",
                vendor_dir=mock_mixin_dir / "vendor",
                mixin_libsonnet=mock_mixin_dir / "mixin.libsonnet",
            )
            with patch("startd8.dashboard_creator.workflow.detect_toolchain", return_value=mock_toolchain):
                with patch("startd8.dashboard_creator.workflow.compile_jsonnet_string") as mock_compile:
                    mock_compile.return_value = MagicMock(
                        json_str=compiled_json,
                        duration_ms=10,
                        backend="binary",
                    )
                    result = workflow.run({"spec": spec_dict, "check": True})

        assert result.success is True
        assert result.output["check"] == "passed"
        # No files should have been written
        assert "json_path" not in result.output
