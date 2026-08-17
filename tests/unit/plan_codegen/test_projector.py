"""Unit tests for the $0 det-req → det-plan/0.1 projector (REQ-29 FR-1..FR-6, FR-8).

Hard exit criteria exercised here:
- $0 / no LLM: the projector imports/calls nothing network/LLM (FR-2).
- Never-inferred: every dependsOn edge traces to an authored Depends:; a cyclic req is rejected by
  queue.py with a named error (FR-2).
- Solo-vs-gap gate (FR-3); anti-inflation maturity 0.1 (FR-4); conformance + SARIF (FR-5);
  provider registration/round-trip (FR-6); idempotency/byte-identity (FR-8).
"""

from __future__ import annotations

import pytest

from startd8.plan_codegen import (
    DetPlanProjectorProvider,
    NotPlanOwedError,
    PlanDependencyCycleError,
    findings_to_sarif,
    is_plan_owed,
    project_plan,
    render_plan,
    validate_plan,
)
from startd8.plan_codegen.models import COST_LLM, PROJECTED_MATURITY
from startd8.plan_codegen.projector import GROUP_SHARED_TOUCHES

pytestmark = pytest.mark.unit


# A minimal plan-owed det-req fixture (single-line FR grammar).
REQ_PLAN_OWED = """# Widget — Requirements

**Pairs with:** *(plan deferred — spec-only; delivered via the Spec Delivery Loop)* · `REQ-99`

> **Semantic name:** *SDK builds a widget deterministically and verifies it.*
> **Canonical ref:** `cc:intent:demo:requirement:req-demo`

## Functional requirements

- **FR-1 — Build the widget.** Name: The SDK builds a widget. Touches: `src/startd8/widget.py`, tests. Lives: code src/startd8/widget.py. Approve?: does it build?. Verify: `startd8 widget build` exits 0. Serves: O-1
- **FR-2 — Verify the widget.** Name: The SDK verifies a widget. Touches: `src/startd8/widget.py`. Depends: FR-1. Verify: the widget passes its self-check. Serves: O-2
"""

REQ_SOLO = """# Solo — Requirements

**Pairs with:** the design brief `docs/BRIEF.md`

> **Semantic name:** *A solo requirement with no plan companion.*
> **Canonical ref:** `cc:intent:demo:requirement:req-solo`

- **FR-1 — Do a thing.** Name: Do a thing. Touches: `src/startd8/thing.py`. Verify: it works. Serves: O-1
"""

REQ_CYCLIC = """# Cyclic — Requirements

**Pairs with:** *(plan deferred)*

> **Semantic name:** *A cyclic requirement.*
> **Canonical ref:** `cc:intent:demo:requirement:req-cyc`

- **FR-1 — A.** Touches: `a.py`. Depends: FR-2. Verify: a works. Serves: O-1
- **FR-2 — B.** Touches: `b.py`. Depends: FR-1. Verify: b works. Serves: O-1
"""


# ── FR-3: solo-vs-gap gate ───────────────────────────────────────────────────────────────────────


def test_plan_owed_marker_fires():
    assert is_plan_owed(REQ_PLAN_OWED) is True


def test_solo_req_is_not_plan_owed():
    assert is_plan_owed(REQ_SOLO) is False


def test_project_solo_req_raises_not_plan_owed():
    with pytest.raises(NotPlanOwedError):
        project_plan(REQ_SOLO)


def test_plan_ref_companion_is_plan_owed():
    req = REQ_SOLO.replace("the design brief `docs/BRIEF.md`", "`PLAN-solo.md`")
    assert is_plan_owed(req) is True


# ── FR-1: projection derives iterations/targetFiles/gate ─────────────────────────────────────────


def test_projects_one_iteration_per_fr_by_default():
    plan = project_plan(REQ_PLAN_OWED)
    assert len(plan.iterations) == 2
    assert plan.iterations[0].frs == ("FR-1",)
    assert plan.iterations[1].frs == ("FR-2",)


def test_target_files_derive_from_touches():
    plan = project_plan(REQ_PLAN_OWED)
    # FR-1 touches widget.py + "tests" (bare token retained); files are cleaned + sorted.
    assert "src/startd8/widget.py" in plan.iterations[0].target_files


def test_gate_derives_from_verify_clauses():
    plan = project_plan(REQ_PLAN_OWED)
    gate0 = plan.iterations[0].gate
    assert gate0 and gate0[0].fr == "FR-1"
    assert "exits 0" in gate0[0].verify


def test_cost_class_is_a_valid_band():
    plan = project_plan(REQ_PLAN_OWED)
    for it in plan.iterations:
        assert it.cost_class == COST_LLM  # hand-written src/startd8 code → integration


def test_shared_touches_strategy_merges_fr_sharing_a_file():
    # FR-1 and FR-2 both touch widget.py → one iteration under shared-touches.
    plan = project_plan(REQ_PLAN_OWED, strategy=GROUP_SHARED_TOUCHES)
    assert len(plan.iterations) == 1
    assert set(plan.iterations[0].frs) == {"FR-1", "FR-2"}


# ── FR-2: $0 / never-inferred ────────────────────────────────────────────────────────────────────


def test_depends_on_traces_to_authored_edge_only():
    plan = project_plan(REQ_PLAN_OWED)
    # FR-2 authored `Depends: FR-1`; FR-1 authored none.
    assert plan.iterations[0].depends_on == ()
    assert plan.iterations[1].depends_on == ("F-1",)


def test_no_invented_dependency_without_authored_depends():
    # Strip the authored Depends: → no edges at all (never inferred from shared files/ordinal).
    req = REQ_PLAN_OWED.replace("Depends: FR-1. ", "")
    plan = project_plan(req)
    assert all(it.depends_on == () for it in plan.iterations)


