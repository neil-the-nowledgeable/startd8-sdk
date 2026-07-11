# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Tests for config-driven facilitation context resolution (FR-6/FR-7)."""

from __future__ import annotations

from pathlib import Path

from startd8.stakeholder_panel.context_resolver import (
    NEUTRAL_DESC,
    NEUTRAL_OBJECTIVE,
    NEUTRAL_STRATEGY,
    resolve_context,
)


def _write_business_targets(root: Path, body: str) -> None:
    d = root / "docs" / "kickoff" / "inputs"
    d.mkdir(parents=True, exist_ok=True)
    (d / "business-targets.yaml").write_text(body)


# ── derivation from the real `goals` list shape ──
def test_objective_and_strategy_derived_from_goals(tmp_path):
    _write_business_targets(
        tmp_path,
        """
domain: business-targets
goals:
  - id: G-1
    metric: reviewed_cells_covered
    target: "65 reviewable r0 cells reviewed by BE + SRE"
  - id: G-2
    metric: human_auto_agreement_captured
    target: "every reviewed cell records agree/disagree"
""",
    )
    ctx = resolve_context(tmp_path)
    assert "65 reviewable r0 cells" in ctx.objective
    assert "every reviewed cell records agree/disagree" in ctx.objective
    assert "reviewed_cells_covered" in ctx.strategy
    assert ctx.sources["objective"] == "business-targets.yaml"
    assert ctx.sources["strategy"] == "business-targets.yaml"
    assert "objective" not in ctx.missing
    # No retail domain anywhere.
    assert "blue planet" not in (ctx.objective + ctx.strategy + ctx.desc).lower()


def test_explicit_fields_win_over_derived(tmp_path):
    _write_business_targets(
        tmp_path,
        """
domain: business-targets
objective: "Ship the reviewer portal cleanly."
strategy: "Cover every cell, then publish."
goals:
  - id: G-1
    metric: m
    target: "t"
""",
    )
    ctx = resolve_context(tmp_path)
    assert ctx.objective == "Ship the reviewer portal cleanly."
    assert ctx.strategy == "Cover every cell, then publish."


def test_override_args_win(tmp_path):
    _write_business_targets(tmp_path, "domain: business-targets\ngoals: [{id: G, metric: m, target: t}]\n")
    ctx = resolve_context(tmp_path, objective="OVR-O", strategy="OVR-S", desc="OVR-D")
    assert (ctx.objective, ctx.strategy, ctx.desc) == ("OVR-O", "OVR-S", "OVR-D")
    assert ctx.sources == {"objective": "override", "strategy": "override", "desc": "override"}
    assert ctx.missing == []


# ── desc sources ──
def test_desc_from_business_targets_description(tmp_path):
    _write_business_targets(
        tmp_path,
        "domain: business-targets\ndescription: 'An internal benchmark reviewer portal.'\n",
    )
    ctx = resolve_context(tmp_path)
    assert ctx.desc == "An internal benchmark reviewer portal."
    assert ctx.sources["desc"] == "business-targets.yaml"


def test_desc_from_requirements_overview(tmp_path):
    _write_business_targets(tmp_path, "domain: business-targets\n")
    req = tmp_path / "REQUIREMENTS.md"
    req.write_text(
        "# Portal Requirements\n\n**Version:** 0.1\n\n## 1. Problem Statement\n\n"
        "The reviewer portal is a human-review layer over a multi-model benchmark.\n\n## 2. Requirements\n"
    )
    ctx = resolve_context(tmp_path)
    assert "human-review layer over a multi-model benchmark" in ctx.desc
    assert ctx.sources["desc"].startswith("requirements:")


# ── neutral fallback when nothing is present ──
def test_neutral_fallback_records_missing(tmp_path):
    ctx = resolve_context(tmp_path)  # no inputs at all
    assert ctx.desc == NEUTRAL_DESC
    assert ctx.objective == NEUTRAL_OBJECTIVE
    assert ctx.strategy == NEUTRAL_STRATEGY
    assert set(ctx.missing) == {"desc", "objective", "strategy"}
    assert all(v == "default-neutral" for v in ctx.sources.values())
    assert "context:" in ctx.summary_line()
    assert "neutral fallback" in ctx.summary_line()
