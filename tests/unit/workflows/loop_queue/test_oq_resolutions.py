# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Open-question resolutions: lease TTL, reflective-reqs, markdown hand-off."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from startd8.workflows.loop_queue import (
    DrainHandoff,
    LoopJobStatus,
    LoopQueueConfig,
    WorkflowLoopJob,
    WorkflowLoopQueue,
)


def test_expired_lease_is_reclaimed(tmp_path: Path):
    plan = tmp_path / "PLAN.md"
    plan.write_text("# Plan\n", encoding="utf-8")
    template = tmp_path / "t.md"
    template.write_text("Round {{round_number}} {{plan_path}} {{scope}}", encoding="utf-8")
    queue = WorkflowLoopQueue(
        LoopQueueConfig(queue_root=tmp_path / "queue", lease_ttl_seconds=60)
    )
    queue.enqueue(
        WorkflowLoopJob(
            job_id="leased",
            loop_id="crp",
            executor="agent-surface",
            surface_id="cursor",
            config={
                "plan_path": str(plan),
                "scope": "Lease test",
                "agent_template_path": str(template),
            },
        )
    )
    handoff = queue.run_next("leased")
    assert isinstance(handoff, DrainHandoff)
    job = queue.get("leased")
    assert job.status is LoopJobStatus.PROCESSING
    assert job.lease_expires_at is not None

    # Force expiry and reclaim.
    job.lease_expires_at = (
        datetime.now(timezone.utc) - timedelta(seconds=1)
    ).isoformat()
    queue.storage.save_job(job)
    reclaimed = queue.reclaim_expired_leases()
    assert reclaimed == ["leased"]
    assert queue.get("leased").status is LoopJobStatus.PENDING
    assert queue.get("leased").lease_expires_at is None


def test_lease_disabled_with_zero_ttl(tmp_path: Path):
    plan = tmp_path / "PLAN.md"
    plan.write_text("# Plan\n", encoding="utf-8")
    template = tmp_path / "t.md"
    template.write_text("{{scope}} {{plan_path}} {{round_number}}", encoding="utf-8")
    queue = WorkflowLoopQueue(
        LoopQueueConfig(queue_root=tmp_path / "queue", lease_ttl_seconds=0)
    )
    queue.enqueue(
        WorkflowLoopJob(
            job_id="nolease",
            loop_id="crp",
            executor="agent-surface",
            surface_id="cursor",
            config={
                "plan_path": str(plan),
                "scope": "No lease",
                "agent_template_path": str(template),
            },
        )
    )
    queue.run_next("nolease")
    assert queue.get("nolease").lease_expires_at is None
    assert queue.reclaim_expired_leases() == []


def test_markdown_card_emitted_with_handoff(tmp_path: Path):
    plan = tmp_path / "PLAN.md"
    plan.write_text("# Plan\n", encoding="utf-8")
    template = tmp_path / "t.md"
    template.write_text("{{scope}} {{plan_path}} {{round_number}}", encoding="utf-8")
    queue = WorkflowLoopQueue(LoopQueueConfig(queue_root=tmp_path / "queue"))
    queue.enqueue(
        WorkflowLoopJob(
            job_id="card",
            loop_id="crp",
            executor="agent-surface",
            surface_id="cursor",
            config={
                "plan_path": str(plan),
                "scope": "Card",
                "agent_template_path": str(template),
            },
        )
    )
    handoff = queue.run_next("card")
    assert isinstance(handoff, DrainHandoff)
    assert handoff.markdown_card_path
    card = Path(handoff.markdown_card_path)
    assert card.is_file()
    text = card.read_text(encoding="utf-8")
    assert "Drain Hand-off" in text
    assert "card" in text
    assert handoff.bundle_path in text


def test_reflective_requirements_drain(tmp_path: Path):
    out_dir = tmp_path / "docs"
    out_dir.mkdir()
    reqs = out_dir / "REQS.md"
    plan = out_dir / "PLAN.md"
    queue = WorkflowLoopQueue(LoopQueueConfig(queue_root=tmp_path / "queue"))
    queue.enqueue(
        WorkflowLoopJob(
            job_id="refl-1",
            loop_id="reflective-requirements",
            executor="agent-surface",
            surface_id="cursor",
            config={
                "scope": "Widget feature",
                "requirements_path": str(reqs),
                "plan_path": str(plan),
            },
        )
    )
    handoff = queue.run_next("refl-1")
    assert isinstance(handoff, DrainHandoff)
    assert handoff.loop_id == "reflective-requirements"
    assert handoff.round_number == 1
    assert "Widget feature" in Path(handoff.bundle_path).read_text(encoding="utf-8")
    assert handoff.markdown_card_path

    # Mock surface writes the two docs + result (must clear harden gate).
    reqs.write_text(
        "# Requirements\n\n"
        "**Version:** 0.3.1\n\n"
        "### 0.1 Lessons-Learned Hardening (v0.3)\n\n"
        "Checked lessons; none applicable.\n\n"
        "### 0.2 Design-Principle Hardening (v0.3.1)\n\n"
        "Checked design principles; none applicable.\n\n"
        "FR-1.\n",
        encoding="utf-8",
    )
    plan.write_text("# Plan\n\nSteps.\n", encoding="utf-8")
    Path(handoff.status_writeback_path).write_text(
        json.dumps(
            {
                "vasi_version": "0.1.0",
                "job_id": "refl-1",
                "surface_id": "cursor",
                "ok": True,
                "round_number": 1,
                "suggestion_counts": {},
                "paths_written": handoff.source_paths,
                "error": None,
            }
        ),
        encoding="utf-8",
    )
    done = queue.run_next("refl-1")
    assert done.status is LoopJobStatus.COMPLETED


