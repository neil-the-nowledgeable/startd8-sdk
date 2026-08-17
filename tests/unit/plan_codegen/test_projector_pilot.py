"""FR-7 pilot: the projector across the iteration-1 matrix, golden-first (reflective-adoption).

Five pilot cells (REQ-29 FR-7):
  1. REQ-08 (9 FRs)  — golden-parity ⭐  diff vs PLAN-nl-programming-pipeline-provenance.md
  2. REQ-01 (19 FRs) — golden-parity / stress ⭐  diff vs PLAN-01-sdk-node-home.md
  3. REQ-03          — negative-gate: projects NOTHING (solo/NONE)
  4. REQ-16 (4 FRs)  — demand-clearing: a conformant det-plan/0.1
  5. REQ-17 (4 FRs)  — demand-clearing: second demand case

The golden-diff *deltas* + their dispositions are recorded in the pilot report
(``docs/design/requirements-visualization/PILOT_REPORT_REQ-29-det-plan-projector.md``); these tests
pin the hard, machine-checkable facts (projected / conformant / skipped) the report rests on.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from startd8.plan_codegen import (
    NotPlanOwedError,
    is_plan_owed,
    project_plan,
    render_plan,
    validate_plan,
)

pytestmark = pytest.mark.unit

# The NLPS design corpus (this repo's design docs) — the pilot subjects live here.
_DOCS = (
    Path(__file__).resolve().parents[3]
    / "docs"
    / "design"
    / "requirements-visualization"
)


def _req(stem: str) -> Path:
    p = _DOCS / f"{stem}.md"
    if not p.is_file():
        pytest.skip(f"pilot subject {p} not present in this checkout")
    return p


def _project(stem: str):
    p = _req(stem)
    plan = project_plan(p.read_text(encoding="utf-8"), req_path=p)
    fr_ids = {fr for it in plan.iterations for fr in it.frs}
    findings = validate_plan(plan, req_fr_ids=fr_ids, base_dir=_DOCS)
    return p, plan, findings


# ── Cells 1 & 2: golden-parity ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "req_stem, golden_stem",
    [
        (
            "REQ-08-nl-programming-pipeline-provenance",
            "PLAN-nl-programming-pipeline-provenance",
        ),
        ("REQ-01-sdk-node-home", "PLAN-01-sdk-node-home"),
    ],
)
def test_golden_parity_projects_conformant_and_the_delta_is_real(req_stem, golden_stem):
    p, plan, findings = _project(req_stem)
    # It projects (plan-owed), stamped 0.1, LIVE pairsWith (the req resolves) → no errors.
    assert plan.maturity == "0.1"
    assert [f for f in findings if f.severity == "error"] == []
    # The projection covers every FR the req declares.
    req_fr_count = sum(
        1 for line in p.read_text().splitlines() if line.strip().startswith("- **FR-")
    )
    projected_frs = {fr for it in plan.iterations for fr in it.frs}
    assert len(projected_frs) == req_fr_count

    # The golden human PLAN exists and the projection DOES NOT match it byte-for-byte — the delta is
    # the deliverable (recorded in the pilot report as friction / human-residue).
    golden = _DOCS / f"{golden_stem}.md"
    assert golden.is_file()
    assert render_plan(plan) != golden.read_text(encoding="utf-8")


def test_golden_projection_carries_the_verify_rollup_and_phantom_audit():
    # Two sections the human PLANs carry that the projector DOES derive (folded, not residue):
    # the Verify (whole change) rollup (§5) and the reuse/phantom audit (§4).
    _, plan, _ = _project("REQ-08-nl-programming-pipeline-provenance")
    rendered = render_plan(plan)
    assert "Verify (whole change)" in rendered
    assert "phantom audit" in rendered
    assert plan.verify_rollup  # every FR verify carried forward


# ── Cell 3: negative-gate ─────────────────────────────────────────────────────────────────────────


def test_negative_gate_solo_req_projects_nothing():
    p = _req("REQ-03-a11y-renderer-and-corpus-index")
    assert is_plan_owed(p.read_text(encoding="utf-8")) is False
    with pytest.raises(NotPlanOwedError):
        project_plan(p.read_text(encoding="utf-8"), req_path=p)


# ── Cells 4 & 5: demand-clearing ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "req_stem",
    [
        "REQ-16-node-derivation-edge-and-schema-conformance",
        "REQ-17-promote-oracle-gate-history-to-node-fields",
    ],
)
def test_demand_clearing_projects_a_conformant_det_plan(req_stem):
    p, plan, findings = _project(req_stem)
    # A companionless small REQ projects a fully conformant det-plan/0.1: no findings at all
    # (pairsWith resolves LIVE against the corpus dir → not even a liveness warning).
    assert (
        findings == []
    ), f"{req_stem} should project cleanly, got {[f.check for f in findings]}"
    assert plan.companion_kind == "PLAN"
    assert plan.maturity == "0.1"
    assert plan.iterations
    # Every iteration carries a gate (§5) and a valid cost band.
    for it in plan.iterations:
        assert it.gate
        assert it.cost_class in ("deterministic-$0", "llm-integration", "human")
