"""Tests for repair SHADOW (observer / counterfactual) mode in IntegrationEngine.

Shadow mode (RepairConfig.repair_mode="shadow") is benchmark instrumentation:
the raw model output is preserved as the deliverable, while the repair pipeline
runs against a throwaway staging copy ONLY, emitting a per-unit report of what
repair WOULD have done. Core guarantees validated here:

- _is_shadow() reflects repair_mode.
- _shadow_repair NEVER mutates the on-disk file (observer; no apply_atomic).
- A shadow report JSON is written capturing steps / per-file detail /
  recheckpoint-would-pass.
- When no repairable failures exist, the report records that (and the file is
  still untouched).
"""

import json
from unittest.mock import MagicMock, patch

from startd8.contractors.integration_engine import IntegrationEngine
from startd8.repair.config import RepairConfig


class _FakeUnit:
    def __init__(self, name="feat_shadow", target_files=None):
        self.id = "shadow-id"
        self.name = name
        self.target_files = target_files or ["a.py"]
        self.source_files = {}


def _make_engine(tmp_path, repair_config=None, checkpoint=None):
    return IntegrationEngine(
        project_root=tmp_path,
        merge_strategy=MagicMock(),
        checkpoint=checkpoint,
        repair_config=repair_config,
    )


class TestIsShadow:
    def test_apply_mode_is_not_shadow(self, tmp_path):
        engine = _make_engine(tmp_path, repair_config=RepairConfig())
        assert engine._is_shadow() is False

    def test_shadow_mode_detected(self, tmp_path):
        engine = _make_engine(tmp_path, repair_config=RepairConfig(repair_mode="shadow"))
        assert engine._is_shadow() is True

    def test_no_config_is_not_shadow(self, tmp_path):
        assert _make_engine(tmp_path)._is_shadow() is False


class TestShadowRepairObserver:
    @patch("startd8.contractors.integration_engine.run_file_repair")
    @patch("startd8.contractors.integration_engine.create_staging")
    @patch("startd8.contractors.integration_engine.parse_checkpoint_diagnostics")
    @patch("startd8.contractors.integration_engine.classify_checkpoint_category")
    def test_shadow_repair_does_not_mutate_and_writes_report(
        self, mock_classify, mock_parse, mock_staging, mock_repair, tmp_path,
    ):
        from startd8.contractors.checkpoint import CheckpointStatus
        from startd8.repair.models import (
            FileRepairResult,
            RepairOutcome,
            RepairRoute,
            RepairStepResult,
        )

        # Raw (broken) model output on disk — this must survive untouched.
        py_file = tmp_path / "a.py"
        RAW = "import os\n```\nx = 1\n"  # contains a stray fence (repairable)
        py_file.write_text(RAW)

        # A repairable failed checkpoint.
        failed = MagicMock()
        failed.name = "Syntax Check"
        failed.status = CheckpointStatus.FAILED
        failed.errors = ["fence"]
        failed.message = "syntax"
        failed.warnings = []

        checkpoint = MagicMock()
        checkpoint.run_all_checkpoints.return_value = [failed]
        checkpoint.summarize_results.return_value = True  # repaired copy would pass

        mock_classify.return_value = "syntax"
        mock_parse.return_value = []

        staged = MagicMock()
        staged.files = {py_file: RAW}
        staged.paths = [tmp_path / "staging" / "a.py"]
        staged.__enter__ = MagicMock(return_value=staged)
        staged.__exit__ = MagicMock(return_value=False)
        mock_staging.return_value = staged

        mock_repair.return_value = RepairOutcome(
            repaired_files={py_file: "import os\nx = 1\n"},
            file_results=[
                FileRepairResult(
                    file_path=py_file, success=True,
                    before_valid=False, after_valid=True,
                    steps_applied=["fence_strip"],
                    step_results=[
                        RepairStepResult(
                            step_name="fence_strip", modified=True,
                            code="import os\nx = 1\n", metrics={"had_fences": True},
                        ),
                    ],
                ),
            ],
            steps_applied=["fence_strip"],
            route=RepairRoute(matched_patterns=["fence"], steps=["fence_strip"], confidence="HIGH"),
            any_modified=True,
        )

        engine = _make_engine(
            tmp_path, repair_config=RepairConfig(repair_mode="shadow"),
            checkpoint=checkpoint,
        )
        metadata: dict = {}
        engine._shadow_repair([failed], [py_file], _FakeUnit(), 0, metadata)

        # GUARANTEE 1: the raw file on disk is byte-identical (observer never applies).
        assert py_file.read_text() == RAW
        # apply_atomic must never be called in shadow mode.
        assert staged.apply_atomic.call_count == 0

        # GUARANTEE 2: a shadow report was written capturing what repair would do.
        report_path = tmp_path / ".startd8" / "repair-shadow" / "feat_shadow__attempt0.json"
        assert report_path.exists()
        report = json.loads(report_path.read_text())
        assert report["triggered"] is True
        assert report["any_modified"] is True
        assert report["steps_applied"] == ["fence_strip"]
        assert report["recheckpoint_would_pass"] is True
        assert report["files"][0]["before_valid"] is False
        assert report["files"][0]["after_valid"] is True
        assert report["files"][0]["steps"][0]["name"] == "fence_strip"
        assert report["files"][0]["steps"][0]["metrics"]["had_fences"] is True

        # And the in-band metadata mirror is stamped.
        assert metadata["repair_shadow"]["triggered"] is True
        assert metadata["repair_shadow"]["recheckpoint_would_pass"] is True

    def test_shadow_repair_no_failed_checks_records_reason(self, tmp_path):
        from startd8.contractors.checkpoint import CheckpointStatus

        py_file = tmp_path / "ok.py"
        RAW = "x = 1\n"
        py_file.write_text(RAW)

        passed = MagicMock()
        passed.name = "Syntax Check"
        passed.status = CheckpointStatus.PASSED

        engine = _make_engine(
            tmp_path, repair_config=RepairConfig(repair_mode="shadow"),
            checkpoint=MagicMock(),
        )
        engine._shadow_repair([passed], [py_file], _FakeUnit(name="clean"), 1, {})

        # File untouched.
        assert py_file.read_text() == RAW
        report = json.loads(
            (tmp_path / ".startd8" / "repair-shadow" / "clean__attempt1.json").read_text()
        )
        assert report["triggered"] is False
        assert report["reason"] == "no_repairable_failed_checks"
