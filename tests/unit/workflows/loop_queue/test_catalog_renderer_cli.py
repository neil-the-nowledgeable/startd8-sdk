# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Catalog validation, default renderer, and `startd8 wloop` CLI smoke tests."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from startd8.cli_wloop import wloop_app
from startd8.workflows.loop_queue import (
    CrpReviewRequest,
    LoopQueueConfig,
    LoopQueueValidationError,
    WorkflowLoopJob,
    WorkflowLoopQueue,
)
from startd8.workflows.loop_queue.renderer import render_bundle
from startd8.workflows.models import ValidationResult

runner = CliRunner()


def test_catalog_validation_accepts_valid_and_rejects_missing(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr(
        "startd8.workflows.loop_queue.queue.WorkflowRegistry.discover",
        lambda: None,
    )
    monkeypatch.setattr(
        "startd8.workflows.loop_queue.queue.WorkflowRegistry.get_workflow_info",
        lambda workflow_id: {"workflow_id": workflow_id},
    )

    def validate(_workflow_id, config):
        if "document_path" not in config:
            return ValidationResult.failure(["Missing required input: document_path"])
        return ValidationResult.success()

    monkeypatch.setattr(
        "startd8.workflows.loop_queue.queue.WorkflowRegistry.validate_config",
        validate,
    )

    queue = WorkflowLoopQueue(LoopQueueConfig(queue_root=tmp_path / "queue"))
    valid = WorkflowLoopJob(
        job_id="valid",
        loop_id="one-shot",
        executor="sdk-workflow",
        workflow_id="fake-workflow",
        config={"document_path": "/some/path"},
    )
    assert queue.enqueue(valid).job_id == "valid"

    missing = WorkflowLoopJob(
        job_id="missing",
        loop_id="one-shot",
        executor="sdk-workflow",
        workflow_id="fake-workflow",
        config={},
    )
    with pytest.raises(LoopQueueValidationError, match="Missing required input"):
        queue.enqueue(missing)


def test_default_renderer_script_produces_bundle(tmp_path: Path):
    source = tmp_path / "PLAN.md"
    source.write_text("# Plan\n", encoding="utf-8")
    script = tmp_path / "renderer.py"
    script.write_text(
        """#!/usr/bin/env python3
import pathlib
import sys
out = pathlib.Path(sys.argv[sys.argv.index("--output") + 1])
out.write_text("# Rendered CRP bundle\\n", encoding="utf-8")
""",
        encoding="utf-8",
    )
    script.chmod(0o755)
    bundle = render_bundle(
        request=CrpReviewRequest(plan_path=str(source), scope="Review"),
        round_number=1,
        artifact_dir=tmp_path / "artifacts",
        renderer_script=script,
    )
    rendered = bundle.read_text(encoding="utf-8")
    assert "**Round to append:** R1" in rendered
    assert rendered.endswith("# Rendered CRP bundle\n")


def test_project_template_rejects_single_brace_fields(tmp_path: Path):
    source = tmp_path / "PLAN.md"
    source.write_text("# Plan\n", encoding="utf-8")
    template = tmp_path / "template.md"
    template.write_text("Review R{n}; scope={{scope}}", encoding="utf-8")
    with pytest.raises(LoopQueueValidationError, match="single-brace"):
        render_bundle(
            request=CrpReviewRequest(
                plan_path=str(source),
                scope="Review",
                agent_template_path=str(template),
            ),
            round_number=1,
            artifact_dir=tmp_path / "artifacts",
        )


def test_cli_lists_loops_and_surfaces():
    loops = runner.invoke(wloop_app, ["list-loops"])
    assert loops.exit_code == 0, loops.stdout
    assert '"loop_id": "crp"' in loops.stdout
    assert '"agent-surface"' in loops.stdout

    surfaces = runner.invoke(wloop_app, ["list-surfaces"])
    assert surfaces.exit_code == 0, surfaces.stdout
    assert '"surface_id": "cursor"' in surfaces.stdout
    assert '"surface_id": "codex"' in surfaces.stdout
    assert '"status": "external"' in surfaces.stdout


def test_cli_enqueue_status_cancel(tmp_path: Path):
    source = tmp_path / "PLAN.md"
    source.write_text("# Plan\n", encoding="utf-8")
    template = tmp_path / "template.md"
    template.write_text("Round {{round_number}} for {{plan_path}}", encoding="utf-8")
    config = tmp_path / "job.json"
    config.write_text(
        f"""{{
  "job_id": "cli-job",
  "loop_id": "crp",
  "executor": "agent-surface",
  "surface_id": "cursor",
  "config": {{
    "plan_path": "{source}",
    "scope": "CLI test",
    "agent_template_path": "{template}"
  }}
}}""",
        encoding="utf-8",
    )
    root = tmp_path / "queue"
    result = runner.invoke(
        wloop_app, ["enqueue", "--config", str(config), "--root", str(root)]
    )
    assert result.exit_code == 0, result.stdout
    assert '"status": "pending"' in result.stdout

    status = runner.invoke(
        wloop_app, ["status", "--job-id", "cli-job", "--root", str(root)]
    )
    assert status.exit_code == 0, status.stdout
    assert '"job_id": "cli-job"' in status.stdout

    cancelled = runner.invoke(
        wloop_app, ["cancel", "--job-id", "cli-job", "--root", str(root)]
    )
    assert cancelled.exit_code == 0, cancelled.stdout
    assert '"status": "cancelled"' in cancelled.stdout
