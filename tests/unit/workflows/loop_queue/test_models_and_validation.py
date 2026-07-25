# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Inc 0 contract tests: envelope, CRP intent, fail-closed enqueue."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from startd8.workflows.loop_queue import (
    CrpReviewRequest,
    LoopExecutor,
    LoopJobStatus,
    LoopQueueConfig,
    LoopQueueValidationError,
    WorkflowLoopJob,
    WorkflowLoopQueue,
)


def _job(path: Path, **overrides) -> WorkflowLoopJob:
    data = {
        "job_id": "crp-test",
        "loop_id": "crp",
        "executor": "agent-surface",
        "surface_id": "cursor",
        "config": {
            "plan_path": str(path),
            "scope": "Review architecture",
            "max_rounds": 2,
            "substantially_addressed_threshold": 3,
            "max_suggestions": 10,
        },
    }
    data.update(overrides)
    return WorkflowLoopJob.model_validate(data)


def test_job_envelope_round_trips_every_status(tmp_path: Path):
    source = tmp_path / "PLAN.md"
    source.write_text("# Plan\n", encoding="utf-8")
    for status in LoopJobStatus:
        job = _job(source, job_id=f"status-{status.value}", status=status)
        assert (
            WorkflowLoopJob.model_validate_json(job.model_dump_json()).status is status
        )


def test_job_envelope_rejects_path_traversal_and_wrong_schema_version(
    tmp_path: Path,
):
    source = tmp_path / "PLAN.md"
    source.write_text("# Plan\n", encoding="utf-8")
    with pytest.raises(ValidationError, match="string_pattern_mismatch"):
        _job(source, job_id="../../outside")
    with pytest.raises(ValidationError, match="literal_error"):
        _job(source, schema_version="9.9.9")


def test_cursor_agent_deprecated_alias_is_normalized(tmp_path: Path):
    source = tmp_path / "PLAN.md"
    source.write_text("# Plan\n", encoding="utf-8")
    job = _job(source, executor="cursor-agent", surface_id=None)
    assert job.executor is LoopExecutor.AGENT_SURFACE
    assert job.surface_id == "cursor"


def test_crp_intent_requires_source_and_rejects_unknown_keys():
    with pytest.raises(ValidationError, match="requires plan_path"):
        CrpReviewRequest(
            scope="x",
            max_rounds=1,
            substantially_addressed_threshold=3,
            max_suggestions=5,
        )
    with pytest.raises(ValidationError, match="extra_forbidden"):
        CrpReviewRequest.model_validate(
            {
                "plan_path": "/x.md",
                "scope": "x",
                "mystery": True,
            }
        )


def test_cursor_template_alias_is_accepted():
    request = CrpReviewRequest.model_validate(
        {
            "plan_path": "/x.md",
            "scope": "x",
            "cursor_template_path": "/template.md",
        }
    )
    assert request.agent_template_path == "/template.md"


def test_enqueue_rejects_missing_path(tmp_path: Path):
    queue = WorkflowLoopQueue(LoopQueueConfig(queue_root=tmp_path / "queue"))
    with pytest.raises(LoopQueueValidationError, match="does not exist"):
        queue.enqueue(_job(tmp_path / "missing.md"))
    assert queue.list_jobs() == []


def test_enqueue_rejects_non_markdown_source(tmp_path: Path):
    source = tmp_path / "PLAN.txt"
    source.write_text("not markdown", encoding="utf-8")
    queue = WorkflowLoopQueue(LoopQueueConfig(queue_root=tmp_path / "queue"))
    with pytest.raises(LoopQueueValidationError, match="must be markdown"):
        queue.enqueue(_job(source))


def test_enqueue_persists_atomic_job_status(tmp_path: Path):
    source = tmp_path / "PLAN.md"
    source.write_text("# Plan\n", encoding="utf-8")
    queue = WorkflowLoopQueue(LoopQueueConfig(queue_root=tmp_path / "queue"))
    queue.enqueue(_job(source))
    loaded = queue.get("crp-test")
    assert loaded.status is LoopJobStatus.PENDING
    on_disk = json.loads(queue.storage.job_path("crp-test").read_text())
    assert on_disk["config"]["scope"] == "Review architecture"


def test_unknown_surface_requires_vasi_conformance(tmp_path: Path):
    source = tmp_path / "PLAN.md"
    source.write_text("# Plan\n", encoding="utf-8")
    queue = WorkflowLoopQueue(LoopQueueConfig(queue_root=tmp_path / "queue"))
    with pytest.raises(LoopQueueValidationError, match="must declare"):
        queue.enqueue(_job(source, surface_id="future-ide"))

    conformed = _job(
        source,
        job_id="future",
        surface_id="future-ide",
        config={
            "plan_path": str(source),
            "scope": "Review",
            "surface_conformance": {
                "vasi_version": "0.1.0",
                "capabilities": ["status", "drain"],
            },
        },
    )
    assert queue.enqueue(conformed).surface_id == "future-ide"


def test_sdk_review_template_rejects_agent_bundle(tmp_path: Path, monkeypatch):
    source = tmp_path / "PLAN.md"
    source.write_text("# Plan\n", encoding="utf-8")
    monkeypatch.setattr(
        "startd8.workflows.loop_queue.queue.WorkflowRegistry.discover",
        lambda: None,
    )
    monkeypatch.setattr(
        "startd8.workflows.loop_queue.queue.WorkflowRegistry.get_workflow_info",
        lambda workflow_id: {"workflow_id": workflow_id},
    )
    job = WorkflowLoopJob(
        job_id="sdk-crp",
        loop_id="crp",
        executor="sdk-workflow",
        workflow_id="architectural-review-log",
        config={
            "plan_path": str(source),
            "scope": "Review",
            "review_template": "Append #### Review Round R{n}\n{{scope}}",
        },
    )
    queue = WorkflowLoopQueue(LoopQueueConfig(queue_root=tmp_path / "queue"))
    with pytest.raises(LoopQueueValidationError, match="agent-surface"):
        queue.enqueue(job)


def test_unknown_workflow_fails_closed(tmp_path: Path):
    source = tmp_path / "PLAN.md"
    source.write_text("# Plan\n", encoding="utf-8")
    job = WorkflowLoopJob(
        job_id="sdk-crp",
        loop_id="crp",
        executor="sdk-workflow",
        workflow_id="definitely-not-a-workflow",
        config={"plan_path": str(source), "scope": "Review"},
    )
    queue = WorkflowLoopQueue(LoopQueueConfig(queue_root=tmp_path / "queue"))
    with pytest.raises(LoopQueueValidationError, match="unknown workflow_id"):
        queue.enqueue(job)
