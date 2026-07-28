# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Tests for packaged WLQ prompt configs (P0 externalization)."""

from __future__ import annotations

from pathlib import Path

import pytest

from startd8.workflows.loop_queue.handoff import render_handoff_markdown
from startd8.workflows.loop_queue.models import AssignedReviewer, DrainHandoff
from startd8.workflows.loop_queue.prompt_loader import (
    PROMPT_ENV,
    load_prompt_text,
    packaged_prompts_dir,
    resolve_prompt_path,
)
from startd8.workflows.loop_queue.renderer import (
    default_reflective_template_text,
    default_research_template_text,
    render_reflective_bundle,
)
from startd8.workflows.loop_queue.models import ReflectiveRequirementsRequest


def test_packaged_prompts_exist():
    root = packaged_prompts_dir()
    for name in (
        "reflective-requirements.md",
        "research.md",
        "drain-handoff.md",
        "drain-handoff-do-this-current.md",
        "drain-handoff-do-this-blind-rotate.md",
        "drain-handoff-reviewer-block.md",
        "crp-memory-preamble.md",
    ):
        assert (root / name).is_file(), name


def test_crp_memory_preamble_slots():
    text = load_prompt_text("crp-memory-preamble.md")
    assert "{{round_number}}" in text
    assert "{{applied_ids}}" in text
    assert "WLQ authoritative drain context" in text


def test_reflective_default_mentions_phase_46():
    text = default_reflective_template_text()
    assert "Phase 4.5" in text
    assert "Phase 4.6" in text
    assert "{{requirements_path}}" in text
    assert "**soft** — not consume-checked" in text
    assert "vasi_version" in text
    assert "job_id" in text
    assert "surface_id" in text


def test_reflective_recipe_completion_matches_gate_ceiling():
    from startd8.workflows.loop_queue import list_recipes

    refl = next(r for r in list_recipes() if r.loop_id == "reflective-requirements")
    assert "not consume-checked" in refl.completion
    assert "plan hardened through" not in refl.completion


def test_research_default_has_slots():
    text = default_research_template_text()
    assert "{{brief_path}}" in text
    assert "{{findings_path}}" in text


def test_env_override_reflective(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    custom = tmp_path / "custom-refl.md"
    custom.write_text("# Custom — {{scope}}\n\n`{{requirements_path}}`\n", encoding="utf-8")
    monkeypatch.setenv(PROMPT_ENV["reflective-requirements.md"], str(custom))
    assert "Custom" in load_prompt_text("reflective-requirements.md")
    assert resolve_prompt_path("reflective-requirements.md") == custom.resolve()


def test_render_reflective_uses_packaged_default(tmp_path: Path):
    req = tmp_path / "r.md"
    plan = tmp_path / "p.md"
    art = tmp_path / "art"
    art.mkdir()
    path = render_reflective_bundle(
        ReflectiveRequirementsRequest(
            scope="widget",
            requirements_path=str(req),
            plan_path=str(plan),
        ),
        art,
    )
    body = path.read_text(encoding="utf-8")
    assert "Phase 4.6" in body
    assert str(req.resolve()) in body


def test_handoff_current_from_config():
    md = render_handoff_markdown(
        DrainHandoff(
            job_id="job-1",
            surface_id="cursor",
            loop_id="reflective-requirements",
            round_number=1,
            bundle_path="/tmp/bundle.md",
            source_paths=["/tmp/a.md", "/tmp/b.md"],
            success_criteria={"write_plan": True},
            status_writeback_path="/tmp/drain-result.json",
        )
    )
    assert "# WLQ Drain Hand-off — `job-1`" in md
    assert "Open `/tmp/bundle.md`" in md
    assert "`write_plan`: True" in md


def test_handoff_blind_rotate_from_config():
    md = render_handoff_markdown(
        DrainHandoff(
            job_id="crp-1",
            surface_id="cursor",
            loop_id="crp",
            round_number=2,
            bundle_path="/tmp/b.md",
            source_paths=["/tmp/plan.md"],
            success_criteria={"append_review_round": True},
            status_writeback_path="/tmp/dr.json",
            assigned_reviewer=AssignedReviewer(
                mode="blind_rotate",
                model="claude-opus-5-thinking-high",
                roster_index=1,
                roster=["a", "claude-opus-5-thinking-high", "c"],
            ),
        )
    )
    assert "Blind rotate" in md
    assert "claude-opus-5-thinking-high" in md
    assert "## Assigned reviewer" in md
