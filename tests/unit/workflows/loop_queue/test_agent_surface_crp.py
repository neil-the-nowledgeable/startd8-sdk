# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Inc 0.5/1 tests: VASI hand-off, mock surface, R1→R2, triage."""

import json
from pathlib import Path
from typing import Optional

import pytest

from startd8.workflows.builtin.architectural_review_log_constants import (
    APPENDIX_TEMPLATE,
)
from startd8.workflows.loop_queue import (
    DrainHandoff,
    LoopJobStatus,
    LoopQueueBlockedError,
    LoopQueueConfig,
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


def _make_queue_and_job(
    tmp_path: Path,
    *,
    dual: bool = True,
    max_rounds: int = 2,
) -> tuple[WorkflowLoopQueue, WorkflowLoopJob, Path, Optional[Path]]:
    plan = tmp_path / "PLAN.md"
    plan.write_text("# Plan\n\nArchitecture text.\n", encoding="utf-8")
    requirements = tmp_path / "REQUIREMENTS.md" if dual else None
    if requirements:
        requirements.write_text("# Requirements\n\nFR-1 text.\n", encoding="utf-8")
    template = tmp_path / "agent-template.md"
    template.write_text(_TEMPLATE, encoding="utf-8")
    config = {
        "plan_path": str(plan),
        "scope": "Review architecture and requirements",
        "max_rounds": max_rounds,
        "substantially_addressed_threshold": 3,
        "max_suggestions": 10,
        "agent_template_path": str(template),
    }
    if requirements:
        config["requirements_path"] = str(requirements)
    job = WorkflowLoopJob(
        job_id="mock-crp",
        loop_id="crp",
        executor="agent-surface",
        surface_id="mock-surface",
        config={
            **config,
            "surface_conformance": {
                "vasi_version": "0.1.0",
                "capabilities": ["status", "drain"],
            },
        },
    )
    queue = WorkflowLoopQueue(LoopQueueConfig(queue_root=tmp_path / "queue"))
    queue.enqueue(job)
    return queue, job, plan, requirements


def _mock_surface_drain(
    queue: WorkflowLoopQueue,
    handoff: DrainHandoff,
) -> None:
    """Vendor-neutral fixture: only consumes hand-off and writes result."""
    assert Path(handoff.bundle_path).is_file()
    counts = {"S": 0, "F": 0}
    for raw_path in handoff.source_paths:
        path = Path(raw_path)
        doc = path.read_text(encoding="utf-8")
        if "### Appendix C: Incoming Suggestions" not in doc:
            doc = doc.rstrip() + "\n\n" + APPENDIX_TEMPLATE
        prefix = "F" if "REQUIREMENTS" in path.name else "S"
        counts[prefix] += 1
        doc += (
            f"\n\n#### Review Round R{handoff.round_number} — mock — 2026-07-24\n\n"
            f"| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |\n"
            f"|----|------|----------|------------|-----------|--------------------|---------------------|\n"
            f"| R{handoff.round_number}-{prefix}1 | Architecture | medium | "
            f"Mock {prefix} suggestion | Test rationale | §1 | Unit test |\n"
        )
        if prefix == "S" and handoff.success_criteria["dual_doc_coverage_matrix"]:
            doc += (
                f"\n## Requirements Coverage Matrix — R{handoff.round_number}\n\n"
                "| Requirement | Coverage |\n|---|---|\n| FR-1 | Covered |\n"
            )
        path.write_text(doc, encoding="utf-8")

    Path(handoff.status_writeback_path).write_text(
        json.dumps(
            {
                "vasi_version": "0.1.0",
                "job_id": handoff.job_id,
                "surface_id": handoff.surface_id,
                "ok": True,
                "round_number": handoff.round_number,
                "suggestion_counts": counts,
                "paths_written": handoff.source_paths,
                "error": None,
            }
        ),
        encoding="utf-8",
    )


def test_mock_surface_dual_doc_r1_r2_and_triage(tmp_path: Path):
    queue, _, plan, requirements = _make_queue_and_job(tmp_path)
    assert requirements is not None

    handoff1 = queue.run_next("mock-crp")
    assert isinstance(handoff1, DrainHandoff)
    assert handoff1.round_number == 1
    assert handoff1.surface_id == "mock-surface"
    assert "{{" not in Path(handoff1.bundle_path).read_text(encoding="utf-8")

    _mock_surface_drain(queue, handoff1)
    job = queue.run_next("mock-crp")
    assert job.status is LoopJobStatus.AWAITING_TRIAGE
    assert job.rounds[0].suggestion_counts == {"S": 1, "F": 1}
    assert not queue.storage.result_path("mock-crp").exists()

    job = queue.triage(
        "mock-crp",
        [
            {
                "id": "R1-S1",
                "decision": "ACCEPT",
                "summary": "Mock plan change",
                "rationale": "Accepted for test",
                "source": "mock",
            },
            {
                "id": "R1-F1",
                "decision": "REJECT",
                "summary": "Mock requirements change",
                "rationale": "Rejected for test",
                "source": "mock",
            },
        ],
    )
    assert job.status is LoopJobStatus.PENDING
    assert "R1-S1" in plan.read_text(encoding="utf-8")
    assert "R1-F1" in requirements.read_text(encoding="utf-8")
    assert "#### Review Round R1" in plan.read_text(encoding="utf-8")

    handoff2 = queue.run_next("mock-crp")
    assert isinstance(handoff2, DrainHandoff)
    assert handoff2.round_number == 2
    _mock_surface_drain(queue, handoff2)
    assert queue.run_next("mock-crp").status is LoopJobStatus.AWAITING_TRIAGE

    final = queue.triage(
        "mock-crp",
        [
            {
                "id": "R2-S1",
                "decision": "REJECT",
                "summary": "Round 2 plan item",
                "rationale": "No longer needed",
            },
            {
                "id": "R2-F1",
                "decision": "ACCEPT",
                "summary": "Round 2 requirement",
                "rationale": "Needed",
            },
        ],
    )
    assert final.status is LoopJobStatus.COMPLETED
    assert len(final.rounds) == 2
    assert plan.read_text(encoding="utf-8").count("#### Review Round R1") == 1
    assert plan.read_text(encoding="utf-8").count("#### Review Round R2") == 1


def test_max_rounds_one_never_schedules_second_round(tmp_path: Path):
    queue, _, _, _ = _make_queue_and_job(tmp_path, dual=False, max_rounds=1)
    handoff = queue.run_next("mock-crp")
    assert isinstance(handoff, DrainHandoff)
    _mock_surface_drain(queue, handoff)
    assert queue.run_next("mock-crp").status is LoopJobStatus.AWAITING_TRIAGE
    final = queue.triage(
        "mock-crp",
        [
            {
                "id": "R1-S1",
                "decision": "ACCEPT",
                "summary": "Item",
                "rationale": "Good",
            }
        ],
    )
    assert final.status is LoopJobStatus.COMPLETED


def test_render_cache_reuses_same_bundle(tmp_path: Path):
    queue, _, _, _ = _make_queue_and_job(tmp_path, dual=False)
    first = queue.render("mock-crp")
    second = queue.render("mock-crp")
    assert first == second
    assert len(list(queue.storage.artifact_dir("mock-crp").glob("bundle-*.md"))) == 1


def test_delete_after_enqueue_blocks_and_can_requeue(tmp_path: Path):
    queue, _, plan, _ = _make_queue_and_job(tmp_path, dual=False)
    plan.unlink()
    with pytest.raises(LoopQueueBlockedError, match="vanished"):
        queue.run_next("mock-crp")
    assert queue.get("mock-crp").status is LoopJobStatus.BLOCKED
    plan.write_text("# Restored\n", encoding="utf-8")
    assert queue.requeue("mock-crp").status is LoopJobStatus.PENDING


def test_invalid_surface_writeback_fails_closed(tmp_path: Path):
    queue, _, _, _ = _make_queue_and_job(tmp_path, dual=False)
    handoff = queue.run_next("mock-crp")
    assert isinstance(handoff, DrainHandoff)
    Path(handoff.status_writeback_path).write_text(
        json.dumps(
            {
                "vasi_version": "0.1.0",
                "job_id": "wrong-job",
                "surface_id": handoff.surface_id,
                "ok": True,
                "round_number": handoff.round_number,
                "suggestion_counts": {},
                "paths_written": handoff.source_paths,
                "error": None,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(Exception, match="job_id"):
        queue.run_next("mock-crp")
    assert queue.get("mock-crp").status is LoopJobStatus.FAILED


def test_vasi_handoff_matches_published_json_schema(tmp_path: Path):
    jsonschema = pytest.importorskip("jsonschema")
    queue, _, _, _ = _make_queue_and_job(tmp_path, dual=False)
    handoff = queue.run_next("mock-crp")
    assert isinstance(handoff, DrainHandoff)
    schema_path = (
        Path(__file__).parents[4]
        / "docs/design/cursor-workflow-loop/schemas/drain-handoff.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    jsonschema.validate(handoff.model_dump(mode="json"), schema)
