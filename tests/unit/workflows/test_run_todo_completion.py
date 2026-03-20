"""Tests for scripts/run_todo_completion.py — build_config() and CLI integration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest import mock

import pytest

import sys

# Ensure the scripts directory is importable
_scripts = str(Path(__file__).resolve().parent.parent.parent.parent / "scripts")
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)

from run_todo_completion import build_config, build_parser  # noqa: E402


def _parse(args: list[str]) -> argparse.Namespace:
    """Parse CLI arguments using the real parser."""
    return build_parser().parse_args(args)


class TestBuildConfigDefaults:
    """Verify default config values."""

    def test_config_defaults(self):
        ns = _parse(["--project-root", "/tmp/proj", "--output-dir", "/tmp/out"])
        config = build_config(ns)
        assert config["categories"] == "A,B"
        assert config["execute"] is False
        assert config["max_tasks"] == 20
        assert config["scan_dir"] == "/tmp/proj"
        assert config["output_dir"] == "/tmp/out"
        assert config["source_run_id"] == ""

    def test_scan_only_overrides_execute(self):
        ns = _parse([
            "--project-root", "/tmp/proj", "--output-dir", "/tmp/out",
            "--execute", "--scan-only",
        ])
        config = build_config(ns)
        assert config["execute"] is False

    def test_execute_flag(self):
        ns = _parse([
            "--project-root", "/tmp/proj", "--output-dir", "/tmp/out",
            "--execute",
        ])
        config = build_config(ns)
        assert config["execute"] is True

    def test_category_a_only(self):
        ns = _parse([
            "--project-root", "/tmp/proj", "--output-dir", "/tmp/out",
            "--categories", "A",
        ])
        config = build_config(ns)
        assert config["categories"] == "A"

    def test_category_ab(self):
        ns = _parse([
            "--project-root", "/tmp/proj", "--output-dir", "/tmp/out",
            "--categories", "A,B",
        ])
        config = build_config(ns)
        assert config["categories"] == "A,B"


class TestContractLoading:
    """Verify instrumentation contract loading."""

    def test_contract_loaded(self, tmp_path: Path):
        contract = {"services": [{"name": "metrics-service"}]}
        contract_path = tmp_path / "contract.json"
        contract_path.write_text(json.dumps(contract), encoding="utf-8")

        ns = _parse([
            "--project-root", "/tmp/proj", "--output-dir", "/tmp/out",
            "--instrumentation-contract", str(contract_path),
        ])
        config = build_config(ns)
        assert config["instrumentation_contract"] == contract

    def test_missing_contract_no_crash(self):
        ns = _parse([
            "--project-root", "/tmp/proj", "--output-dir", "/tmp/out",
            "--instrumentation-contract", "/nonexistent/contract.json",
        ])
        config = build_config(ns)
        assert "instrumentation_contract" not in config


class TestSecurityContractLoading:
    """Verify security contract loading (REQ-ICD-106)."""

    def test_security_contract_loaded(self, tmp_path: Path):
        contract = {"databases": {"cartdb": {"type": "spanner"}}, "source": "manifest"}
        sc_path = tmp_path / "security-contract.json"
        sc_path.write_text(json.dumps(contract), encoding="utf-8")

        ns = _parse([
            "--project-root", "/tmp/proj", "--output-dir", "/tmp/out",
            "--security-contract", str(sc_path),
        ])
        config = build_config(ns)
        assert config["security_contract"] == contract

    def test_missing_security_contract_no_crash(self):
        ns = _parse([
            "--project-root", "/tmp/proj", "--output-dir", "/tmp/out",
            "--security-contract", "/nonexistent/sc.json",
        ])
        config = build_config(ns)
        assert "security_contract" not in config

    def test_no_security_contract_flag(self):
        ns = _parse(["--project-root", "/tmp/proj", "--output-dir", "/tmp/out"])
        config = build_config(ns)
        assert "security_contract" not in config


class TestDryRun:
    """Verify --dry-run exits cleanly without invoking the workflow."""

    def test_dry_run_exits_zero(self):
        from run_todo_completion import main

        with mock.patch(
            "sys.argv",
            ["run_todo_completion.py",
             "--project-root", "/tmp/proj",
             "--output-dir", "/tmp/out",
             "--dry-run"],
        ):
            assert main() == 0


class TestResultJsonWritten:
    """Verify that instrumentation-result.json is written on success."""

    def test_result_json_written(self, tmp_path: Path):
        from run_todo_completion import main

        project_dir = tmp_path / "proj"
        project_dir.mkdir()
        output_dir = tmp_path / "out"

        mock_result = mock.MagicMock()
        mock_result.success = True
        mock_result.output = {"todo_count": 3, "task_count": 2, "executed": False}

        mock_workflow_cls = mock.MagicMock()
        mock_workflow_inst = mock_workflow_cls.return_value
        mock_workflow_inst.validate_config.return_value = mock.MagicMock(
            valid=True, errors=[],
        )
        mock_workflow_inst.run.return_value = mock_result

        with mock.patch(
            "sys.argv",
            ["run_todo_completion.py",
             "--project-root", str(project_dir),
             "--output-dir", str(output_dir)],
        ), mock.patch.dict(
            "sys.modules",
            {"startd8.workflows.builtin.todo_completion_workflow": mock.MagicMock(
                TodoCompletionWorkflow=mock_workflow_cls,
            )},
        ):
            exit_code = main()

        assert exit_code == 0
        result_path = output_dir / "instrumentation-result.json"
        assert result_path.exists()
        data = json.loads(result_path.read_text(encoding="utf-8"))
        assert data["todo_count"] == 3
        assert data["task_count"] == 2
