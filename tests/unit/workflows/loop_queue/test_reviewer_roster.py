# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Blind-rotate reviewer roster: assignment, coerce, fail-closed write-back."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from startd8.workflows.builtin.architectural_review_log_constants import (
    APPENDIX_TEMPLATE,
)
from startd8.workflows.loop_queue import (
    CrpReviewRequest,
    DrainHandoff,
    LoopJobStatus,
    LoopQueueConfig,
    LoopQueueValidationError,
    WorkflowLoopJob,
    WorkflowLoopQueue,
)

_TEMPLATE = """# CRP agent bundle

Round: R{{round_number}}
Scope: {{scope}}
Plan: {{plan_path}}
Requirements: {{requirements_path}}
Applied memory: {{applied_ids}}
Rejected memory: {{rejected_ids}}

Read {{source_paths}}. Append Review Round R{{round_number}} under Appendix C.
Do not triage Appendix A/B.
"""

_ROSTER = [
    "claude-opus-5-thinking-high",
    "gpt-5.6-luna-medium",
    "gemini-3.1-pro",
]


def _paths(tmp_path: Path) -> tuple[Path, Path, Path]:
    plan = tmp_path / "PLAN.md"
    plan.write_text("# Plan\n\nArchitecture text.\n", encoding="utf-8")
    requirements = tmp_path / "REQUIREMENTS.md"
    requirements.write_text("# Requirements\n\nFR-1 text.\n", encoding="utf-8")
    template = tmp_path / "agent-template.md"
    template.write_text(_TEMPLATE, encoding="utf-8")
    return plan, requirements, template


def _enqueue_roster_job(
    tmp_path: Path,
    *,
    reviewer_mode: str | None = "blind_rotate",
    roster: list[str] | None = None,
    max_rounds: int = 3,
) -> tuple[WorkflowLoopQueue, Path, Path]:
    plan, requirements, template = _paths(tmp_path)
    config: dict = {
        "plan_path": str(plan),
        "requirements_path": str(requirements),
        "scope": "Multi-vendor CRP",
        "max_rounds": max_rounds,
        "substantially_addressed_threshold": 3,
        "max_suggestions": 10,
        "agent_template_path": str(template),
        "surface_conformance": {
            "vasi_version": "0.1.0",
            "capabilities": ["status", "drain"],
        },
    }
    if reviewer_mode is not None:
        config["reviewer_mode"] = reviewer_mode
    if roster is not None:
        config["reviewer_roster"] = roster
    job = WorkflowLoopJob(
        job_id="roster-crp",
        loop_id="crp",
        executor="agent-surface",
        surface_id="mock-surface",
        config=config,
    )
    queue = WorkflowLoopQueue(LoopQueueConfig(queue_root=tmp_path / "queue"))
    queue.enqueue(job)
    return queue, plan, requirements


def _surface_drain(
    handoff: DrainHandoff,
    *,
    reviewer_model: str | None = None,
) -> None:
    for raw_path in handoff.source_paths:
        path = Path(raw_path)
        doc = path.read_text(encoding="utf-8")
        if "### Appendix C: Incoming Suggestions" not in doc:
            doc = doc.rstrip() + "\n\n" + APPENDIX_TEMPLATE
        prefix = "F" if "REQUIREMENTS" in path.name else "S"
        doc += (
            f"\n\n#### Review Round R{handoff.round_number} — mock — 2026-07-25\n\n"
            f"| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |\n"
            f"|----|------|----------|------------|-----------|--------------------|---------------------|\n"
            f"| R{handoff.round_number}-{prefix}1 | Architecture | medium | "
            f"Mock {prefix} | Test | §1 | Unit test |\n"
        )
        if prefix == "S" and handoff.success_criteria.get("dual_doc_coverage_matrix"):
            doc += (
                f"\n## Requirements Coverage Matrix — R{handoff.round_number}\n\n"
                "| Requirement | Coverage |\n|---|---|\n| FR-1 | Covered |\n"
            )
        path.write_text(doc, encoding="utf-8")

    payload = {
        "vasi_version": "0.1.0",
        "job_id": handoff.job_id,
        "surface_id": handoff.surface_id,
        "ok": True,
        "round_number": handoff.round_number,
        "suggestion_counts": {"S": 1, "F": 1},
        "paths_written": handoff.source_paths,
        "error": None,
    }
    if reviewer_model is not None:
        payload["reviewer_model"] = reviewer_model
    Path(handoff.status_writeback_path).write_text(
        json.dumps(payload), encoding="utf-8"
    )


def test_blind_rotate_requires_roster():
    with pytest.raises(ValidationError, match="reviewer_roster"):
        CrpReviewRequest(
            plan_path="/tmp/p.md",
            scope="x",
            reviewer_mode="blind_rotate",
        )


