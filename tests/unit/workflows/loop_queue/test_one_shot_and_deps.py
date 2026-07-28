# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Increment 2: one-shot catalog jobs + depends_on DAG."""

from __future__ import annotations

from pathlib import Path

import pytest

from startd8.workflows.loop_queue import (
    ONE_SHOT_PRIORITY_WORKFLOWS,
    LoopJobStatus,
    LoopQueueConfig,
    LoopQueueValidationError,
    WorkflowLoopJob,
    WorkflowLoopQueue,
)
from startd8.workflows.models import ValidationResult, WorkflowResult


def _queue(tmp_path: Path) -> WorkflowLoopQueue:
    return WorkflowLoopQueue(LoopQueueConfig(queue_root=tmp_path / "queue"))


def _stub_registry(monkeypatch) -> None:
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
            WorkflowResult(
                workflow_id=workflow_id,
                success=True,
                output={"echo": config.get("document_path")},
            )
        ),
    )


def _oneshot(job_id: str, **kwargs) -> WorkflowLoopJob:
    data = {
        "job_id": job_id,
        "loop_id": "one-shot",
        "executor": "sdk-workflow",
        "workflow_id": "plain-language",
        "config": {"document_path": f"/tmp/{job_id}.md"},
    }
    data.update(kwargs)
    return WorkflowLoopJob.model_validate(data)


def test_priority_family_is_documented():
    assert "plain-language" in ONE_SHOT_PRIORITY_WORKFLOWS
    assert "critical-review" in ONE_SHOT_PRIORITY_WORKFLOWS


def test_one_shot_drain_completes(tmp_path: Path, monkeypatch):
    _stub_registry(monkeypatch)
    queue = _queue(tmp_path)
    queue.enqueue(_oneshot("oneshot-1"))
    job = queue.run_next("oneshot-1")
    assert job.status is LoopJobStatus.COMPLETED
    assert "plain-language" in (job.status_reason or "")


def test_depends_on_blocks_until_completed(tmp_path: Path, monkeypatch):
    _stub_registry(monkeypatch)
    queue = _queue(tmp_path)
    queue.enqueue(_oneshot("a", priority=1))
    queue.enqueue(_oneshot("b", depends_on=["a"], priority=10))

    # Higher-priority B is skipped while A is unfinished.
    first = queue.run_next()
    assert first.job_id == "a"
    assert first.status is LoopJobStatus.COMPLETED

    second = queue.run_next()
    assert second.job_id == "b"
    assert second.status is LoopJobStatus.COMPLETED


def test_depends_on_unknown_and_self_fail_at_enqueue(tmp_path: Path, monkeypatch):
    _stub_registry(monkeypatch)
    queue = _queue(tmp_path)
    with pytest.raises(LoopQueueValidationError, match="unknown job_id"):
        queue.enqueue(_oneshot("orphan", depends_on=["missing"]))
    with pytest.raises(LoopQueueValidationError, match="itself"):
        queue.enqueue(_oneshot("self", depends_on=["self"]))


def test_dependency_cycle_detected_in_graph():
    cycle = WorkflowLoopQueue._find_dependency_cycle(
        {"job-a": ["job-b"], "job-b": ["job-a"]}
    )
    assert cycle is not None
    assert "job-a" in cycle and "job-b" in cycle
    assert (
        WorkflowLoopQueue._find_dependency_cycle({"job-a": [], "job-b": ["job-a"]})
        is None
    )


def test_enqueue_rejects_cycle_closing_edge(tmp_path: Path, monkeypatch):
    """A→B already on disk; enqueueing A←B via editing isn't possible, so
    seed A←C and B→C then close C→A when A already depends on C… instead:

    Enqueue leaf jobs that form a cycle only when the new edge closes it:
    a (no deps), b→a, then c→b with a forged graph check via private helper
    is covered above. Here we close a cycle by enqueueing a job that depends
    on a job which (through existing edges) already depends on it — impossible
    without mutation.

    Practical wire test: enqueue two jobs where the second's depends_on list
    includes a forward edge that, together with a third stub file written
    out-of-band, closes a cycle. Simpler: write job-a depending on job-b into
    storage without going through enqueue validation for job-a, then enqueue
    job-b depending on job-a.
    """
    _stub_registry(monkeypatch)
    queue = _queue(tmp_path)
    # Bypass enqueue validation to plant the first half of a cycle.
    planted = _oneshot("job-a", depends_on=["job-b"])
    queue.storage.save_job(planted)
    with pytest.raises(LoopQueueValidationError, match="cycle"):
        queue.enqueue(_oneshot("job-b", depends_on=["job-a"]))


def test_explicit_run_next_rejects_unmet_dependency(tmp_path: Path, monkeypatch):
    _stub_registry(monkeypatch)
    queue = _queue(tmp_path)
    queue.enqueue(_oneshot("dep"))
    queue.enqueue(_oneshot("child", depends_on=["dep"]))
    with pytest.raises(LoopQueueValidationError, match="blocked by unfinished"):
        queue.run_next("child")
