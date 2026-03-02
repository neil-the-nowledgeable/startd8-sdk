"""Tests for dashboard CLI commands (DC-206, DC-208)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from typer.testing import CliRunner

from startd8.cli import app

runner = CliRunner()


@pytest.fixture
def spec_file(tmp_path):
    """Create a minimal spec YAML file."""
    spec = {
        "title": "CLI Test Dashboard",
        "panels": [{"type": "stat", "title": "Up", "expr": "up"}],
    }
    path = tmp_path / "spec.yaml"
    path.write_text(yaml.dump(spec))
    return path


# ---------------------------------------------------------------------------
# dashboard create
# ---------------------------------------------------------------------------


class TestDashboardCreate:
    def test_print_template(self):
        result = runner.invoke(app, ["dashboard", "create", "--print-template"])
        assert result.exit_code == 0
        assert "title:" in result.output
        assert "panels:" in result.output

    def test_missing_spec_file_exits_1(self):
        result = runner.invoke(app, ["dashboard", "create"])
        assert result.exit_code == 1
        assert "required" in result.output.lower() or "spec" in result.output.lower()

    def test_nonexistent_spec_file_exits_1(self, tmp_path):
        fake = tmp_path / "nope.yaml"
        result = runner.invoke(app, ["dashboard", "create", str(fake)])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_successful_create(self, spec_file):
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.output = {"uid": "cc-startd8-cli-test", "json_path": "/tmp/out.json"}

        with patch("startd8.dashboard_creator.workflow.DashboardCreatorWorkflow") as MockWF:
            instance = MockWF.return_value
            instance.run.return_value = mock_result
            result = runner.invoke(app, ["dashboard", "create", str(spec_file)])
            assert result.exit_code == 0
            assert "cc-startd8-cli-test" in result.output
            instance.run.assert_called_once()

    def test_dry_run_flag_forwarded(self, spec_file):
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.output = {"uid": "test-uid"}

        with patch("startd8.dashboard_creator.workflow.DashboardCreatorWorkflow") as MockWF:
            instance = MockWF.return_value
            instance.run.return_value = mock_result
            result = runner.invoke(app, ["dashboard", "create", str(spec_file), "--dry-run"])
            assert result.exit_code == 0
            call_config = instance.run.call_args[0][0]
            assert call_config["dry_run"] is True

    def test_provision_flag_forwarded(self, spec_file):
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.output = {
            "uid": "test-uid",
            "json_path": "/tmp/out.json",
            "dashboard_url": "https://grafana.local/d/test-uid",
        }

        with patch("startd8.dashboard_creator.workflow.DashboardCreatorWorkflow") as MockWF:
            instance = MockWF.return_value
            instance.run.return_value = mock_result
            result = runner.invoke(app, [
                "dashboard", "create", str(spec_file),
                "--provision", "--grafana-url", "https://grafana.local",
            ])
            assert result.exit_code == 0
            call_config = instance.run.call_args[0][0]
            assert call_config["provision"] is True
            assert call_config["grafana_url"] == "https://grafana.local"

    def test_workflow_failure_exits_1(self, spec_file):
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.error = "Compilation failed"

        with patch("startd8.dashboard_creator.workflow.DashboardCreatorWorkflow") as MockWF:
            instance = MockWF.return_value
            instance.run.return_value = mock_result
            result = runner.invoke(app, ["dashboard", "create", str(spec_file)])
            assert result.exit_code == 1
            assert "failed" in result.output.lower()


# ---------------------------------------------------------------------------
# dashboard delete
# ---------------------------------------------------------------------------


class TestDashboardDelete:
    def test_delete_with_confirmation(self):
        with patch("startd8.dashboard_creator.provisioning.delete_local_artifacts", return_value={"json": True}):
            result = runner.invoke(app, ["dashboard", "delete", "my-uid", "--yes"])
            assert result.exit_code == 0

    def test_delete_aborted_without_yes(self):
        result = runner.invoke(app, ["dashboard", "delete", "my-uid"], input="n\n")
        assert result.exit_code == 0
        assert "aborted" in result.output.lower()

    def test_delete_with_grafana(self, monkeypatch):
        monkeypatch.setenv("GRAFANA_API_TOKEN", "fake")

        mock_prov_result = MagicMock()
        mock_prov_result.success = True

        with patch("startd8.dashboard_creator.grafana_client.GrafanaClient") as MockClient, \
             patch("startd8.dashboard_creator.provisioning.deprovision_dashboard", return_value=mock_prov_result), \
             patch("startd8.dashboard_creator.provisioning.delete_local_artifacts", return_value={"json": True}):
            result = runner.invoke(app, [
                "dashboard", "delete", "my-uid",
                "--grafana-url", "https://grafana.local",
                "--yes",
            ])
            assert result.exit_code == 0