def test_roster_without_mode_coerces_to_blind_rotate(tmp_path: Path):
    plan = tmp_path / "p.md"
    plan.write_text("# p\n", encoding="utf-8")
    req = CrpReviewRequest.model_validate(
        {
            "plan_path": str(plan),
            "scope": "coerce",
            "reviewer_roster": list(_ROSTER),
        }
    )
    assert req.reviewer_mode == "blind_rotate"
    assert req.reviewer_roster == _ROSTER


def test_handoff_assigns_roster_by_round(tmp_path: Path):
    queue, plan, requirements = _enqueue_roster_job(
        tmp_path, roster=list(_ROSTER)
    )

    handoff1 = queue.run_next("roster-crp")
    assert isinstance(handoff1, DrainHandoff)
    assert handoff1.round_number == 1
    assert handoff1.assigned_reviewer is not None
    assert handoff1.assigned_reviewer.mode == "blind_rotate"
    assert handoff1.assigned_reviewer.model == _ROSTER[0]
    assert handoff1.assigned_reviewer.roster_index == 0
    card = Path(handoff1.markdown_card_path or "").read_text(encoding="utf-8")
    assert "Blind rotate" in card
    assert _ROSTER[0] in card

    _surface_drain(handoff1, reviewer_model=_ROSTER[0])
    job = queue.run_next("roster-crp")
    assert job.status is LoopJobStatus.PENDING
    assert len(job.rounds) == 1

    handoff2 = queue.run_next("roster-crp")
    assert isinstance(handoff2, DrainHandoff)
    assert handoff2.round_number == 2
    assert handoff2.assigned_reviewer is not None
    assert handoff2.assigned_reviewer.model == _ROSTER[1]
    assert handoff2.assigned_reviewer.roster_index == 1


def test_drain_result_missing_reviewer_model_fails(tmp_path: Path):
    queue, _, _ = _enqueue_roster_job(tmp_path, roster=list(_ROSTER))
    handoff = queue.run_next("roster-crp")
    assert isinstance(handoff, DrainHandoff)
    _surface_drain(handoff, reviewer_model=None)
    with pytest.raises(LoopQueueValidationError, match="reviewer_model"):
        queue.run_next("roster-crp")
    assert queue.get("roster-crp").status is LoopJobStatus.FAILED


def test_drain_result_wrong_reviewer_model_fails(tmp_path: Path):
    queue, _, _ = _enqueue_roster_job(tmp_path, roster=list(_ROSTER))
    handoff = queue.run_next("roster-crp")
    assert isinstance(handoff, DrainHandoff)
    _surface_drain(handoff, reviewer_model="wrong-model-slug")
    with pytest.raises(LoopQueueValidationError, match="reviewer_model"):
        queue.run_next("roster-crp")
    assert queue.get("roster-crp").status is LoopJobStatus.FAILED


def test_matching_reviewer_model_awaits_triage(tmp_path: Path):
    queue, _, _ = _enqueue_roster_job(tmp_path, roster=list(_ROSTER), max_rounds=1)
    handoff = queue.run_next("roster-crp")
    assert isinstance(handoff, DrainHandoff)
    _surface_drain(handoff, reviewer_model=_ROSTER[0])
    job = queue.run_next("roster-crp")
    assert job.status is LoopJobStatus.COMPLETED


def test_current_mode_does_not_require_reviewer_model(tmp_path: Path):
    queue, _, _ = _enqueue_roster_job(
        tmp_path, reviewer_mode="current", roster=None, max_rounds=1
    )
    handoff = queue.run_next("roster-crp")
    assert isinstance(handoff, DrainHandoff)
    assert handoff.assigned_reviewer is not None
    assert handoff.assigned_reviewer.mode == "current"
    assert handoff.assigned_reviewer.model is None
    _surface_drain(handoff, reviewer_model=None)
    job = queue.run_next("roster-crp")
    assert job.status is LoopJobStatus.COMPLETED


def test_enqueue_rejects_blind_rotate_empty_roster(tmp_path: Path):
    plan, requirements, template = _paths(tmp_path)
    job = WorkflowLoopJob(
        job_id="bad-roster",
        loop_id="crp",
        executor="agent-surface",
        surface_id="mock-surface",
        config={
            "plan_path": str(plan),
            "requirements_path": str(requirements),
            "scope": "bad",
            "max_rounds": 1,
            "substantially_addressed_threshold": 3,
            "max_suggestions": 10,
            "agent_template_path": str(template),
            "reviewer_mode": "blind_rotate",
            "reviewer_roster": [],
            "surface_conformance": {
                "vasi_version": "0.1.0",
                "capabilities": ["status", "drain"],
            },
        },
    )
    queue = WorkflowLoopQueue(LoopQueueConfig(queue_root=tmp_path / "queue"))
    with pytest.raises(LoopQueueValidationError, match="reviewer_roster"):
        queue.enqueue(job)
