# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Tests for WLQ CRP Appendix A/B/C scaffold ownership."""

from __future__ import annotations

from pathlib import Path

from startd8.workflows.loop_queue.scaffold import (
    SCAFFOLD_MARKER,
    ensure_review_log_scaffold,
    ensure_source_scaffolds,
    has_review_log_scaffold,
)
from startd8.workflows.loop_queue.models import DrainHandoff


def test_ensure_scaffold_appends_once(tmp_path: Path) -> None:
    doc = tmp_path / "plan.md"
    doc.write_text("# Plan\n\nBody.\n", encoding="utf-8")
    assert not has_review_log_scaffold(doc)
    assert ensure_review_log_scaffold(doc) is True
    text = doc.read_text(encoding="utf-8")
    assert SCAFFOLD_MARKER in text
    assert "### Appendix A: Applied Suggestions" in text
    assert "### Appendix B: Rejected Suggestions (with Rationale)" in text
    assert "### Appendix C: Incoming Suggestions" in text
    # Idempotent — second call leaves bytes unchanged.
    before = doc.read_bytes()
    assert ensure_review_log_scaffold(doc) is False
    assert doc.read_bytes() == before


def test_ensure_source_scaffolds_dual_doc(tmp_path: Path) -> None:
    plan = tmp_path / "plan.md"
    reqs = tmp_path / "reqs.md"
    plan.write_text("# Plan\n", encoding="utf-8")
    reqs.write_text("# Reqs\n", encoding="utf-8")
    initialized = ensure_source_scaffolds([plan, reqs])
    assert {p.name for p in initialized} == {"plan.md", "reqs.md"}
    assert ensure_source_scaffolds([plan, reqs]) == []


def test_drain_handoff_defaults_scaffold_ensured() -> None:
    handoff = DrainHandoff(
        job_id="job-1",
        surface_id="cursor",
        loop_id="crp",
        round_number=1,
        bundle_path="/tmp/bundle.md",
        source_paths=["/tmp/plan.md"],
        status_writeback_path="/tmp/drain-result.json",
    )
    assert handoff.success_criteria["init_appendix_if_missing"] is False
    assert handoff.success_criteria["appendix_scaffold_ensured"] is True
    assert handoff.success_criteria["append_review_round"] is True