def test_reflective_harden_gate_fails_consume_without_markers(tmp_path: Path):
    """FR-PC-3: consume must REJECT requirements that skip Phase 4.5/4.6 markers."""
    from startd8.workflows.loop_queue.models import LoopQueueValidationError

    docs = tmp_path / "docs"
    docs.mkdir()
    reqs = docs / "REQ.md"
    plan = docs / "PLAN.md"
    queue = WorkflowLoopQueue(LoopQueueConfig(queue_root=tmp_path / "queue"))
    queue.enqueue(
        WorkflowLoopJob(
            job_id="refl-fail",
            loop_id="reflective-requirements",
            executor="agent-surface",
            surface_id="cursor",
            config={
                "scope": "Skip harden",
                "requirements_path": str(reqs),
                "plan_path": str(plan),
            },
        )
    )
    handoff = queue.run_next("refl-fail")
    assert isinstance(handoff, DrainHandoff)
    reqs.write_text("# Requirements\n\nFR-1.\n", encoding="utf-8")
    plan.write_text("# Plan\n\nSteps.\n", encoding="utf-8")
    Path(handoff.status_writeback_path).write_text(
        json.dumps(
            {
                "vasi_version": "0.1.0",
                "job_id": "refl-fail",
                "surface_id": "cursor",
                "ok": True,
                "round_number": 1,
                "suggestion_counts": {},
                "paths_written": handoff.source_paths,
                "error": None,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(LoopQueueValidationError, match="Phase 4"):
        queue.run_next("refl-fail")
    assert queue.get("refl-fail").status is LoopJobStatus.FAILED


def test_reflective_enqueue_requires_parent_dir(tmp_path: Path):
    queue = WorkflowLoopQueue(LoopQueueConfig(queue_root=tmp_path / "queue"))
    with pytest.raises(Exception, match="parent directory"):
        queue.enqueue(
            WorkflowLoopJob(
                job_id="bad-parent",
                loop_id="reflective-requirements",
                executor="agent-surface",
                surface_id="cursor",
                config={
                    "scope": "X",
                    "requirements_path": str(tmp_path / "missing" / "R.md"),
                    "plan_path": str(tmp_path / "missing" / "P.md"),
                },
            )
        )


def test_list_loops_includes_reflective():
    from startd8.workflows.loop_queue import list_recipes

    ids = {r.loop_id for r in list_recipes()}
    assert "reflective-requirements" in ids
    assert "crp" in ids
    assert "research" in ids


def test_research_drain(tmp_path: Path):
    docs = tmp_path / "docs"
    docs.mkdir()
    brief = docs / "RESEARCH-Widget.md"
    findings = docs / "FINDINGS-Widget.md"
    brief.write_text(
        "# Research brief — Widget\n\n## Expected deliverables\n1. Ranked shortlist\n",
        encoding="utf-8",
    )
    queue = WorkflowLoopQueue(LoopQueueConfig(queue_root=tmp_path / "queue"))
    queue.enqueue(
        WorkflowLoopJob(
            job_id="research-widget-1",
            loop_id="research",
            executor="agent-surface",
            surface_id="cursor",
            config={
                "scope": "Widget FX opportunity scan",
                "brief_path": str(brief),
                "findings_path": str(findings),
            },
        )
    )
    handoff = queue.run_next("research-widget-1")
    assert isinstance(handoff, DrainHandoff)
    assert handoff.loop_id == "research"
    assert handoff.round_number == 1
    bundle = Path(handoff.bundle_path).read_text(encoding="utf-8")
    assert "Widget FX opportunity scan" in bundle
    assert str(brief.resolve()) in bundle
    assert str(findings.resolve()) in handoff.source_paths

    findings.write_text("# Findings — Widget\n\nDo squash first.\n", encoding="utf-8")
    Path(handoff.status_writeback_path).write_text(
        json.dumps(
            {
                "vasi_version": "0.1.0",
                "job_id": "research-widget-1",
                "surface_id": "cursor",
                "ok": True,
                "round_number": 1,
                "suggestion_counts": {},
                "paths_written": handoff.source_paths,
                "error": None,
            }
        ),
        encoding="utf-8",
    )
    done = queue.run_next("research-widget-1")
    assert done.status is LoopJobStatus.COMPLETED


def test_research_enqueue_requires_brief(tmp_path: Path):
    docs = tmp_path / "docs"
    docs.mkdir()
    queue = WorkflowLoopQueue(LoopQueueConfig(queue_root=tmp_path / "queue"))
    with pytest.raises(Exception, match="brief_path"):
        queue.enqueue(
            WorkflowLoopJob(
                job_id="research-missing-brief",
                loop_id="research",
                executor="agent-surface",
                surface_id="cursor",
                config={
                    "scope": "X",
                    "brief_path": str(docs / "MISSING.md"),
                    "findings_path": str(docs / "FINDINGS.md"),
                },
            )
        )