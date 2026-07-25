# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Increment 3: budget fail-closed + experimental API smoke."""

from __future__ import annotations

from pathlib import Path

import pytest

from startd8.workflows import loop_queue as wlq_api
from startd8.workflows.loop_queue import (
    LoopQueueConfig,
    LoopQueueValidationError,
    WorkflowLoopJob,
    WorkflowLoopQueue,
)
from startd8.workflows.models import ValidationResult, WorkflowResult


def test_zero_dollar_budget_refuses_sdk_enqueue(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "startd8.workflows.loop_queue.queue.WorkflowRegistry.discover",
        lambda: None,
    )
    monkeypatch.setattr(
        "startd8.workflows.loop_queue.queue.WorkflowRegistry.get_workflow_info",
        lambda workflow_id: {"workflow_id": workflow_id},
    )
    monkeypatch.setattr(
        "startd8.workflows.loop_queue.queue.WorkflowRegistry.validate_config",
        lambda _wid, _cfg: ValidationResult.success(),
    )
    queue = WorkflowLoopQueue(LoopQueueConfig(queue_root=tmp_path / "queue"))
    with pytest.raises(LoopQueueValidationError, match="max_cost_usd=0"):
        queue.enqueue(
            WorkflowLoopJob(
                job_id="broke",
                loop_id="one-shot",
                executor="sdk-workflow",
                workflow_id="plain-language",
                config={"document_path": "/tmp/x.md"},
                budget={"max_cost_usd": 0},
            )
        )


def test_positive_budget_allows_sdk_drain(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "startd8.workflows.loop_queue.queue.WorkflowRegistry.discover",
        lambda: None,
    )
    monkeypatch.setattr(
        "startd8.workflows.loop_queue.queue.WorkflowRegistry.get_workflow_info",
        lambda workflow_id: {"workflow_id": workflow_id},
    )
    monkeypatch.setattr(
        "startd8.workflows.loop_queue.queue.WorkflowRegistry.validate_config",
        lambda _wid, _cfg: ValidationResult.success(),
    )
    monkeypatch.setattr(
        "startd8.workflows.loop_queue.queue.WorkflowRegistry.run_workflow",
        lambda workflow_id, config, agents=None, on_progress=None, dry_run=False: (
            WorkflowResult(workflow_id=workflow_id, success=True, output={})
        ),
    )
    queue = WorkflowLoopQueue(LoopQueueConfig(queue_root=tmp_path / "queue"))
    queue.enqueue(
        WorkflowLoopJob(
            job_id="budgeted",
            loop_id="one-shot",
            executor="sdk-workflow",
            workflow_id="plain-language",
            config={"document_path": "/tmp/x.md"},
            budget={"max_cost_usd": 5.0},
        )
    )
    assert queue.run_next("budgeted").status.value == "completed"


def test_experimental_api_exports_smoke():
    assert hasattr(wlq_api, "WorkflowLoopQueue")
    assert hasattr(wlq_api, "CrpReviewRequest")
    assert hasattr(wlq_api, "DrainHandoff")
    assert hasattr(wlq_api, "map_crp_request_to_workflow_config")
    assert "experimental" in (wlq_api.__doc__ or "").lower()
