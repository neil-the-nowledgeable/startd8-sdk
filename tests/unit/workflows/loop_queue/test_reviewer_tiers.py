# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""FR-23 reviewer_tier flagship / mid_tier presets."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from startd8.workflows.loop_queue import (
    CrpReviewRequest,
    DrainHandoff,
    FLAGSHIP_CURSOR_ROSTER,
    LoopQueueConfig,
    MID_TIER_CURSOR_ROSTER,
    WorkflowLoopJob,
    WorkflowLoopQueue,
    list_reviewer_tiers,
)
from startd8.workflows.loop_queue.reviewer_presets import resolve_reviewer_tier_roster

_TEMPLATE = """# CRP agent bundle
Round: R{{round_number}}
Scope: {{scope}}
Plan: {{plan_path}}
Requirements: {{requirements_path}}
Applied memory: {{applied_ids}}
Rejected memory: {{rejected_ids}}
Read {{source_paths}}. Append Review Round R{{round_number}} under Appendix C.
"""


def test_presets_are_three_vendors_distinct():
    assert len(FLAGSHIP_CURSOR_ROSTER) == 3
    assert len(MID_TIER_CURSOR_ROSTER) == 3
    assert set(FLAGSHIP_CURSOR_ROSTER).isdisjoint(MID_TIER_CURSOR_ROSTER)
    tiers = list_reviewer_tiers()
    assert {t["tier"] for t in tiers} == {"flagship", "mid_tier"}
    assert tiers[0]["roster"] == list(FLAGSHIP_CURSOR_ROSTER)


def test_flagship_tier_expands_roster_and_blind_rotate(tmp_path: Path):
    plan = tmp_path / "p.md"
    plan.write_text("# p\n", encoding="utf-8")
    req = CrpReviewRequest.model_validate(
        {
            "plan_path": str(plan),
            "scope": "flagship CRP",
            "max_rounds": 3,
            "reviewer_tier": "flagship",
        }
    )
    assert req.reviewer_mode == "blind_rotate"
    assert req.reviewer_roster == list(FLAGSHIP_CURSOR_ROSTER)
    assert req.assigned_reviewer_for_round(1).model == FLAGSHIP_CURSOR_ROSTER[0]
    assert req.assigned_reviewer_for_round(2).model == FLAGSHIP_CURSOR_ROSTER[1]
    assert req.assigned_reviewer_for_round(3).model == FLAGSHIP_CURSOR_ROSTER[2]
    assert req.assigned_reviewer_for_round(1).reviewer_tier == "flagship"


def test_mid_tier_expands_distinct_roster(tmp_path: Path):
    plan = tmp_path / "p.md"
    plan.write_text("# p\n", encoding="utf-8")
    req = CrpReviewRequest.model_validate(
        {
            "plan_path": str(plan),
            "scope": "mid",
            "reviewer_tier": "mid_tier",
        }
    )
    assert req.reviewer_roster == list(MID_TIER_CURSOR_ROSTER)


def test_explicit_roster_overrides_tier(tmp_path: Path):
    plan = tmp_path / "p.md"
    plan.write_text("# p\n", encoding="utf-8")
    custom = ["claude-sonnet-5-thinking-high", "gpt-5.6-sol-medium"]
    req = CrpReviewRequest.model_validate(
        {
            "plan_path": str(plan),
            "scope": "override",
            "reviewer_tier": "flagship",
            "reviewer_roster": custom,
        }
    )
    assert req.reviewer_roster == custom
    assert req.reviewer_tier == "flagship"


def test_tier_with_current_mode_fails(tmp_path: Path):
    plan = tmp_path / "p.md"
    plan.write_text("# p\n", encoding="utf-8")
    with pytest.raises(ValidationError, match="blind_rotate"):
        CrpReviewRequest.model_validate(
            {
                "plan_path": str(plan),
                "scope": "bad",
                "reviewer_mode": "current",
                "reviewer_tier": "flagship",
            }
        )


def test_handoff_uses_flagship_roster(tmp_path: Path):
    plan = tmp_path / "PLAN.md"
    plan.write_text("# Plan\n\nBody.\n", encoding="utf-8")
    template = tmp_path / "t.md"
    template.write_text(_TEMPLATE, encoding="utf-8")
    queue = WorkflowLoopQueue(LoopQueueConfig(queue_root=tmp_path / "q"))
    queue.enqueue(
        WorkflowLoopJob(
            job_id="tier-crp",
            loop_id="crp",
            executor="agent-surface",
            surface_id="mock-surface",
            config={
                "plan_path": str(plan),
                "scope": "tier handoff",
                "max_rounds": 3,
                "substantially_addressed_threshold": 3,
                "max_suggestions": 10,
                "agent_template_path": str(template),
                "reviewer_tier": "flagship",
                "surface_conformance": {
                    "vasi_version": "0.1.0",
                    "capabilities": ["status", "drain"],
                },
            },
        )
    )
    handoff = queue.run_next("tier-crp")
    assert isinstance(handoff, DrainHandoff)
    assert handoff.assigned_reviewer is not None
    assert handoff.assigned_reviewer.model == FLAGSHIP_CURSOR_ROSTER[0]
    assert handoff.assigned_reviewer.reviewer_tier == "flagship"
    assert handoff.assigned_reviewer.roster == list(FLAGSHIP_CURSOR_ROSTER)


def test_resolve_unknown_tier_fails():
    with pytest.raises(ValueError, match="unknown reviewer_tier"):
        resolve_reviewer_tier_roster("legendary")  # type: ignore[arg-type]
