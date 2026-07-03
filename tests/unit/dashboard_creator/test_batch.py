"""Tests for dashboard_creator.batch — DC-111."""

import json
from unittest.mock import MagicMock, patch

import yaml

from startd8.dashboard_creator.batch import (
    BatchReport,
    load_specs_from_directory,
    run_batch,
)


# ---------------------------------------------------------------------------
# BatchReport
# ---------------------------------------------------------------------------


class TestBatchReport:
    def test_exit_code_all_success(self):
        report = BatchReport(total=3, succeeded=3, failed=0)
        assert report.exit_code == 0

    def test_exit_code_all_failed(self):
        report = BatchReport(total=3, succeeded=0, failed=3)
        assert report.exit_code == 1

    def test_exit_code_partial(self):
        report = BatchReport(total=3, succeeded=2, failed=1)
        assert report.exit_code == 2

    def test_exit_code_empty(self):
        report = BatchReport(total=0, succeeded=0, failed=0)
        assert report.exit_code == 0


# ---------------------------------------------------------------------------
# load_specs_from_directory
# ---------------------------------------------------------------------------


class TestLoadSpecsFromDirectory:
    def test_loads_yaml_and_json(self, tmp_path):
        (tmp_path / "a.yaml").write_text(yaml.dump({"title": "A", "panels": []}))
        (tmp_path / "b.json").write_text(json.dumps({"title": "B", "panels": []}))
        (tmp_path / "c.yml").write_text(yaml.dump({"title": "C", "panels": []}))
        specs = load_specs_from_directory(tmp_path)
        titles = [s["title"] for s in specs]
        assert sorted(titles) == ["A", "B", "C"]

    def test_sorted_alphabetically(self, tmp_path):
        (tmp_path / "z.yaml").write_text(yaml.dump({"title": "Z", "panels": []}))
        (tmp_path / "a.yaml").write_text(yaml.dump({"title": "A", "panels": []}))
        specs = load_specs_from_directory(tmp_path)
        assert specs[0]["title"] == "A"
        assert specs[1]["title"] == "Z"

    def test_invalid_file_captured_as_error(self, tmp_path):
        (tmp_path / "bad.yaml").write_text(": : invalid yaml {{")
        specs = load_specs_from_directory(tmp_path)
        assert len(specs) == 1
        assert "_error" in specs[0]

    def test_empty_directory(self, tmp_path):
        assert load_specs_from_directory(tmp_path) == []


# ---------------------------------------------------------------------------
# run_batch
# ---------------------------------------------------------------------------


class TestRunBatch:
    def _mock_workflow_run(self, success=True, uid="cc-startd8-test", json_path="/out/test.json", error=None):
        """Create a mock workflow result."""
        result = MagicMock()
        result.success = success
        result.output = {"uid": uid, "json_path": json_path} if success else {}
        result.error = error
        return result

    @patch("startd8.dashboard_creator.batch.DashboardCreatorWorkflow")
    def test_all_succeed(self, MockWorkflow, tmp_path):
        mock_wf = MockWorkflow.return_value
        mock_wf.run.return_value = self._mock_workflow_run()

        specs = [
            {"title": "A", "panels": [{"type": "stat", "title": "M", "expr": "up"}]},
            {"title": "B", "panels": [{"type": "stat", "title": "M", "expr": "up"}]},
        ]
        report = run_batch(specs, report_dir=tmp_path)
        assert report.succeeded == 2
        assert report.failed == 0
        assert report.exit_code == 0

    @patch("startd8.dashboard_creator.batch.DashboardCreatorWorkflow")
    def test_partial_failure(self, MockWorkflow, tmp_path):
        mock_wf = MockWorkflow.return_value
        mock_wf.run.side_effect = [
            self._mock_workflow_run(success=True),
            self._mock_workflow_run(success=False, error="Bad panel"),
        ]

        specs = [
            {"title": "Good", "panels": [{"type": "stat", "title": "M", "expr": "up"}]},
            {"title": "Bad", "panels": [{"type": "stat", "title": "M", "expr": "up"}]},
        ]
        report = run_batch(specs, report_dir=tmp_path)
        assert report.succeeded == 1
        assert report.failed == 1
        assert report.exit_code == 2

    @patch("startd8.dashboard_creator.batch.DashboardCreatorWorkflow")
    def test_exception_isolation(self, MockWorkflow, tmp_path):
        mock_wf = MockWorkflow.return_value
        mock_wf.run.side_effect = [
            RuntimeError("Kaboom"),
            self._mock_workflow_run(success=True),
        ]

        specs = [
            {"title": "Crash", "panels": [{"type": "stat", "title": "M", "expr": "up"}]},
            {"title": "OK", "panels": [{"type": "stat", "title": "M", "expr": "up"}]},
        ]
        report = run_batch(specs, report_dir=tmp_path)
        assert report.succeeded == 1
        assert report.failed == 1
        assert report.dashboards[0].error == "Kaboom"

    @patch("startd8.dashboard_creator.batch.DashboardCreatorWorkflow")
    def test_report_persisted(self, MockWorkflow, tmp_path):
        mock_wf = MockWorkflow.return_value
        mock_wf.run.return_value = self._mock_workflow_run()

        specs = [{"title": "A", "panels": [{"type": "stat", "title": "M", "expr": "up"}]}]
        run_batch(specs, report_dir=tmp_path)

        report_path = tmp_path / "dashboard-create-report.json"
        assert report_path.is_file()
        data = json.loads(report_path.read_text())
        assert data["total"] == 1
        assert data["succeeded"] == 1

    @patch("startd8.dashboard_creator.batch.DashboardCreatorWorkflow")
    def test_progress_callback(self, MockWorkflow, tmp_path):
        mock_wf = MockWorkflow.return_value
        mock_wf.run.return_value = self._mock_workflow_run()

        calls = []
        specs = [{"title": "A", "panels": [{"type": "stat", "title": "M", "expr": "up"}]}]
        run_batch(specs, report_dir=tmp_path, on_progress=lambda c, t, m: calls.append((c, t)))
        assert len(calls) == 1
        assert calls[0] == (1, 1)

    @patch("startd8.dashboard_creator.batch.DashboardCreatorWorkflow")
    def test_directory_input(self, MockWorkflow, tmp_path):
        mock_wf = MockWorkflow.return_value
        mock_wf.run.return_value = self._mock_workflow_run()

        spec_dir = tmp_path / "specs"
        spec_dir.mkdir()
        (spec_dir / "a.yaml").write_text(
            yaml.dump({"title": "A", "panels": [{"type": "stat", "title": "M", "expr": "up"}]})
        )
        report = run_batch(spec_dir, report_dir=tmp_path)
        assert report.total == 1
        assert report.succeeded == 1