def test_cyclic_depends_rejected_with_named_error():
    with pytest.raises(PlanDependencyCycleError):
        project_plan(REQ_CYCLIC)


def test_unterminated_depends_does_not_pollute_touches():
    # HTH hardening regression: an authored `Depends: FR-1` with NO trailing period before the next
    # field must not leak into the Touches capture — it stops at the next field label.
    req = REQ_PLAN_OWED.replace(
        "Depends: FR-1. Verify: the widget passes its self-check",
        "Depends: FR-1 Verify: the widget passes its self-check",
    )
    plan = project_plan(req)
    # FR-2's edge still resolves (F-1) AND its targetFiles are clean (no "Depends"/"FR-1" token).
    assert plan.iterations[1].depends_on == ("F-1",)
    for f in plan.iterations[1].target_files:
        assert "Depends" not in f and "FR-1" not in f


def test_projector_makes_no_network_or_llm_call(monkeypatch):
    # $0 guard: any socket use inside the projector is a bug. We forbid socket.socket entirely.
    import socket

    def _boom(*a, **k):  # pragma: no cover - only fires on a regression
        raise AssertionError("projector attempted a network call — it must be $0")

    monkeypatch.setattr(socket, "socket", _boom)
    plan = project_plan(REQ_PLAN_OWED)
    assert plan.iterations  # completed with sockets forbidden


def test_projector_source_imports_no_llm_provider_modules():
    # The projector source must not import an agent/provider/httpx module ($0 by construction).
    import inspect

    import startd8.plan_codegen.projector as proj

    src = inspect.getsource(proj)
    for forbidden in (
        "import httpx",
        "anthropic",
        "openai",
        "from ..agents",
        "from ..providers",
    ):
        assert forbidden not in src, f"projector must be LLM-free, found {forbidden!r}"


# ── FR-4: anti-inflation maturity ────────────────────────────────────────────────────────────────


def test_projected_plan_is_maturity_0_1():
    plan = project_plan(REQ_PLAN_OWED)
    assert plan.maturity == PROJECTED_MATURITY == "0.1"
    rendered = render_plan(plan)
    assert "**maturity:** 0.1" in rendered
    assert "post-CRP" not in rendered and "§0.2" not in rendered


# ── FR-5: conformance + SARIF ────────────────────────────────────────────────────────────────────


def test_clean_projection_has_no_findings():
    plan = project_plan(REQ_PLAN_OWED)
    fr_ids = {fr for it in plan.iterations for fr in it.frs}
    # base_dir=None → pairsWith cannot resolve → a single liveness warning (not an error).
    findings = validate_plan(plan, req_fr_ids=fr_ids, base_dir=None)
    assert [f.check for f in findings] == ["plan-liveness"]
    assert all(f.severity == "warning" for f in findings)


def test_phantom_fr_is_a_conformance_error():
    plan = project_plan(REQ_PLAN_OWED)
    findings = validate_plan(
        plan, req_fr_ids={"FR-1"}, base_dir=None
    )  # FR-2 now "phantom"
    checks = {f.check for f in findings}
    assert "phantom-fr" in checks
    assert any(f.severity == "error" for f in findings)


def test_findings_render_as_sarif_via_reusable_renderer():
    plan = project_plan(REQ_PLAN_OWED)
    findings = validate_plan(plan, req_fr_ids={"FR-1"}, base_dir=None)
    sarif = findings_to_sarif(findings, corpus="widget")
    assert sarif["version"] == "2.1.0"
    assert sarif["runs"][0]["tool"]["driver"]["name"] == "startd8-plan-projector"
    assert sarif["runs"][0]["results"]  # at least the phantom-fr result


def test_sarif_path_imports_not_vendors_findings_sarif():
    # Reuse-not-vendor: the SARIF renderer is the ONE coverage_map module, imported.
    import startd8.plan_codegen.conformance as conf

    assert (
        conf.render_sarif_from_findings.__module__
        == "startd8.coverage_map.findings_sarif"
    )


# ── FR-6: provider round-trip ────────────────────────────────────────────────────────────────────


def test_provider_owns_only_generated_plans():
    prov = DetPlanProjectorProvider()
    plan = project_plan(REQ_PLAN_OWED)
    content = render_plan(plan)
    assert prov.name == "det-plan-projector"
    from pathlib import Path

    assert prov.owns(Path("PLAN.md"), content) is True
    assert prov.owns(Path("PLAN.md"), "# hand-authored plan\n") is False


def test_provider_in_sync_against_source(tmp_path):

    from startd8.contractors.deterministic_providers import ProviderContext

    req = tmp_path / "REQ-demo.md"
    req.write_text(REQ_PLAN_OWED, encoding="utf-8")
    plan = project_plan(req.read_text(), req_path=req)
    content = render_plan(plan)
    plan_path = tmp_path / plan.pairs_with.replace("REQ", "PLAN")
    prov = DetPlanProjectorProvider()
    ctx = ProviderContext(project_root=tmp_path, source_anchors=())
    assert prov.is_in_sync(plan_path, content, ctx) is True
    assert prov.is_in_sync(plan_path, content + "\nHAND EDIT", ctx) is False


# ── FR-8: idempotency / byte-identity ────────────────────────────────────────────────────────────


def test_projection_is_idempotent():
    a = render_plan(project_plan(REQ_PLAN_OWED))
    b = render_plan(project_plan(REQ_PLAN_OWED))
    assert a == b


def test_render_has_no_timestamp():
    # A pure function of the req: no ISO date may leak into the output (would break byte-identity).
    import re

    rendered = render_plan(project_plan(REQ_PLAN_OWED))
    assert not re.search(r"\d{4}-\d{2}-\d{2}", rendered)
